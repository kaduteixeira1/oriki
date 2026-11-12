"""Chaves HMAC dos dispositivos, guardadas cifradas com Fernet (seção 10.1, "vazamento do banco").

A chave precisa ser recuperável para conferir a assinatura, por isso é cifrada e não hasheada.
"""
import secrets

from flask import current_app

from .config import criar_fernet


def _fernet():
    fernet = current_app.extensions.get("oriki_fernet")
    if fernet is None:
        fernet = criar_fernet(current_app.config["CHAVE_CIFRA"])
        current_app.extensions["oriki_fernet"] = fernet
    return fernet


def gerar_chave_dispositivo() -> str:
    """64 caracteres hex, usados pelo firmware como texto (bytes ASCII)."""
    return secrets.token_hex(32)


def cifrar(chave: str) -> str:
    return _fernet().encrypt(chave.encode()).decode()


def decifrar(cifrada: str) -> bytes:
    return _fernet().decrypt(cifrada.encode())


def recifrar(cifrada: str) -> str:
    """Recifra com a primeira chave de CHAVE_CIFRA (rotação da chave mestra)."""
    return _fernet().rotate(cifrada.encode()).decode()
