"""Regras de cada ciclo enviado pelo ESP32 (seção 7.4 do plano), na ordem em que o servidor as aplica.

Usado pelo POST /api/ciclos e pelo scripts/conferir_envio.py: o conferidor recusa exatamente o que o
servidor recusaria. A mensagem assinada continua em assinatura.py (contrato da seção 7.2).
"""
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from . import regras
from .assinatura import confere_ciclo
from .models import StatusCiclo
from .validacao import e_inteiro, e_numero

MAX_CONTADOR = 2_147_483_647  # INTEGER do PostgreSQL
RE_HEX64 = re.compile(r"[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class CicloValido:
    codigo: str
    contador: int
    inicio: datetime
    fim: datetime
    temp_min: Decimal
    temp_max: Decimal
    segundos_acima_80: int
    status: StatusCiclo
    assinatura: str


def instante(valor) -> datetime | None:
    """ISO 8601 com offset obrigatório (seção 6.4): hora sem fuso é recusada."""
    if not isinstance(valor, str) or len(valor) > 40:
        return None
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return momento if momento.utcoffset() is not None else None


def _temperatura(valor) -> Decimal | None:
    if not e_numero(valor) or not -55 <= valor <= 125:
        return None
    return Decimal(f"{float(valor):.2f}")  # mesma representação da mensagem assinada


def analisar_ciclo(item, identificador: str, chave: bytes) -> tuple[CicloValido | None, str | None]:
    """Formato, coerência e HMAC, nesta ordem. Devolve (ciclo, None) ou (None, motivo_da_recusa)."""
    if not isinstance(item, dict):
        return None, "formato_invalido"
    contador = item.get("contador")
    if not e_inteiro(contador) or not 1 <= contador <= MAX_CONTADOR:
        return None, "formato_invalido"
    codigo = item.get("codigo")
    if codigo != f"{identificador}-{contador:06d}":
        return None, "codigo_invalido"
    inicio, fim = instante(item.get("inicio")), instante(item.get("fim"))
    if inicio is None or fim is None or fim < inicio:
        return None, "formato_invalido"
    temp_min, temp_max = _temperatura(item.get("temp_min")), _temperatura(item.get("temp_max"))
    if temp_min is None or temp_max is None or temp_min > temp_max:
        return None, "formato_invalido"
    segundos = item.get("segundos_acima_80")
    if not e_inteiro(segundos) or not 0 <= segundos <= 32767:
        return None, "formato_invalido"
    if item.get("status") not in (StatusCiclo.APROVADO.value, StatusCiclo.REPROVADO.value):
        return None, "formato_invalido"
    status = StatusCiclo(item["status"])
    if status == StatusCiclo.APROVADO and segundos < regras.SEGUNDOS_MINIMOS_APROVADO:
        return None, "status_inconsistente"
    assinatura = item.get("assinatura")
    if not isinstance(assinatura, str) or not RE_HEX64.fullmatch(assinatura) or not confere_ciclo(item, chave):
        return None, "assinatura_invalida"
    return CicloValido(codigo, contador, inicio, fim, temp_min, temp_max, segundos, status,
                       assinatura.lower()), None


def validar_ciclo(dispositivo: str, ciclo, chave: bytes) -> str | None:
    """Motivo da recusa (codigo_invalido, formato_invalido, status_inconsistente, assinatura_invalida) ou None."""
    return analisar_ciclo(ciclo, dispositivo, chave)[1]
