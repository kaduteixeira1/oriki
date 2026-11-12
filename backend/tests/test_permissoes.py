"""Matriz de permissões da seção 8.3: cada rota × cada perfil (anônimo, batedor, fiscal, admin)."""
import pytest

from app.models import PerfilUsuario
from conftest import SENHA, ciclo_assinado, enviar, logar

# Esperado por perfil: (anônimo, batedor, fiscal, admin)
SO_BATEDOR = (401, 200, 403, 403)
FISCAL_E_ADMIN = (401, 403, 200, 200)
PUBLICO = (200, 200, 200, 200)
LOGADO = (401, 200, 200, 200)

ROTAS = [
    ("GET", "/api/batedor/resumo", None, SO_BATEDOR),
    ("GET", "/api/batedor/lotes", None, SO_BATEDOR),
    ("GET", "/api/batedor/qr.svg", None, SO_BATEDOR),
    ("GET", "/api/batedor/relatorio.pdf", None, SO_BATEDOR),
    ("POST", "/api/batedor/termo", {}, SO_BATEDOR),
    ("GET", "/api/lotes/ORK01-000001", None, SO_BATEDOR),
    ("PATCH", "/api/lotes/ORK01-000001", {"catacao": True}, SO_BATEDOR),
    ("GET", "/api/fiscal/alertas", None, FISCAL_E_ADMIN),
    ("GET", "/api/fiscal/estabelecimentos", None, FISCAL_E_ADMIN),
    ("GET", "/api/fiscal/estabelecimentos/{id}", None, FISCAL_E_ADMIN),
    ("POST", "/api/fiscal/estabelecimentos/{id}/vistorias", {"data": "2026-01-02", "resultado": "regular"},
     (401, 403, 201, 201)),
    ("GET", "/api/publico/acai-da-dona-rosa", None, PUBLICO),
    ("GET", "/api/me", None, LOGADO),
]
PERFIS = ("anonimo", PerfilUsuario.BATEDOR, PerfilUsuario.FISCAL, PerfilUsuario.ADMIN)


@pytest.mark.parametrize("metodo, rota, corpo, esperados", ROTAS, ids=[f"{m} {r}" for m, r, _, _ in ROTAS])
@pytest.mark.parametrize("indice", range(4), ids=[str(p) for p in PERFIS])
def test_matriz_de_permissoes(cliente, fabrica, metodo, rota, corpo, esperados, indice):
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    perfil = PERFIS[indice]
    if perfil != "anonimo":
        usuario = fabrica.usuario(perfil, est=est if perfil == PerfilUsuario.BATEDOR else None)
        assert logar(cliente, usuario).status_code == 200

    url = rota.format(id=est.id)
    resposta = cliente.open(url, method=metodo, json=corpo) if corpo is not None else cliente.open(url, method=metodo)
    assert resposta.status_code == esperados[indice], resposta.get_data(as_text=True)


def test_login_certo_nao_gasta_o_limite_de_tentativas(cliente, fabrica):
    usuario = fabrica.usuario(PerfilUsuario.ADMIN, email="admin@exemplo.com")
    for _ in range(8):  # trocar de usuário várias vezes não bloqueia
        assert logar(cliente, usuario).status_code == 200
    for _ in range(5):
        assert cliente.post("/api/login", json={"email": "admin@exemplo.com", "senha": "errada"}).status_code == 401
    # Na 6ª tentativa o limite já foi atingido: nem a senha certa entra até passar o minuto.
    assert cliente.post("/api/login", json={"email": "admin@exemplo.com", "senha": SENHA}).status_code == 429
