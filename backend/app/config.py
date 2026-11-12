"""Configuração lida do ambiente (.env em desenvolvimento, painel do provedor em produção)."""
import os
from datetime import timedelta

from cryptography.fernet import Fernet, MultiFernet
from dotenv import load_dotenv

load_dotenv()


def normalizar_url_banco(url: str | None) -> str | None:
    """Alguns provedores entregam `postgres://`, que o SQLAlchemy 2 não aceita (seção 12)."""
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _bool(nome: str, padrao: str = "0") -> bool:
    return os.environ.get(nome, padrao).strip().lower() in ("1", "true", "sim", "yes")


def carregar_config() -> dict:
    cookie_seguro = _bool("COOKIE_SEGURO")
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "SQLALCHEMY_DATABASE_URI": normalizar_url_banco(os.environ.get("DATABASE_URL")),
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "CHAVE_CIFRA": os.environ.get("CHAVE_CIFRA"),
        "URL_PUBLICA": os.environ.get("URL_PUBLICA", "http://localhost:5173").rstrip("/"),
        "FUSO": os.environ.get("FUSO", "America/Belem"),
        "FRONTEND_DIST": os.environ.get("FRONTEND_DIST", "../frontend/dist"),
        "PROXIES_CONFIAVEIS": int(os.environ.get("PROXIES_CONFIAVEIS", "0")),
        "LOG_SEGURANCA_ARQUIVO": os.environ.get("LOG_SEGURANCA_ARQUIVO"),
        "LOG_SEGURANCA_DIAS": int(os.environ.get("LOG_SEGURANCA_DIAS", "90")),
        # Limitador: memory:// exige 1 worker do gunicorn (seção 14.2); redis://… para escalar.
        "RATELIMIT_STORAGE_URI": os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
        "RATELIMIT_HEADERS_ENABLED": True,
        # O maior corpo legítimo é o envio de 50 ciclos (~25 KB).
        "MAX_CONTENT_LENGTH": 128 * 1024,
        # Cookies (seção 10.1): HttpOnly + SameSite=Lax sempre; Secure em produção.
        "COOKIE_SEGURO": cookie_seguro,
        "SESSION_COOKIE_NAME": "oriki_sessao",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": cookie_seguro,
        "REMEMBER_COOKIE_NAME": "oriki_lembrar",
        "REMEMBER_COOKIE_DURATION": timedelta(days=30),
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_SECURE": cookie_seguro,
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
    }


def validar_config(config) -> None:
    """Falha na subida, com mensagem clara, em vez de falhar no meio de uma requisição."""
    faltando = [nome for nome in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI", "CHAVE_CIFRA") if not config.get(nome)]
    if faltando:
        nomes = ", ".join("DATABASE_URL" if n == "SQLALCHEMY_DATABASE_URI" else n for n in faltando)
        raise RuntimeError(f"Configuração ausente: {nomes}. Veja o .env.example.")
    if len(config["SECRET_KEY"]) < 32:
        raise RuntimeError("SECRET_KEY curta demais; gere com: python -c \"import secrets; print(secrets.token_hex(32))\"")
    try:
        criar_fernet(config["CHAVE_CIFRA"])
    except (ValueError, TypeError) as erro:
        raise RuntimeError("CHAVE_CIFRA inválida; gere com: python -c \"from cryptography.fernet import Fernet; "
                           "print(Fernet.generate_key().decode())\"") from erro


def criar_fernet(chave_cifra: str) -> MultiFernet:
    """`CHAVE_CIFRA` aceita várias chaves separadas por vírgula: a primeira cifra, todas decifram.

    Isso permite trocar a chave mestra sem perder os dispositivos (comando `recifrar-chaves`).
    """
    chaves = [c.strip() for c in chave_cifra.split(",") if c.strip()]
    if not chaves:
        raise ValueError("CHAVE_CIFRA vazia")
    return MultiFernet([Fernet(c.encode()) for c in chaves])
