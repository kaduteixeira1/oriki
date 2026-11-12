"""F3: página pública do QR (seção 13.2)."""
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AcessoQR
from conftest import URL_PUBLICA, ciclo_assinado, enviar, logar


@pytest.fixture
def ponto(fabrica):
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    batedor = fabrica.usuario(est=est, email="rosa@exemplo.com", nome="Rosilene Batedora")
    return est, chave, batedor


def test_responde_sem_login_e_slug_inexistente_e_404(cliente, ponto):
    resposta = cliente.get("/api/publico/acai-da-dona-rosa")
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["nome"] == "Açaí da Dona Rosa (exemplo)"
    assert corpo["licenca"]["situacao"] == "em_dia"
    assert corpo["curso_casa_acai_em"] == "2025-05-12"
    assert "Não é selo oficial" in corpo["aviso"]
    assert cliente.get("/api/publico/nao-existe").status_code == 404
    assert cliente.get("/api/publico/..%2Fadmin").status_code == 404


def test_nao_expoe_dados_de_pessoas(cliente, ponto):
    texto = cliente.get("/api/publico/acai-da-dona-rosa").get_data(as_text=True)
    assert "rosa@exemplo.com" not in texto
    assert "Rosilene" not in texto
    assert "@" not in texto


def test_dias_tem_sempre_7_itens_com_zeros(cliente, ponto, relogio):
    _, chave, _ = ponto
    relogio.ajustar(datetime(2026, 10, 8, 13, 0, tzinfo=UTC))  # 10:00 em Belém
    enviar(cliente, "ORK01", chave, [
        ciclo_assinado("ORK01", 1, chave, inicio=datetime(2026, 10, 8, 10, 42, 10, tzinfo=UTC)),  # 07:42 local
        ciclo_assinado("ORK01", 2, chave, inicio=datetime(2026, 10, 8, 11, 0, tzinfo=UTC), status="reprovado",
                       segundos=2),
        ciclo_assinado("ORK01", 3, chave, inicio=datetime(2026, 10, 6, 13, 5, tzinfo=UTC)),
        ciclo_assinado("ORK01", 4, chave, inicio=datetime(2026, 9, 30, 13, 5, tzinfo=UTC)),  # fora dos 7 dias
    ])
    dias = cliente.get("/api/publico/acai-da-dona-rosa").get_json()["dias"]
    assert [d["data"] for d in dias] == [f"2026-10-0{n}" for n in range(8, 1, -1)]
    assert dias[0] == {"data": "2026-10-08", "aprovados": 1, "reprovados": 1, "ultimo": "08:00"}
    assert dias[1] == {"data": "2026-10-07", "aprovados": 0, "reprovados": 0, "ultimo": None}
    assert dias[2] == {"data": "2026-10-06", "aprovados": 1, "reprovados": 0, "ultimo": "10:05"}
    assert sum(d["aprovados"] + d["reprovados"] for d in dias) == 3


def test_origem_qr_conta_acesso_e_sem_parametro_nao(cliente, sessao, ponto):
    est = ponto[0]
    cliente.get("/api/publico/acai-da-dona-rosa")
    assert sessao.execute(select(AcessoQR)).first() is None
    for _ in range(3):
        cliente.get("/api/publico/acai-da-dona-rosa?origem=qr")
    acesso = sessao.execute(select(AcessoQR)).scalar_one()
    assert (acesso.estabelecimento_id, acesso.total) == (est.id, 3)


def test_cache_publico_sem_cookie(cliente, ponto):
    resposta = cliente.get("/api/publico/acai-da-dona-rosa?origem=qr")
    assert resposta.headers["Cache-Control"] == "public, max-age=60"
    assert "Set-Cookie" not in resposta.headers


def test_limite_de_60_por_minuto(cliente, ponto):
    for _ in range(60):
        assert cliente.get("/api/publico/acai-da-dona-rosa").status_code == 200
    assert cliente.get("/api/publico/acai-da-dona-rosa").status_code == 429


def test_ultima_vistoria_aparece(cliente, fabrica, ponto, relogio):
    from app.models import PerfilUsuario
    fiscal = fabrica.usuario(PerfilUsuario.FISCAL)
    logar(cliente, fiscal)
    dia = (relogio.instante - timedelta(days=20)).date().isoformat()
    cliente.post(f"/api/fiscal/estabelecimentos/{ponto[0].id}/vistorias", json={"data": dia, "resultado": "regular"})
    assert cliente.get("/api/publico/acai-da-dona-rosa").get_json()["ultima_vistoria"] == dia


# ---------- QR em SVG ----------

def _decodificar_svg(svg: str) -> str:
    """Rasteriza os quadrados do <path> do SVG e lê o QR com o OpenCV."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    tamanho = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    quadrados = [tuple(map(float, q)) for q in
                 re.findall(r"M([\d.]+),([\d.]+)H([\d.]+)V([\d.]+)H[\d.]+z", svg)]
    modulo = quadrados[0][2] - quadrados[0][0]
    n = round(tamanho / modulo)
    imagem = np.full((n, n), 255, dtype=np.uint8)
    for x, y, _, _ in quadrados:
        imagem[round(y / modulo), round(x / modulo)] = 0
    imagem = cv2.resize(imagem, (n * 10, n * 10), interpolation=cv2.INTER_NEAREST)
    texto, _, _ = cv2.QRCodeDetector().detectAndDecode(imagem)
    return texto


def test_qr_svg_aponta_para_a_pagina_publica(cliente, ponto):
    logar(cliente, ponto[2])
    resposta = cliente.get("/api/batedor/qr.svg")
    assert resposta.status_code == 200
    assert resposta.mimetype == "image/svg+xml"
    assert _decodificar_svg(resposta.get_data(as_text=True)) == f"{URL_PUBLICA}/p/acai-da-dona-rosa?origem=qr"


def test_qr_svg_exige_login(cliente, ponto):
    assert cliente.get("/api/batedor/qr.svg").status_code == 401
