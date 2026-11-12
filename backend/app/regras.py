"""Regras de negócio puras: relógio, "hoje" em Belém, situação da licença e status do lote (seção 9)."""
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from flask import current_app

ANTECEDENCIA_LICENCA = timedelta(days=30)  # seção 17: "vence em breve" (proposto)
DIAS_PAGINA_PUBLICA = 7                    # seção 17: dias mostrados no QR (proposto)
PERIODO_MAXIMO = timedelta(days=92)        # relatório, histórico e detalhe do fiscal
SEGUNDOS_MINIMOS_APROVADO = 10             # seção 9.1: água >= 80 °C por >= 10 s
TOLERANCIA_RELOGIO = timedelta(seconds=120)

AVISO_PUBLICO = ("Registros do próprio estabelecimento, medidos pelo dispositivo no tanque. "
                 "Não é selo oficial: a fonte oficial é a licença da Sesma.")


def agora() -> datetime:
    """Única fonte de "agora" do sistema (UTC). Os testes substituem esta função."""
    return datetime.now(UTC)


@lru_cache(maxsize=4)
def _zona(nome: str) -> ZoneInfo:
    return ZoneInfo(nome)


def fuso() -> ZoneInfo:
    return _zona(current_app.config["FUSO"])


def nome_fuso() -> str:
    return current_app.config["FUSO"]


def hoje() -> date:
    """Data de hoje no fuso do sistema (America/Belem)."""
    return agora().astimezone(fuso()).date()


def inicio_do_dia(dia: date) -> datetime:
    """Instante (com fuso) em que o dia local começa; serve para filtrar `inicio` usando o índice."""
    return datetime.combine(dia, time.min, tzinfo=fuso())


def intervalo_dias(de: date, ate: date) -> tuple[datetime, datetime]:
    """[início de `de`, início do dia seguinte a `ate`), em hora local."""
    return inicio_do_dia(de), inicio_do_dia(ate + timedelta(days=1))


def situacao_licenca(validade: date, referencia: date | None = None) -> str:
    referencia = referencia or hoje()
    if validade < referencia:
        return "vencida"
    if validade <= referencia + ANTECEDENCIA_LICENCA:
        return "vence_em_breve"
    return "em_dia"


def lote_completo(origem_fruto: str | None, quantidade_rasas: Decimal | None) -> bool:
    return bool(origem_fruto) and quantidade_rasas is not None


# ---------- formatação das respostas ----------

def iso_utc(instante: datetime | None) -> str | None:
    if instante is None:
        return None
    return instante.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hora_local(instante: datetime | None) -> str | None:
    if instante is None:
        return None
    return instante.astimezone(fuso()).strftime("%H:%M")


def data_local(instante: datetime | None) -> date | None:
    if instante is None:
        return None
    return instante.astimezone(fuso()).date()


def iso_data(dia: date | None) -> str | None:
    return dia.isoformat() if dia else None


def numero(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None
