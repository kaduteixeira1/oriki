"""POST /api/ciclos: recebe os ciclos assinados do ESP32 (seção 7).

Fluxo otimizado para o envio em bloco: 1 consulta para os códigos já gravados,
1 INSERT para os lotes novos e 1 para os ciclos, em vez de 2 por ciclo.
"""
import hmac
import re
import secrets

from flask import Blueprint, jsonify
from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .. import regras
from ..assinatura import confere_envio
from ..chaves import decifrar
from ..contrato import RE_HEX64, CicloValido, analisar_ciclo, instante
from ..erros import ErroApi
from ..extensoes import db, limiter
from ..models import Ciclo, Dispositivo, Lote, RecusaEnvio, StatusLote
from ..seguranca import log_seguranca
from ..validacao import corpo_json

bp = Blueprint("dispositivo", __name__, url_prefix="/api")

MAX_CICLOS = 50
RE_IDENTIFICADOR = re.compile(r"[A-Z0-9]{3,20}")


def _validar_envelope(corpo: dict):
    erros = {}
    identificador = corpo.get("dispositivo")
    if not isinstance(identificador, str) or not RE_IDENTIFICADOR.fullmatch(identificador):
        erros["dispositivo"] = "esperado [A-Z0-9]{3,20}"
    enviado_em = corpo.get("enviado_em")
    enviado_em_dt = instante(enviado_em)
    if enviado_em_dt is None:
        erros["enviado_em"] = "esperado ISO 8601 com offset"
    assinatura = corpo.get("assinatura_envio")
    if not isinstance(assinatura, str) or not RE_HEX64.fullmatch(assinatura):
        erros["assinatura_envio"] = "esperado 64 caracteres hex"
    ciclos = corpo.get("ciclos")
    if not isinstance(ciclos, list):
        erros["ciclos"] = "esperada uma lista"
    elif len(ciclos) > MAX_CICLOS:
        erros["ciclos"] = f"no máximo {MAX_CICLOS} por envio"
    if erros:
        raise ErroApi(400, "envelope_invalido", **erros)
    return identificador, enviado_em, enviado_em_dt, assinatura, ciclos


def _codigo_para_resposta(item) -> str | None:
    codigo = item.get("codigo") if isinstance(item, dict) else None
    return codigo[:40] if isinstance(codigo, str) else None


def _assinaturas_gravadas(codigos) -> dict[str, str]:
    if not codigos:
        return {}
    linhas = db.session.execute(
        select(Lote.codigo, Ciclo.assinatura).join(Ciclo, Ciclo.lote_id == Lote.id).where(Lote.codigo.in_(codigos))
    ).all()
    return {codigo: assinatura for codigo, assinatura in linhas}


@bp.post("/ciclos")
@limiter.limit("60 per minute")
def receber_ciclos():
    identificador, enviado_em, enviado_em_dt, assinatura_envio, itens = _validar_envelope(corpo_json())

    dispositivo = db.session.execute(
        select(Dispositivo).where(Dispositivo.identificador == identificador)
    ).scalar_one_or_none()
    # Com dispositivo inexistente, confere contra uma chave aleatória: mesmo caminho, mesma resposta.
    chave = decifrar(dispositivo.chave_hmac_cifrada) if dispositivo else secrets.token_hex(32).encode()
    if not confere_envio(identificador, enviado_em, assinatura_envio, chave) or dispositivo is None:
        log_seguranca("assinatura_envio_invalida", dispositivo=identificador)
        raise ErroApi(401, "nao_autorizado")  # não revela quais identificadores existem

    momento = regras.agora()
    relogio_divergente = abs(enviado_em_dt - momento) > regras.TOLERANCIA_RELOGIO
    if relogio_divergente:
        log_seguranca("relogio_divergente", dispositivo=identificador,
                      diferenca_s=int((enviado_em_dt - momento).total_seconds()))

    # 1) Validação e assinatura de cada ciclo, sem tocar no banco.
    recusados: list[dict] = []
    validos: list[CicloValido] = []
    for item in itens:
        ciclo, motivo = analisar_ciclo(item, identificador, chave)
        if motivo:
            if motivo == "assinatura_invalida":
                log_seguranca("assinatura_ciclo_invalida", dispositivo=identificador,
                              codigo=_codigo_para_resposta(item))
            recusados.append({"codigo": _codigo_para_resposta(item), "motivo": motivo})
        else:
            validos.append(ciclo)

    # 2) Idempotência: código já gravado com a mesma assinatura é reenvio; com outra, conflito.
    gravados = _assinaturas_gravadas({c.codigo for c in validos})
    recebidos: list[str] = []
    novos: list[CicloValido] = []

    def classificar(ciclo: CicloValido, assinatura_gravada: str) -> None:
        if hmac.compare_digest(assinatura_gravada.strip(), ciclo.assinatura):
            recebidos.append(ciclo.codigo)
        else:
            log_seguranca("conflito_codigo", dispositivo=identificador, codigo=ciclo.codigo)
            recusados.append({"codigo": ciclo.codigo, "motivo": "conflito"})

    for ciclo in validos:
        if ciclo.codigo in gravados:
            classificar(ciclo, gravados[ciclo.codigo])
        else:
            gravados[ciclo.codigo] = ciclo.assinatura  # repetido dentro do mesmo envio
            novos.append(ciclo)

    # 3) Gravação em bloco. ON CONFLICT cobre dois envios simultâneos do mesmo ciclo.
    if novos:
        linhas = db.session.execute(
            pg_insert(Lote)
            .values([{"dispositivo_id": dispositivo.id, "codigo": c.codigo, "status": StatusLote.INCOMPLETO,
                      "catacao": False, "sanitizacao": False, "resfriamento": False,
                      "created_at": momento, "updated_at": momento} for c in novos])
            .on_conflict_do_nothing(index_elements=[Lote.codigo])
            .returning(Lote.id, Lote.codigo)
        ).all()
        lote_id = {codigo: id_ for id_, codigo in linhas}
        inseridos = [c for c in novos if c.codigo in lote_id]
        if inseridos:
            db.session.execute(insert(Ciclo), [
                {"lote_id": lote_id[c.codigo], "inicio": c.inicio, "fim": c.fim, "temp_min": c.temp_min,
                 "temp_max": c.temp_max, "segundos_acima_80": c.segundos_acima_80, "status": c.status,
                 "contador": c.contador, "assinatura": c.assinatura, "relogio_divergente": relogio_divergente,
                 "created_at": momento}
                for c in inseridos
            ])
            recebidos.extend(c.codigo for c in inseridos)
        corrida = [c for c in novos if c.codigo not in lote_id]
        if corrida:
            gravados_agora = _assinaturas_gravadas({c.codigo for c in corrida})
            for ciclo in corrida:
                classificar(ciclo, gravados_agora.get(ciclo.codigo, ""))

    dispositivo.ultimo_contato = momento
    # OR-31: as recusas ficam no banco para o painel do fiscal (o log de segurança continua igual).
    if recusados:
        db.session.execute(insert(RecusaEnvio), [
            {"dispositivo_id": dispositivo.id, "codigo": (r["codigo"] or "")[:40] or None, "motivo": r["motivo"],
             "created_at": momento} for r in recusados])
        for r in recusados:
            if r["motivo"] not in ("assinatura_invalida", "conflito"):  # esses dois já foram para o log
                log_seguranca("ciclo_recusado", dispositivo=identificador, codigo=r["codigo"], motivo=r["motivo"])
    db.session.commit()

    return jsonify({
        "recebidos": recebidos,
        "recusados": recusados,
        "hora_servidor": regras.iso_utc(momento),
    })
