from zoneinfo import ZoneInfo
"""F2: login, resumo e formulário do lote (seção 13.2), mais as proteções de sessão."""
from datetime import UTC, datetime, timedelta

import pytest

from app.models import PerfilUsuario
from conftest import SENHA, ciclo_assinado, enviar, logar


@pytest.fixture
def ponto(fabrica):
    est = fabrica.estabelecimento()
    disp, chave = fabrica.dispositivo(est)
    batedor = fabrica.usuario(est=est, email="rosa@exemplo.com")
    return est, chave, batedor


# ---------- login ----------

def test_login_certo_devolve_usuario_e_cookie_protegido(cliente, ponto):
    est, _, batedor = ponto
    resposta = logar(cliente, batedor)
    assert resposta.status_code == 200
    assert resposta.get_json() == {
        "id": batedor.id, "nome": "Rosa (exemplo)", "perfil": "batedor",
        "estabelecimento": {"nome": est.nome, "slug_qr": est.slug_qr}, "termo_aceito": True,
    }
    cookies = resposta.headers.getlist("Set-Cookie")
    for nome in ("oriki_sessao=", "oriki_lembrar="):
        cookie = next(c for c in cookies if c.startswith(nome))
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_email_em_maiusculas_tambem_entra(cliente, ponto):
    assert cliente.post("/api/login", json={"email": " ROSA@Exemplo.com ", "senha": SENHA}).status_code == 200


def test_senha_errada_e_email_inexistente_tem_a_mesma_resposta(cliente, ponto):
    errada = cliente.post("/api/login", json={"email": "rosa@exemplo.com", "senha": "errada"})
    inexistente = cliente.post("/api/login", json={"email": "ninguem@exemplo.com", "senha": "errada"})
    assert errada.status_code == inexistente.status_code == 401
    assert errada.get_json() == inexistente.get_json() == {"erro": "credenciais_invalidas"}


@pytest.mark.parametrize("corpo", [[], "texto", {"email": "rosa@exemplo.com"}, {"email": 1, "senha": "x"}])
def test_login_com_corpo_invalido_e_400(cliente, ponto, corpo):
    resposta = cliente.post("/api/login", json=corpo)
    assert resposta.status_code == 400 and resposta.get_json()["erro"] == "corpo_invalido"


def test_sexta_tentativa_no_minuto_e_429(cliente, ponto):
    for _ in range(5):
        assert cliente.post("/api/login", json={"email": "rosa@exemplo.com", "senha": "x"}).status_code == 401
    assert cliente.post("/api/login", json={"email": "rosa@exemplo.com", "senha": SENHA}).status_code == 429


def test_me_e_logout(cliente, ponto):
    assert cliente.get("/api/me").status_code == 401
    logar(cliente, ponto[2])
    assert cliente.get("/api/me").get_json()["perfil"] == "batedor"
    assert cliente.post("/api/logout", json={}).status_code == 204
    assert cliente.get("/api/me").status_code == 401


def test_sessao_cai_quando_o_token_do_usuario_muda(cliente, sessao, ponto):
    batedor = ponto[2]
    logar(cliente, batedor)
    batedor.renovar_token_sessao()  # o que `trocar-senha` e `anonimizar-usuario` fazem
    sessao.commit()
    assert cliente.get("/api/me").status_code == 401


# ---------- permissões ----------

def test_rota_protegida_sem_sessao_e_401(cliente):
    resposta = cliente.get("/api/batedor/resumo")
    assert resposta.status_code == 401
    assert resposta.get_json() == {"erro": "nao_autenticado"}


def test_fiscal_no_resumo_do_batedor_e_403(cliente, fabrica):
    fiscal = fabrica.usuario(PerfilUsuario.FISCAL)
    logar(cliente, fiscal)
    assert cliente.get("/api/batedor/resumo").status_code == 403


def test_batedor_sem_termo_e_barrado_ate_aceitar(cliente, fabrica, ponto):
    novo = fabrica.usuario(est=ponto[0], termo=False)
    corpo = logar(cliente, novo).get_json()
    assert corpo["termo_aceito"] is False
    resposta = cliente.get("/api/batedor/resumo")
    assert resposta.status_code == 403 and resposta.get_json()["erro"] == "termo_pendente"
    aceite = cliente.post("/api/batedor/termo", json={})
    assert aceite.status_code == 200 and aceite.get_json()["termo_aceito"] is True
    assert cliente.get("/api/batedor/resumo").status_code == 200


