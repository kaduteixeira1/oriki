"""Fábrica do app Flask: configuração, extensões, rotas e proteções."""
import hmac
from pathlib import Path

from flask import Flask, abort, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import carregar_config, validar_config
from .erros import ErroApi, registrar_erros
from .extensoes import db, limiter, login_manager, migrate
from .seguranca import configurar_log_seguranca, registrar_protecoes

PASTA_BACKEND = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    # static_folder=None: os arquivos do front são servidos pela rota spa() (seção 14.2).
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(carregar_config())
    if config:
        app.config.update(config)
    validar_config(app.config)

    if app.config["PROXIES_CONFIAVEIS"]:
        # Atrás do roteador do provedor: IP real (limite por IP, log) e esquema https corretos.
        n = app.config["PROXIES_CONFIAVEIS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    app.json.sort_keys = False
    app.json.ensure_ascii = False

    db.init_app(app)
    migrate.init_app(app, db, directory=str(PASTA_BACKEND / "migrations"))
    _configurar_login(app)
    limiter.init_app(app)
    configurar_log_seguranca(app)

    from .rotas import auth, batedor, dispositivo, fiscal, publico
    for modulo in (auth, dispositivo, batedor, publico, fiscal):
        app.register_blueprint(modulo.bp)

    registrar_erros(app)
    registrar_protecoes(app)

    from .comandos import registrar_comandos
    registrar_comandos(app)

    _servir_frontend(app)
    return app


def _configurar_login(app: Flask) -> None:
    from .models import Usuario

    login_manager.init_app(app)
    # "basic" e não "strong": o IP do celular muda o tempo todo e "strong" derrubaria a sessão.
    login_manager.session_protection = "basic"

    @login_manager.user_loader
    def carregar_usuario(id_sessao: str):
        id_texto, _, token = id_sessao.partition(":")
        if not id_texto.isdigit() or not token:
            return None
        usuario = db.session.get(Usuario, int(id_texto))
        if usuario is None or not usuario.is_active:
            return None
        if not hmac.compare_digest(usuario.token_sessao.encode(), token.encode()):
            return None  # sessão emitida antes de anonimizar ou trocar a senha
        return usuario

    @login_manager.unauthorized_handler
    def nao_autenticado():
        raise ErroApi(401, "nao_autenticado")


def _servir_frontend(app: Flask) -> None:
    """Em produção o Flask serve o build do React no mesmo domínio da API (cookie sem CORS)."""
    dist = (PASTA_BACKEND / app.config["FRONTEND_DIST"]).resolve()
    if not (dist / "index.html").is_file():
        return

    @app.get("/", defaults={"caminho": ""})
    @app.get("/<path:caminho>")
    def spa(caminho: str):
        if caminho == "api" or caminho.startswith("api/"):
            abort(404)  # rota de API inexistente não vira index.html
        if caminho and (dist / caminho).is_file():
            # Arquivos com hash do Vite (assets/) nunca mudam: cache longo. O resto revalida.
            cache = 31_536_000 if caminho.startswith("assets/") else 0
            return send_from_directory(dist, caminho, max_age=cache)  # send_from_directory barra "../"
        resposta = send_from_directory(dist, "index.html", max_age=0)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta
