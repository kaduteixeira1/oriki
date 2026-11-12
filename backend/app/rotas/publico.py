"""Página do QR (seção 8.4). Sem login, sem rastreio individual e sem nenhum dado de pessoas (LGPD)."""
import re
from datetime import timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .. import regras
from ..consultas import resumo_por_dia
from ..erros import ErroApi
from ..extensoes import db, limiter
from ..models import AcessoQR, Estabelecimento, Vistoria

bp = Blueprint("publico", __name__, url_prefix="/api/publico")

RE_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def _contar_acesso(estabelecimento_id: int) -> None:
    """Anexo C: um total por dia, incrementado atomicamente (sem corrida entre acessos simultâneos)."""
    comando = pg_insert(AcessoQR).values(estabelecimento_id=estabelecimento_id, data=regras.hoje(), total=1)
    comando = comando.on_conflict_do_update(
        constraint="uq_acessos_qr_estabelecimento_data",
        set_={"total": AcessoQR.total + 1},
    )
    db.session.execute(comando)
    db.session.commit()


@bp.get("/<slug_qr>")
@limiter.limit("60 per minute")
def pagina(slug_qr: str):
    if len(slug_qr) > 80 or not RE_SLUG.fullmatch(slug_qr):
        raise ErroApi(404, "nao_encontrado")
    est = db.session.execute(
        select(Estabelecimento).where(Estabelecimento.slug_qr == slug_qr)
    ).scalar_one_or_none()
    if est is None:
        raise ErroApi(404, "nao_encontrado")

    hoje = regras.hoje()
    dias = resumo_por_dia(db.session, est.id, hoje - timedelta(days=regras.DIAS_PAGINA_PUBLICA - 1), hoje)
    ultima_vistoria = db.session.scalar(
        select(func.max(Vistoria.data)).where(Vistoria.estabelecimento_id == est.id))

    if request.args.get("origem") == "qr":
        _contar_acesso(est.id)

    # Só dados do estabelecimento: nada de nome, e-mail ou telefone de pessoas.
    resposta = jsonify({
        "nome": est.nome,
        "endereco": est.endereco,
        "licenca": {"validade": regras.iso_data(est.licenca_validade),
                    "situacao": regras.situacao_licenca(est.licenca_validade, hoje)},
        "curso_casa_acai_em": regras.iso_data(est.curso_casa_acai_em),
        "ultima_vistoria": regras.iso_data(ultima_vistoria),
        "dias": [{"data": d.data.isoformat(), "aprovados": d.aprovados, "reprovados": d.reprovados,
                  "ultimo": regras.hora_local(d.ultimo)} for d in dias],
        "aviso": regras.AVISO_PUBLICO,
    })
    resposta.headers["Cache-Control"] = "public, max-age=60"
    return resposta