def test_batedor_de_outro_ponto_recebe_404(cliente, fabrica, ponto):
    _, chave, _ = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    outro_est = fabrica.estabelecimento(slug="acai-do-ze", nome="Açaí do Zé")
    intruso = fabrica.usuario(est=outro_est)
    logar(cliente, intruso)
    assert cliente.get("/api/lotes/ORK01-000001").status_code == 404
    patch = cliente.patch("/api/lotes/ORK01-000001", json={"origem_fruto": "Combu"})
    assert patch.status_code == 404
    assert patch.get_json() == cliente.get("/api/lotes/ORK99-000001").get_json() == {"erro": "nao_encontrado"}


# ---------- fluxo: ciclo → lote a completar → completo ----------

def test_ciclo_vira_lote_a_completar_e_some_depois_do_patch(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave),
                                     ciclo_assinado("ORK01", 2, chave, status="reprovado", segundos=3)])
    logar(cliente, batedor)
    resumo = cliente.get("/api/batedor/resumo").get_json()
    assert [l["codigo"] for l in resumo["lotes_a_completar"]] == ["ORK01-000001", "ORK01-000002"]
    assert resumo["total_a_completar"] == 2
    assert resumo["estabelecimento"]["licenca_situacao"] == "em_dia"

    resposta = cliente.patch("/api/lotes/ORK01-000001", json={
        "origem_fruto": "Ilha do Combu", "quantidade_rasas": 3,
        "catacao": True, "sanitizacao": True, "resfriamento": False})
    assert resposta.status_code == 200
    lote = resposta.get_json()
    assert lote["status"] == "completo" and lote["quantidade_rasas"] == 3.0
    assert lote["ciclo"]["status"] == "aprovado" and lote["ciclo"]["temp_max"] == 84.6

    resumo = cliente.get("/api/batedor/resumo").get_json()
    assert [l["codigo"] for l in resumo["lotes_a_completar"]] == ["ORK01-000002"]


