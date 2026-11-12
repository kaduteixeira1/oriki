"""Painel do fiscal (seção 8.4): alertas, pontos, histórico e vistorias. Fiscal e admin veem todos os pontos."""
from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func, select

from .. import regras
from ..alertas import calcular_alertas, lacunas
from ..consultas import lote_em_json, lotes_com_ciclo, no_periodo, resumo_por_dia
from ..erros import ErroApi
from ..extensoes import db
from ..models import AcessoQR, Ciclo, Dispositivo, Estabelecimento, Lote, PerfilUsuario, RecusaEnvio, Vistoria
from ..seguranca import perfil_requerido
from ..validacao import campos_permitidos, corpo_json, ler_data, periodo_da_consulta, texto_limpo

bp = Blueprint("fiscal", __name__, url_prefix="/api/fiscal")

LIMITE_BUSCA = 100
LIMITE_OBSERVACOES = 2000
LIMITE_RECUSAS = 100


@bp.before_request
@perfil_requerido(PerfilUsuario.FISCAL, PerfilUsuario.ADMIN)
def _somente_fiscal():
    """Vale para todas as rotas do blueprint: nenhuma rota nova fica aberta por esquecimento."""


def _estabelecimento(id_: int) -> Estabelecimento:
    est = db.session.get(Estabelecimento, id_)
    if est is None:
        raise ErroApi(404, "nao_encontrado")
    return est


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.get("/alertas")
def alertas():
    return jsonify(calcular_alertas(db.session))


@bp.get("/estabelecimentos")
def estabelecimentos():
    busca = (request.args.get("busca") or "").strip()
    if len(busca) > LIMITE_BUSCA:
        raise ErroApi(422, "texto_muito_longo", campo="busca", maximo=LIMITE_BUSCA)
    consulta = select(Estabelecimento).order_by(Estabelecimento.nome)
    if busca:
        consulta = consulta.where(Estabelecimento.nome.ilike(f"%{_escapar_like(busca)}%", escape="\\"))
    lista = db.session.execute(consulta).scalars().all()

    ultimo_ciclo = dict(db.session.execute(
        select(Dispositivo.estabelecimento_id, func.max(Ciclo.inicio))
        .select_from(Ciclo).join(Lote, Ciclo.lote_id == Lote.id)
        .join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
        .group_by(Dispositivo.estabelecimento_id)).all())
    ultimo_contato = dict(db.session.execute(
        select(Dispositivo.estabelecimento_id, func.max(Dispositivo.ultimo_contato))
        .group_by(Dispositivo.estabelecimento_id)).all())
    alertas_por_ponto: dict[int, int] = {}
    for alerta in calcular_alertas(db.session):
        id_ = alerta["estabelecimento"]["id"]
        alertas_por_ponto[id_] = alertas_por_ponto.get(id_, 0) + 1

    hoje = regras.hoje()
    return jsonify([{
        "id": est.id,
        "nome": est.nome,
        "endereco": est.endereco,
        "licenca_validade": regras.iso_data(est.licenca_validade),
        "licenca_situacao": regras.situacao_licenca(est.licenca_validade, hoje),
        "ultimo_ciclo": regras.iso_utc(ultimo_ciclo.get(est.id)),
        "ultimo_contato": regras.iso_utc(ultimo_contato.get(est.id)),
        "alertas": alertas_por_ponto.get(est.id, 0),
    } for est in lista])


