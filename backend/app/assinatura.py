"""Contrato da assinatura entre o ESP32 e a API (seção 7.2 do plano).

Mudar qualquer detalhe da mensagem aqui faz o servidor recusar todos os ciclos do firmware.
Os vetores de teste da seção 7.2 estão em tests/test_ciclos.py.
"""
import hashlib
import hmac

CAMPOS = ("codigo", "contador", "inicio", "fim", "temp_min", "temp_max", "segundos_acima_80", "status")


def _hmac(chave: bytes, mensagem: bytes) -> str:
    return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()


def _iguais(esperado: str, recebido) -> bool:
    # Comparação em tempo constante: não revela quantos caracteres batem.
    return hmac.compare_digest(esperado.encode(), str(recebido or "").lower().encode())


def mensagem_ciclo(ciclo: dict) -> bytes:
    partes = []
    for campo in CAMPOS:
        valor = ciclo[campo]
        if campo in ("temp_min", "temp_max"):
            valor = f"{float(valor):.2f}"
        partes.append(str(valor))
    return "|".join(partes).encode()


def mensagem_envio(dispositivo: str, enviado_em: str) -> bytes:
    return f"{dispositivo}|{enviado_em}".encode()


def assinar_ciclo(ciclo: dict, chave: bytes) -> str:
    return _hmac(chave, mensagem_ciclo(ciclo))


def assinar_envio(dispositivo: str, enviado_em: str, chave: bytes) -> str:
    return _hmac(chave, mensagem_envio(dispositivo, enviado_em))


def confere_ciclo(ciclo: dict, chave: bytes) -> bool:
    return _iguais(assinar_ciclo(ciclo, chave), ciclo.get("assinatura"))


def confere_envio(dispositivo: str, enviado_em: str, assinatura: str, chave: bytes) -> bool:
    return _iguais(assinar_envio(dispositivo, enviado_em, chave), assinatura)
