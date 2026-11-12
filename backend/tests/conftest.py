"""App de teste com PostgreSQL real (oriki_test): enum, timestamptz, fuso e window functions (seção 13.1).

O schema é recriado pela migração a cada sessão do pytest (testa a migração também) e cada teste
roda dentro de uma transação desfeita no final.
"""
import itertools
import os
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from cryptography.fernet import Fernet
from flask import g
from flask_migrate import upgrade
from sqlalchemy import text
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash

from app import create_app, regras
from app.assinatura import assinar_ciclo, assinar_envio
from app.chaves import cifrar
from app.config import normalizar_url_banco
from app.extensoes import db, limiter
from app.models import Dispositivo, Estabelecimento, PerfilUsuario, Usuario

SENHA = "senha-de-teste-123"
_SEQUENCIA = itertools.count(1)
URL_PUBLICA = "https://oriki.exemplo"


@pytest.fixture(scope="session")
def app():
    url = normalizar_url_banco(os.environ.get("DATABASE_URL_TESTE"))
    if not url:
        pytest.exit("Defina DATABASE_URL_TESTE no .env (banco oriki_test).", returncode=2)
    if not urlsplit(url).path.rstrip("/").endswith("_test"):
        # Proteção: o schema é apagado; nunca rodar contra o banco de desenvolvimento ou produção.
        pytest.exit("DATABASE_URL_TESTE precisa apontar para um banco terminado em _test.", returncode=2)

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": url,
        "SECRET_KEY": "s" * 64,
        "CHAVE_CIFRA": Fernet.generate_key().decode(),
        "URL_PUBLICA": URL_PUBLICA,
        "FUSO": "America/Belem",
        "COOKIE_SEGURO": False,
        "PROXIES_CONFIAVEIS": 0,
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with app.app_context():
        with db.engine.begin() as conexao:
            conexao.execute(text("DROP SCHEMA public CASCADE"))
            conexao.execute(text("CREATE SCHEMA public"))
        upgrade()
        db.engine.dispose()

    @app.before_request
    def _usuario_recarregado_a_cada_requisicao():
        # O teste mantém um app context aberto, e o test client o reaproveita em todas as requisições.
        # Em produção cada requisição tem o seu `g`; aqui o cache do Flask-Login é limpo para imitar isso.
        g.pop("_login_user", None)

    return app


@pytest.fixture(autouse=True)
def sessao(app):
    """Cada teste numa transação externa; os commits da API viram savepoints e tudo é desfeito no fim."""
    with app.app_context():
        conexao = db.engine.connect()
        transacao = conexao.begin()
        original = db.session
        db.session = scoped_session(sessionmaker(bind=conexao, join_transaction_mode="create_savepoint",
                                                 expire_on_commit=False))
        limiter.reset()
        try:
            yield db.session
        finally:
            db.session.remove()
            db.session = original
            transacao.rollback()
            conexao.close()


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def relogio(monkeypatch):
    """Congela regras.agora(): relogio.ajustar(datetime) e relogio.avancar(timedelta)."""
    class Relogio:
        instante = datetime.now(UTC).replace(microsecond=0)

        def ajustar(self, instante: datetime):
            self.instante = instante

        def avancar(self, delta: timedelta):
            self.instante += delta

    r = Relogio()
    monkeypatch.setattr(regras, "agora", lambda: r.instante)
    return r


# ---------- fábricas ----------

class Fabrica:
    def __init__(self, sessao):
        self.sessao = sessao

    def estabelecimento(self, slug="acai-da-dona-rosa", nome="Açaí da Dona Rosa (exemplo)", **extra) -> Estabelecimento:
        dados = {"endereco": "Rua Exemplo, 100 · Guamá, Belém", "licenca_numero": f"SESMA-{slug}",
                 "licenca_validade": regras.agora().date() + timedelta(days=200),
                 "curso_casa_acai_em": date(2025, 5, 12), **extra}
        est = Estabelecimento(nome=nome, slug_qr=slug, **dados)
        self.sessao.add(est)
        self.sessao.commit()
        return est

    def dispositivo(self, est: Estabelecimento, identificador="ORK01") -> tuple[Dispositivo, bytes]:
        chave = f"chave-{identificador}".ljust(64, "0")
        disp = Dispositivo(estabelecimento_id=est.id, identificador=identificador, chave_hmac_cifrada=cifrar(chave))
        self.sessao.add(disp)
        self.sessao.commit()
        return disp, chave.encode()

    def usuario(self, perfil=PerfilUsuario.BATEDOR, est: Estabelecimento | None = None, email=None,
                nome="Rosa (exemplo)", termo=True) -> Usuario:
        usuario = Usuario(nome=nome, email=email or f"{perfil.value}{next(_SEQUENCIA)}@exemplo.com",
                          senha_hash=generate_password_hash(SENHA, method="pbkdf2:sha256:1000"), perfil=perfil,
                          estabelecimento_id=est.id if est else None,
                          termo_aceito_em=regras.agora() if termo else None)
        self.sessao.add(usuario)
        self.sessao.commit()
        return usuario


@pytest.fixture
def fabrica(sessao):
    return Fabrica(sessao)


# ---------- ESP32 de mentira (mesmo contrato da seção 7) ----------

def iso(instante: datetime) -> str:
    """Hora do RTC com offset de Belém, como o firmware envia."""
    return instante.astimezone(regras._zona("America/Belem")).isoformat(timespec="seconds")


def ciclo_assinado(identificador: str, contador: int, chave: bytes, inicio: datetime | None = None,
                   segundos=12, status="aprovado", temp_min=81.2, temp_max=84.6) -> dict:
    inicio = inicio or regras.agora() - timedelta(minutes=30)
    ciclo = {
        "codigo": f"{identificador}-{contador:06d}",
        "contador": contador,
        "inicio": iso(inicio),
        "fim": iso(inicio + timedelta(seconds=14)),
        "temp_min": temp_min,
        "temp_max": temp_max,
        "segundos_acima_80": segundos,
        "status": status,
    }
    ciclo["assinatura"] = assinar_ciclo(ciclo, chave)
    return ciclo


def envelope(identificador: str, chave: bytes, ciclos: list, enviado_em: datetime | None = None) -> dict:
    enviado = iso(enviado_em or regras.agora())
    return {"dispositivo": identificador, "enviado_em": enviado,
            "assinatura_envio": assinar_envio(identificador, enviado, chave), "ciclos": ciclos}


def enviar(cliente, identificador: str, chave: bytes, ciclos: list, **kwargs):
    return cliente.post("/api/ciclos", json=envelope(identificador, chave, ciclos, **kwargs))


def logar(cliente, usuario: Usuario, senha=SENHA):
    return cliente.post("/api/login", json={"email": usuario.email, "senha": senha})
