"""OR-31 (erros de envio no painel) e OR-23 (acessos do QR no detalhe do fiscal)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import PerfilUsuario, RecusaEnvio
from conftest import ciclo_assinado, enviar, logar

T = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)  # 12:00 em Belém


@pytest.fixture
def cenario(cliente, fabrica, relogio):
    relogio.ajustar(T)
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est, "ORK01")
    fiscal = fabrica.usuario(PerfilUsuario.FISCAL)
    return est, chave, fiscal


def test_recusas_ficam_gravadas_e_viram_alerta(cliente, sessao, cenario):
    est, chave, fiscal = cenario
    bom = ciclo_assinado("ORK01", 1, chave)
    adulterado = ciclo_assinado("ORK01", 2, chave, status="reprovado", segundos=4)
    adulterado["status"] = "aprovado"
    adulterado["segundos_acima_80"] = 14
    resposta = enviar(cliente, "ORK01", chave, [bom, adulterado]).get_json()
    assert resposta["recusados"] == [{"codigo": "ORK01-000002", "motivo": "assinatura_invalida"}]

    conflito = ciclo_assinado("ORK01", 1, chave, temp_max=90.0)  # mesmo código, outra assinatura
    enviar(cliente, "ORK01", chave, [conflito])

    assert sessao.scalar(select(func.count()).select_from(RecusaEnvio)) == 2
    logar(cliente, fiscal)
    alertas = [a for a in cliente.get("/api/fiscal/alertas").get_json() if a["tipo"] == "envios_recusados"]
    assert len(alertas) == 1
    assert "2 ciclo(s) recusado(s)" in alertas[0]["detalhe"]
    assert "assinatura_invalida" in alertas[0]["detalhe"] and "conflito" in alertas[0]["detalhe"]
    assert alertas[0]["desde"] == "2026-10-08"

    detalhe = cliente.get(f"/api/fiscal/estabelecimentos/{est.id}").get_json()
    assert [(r["codigo"], r["motivo"]) for r in detalhe["recusas"]] == [
        ("ORK01-000001", "conflito"), ("ORK01-000002", "assinatura_invalida")]
    assert detalhe["recusas"][0]["dispositivo"] == "ORK01"


def test_envio_com_assinatura_de_envio_errada_nao_grava_recusa(cliente, sessao, cenario):
    _, chave, _ = cenario
    ciclo = ciclo_assinado("ORK01", 1, chave)
    resposta = enviar(cliente, "ORK01", b"outra-chave" * 6, [ciclo])
    assert resposta.status_code == 401
    assert sessao.scalar(select(func.count()).select_from(RecusaEnvio)) == 0


def test_recusa_antiga_sai_do_alerta(cliente, cenario, relogio):
    _, chave, fiscal = cenario
    relogio.ajustar(T - timedelta(days=10))
    ruim = ciclo_assinado("ORK01", 1, chave)
    ruim["temp_max"] = 99.0
    enviar(cliente, "ORK01", chave, [ruim], enviado_em=T - timedelta(days=10))
    relogio.ajustar(T)
    logar(cliente, fiscal)
    assert not [a for a in cliente.get("/api/fiscal/alertas").get_json() if a["tipo"] == "envios_recusados"]


def test_detalhe_traz_acessos_do_qr_sem_dado_pessoal(cliente, cenario):
    est, _, fiscal = cenario
    for _ in range(3):
        cliente.get(f"/api/publico/{est.slug_qr}?origem=qr")
    cliente.get(f"/api/publico/{est.slug_qr}")  # sem origem=qr não conta
    logar(cliente, fiscal)
    acessos = cliente.get(f"/api/fiscal/estabelecimentos/{est.id}").get_json()["acessos_qr"]
    assert acessos == {"total": 3, "por_dia": [{"data": "2026-10-08", "total": 3}]}
