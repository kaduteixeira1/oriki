"""Consultas reutilizadas pelas rotas. Filtro de período sempre por intervalo em `ciclos.inicio`
(usa o índice); o agrupamento por dia é feito no fuso de Belém (seção 6.4)."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, Select, case, cast, func, select

from . import regras
from .models import Ciclo, Dispositivo, Lote, StatusCiclo, StatusLote


def dia_local(coluna):
    """`(coluna AT TIME ZONE 'America/Belem')::date`, com o fuso como parâmetro vinculado."""
    return cast(func.timezone(regras.nome_fuso(), coluna), Date)


def do_estabelecimento(consulta: Select, estabelecimento_id: int) -> Select:
    """Restringe uma consulta que já envolve `ciclos` aos dispositivos do estabelecimento."""
    return (consulta.join(Lote, Ciclo.lote_id == Lote.id)
                    .join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
                    .where(Dispositivo.estabelecimento_id == estabelecimento_id))


def no_periodo(consulta: Select, de: date, ate: date) -> Select:
    inicio, fim = regras.intervalo_dias(de, ate)
    return consulta.where(Ciclo.inicio >= inicio, Ciclo.inicio < fim)


@dataclass
class ResumoDia:
    data: date
    aprovados: int = 0
    reprovados: int = 0
    ultimo: datetime | None = None
    lotes_completos: int = 0
    rasas_declaradas: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def ciclos(self) -> int:
        return self.aprovados + self.reprovados


def resumo_por_dia(sessao, estabelecimento_id: int, de: date, ate: date) -> list[ResumoDia]:
    """Um item por dia do período, do mais novo para o mais antigo, inclusive dias sem registro."""
    dia = dia_local(Ciclo.inicio).label("dia")
    consulta = select(
        dia,
        func.count().filter(Ciclo.status == StatusCiclo.APROVADO).label("aprovados"),
        func.count().filter(Ciclo.status == StatusCiclo.REPROVADO).label("reprovados"),
        func.max(Ciclo.inicio).label("ultimo"),
        func.count().filter(Lote.status == StatusLote.COMPLETO).label("completos"),
        func.coalesce(func.sum(Lote.quantidade_rasas), 0).label("rasas"),
    ).select_from(Ciclo)
    consulta = no_periodo(do_estabelecimento(consulta, estabelecimento_id), de, ate).group_by(dia)

    por_dia = {linha.dia: linha for linha in sessao.execute(consulta)}
    dias = []
    atual = ate
    while atual >= de:
        linha = por_dia.get(atual)
        if linha:
            dias.append(ResumoDia(atual, linha.aprovados, linha.reprovados, linha.ultimo, linha.completos,
                                  Decimal(linha.rasas)))
        else:
            dias.append(ResumoDia(atual))
        atual -= timedelta(days=1)
    return dias


def lotes_com_ciclo(estabelecimento_id: int) -> Select:
    """Lote + dados do ciclo, para listas (sem carregar objetos ORM)."""
    consulta = select(
        Lote.codigo, Lote.status, Lote.origem_fruto, Lote.quantidade_rasas,
        Lote.catacao, Lote.sanitizacao, Lote.resfriamento,
        Ciclo.inicio, Ciclo.fim, Ciclo.temp_min, Ciclo.temp_max, Ciclo.segundos_acima_80,
        Ciclo.status.label("status_ciclo"), Ciclo.relogio_divergente, Ciclo.contador,
        Dispositivo.identificador,
    ).select_from(Ciclo)
    return do_estabelecimento(consulta, estabelecimento_id)


def lote_em_json(linha) -> dict:
    return {
        "codigo": linha.codigo,
        "status": linha.status.value,
        "origem_fruto": linha.origem_fruto,
        "quantidade_rasas": regras.numero(linha.quantidade_rasas),
        "catacao": linha.catacao,
        "sanitizacao": linha.sanitizacao,
        "resfriamento": linha.resfriamento,
        "ciclo": {
            "inicio": regras.iso_utc(linha.inicio),
            "temp_max": regras.numero(linha.temp_max),
            "segundos_acima_80": linha.segundos_acima_80,
            "status": linha.status_ciclo.value,
            "relogio_divergente": linha.relogio_divergente,
        },
    }


def totais(sessao, consulta_base: Select) -> dict:
    """Totais de um conjunto de lotes/ciclos (relatório)."""
    sub = consulta_base.subquery()
    linha = sessao.execute(select(
        func.count().filter(sub.c.status_ciclo == StatusCiclo.APROVADO).label("aprovados"),
        func.count().filter(sub.c.status_ciclo == StatusCiclo.REPROVADO).label("reprovados"),
        func.count().filter(sub.c.status == StatusLote.COMPLETO).label("completos"),
        func.count().filter(sub.c.status == StatusLote.INCOMPLETO).label("incompletos"),
        func.sum(case((sub.c.status == StatusLote.COMPLETO, sub.c.quantidade_rasas), else_=0)).label("rasas"),
    )).one()
    return {"aprovados": linha.aprovados, "reprovados": linha.reprovados, "completos": linha.completos,
            "incompletos": linha.incompletos, "rasas": Decimal(linha.rasas or 0)}