def test_patch_repetido_e_idempotente(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    dados = {"origem_fruto": "Ilha do Combu", "quantidade_rasas": 2.5, "catacao": True}
    primeira = cliente.patch("/api/lotes/ORK01-000001", json=dados).get_json()
    segunda = cliente.patch("/api/lotes/ORK01-000001", json=dados).get_json()
    assert primeira == segunda


def test_patch_parcial_e_volta_a_incompleto_ao_apagar(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    cliente.patch("/api/lotes/ORK01-000001", json={"origem_fruto": "Combu", "quantidade_rasas": 1})
    so_checklist = cliente.patch("/api/lotes/ORK01-000001", json={"sanitizacao": True}).get_json()
    assert so_checklist["status"] == "completo" and so_checklist["origem_fruto"] == "Combu"
    apagado = cliente.patch("/api/lotes/ORK01-000001", json={"origem_fruto": "  "}).get_json()
    assert apagado["status"] == "incompleto" and apagado["origem_fruto"] is None


@pytest.mark.parametrize("corpo, status, erro", [
    ({"quantidade_rasas": 0}, 422, "valor_fora_do_limite"),
    ({"quantidade_rasas": 10000}, 422, "valor_fora_do_limite"),
    ({"quantidade_rasas": "3"}, 400, "corpo_invalido"),
    ({"catacao": "sim"}, 400, "corpo_invalido"),
    ({"catacao": 1}, 400, "corpo_invalido"),
    ({"origem_fruto": "x" * 151}, 422, "texto_muito_longo"),
    ({"status": "completo"}, 400, "campo_desconhecido"),
    ({"ciclo": {"status": "aprovado"}}, 400, "campo_desconhecido"),
])
def test_validacao_do_patch(cliente, ponto, corpo, status, erro):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    resposta = cliente.patch("/api/lotes/ORK01-000001", json=corpo)
    assert resposta.status_code == status
    assert resposta.get_json()["erro"] == erro


def test_patch_nunca_altera_o_ciclo(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    antes = cliente.get("/api/lotes/ORK01-000001").get_json()["ciclo"]
    depois = cliente.patch("/api/lotes/ORK01-000001", json={
        "origem_fruto": "Ilha do Combu", "quantidade_rasas": 3, "catacao": True}).get_json()["ciclo"]
    assert depois == antes


def test_quantidade_e_arredondada_para_2_casas(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    lote = cliente.patch("/api/lotes/ORK01-000001", json={"quantidade_rasas": 2.345}).get_json()
    assert lote["quantidade_rasas"] == 2.35


# ---------- "hoje" no fuso de Belém ----------

def test_contagem_de_hoje_respeita_a_virada_do_dia_em_belem(cliente, ponto, relogio):
    _, chave, batedor = ponto
    # Agora: 09/10 00:30 em Belém (03:30 UTC). Em UTC, os dois ciclos seriam do mesmo dia.
    relogio.ajustar(datetime(2026, 10, 9, 3, 30, tzinfo=UTC))
    ontem_2350 = datetime(2026, 10, 9, 2, 50, tzinfo=UTC)
    hoje_0010 = datetime(2026, 10, 9, 3, 10, tzinfo=UTC)
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave, inicio=ontem_2350),
                                     ciclo_assinado("ORK01", 2, chave, inicio=hoje_0010)])
    logar(cliente, batedor)
    hoje = cliente.get("/api/batedor/resumo").get_json()["hoje"]
    assert hoje == {"data": "2026-10-09", "aprovados": 1, "reprovados": 0}


@pytest.mark.parametrize("dias, situacao", [(200, "em_dia"), (10, "vence_em_breve"), (-1, "vencida")])
def test_situacao_da_licenca_no_resumo(cliente, fabrica, relogio, dias, situacao):
    est = fabrica.estabelecimento(licenca_validade=relogio.instante.astimezone(ZoneInfo("America/Belem")).date() + timedelta(days=dias))
    batedor = fabrica.usuario(est=est)
    logar(cliente, batedor)
    assert cliente.get("/api/batedor/resumo").get_json()["estabelecimento"]["licenca_situacao"] == situacao


def test_resumo_sem_ciclos_tem_ultimo_ciclo_nulo(cliente, ponto):
    logar(cliente, ponto[2])
    resumo = cliente.get("/api/batedor/resumo").get_json()
    assert resumo["ultimo_ciclo"] is None and resumo["lotes_a_completar"] == []
    assert (resumo["hoje"]["aprovados"], resumo["hoje"]["reprovados"]) == (0, 0)


def test_resumo_conta_so_o_proprio_ponto_e_separa_reprovados(cliente, fabrica, ponto, relogio):
    _, chave_a, batedor_a = ponto
    relogio.ajustar(datetime(2026, 10, 15, 15, 0, tzinfo=UTC))  # meio-dia em Belém
    manha = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
    est_b = fabrica.estabelecimento(slug="acai-do-ze", nome="Açaí do Zé")
    _, chave_b = fabrica.dispositivo(est_b, "ORK02")
    batedor_b = fabrica.usuario(est=est_b)
    enviar(cliente, "ORK01", chave_a, [
        ciclo_assinado("ORK01", 1, chave_a, inicio=manha),
        ciclo_assinado("ORK01", 2, chave_a, inicio=manha + timedelta(minutes=10)),
        ciclo_assinado("ORK01", 3, chave_a, inicio=manha + timedelta(minutes=20), status="reprovado", segundos=4)])
    enviar(cliente, "ORK02", chave_b, [ciclo_assinado("ORK02", 1, chave_b, inicio=manha)])

    logar(cliente, batedor_a)
    resumo_a = cliente.get("/api/batedor/resumo").get_json()
    assert resumo_a["hoje"] == {"data": "2026-10-15", "aprovados": 2, "reprovados": 1}
    assert resumo_a["ultimo_ciclo"]["codigo"] == "ORK01-000003"
    assert all(l["codigo"].startswith("ORK01-") for l in resumo_a["lotes_a_completar"])

    logar(cliente, batedor_b)
    resumo_b = cliente.get("/api/batedor/resumo").get_json()
    assert resumo_b["hoje"] == {"data": "2026-10-15", "aprovados": 1, "reprovados": 0}
    assert [l["codigo"] for l in resumo_b["lotes_a_completar"]] == ["ORK02-000001"]


# ---------- CSRF e cabeçalhos ----------

def test_patch_vindo_de_outro_site_e_barrado(cliente, ponto):
    _, chave, batedor = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, batedor)
    outro_site = cliente.patch("/api/lotes/ORK01-000001", json={"catacao": True},
                               headers={"Origin": "https://malicioso.exemplo"})
    assert outro_site.status_code == 403
    formulario = cliente.patch("/api/lotes/ORK01-000001", data="catacao=true",
                               content_type="application/x-www-form-urlencoded")
    assert formulario.status_code == 415
    mesma_origem = cliente.patch("/api/lotes/ORK01-000001", json={"catacao": True},
                                 headers={"Origin": "http://localhost"})
    assert mesma_origem.status_code == 200


def test_respostas_da_api_tem_cabecalhos_de_seguranca(cliente, ponto):
    logar(cliente, ponto[2])
    resposta = cliente.get("/api/batedor/resumo")
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in resposta.headers["Content-Security-Policy"]


def test_rota_inexistente_da_api_responde_json(cliente):
    resposta = cliente.get("/api/nao-existe")
    assert resposta.status_code == 404 and resposta.get_json() == {"erro": "nao_encontrado"}