@bp.get("/estabelecimentos/<int:id_>")
def detalhe(id_: int):
    est = _estabelecimento(id_)
    de, ate = periodo_da_consulta()
    hoje = regras.hoje()

    dispositivos = db.session.execute(
        select(Dispositivo).where(Dispositivo.estabelecimento_id == est.id).order_by(Dispositivo.identificador)
    ).scalars()
    lotes = db.session.execute(
        no_periodo(lotes_com_ciclo(est.id), de, ate).order_by(Ciclo.inicio.desc(), Lote.codigo.desc())
    ).all()
    vistorias = db.session.execute(
        select(Vistoria).where(Vistoria.estabelecimento_id == est.id)
        .order_by(Vistoria.data.desc(), Vistoria.id.desc())
    ).scalars()
    por_dia = resumo_por_dia(db.session, est.id, de, ate)
    inicio_periodo, fim_periodo = regras.intervalo_dias(de, ate)
    recusas = db.session.execute(
        select(RecusaEnvio.created_at, RecusaEnvio.codigo, RecusaEnvio.motivo, Dispositivo.identificador)
        .join(Dispositivo, RecusaEnvio.dispositivo_id == Dispositivo.id)
        .where(Dispositivo.estabelecimento_id == est.id, RecusaEnvio.created_at >= inicio_periodo,
               RecusaEnvio.created_at < fim_periodo)
        .order_by(RecusaEnvio.created_at.desc(), RecusaEnvio.id.desc()).limit(LIMITE_RECUSAS)
    ).all()
    acessos = db.session.execute(
        select(AcessoQR.data, AcessoQR.total)
        .where(AcessoQR.estabelecimento_id == est.id, AcessoQR.data >= de, AcessoQR.data <= ate)
        .order_by(AcessoQR.data.desc())
    ).all()
    lacunas_periodo = lacunas(db.session, estabelecimento_id=est.id, inicio_entre=regras.intervalo_dias(de, ate))

    return jsonify({
        "estabelecimento": {
            "id": est.id, "nome": est.nome, "endereco": est.endereco,
            "licenca_numero": est.licenca_numero,
            "licenca_validade": regras.iso_data(est.licenca_validade),
            "licenca_situacao": regras.situacao_licenca(est.licenca_validade, hoje),
            "curso_casa_acai_em": regras.iso_data(est.curso_casa_acai_em),
            "slug_qr": est.slug_qr,
        },
        "periodo": {"de": de.isoformat(), "ate": ate.isoformat()},
        "dispositivos": [{"identificador": d.identificador, "ultimo_contato": regras.iso_utc(d.ultimo_contato)}
                         for d in dispositivos],
        "lotes": [{**lote_em_json(l), "dispositivo": l.identificador, "contador": l.contador} for l in lotes],
        "vistorias": [_vistoria_em_json(v) for v in vistorias],
        # Ciclos × rasas declaradas: muitos ciclos com poucas rasas sugere "ciclo de fachada".
        "por_dia": [{"data": d.data.isoformat(), "ciclos": d.ciclos, "aprovados": d.aprovados,
                     "reprovados": d.reprovados, "lotes_completos": d.lotes_completos,
                     "rasas_declaradas": float(d.rasas_declaradas)} for d in por_dia],
        "lacunas": [l.descricao for l in lacunas_periodo],
        # OR-31: ciclos recusados pela API no período (os 100 mais recentes)
        "recusas": [{"quando": regras.iso_utc(r.created_at), "dispositivo": r.identificador, "codigo": r.codigo,
                     "motivo": r.motivo} for r in recusas],
        # OR-23: escaneamentos do QR (métrica do piloto), só o total por dia
        "acessos_qr": {"total": sum(a.total for a in acessos),
                       "por_dia": [{"data": a.data.isoformat(), "total": a.total} for a in acessos]},
    })


def _vistoria_em_json(vistoria: Vistoria) -> dict:
    return {
        "id": vistoria.id,
        "data": vistoria.data.isoformat(),
        "resultado": vistoria.resultado,
        "observacoes": vistoria.observacoes,
        "fiscal": {"id": vistoria.fiscal_id, "nome": vistoria.fiscal.nome},
    }


@bp.post("/estabelecimentos/<int:id_>/vistorias")
def registrar_vistoria(id_: int):
    est = _estabelecimento(id_)
    corpo = corpo_json()
    campos_permitidos(corpo, {"data", "resultado", "observacoes"})
    if "data" not in corpo:
        raise ErroApi(422, "campo_obrigatorio", campo="data")
    data = ler_data(corpo["data"], "data")
    if data > regras.hoje():
        raise ErroApi(422, "data_futura", campo="data")
    resultado = texto_limpo(corpo.get("resultado"), "resultado", 40, obrigatorio=True)
    observacoes = texto_limpo(corpo.get("observacoes"), "observacoes", LIMITE_OBSERVACOES)

    vistoria = Vistoria(estabelecimento_id=est.id, fiscal_id=current_user.id, data=data,
                        resultado=resultado, observacoes=observacoes)
    db.session.add(vistoria)
    db.session.commit()
    return jsonify(_vistoria_em_json(vistoria)), 201
