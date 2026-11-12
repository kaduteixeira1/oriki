"""Controles transversais de segurança (seção 10): log, perfis, CSRF e cabeçalhos HTTP."""
import logging
import sys
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlsplit

from flask import has_request_context, request
from flask_login import current_user

from .erros import ErroApi
from .models import PerfilUsuario

logger = logging.getLogger("oriki.seguranca")

METODOS_QUE_ALTERAM = {"POST", "PUT", "PATCH", "DELETE"}

CSP_API = "default-src 'none'; frame-ancestors 'none'"
CSP_FRONTEND = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
                "manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; "
                "form-action 'self'; frame-ancestors 'none'")


# ---------- log de segurança (seção 10.2) ----------

def _limpo(valor, limite: int = 120) -> str:
    """Impede injeção de linhas falsas no log e corta valores enormes."""
    texto = str(valor).replace("\r", "\\r").replace("\n", "\\n")
    return texto[:limite]


def log_seguranca(evento: str, **campos) -> None:
    """Registra data, IP e identificador. Nunca recebe senha nem chave."""
    ip = request.remote_addr if has_request_context() else "-"
    extras = " ".join(f"{nome}={_limpo(valor)}" for nome, valor in campos.items())
    logger.warning("evento=%s ip=%s %s", evento, _limpo(ip), extras)


def configurar_log_seguranca(app) -> None:
    if getattr(logger, "_oriki_configurado", False):
        return
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    saida = logging.StreamHandler(sys.stderr)
    saida.setFormatter(formato)
    logger.addHandler(saida)
    arquivo = app.config.get("LOG_SEGURANCA_ARQUIVO")
    if arquivo:
        # Um arquivo por dia; os mais antigos que a retenção (90 dias) são apagados.
        rotativo = TimedRotatingFileHandler(arquivo, when="midnight", backupCount=app.config["LOG_SEGURANCA_DIAS"],
                                            encoding="utf-8", utc=True)
        rotativo.setFormatter(formato)
        logger.addHandler(rotativo)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._oriki_configurado = True


# ---------- autorização ----------

def perfil_requerido(*perfis: PerfilUsuario, exige_termo: bool = True):
    """401 sem sessão; 403 para perfil errado ou batedor que ainda não aceitou o termo (LGPD)."""
    def decorador(funcao):
        @wraps(funcao)
        def envolvida(*args, **kwargs):
            if not current_user.is_authenticated:
                raise ErroApi(401, "nao_autenticado")
            if current_user.perfil not in perfis:
                raise ErroApi(403, "sem_permissao")
            if exige_termo and current_user.perfil == PerfilUsuario.BATEDOR and current_user.termo_aceito_em is None:
                raise ErroApi(403, "termo_pendente")
            return funcao(*args, **kwargs)
        return envolvida
    return decorador


# ---------- CSRF e cabeçalhos ----------

def _e_api() -> bool:
    return request.path == "/api" or request.path.startswith("/api/")


def registrar_protecoes(app) -> None:
    @app.before_request
    def _barrar_csrf():
        """SameSite=Lax + só JSON + origem conferida (seção 10.1, CSRF).

        Um formulário de outro site só consegue enviar text/plain, urlencoded ou multipart,
        então exigir application/json nas rotas que alteram dados já bloqueia o ataque.
        """
        if not _e_api() or request.method not in METODOS_QUE_ALTERAM:
            return
        origem = request.headers.get("Origin")
        if origem and urlsplit(origem).netloc != request.host:  # inclui a origem opaca "null"
            log_seguranca("origem_invalida", origem=origem, rota=request.path)
            raise ErroApi(403, "origem_invalida")
        if not request.is_json:
            raise ErroApi(415, "tipo_de_conteudo_invalido")

    @app.after_request
    def _cabecalhos(resposta):
        cabecalhos = resposta.headers
        cabecalhos.setdefault("X-Content-Type-Options", "nosniff")
        cabecalhos.setdefault("X-Frame-Options", "DENY")
        cabecalhos.setdefault("Referrer-Policy", "same-origin")
        cabecalhos.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config["COOKIE_SEGURO"]:
            cabecalhos.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if _e_api():
            cabecalhos.setdefault("Content-Security-Policy", CSP_API)
            # Dado de sessão nunca fica em cache; a rota pública define o próprio Cache-Control.
            cabecalhos.setdefault("Cache-Control", "no-store")
        else:
            cabecalhos.setdefault("Content-Security-Policy", app.config.get("CSP_FRONTEND", CSP_FRONTEND))
        # Resposta que cria cookie não pode ser guardada por cache compartilhado.
        if "Set-Cookie" in cabecalhos and "public" in cabecalhos.get("Cache-Control", ""):
            cabecalhos["Cache-Control"] = "private, no-store"
        return resposta
