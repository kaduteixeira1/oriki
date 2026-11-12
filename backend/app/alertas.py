"""Alertas do painel do fiscal (seção 9.3) e consulta de lacuna de contador (Anexo A).

Cada tipo de alerta sai de uma única consulta agregada para todos os pontos (sem N+1).
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import distinct, func, select

from . import regras
from .consultas import dia_local
from .models import Ciclo, Dispositivo, Estabelecimento, Lote, RecusaEnvio, StatusCiclo

SEM_REGISTRO = timedelta(days=3)      # seção 17: confirmar com a Casa do Açaí
SEM_CONTATO = timedelta(days=2)
JANELA_RECENTE_DIAS = 7               # reprovados e relógio divergente
ESPERA_LACUNA = timedelta(hours=1)    # tempo para a fila do dispositivo sincronizar (Anexo A)


@dataclass(frozen=True)
class Lacuna:
    dispositivo_id: int
    identificador: str
    estabelecimento_id: int
    faltando_de: int
    faltando_ate: int
    inicio_seguinte: datetime  # início do primeiro ciclo depois da lacuna

    @property
    def descricao(self) -> str:
        return f"{self.identificador}: contadores {self.faltando_de} a {self.faltando_ate} ausentes"


def lacunas(sessao, *, estabelecimento_id: int | None = None, recebido_antes_de: datetime | None = None,
            inicio_entre: tuple[datetime, datetime] | None = None) -> list[Lacuna]:
    """Números faltando na sequência do contador de cada dispositivo.

    Mesma lógica do Anexo A (LAG por dispositivo), montada com o SQLAlchemy para aceitar filtros
    opcionais sem concatenar SQL.
    """
    anterior = func.lag(Ciclo.contador).over(partition_by=Lote.dispositivo_id, order_by=Ciclo.contador)
    interna = (select(Lote.dispositivo_id, Ciclo.contador, Ciclo.inicio, Ciclo.created_at,
                      anterior.label("anterior"))
               .select_from(Ciclo).join(Lote, Ciclo.lote_id == Lote.id))
    if estabelecimento_id is not None:
        interna = interna.join(Dispositivo, Lote.dispositivo_id == Dispositivo.id).where(
            Dispositivo.estabelecimento_id == estabelecimento_id)
    t = interna.subquery()

    consulta = (select(t.c.dispositivo_id, Dispositivo.identificador, Dispositivo.estabelecimento_id,
                       (t.c.anterior + 1).label("faltando_de"), (t.c.contador - 1).label("faltando_ate"),
                       t.c.inicio)
                .join(Dispositivo, Dispositivo.id == t.c.dispositivo_id)
                .where(t.c.contador - t.c.anterior > 1)
                .order_by(Dispositivo.identificador, t.c.anterior))
    if recebido_antes_de is not None:
        consulta = consulta.where(t.c.created_at <= recebido_antes_de)
    if inicio_entre is not None:
        consulta = consulta.where(t.c.inicio >= inicio_entre[0], t.c.inicio < inicio_entre[1])
    return [Lacuna(*linha) for linha in sessao.execute(consulta)]


def _alerta(estabelecimento: Estabelecimento, tipo: str, detalhe: str, desde: date | None) -> dict:
    return {"estabelecimento": {"id": estabelecimento.id, "nome": estabelecimento.nome},
            "tipo": tipo, "detalhe": detalhe, "desde": regras.iso_data(desde)}


def calcular_alertas(sessao) -> list[dict]:
    momento = regras.agora()
    hoje = regras.hoje()
    estabelecimentos = {e.id: e for e in sessao.execute(select(Estabelecimento)).scalars()}
    alertas: list[dict] = []

    # Licença (seção 9.2)
    for est in estabelecimentos.values():
        situacao = regras.situacao_licenca(est.licenca_validade, hoje)
        if situacao == "vencida":
            alertas.append(_alerta(est, "licenca_vencida", f"Licença {est.licenca_numero} vencida",
                                   est.licenca_validade))
        elif situacao == "vence_em_breve":
            alertas.append(_alerta(est, "licenca_vence_em_breve",
                                   f"Licença {est.licenca_numero} vence em {est.licenca_validade:%d/%m/%Y}",
                                   hoje))

    # Sem registro: nenhum ciclo nos últimos 3 dias
    ultimo_ciclo = dict(sessao.execute(
        select(Dispositivo.estabelecimento_id, func.max(Ciclo.inicio))
        .select_from(Ciclo).join(Lote, Ciclo.lote_id == Lote.id)
        .join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
        .group_by(Dispositivo.estabelecimento_id)
    ).all())
    for est in estabelecimentos.values():
        ultimo = ultimo_ciclo.get(est.id)
        if ultimo is None or ultimo < momento - SEM_REGISTRO:
            detalhe = (f"Último ciclo em {regras.data_local(ultimo):%d/%m/%Y}" if ultimo
                       else "Nenhum ciclo registrado")
            alertas.append(_alerta(est, "sem_registro", detalhe,
                                   regras.data_local(ultimo) if ultimo else regras.data_local(est.created_at)))

    # Dispositivo sem contato (nem heartbeat) há mais de 2 dias
    sem_contato = sessao.execute(
        select(Dispositivo).where((Dispositivo.ultimo_contato.is_(None))
                                  | (Dispositivo.ultimo_contato < momento - SEM_CONTATO))
        .order_by(Dispositivo.identificador)
    ).scalars()
    for disp in sem_contato:
        est = estabelecimentos[disp.estabelecimento_id]
        if disp.ultimo_contato:
            detalhe = f"{disp.identificador}: último contato em {regras.data_local(disp.ultimo_contato):%d/%m/%Y}"
        else:
            detalhe = f"{disp.identificador}: nunca se comunicou"
        alertas.append(_alerta(est, "dispositivo_sem_contato", detalhe,
                               regras.data_local(disp.ultimo_contato or disp.created_at)))

    # Reprovados e relógio divergente nos últimos 7 dias (dias de Belém, como na página pública)
    janela_inicio, janela_fim = regras.intervalo_dias(hoje - timedelta(days=JANELA_RECENTE_DIAS - 1), hoje)
    recentes = sessao.execute(
        select(Dispositivo.estabelecimento_id,
               func.count().filter(Ciclo.status == StatusCiclo.REPROVADO).label("reprovados"),
               func.min(dia_local(Ciclo.inicio)).filter(Ciclo.status == StatusCiclo.REPROVADO)
               .label("reprovado_desde"),
               func.count().filter(Ciclo.relogio_divergente.is_(True)).label("divergentes"),
               func.min(dia_local(Ciclo.inicio)).filter(Ciclo.relogio_divergente.is_(True))
               .label("divergente_desde"))
        .select_from(Ciclo).join(Lote, Ciclo.lote_id == Lote.id)
        .join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
        .where(Ciclo.inicio >= janela_inicio, Ciclo.inicio < janela_fim)
        .group_by(Dispositivo.estabelecimento_id)
    ).all()
    for linha in recentes:
        est = estabelecimentos[linha.estabelecimento_id]
        if linha.reprovados:
            alertas.append(_alerta(est, "ciclos_reprovados",
                                   f"{linha.reprovados} ciclo(s) reprovado(s) nos últimos {JANELA_RECENTE_DIAS} dias",
                                   linha.reprovado_desde))
        if linha.divergentes:
            alertas.append(_alerta(est, "relogio_divergente",
                                   f"{linha.divergentes} ciclo(s) com relógio do dispositivo fora de hora",
                                   linha.divergente_desde))

    # OR-31: ciclos recusados pela API nos últimos 7 dias (assinatura, conflito, formato…)
    recusas = sessao.execute(
        select(Dispositivo.estabelecimento_id, func.count().label("total"),
               func.min(dia_local(RecusaEnvio.created_at)).label("desde"),
               func.array_agg(distinct(RecusaEnvio.motivo)).label("motivos"))
        .select_from(RecusaEnvio).join(Dispositivo, RecusaEnvio.dispositivo_id == Dispositivo.id)
        .where(RecusaEnvio.created_at >= janela_inicio, RecusaEnvio.created_at < janela_fim)
        .group_by(Dispositivo.estabelecimento_id)
    ).all()
    for linha in recusas:
        motivos = ", ".join(sorted(linha.motivos))
        alertas.append(_alerta(estabelecimentos[linha.estabelecimento_id], "envios_recusados",
                               f"{linha.total} ciclo(s) recusado(s) pela API nos últimos {JANELA_RECENTE_DIAS} dias "
                               f"({motivos})", linha.desde))

    # Lacuna de contador, com o ciclo seguinte recebido há mais de 1 hora
    for lacuna in lacunas(sessao, recebido_antes_de=momento - ESPERA_LACUNA):
        alertas.append(_alerta(estabelecimentos[lacuna.estabelecimento_id], "lacuna_contador",
                               lacuna.descricao, regras.data_local(lacuna.inicio_seguinte)))

    alertas.sort(key=lambda a: (a["estabelecimento"]["nome"].lower(), a["estabelecimento"]["id"], a["tipo"]))
    return alertas
