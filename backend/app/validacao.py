"""Leitura e validação da entrada (corpo JSON e parâmetros de consulta)."""
import math
from datetime import date, timedelta

from flask import request

from . import regras
from .erros import ErroApi


def corpo_json() -> dict:
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise ErroApi(400, "corpo_invalido", motivo="esperado um objeto JSON")
    return corpo


def campos_permitidos(corpo: dict, permitidos: set[str]) -> None:
    desconhecidos = sorted(set(corpo) - permitidos)
    if desconhecidos:
        raise ErroApi(400, "campo_desconhecido", campos=desconhecidos)


def e_inteiro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def e_numero(valor) -> bool:
    """Número JSON finito. O parser do Python aceita NaN e Infinity, que aqui são recusados."""
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool)) and math.isfinite(valor)


def ler_data(texto, campo: str) -> date:
    if not isinstance(texto, str) or len(texto) != 10:
        raise ErroApi(400, "data_invalida", campo=campo, formato="AAAA-MM-DD")
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ErroApi(400, "data_invalida", campo=campo, formato="AAAA-MM-DD") from None


def periodo_da_consulta(padrao_dias: int = 30) -> tuple[date, date]:
    """Lê `de` e `ate` (dias em Belém). Padrão: os últimos `padrao_dias` dias, até hoje."""
    ate = ler_data(request.args["ate"], "ate") if request.args.get("ate") else regras.hoje()
    de = ler_data(request.args["de"], "de") if request.args.get("de") else ate - timedelta(days=padrao_dias - 1)
    if de > ate:
        raise ErroApi(422, "periodo_invalido", motivo="'de' depois de 'ate'")
    if (ate - de) + timedelta(days=1) > regras.PERIODO_MAXIMO:
        raise ErroApi(422, "periodo_muito_longo", maximo_dias=regras.PERIODO_MAXIMO.days)
    return de, ate


def pagina_da_consulta() -> int:
    texto = request.args.get("pagina", "1")
    if not texto.isdigit() or int(texto) < 1 or int(texto) > 100_000:
        raise ErroApi(400, "pagina_invalida")
    return int(texto)


def texto_limpo(valor, campo: str, maximo: int, obrigatorio: bool = False) -> str | None:
    """Tira espaços das pontas; texto vazio vira nulo (ou erro, se obrigatório)."""
    if valor is None:
        texto = None
    elif isinstance(valor, str):
        texto = valor.strip() or None
    else:
        raise ErroApi(400, "corpo_invalido", campo=campo, motivo="esperado texto")
    if texto is None and obrigatorio:
        raise ErroApi(422, "campo_obrigatorio", campo=campo)
    if texto is not None and len(texto) > maximo:
        raise ErroApi(422, "texto_muito_longo", campo=campo, maximo=maximo)
    return texto
