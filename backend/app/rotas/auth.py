"""Login, logout e sessão atual (seção 8.4)."""
from functools import lru_cache

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..erros import ErroApi
from ..extensoes import db, limiter
from ..models import Usuario
from ..seguranca import log_seguranca
from ..validacao import corpo_json

bp = Blueprint("auth", __name__, url_prefix="/api")


@lru_cache(maxsize=1)
def _hash_falso() -> str:
    """Hash usado quando o e-mail não existe: o tempo de resposta fica igual ao de senha errada."""
    return generate_password_hash("senha-de-um-usuario-que-nao-existe")


def _chave_por_email() -> str:
    """Limite por conta, além do limite por IP: freia ataque distribuído a um e-mail."""
    corpo = request.get_json(silent=True)
    email = corpo.get("email") if isinstance(corpo, dict) else None
    return f"email:{email.strip().lower()[:150]}" if isinstance(email, str) else f"ip:{request.remote_addr}"


def dados_usuario(usuario: Usuario) -> dict:
    estabelecimento = usuario.estabelecimento
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "perfil": usuario.perfil.value,
        "estabelecimento": ({"nome": estabelecimento.nome, "slug_qr": estabelecimento.slug_qr}
                            if estabelecimento else None),
        "termo_aceito": usuario.termo_aceito_em is not None,
    }


def _tentativa_falhou(resposta) -> bool:
    """Só tentativas erradas gastam o limite: força bruta erra; quem acerta a senha não é bloqueado."""
    return resposta.status_code != 200


@bp.post("/login")
@limiter.limit("5 per minute", deduct_when=_tentativa_falhou)
@limiter.limit("20 per hour", key_func=_chave_por_email, deduct_when=_tentativa_falhou)
def login():
    corpo = corpo_json()
    email, senha = corpo.get("email"), corpo.get("senha")
    if not isinstance(email, str) or not isinstance(senha, str) or not email.strip() or not senha:
        raise ErroApi(400, "corpo_invalido", motivo="informe email e senha")
    email = email.strip().lower()
    if len(email) > 150 or len(senha) > 256:
        raise ErroApi(401, "credenciais_invalidas")

    usuario = db.session.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    senha_confere = check_password_hash(usuario.senha_hash if usuario else _hash_falso(), senha)
    if usuario is None or not senha_confere or not usuario.is_active:
        log_seguranca("login_falho", email=email)
        raise ErroApi(401, "credenciais_invalidas")  # mesma resposta para e-mail inexistente e senha errada

    login_user(usuario, remember=True)
    return jsonify(dados_usuario(usuario))


@bp.post("/logout")
def logout():
    logout_user()
    return "", 204


@bp.get("/me")
def me():
    if not current_user.is_authenticated:
        raise ErroApi(401, "nao_autenticado")
    return jsonify(dados_usuario(current_user))
