"""Rotas do batedor (seção 8.4). Toda consulta filtra pelo estabelecimento da sessão (IDOR → 404)."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import qrcode
import qrcode.image.svg
from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .. import regras
from ..consultas import lote_em_json, lotes_com_ciclo, no_periodo, resumo_por_dia
from ..erros import ErroApi
from ..extensoes import db
from ..models import Ciclo, Dispositivo, Lote, PerfilUsuario, StatusLote
from ..relatorio import gerar_relatorio
from ..seguranca import perfil_requerido
from ..validacao import (campos_permitidos, corpo_json, e_numero, pagina_da_consulta, periodo_da_consulta,
                         texto_limpo)

bp = Blueprint("batedor", __name__, url_prefix="/api")

batedor_requerido = perfil_requerido(PerfilUsuario.BATEDOR)

LIMITE_A_COMPLETAR = 100
POR_PAGINA = 50
CAMPOS_LOTE = {"origem_fruto", "quantidade_rasas", "catacao", "sanitizacao", "resfriamento"}
CHECKLIST = ("catacao", "sanitizacao", "resfriamento")
RASAS_MIN, RASAS_MAX = Decimal("0.01"), Decimal("9999.99")


# ---------- resumo (Home) ----------

@bp.get("/batedor/resumo")
@batedor_requerido
def resumo():
    est = current_user.estabelecimento
    hoje = regras.hoje()
    dia = resumo_por_dia(db.session, est.id, hoje, hoje)[0]

    base = lotes_com_ciclo(est.id)
    ultimo = db.session.execute(base.order_by(Ciclo.inicio.desc()).limit(1)).first()
    pendentes = base.where(Lote.status == StatusLote.INCOMPLETO)
    a_completar = db.session.execute(pendentes.order_by(Ciclo.inicio.desc()).limit(LIMITE_A_COMPLETAR)).all()
    total_a_completar = db.session.scalar(select(func.count()).select_from(pendentes.subquery()))

    return jsonify({
        "estabelecimento": {
            "nome": est.nome,
            "licenca_validade": regras.iso_data(est.licenca_validade),
            "licenca_situacao": regras.situacao_licenca(est.licenca_validade, hoje),
        },
        "hoje": {"data": hoje.isoformat(), "aprovados": dia.aprovados, "reprovados": dia.reprovados},
        "ultimo_ciclo": ({
            "codigo": ultimo.codigo,
            "inicio": regras.iso_utc(ultimo.inicio),
            "temp_max": regras.numero(ultimo.temp_max),
            "segundos_acima_80": ultimo.segundos_acima_80,
            "status": ultimo.status_ciclo.value,
        } if ultimo else None),
        "lotes_a_completar": [
            {"codigo": l.codigo, "inicio": regras.iso_utc(l.inicio), "status_ciclo": l.status_ciclo.value}
            for l in a_completar
        ],
        "total_a_completar": total_a_completar,
    })


# ---------- lote (Formulário) ----------

def _lote_do_batedor(codigo: str) -> Lote:
    if len(codigo) > 40:
        raise ErroApi(404, "nao_encontrado")
    lote = db.session.execute(
        select(Lote).join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
        .where(Lote.codigo == codigo, Dispositivo.estabelecimento_id == current_user.estabelecimento_id)
        .options(joinedload(Lote.ciclo))
    ).scalar_one_or_none()
    if lote is None:
        raise ErroApi(404, "nao_encontrado")  # não existe ou é de outro ponto: mesma resposta
    return lote


def _lote_em_json(lote: Lote) -> dict:
    ciclo = lote.ciclo
    return {
        "codigo": lote.codigo,
        "status": lote.status.value,
        "origem_fruto": lote.origem_fruto,
        "quantidade_rasas": regras.numero(lote.quantidade_rasas),
        "catacao": lote.catacao,
        "sanitizacao": lote.sanitizacao,
        "resfriamento": lote.resfriamento,
        "ciclo": {
            "inicio": regras.iso_utc(ciclo.inicio),
            "fim": regras.iso_utc(ciclo.fim),
            "temp_min": regras.numero(ciclo.temp_min),
            "temp_max": regras.numero(ciclo.temp_max),
            "segundos_acima_80": ciclo.segundos_acima_80,
            "status": ciclo.status.value,
            "relogio_divergente": ciclo.relogio_divergente,
        },
    }


def _quantidade(valor) -> Decimal | None:
    if valor is None:
        return None
    if not e_numero(valor):
        raise ErroApi(400, "corpo_invalido", campo="quantidade_rasas", motivo="esperado número")
    try:
        quantidade = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ErroApi(400, "corpo_invalido", campo="quantidade_rasas") from None
    if not RASAS_MIN <= quantidade <= RASAS_MAX:
        raise ErroApi(422, "valor_fora_do_limite", campo="quantidade_rasas",
                      minimo=float(RASAS_MIN), maximo=float(RASAS_MAX))
    return quantidade


@bp.get("/lotes/<codigo>")
@batedor_requerido
def ver_lote(codigo: str):
    return jsonify(_lote_em_json(_lote_do_batedor(codigo)))


@bp.patch("/lotes/<codigo>")
@batedor_requerido
def completar_lote(codigo: str):
    """Atualização parcial e idempotente: o PWA pode reenviar a fila offline sem efeito colateral."""
    corpo = corpo_json()
    campos_permitidos(corpo, CAMPOS_LOTE)
    # Valida tudo antes de alterar qualquer coisa.
    novos = {}
    if "origem_fruto" in corpo:
        novos["origem_fruto"] = texto_limpo(corpo["origem_fruto"], "origem_fruto", 150)
    if "quantidade_rasas" in corpo:
        novos["quantidade_rasas"] = _quantidade(corpo["quantidade_rasas"])
    for campo in CHECKLIST:
        if campo in corpo:
            if not isinstance(corpo[campo], bool):
                raise ErroApi(400, "corpo_invalido", campo=campo, motivo="esperado true ou false")
            novos[campo] = corpo[campo]

    lote = _lote_do_batedor(codigo)
    for campo, valor in novos.items():
        setattr(lote, campo, valor)  # o ciclo nunca é alterado
    completo = regras.lote_completo(lote.origem_fruto, lote.quantidade_rasas)
    lote.status = StatusLote.COMPLETO if completo else StatusLote.INCOMPLETO
    db.session.commit()
    return jsonify(_lote_em_json(lote))


# ---------- histórico, QR e relatório ----------

@bp.get("/batedor/lotes")
@batedor_requerido
def historico():
    de, ate = periodo_da_consulta()
    pagina = pagina_da_consulta()
    status = request.args.get("status")
    consulta = no_periodo(lotes_com_ciclo(current_user.estabelecimento_id), de, ate)
    if status:
        if status not in (StatusLote.INCOMPLETO.value, StatusLote.COMPLETO.value):
            raise ErroApi(400, "status_invalido", aceitos=["incompleto", "completo"])
        consulta = consulta.where(Lote.status == StatusLote(status))

    total = db.session.scalar(select(func.count()).select_from(consulta.subquery()))
    linhas = db.session.execute(
        consulta.order_by(Ciclo.inicio.desc(), Lote.codigo.desc())
        .limit(POR_PAGINA).offset((pagina - 1) * POR_PAGINA)
    ).all()
    return jsonify({
        "de": de.isoformat(), "ate": ate.isoformat(),
        "pagina": pagina, "por_pagina": POR_PAGINA, "total": total,
        "itens": [lote_em_json(l) for l in linhas],
    })


def gerar_qr_svg(url: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=20, border=4,
                       image_factory=qrcode.image.svg.SvgPathImage)  # nível Q: aguenta risco e reflexo
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image().to_string(encoding="unicode")


def url_publica(slug: str) -> str:
    return f"{current_app.config['URL_PUBLICA']}/p/{slug}?origem=qr"


@bp.get("/batedor/qr.svg")
@batedor_requerido
def qr_svg():
    slug = current_user.estabelecimento.slug_qr
    resposta = Response(gerar_qr_svg(url_publica(slug)), mimetype="image/svg+xml")
    resposta.headers["Content-Disposition"] = f'inline; filename="qr-{slug}.svg"'
    return resposta


@bp.get("/batedor/relatorio.pdf")
@batedor_requerido
def relatorio():
    de, ate = periodo_da_consulta()
    est = current_user.estabelecimento
    pdf = gerar_relatorio(db.session, est, de, ate)
    resposta = Response(pdf, mimetype="application/pdf")
    resposta.headers["Content-Disposition"] = (
        f'attachment; filename="relatorio-{est.slug_qr}-{de.isoformat()}-a-{ate.isoformat()}.pdf"')
    return resposta


# ---------- termo de uso (LGPD) ----------

@bp.post("/batedor/termo")
@perfil_requerido(PerfilUsuario.BATEDOR, exige_termo=False)
def aceitar_termo():
    if current_user.termo_aceito_em is None:  # guarda a data do primeiro aceite
        current_user.termo_aceito_em = regras.agora()
        db.session.commit()
    return jsonify({"termo_aceito": True, "termo_aceito_em": regras.iso_utc(current_user.termo_aceito_em)})
