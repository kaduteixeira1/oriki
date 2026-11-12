"""F1: ingestão do sensor (seção 13.2)."""
import json
import random
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app import regras
from app.alertas import lacunas
from app.assinatura import assinar_ciclo, confere_ciclo, confere_envio, mensagem_ciclo
from app.models import Ciclo, Lote
from conftest import ciclo_assinado, enviar, envelope, iso

CHAVE_VETOR = b"chave-de-teste"


def contar(sessao, modelo):
    return sessao.scalar(select(func.count()).select_from(modelo))


@pytest.fixture
def ponto(fabrica):
    est = fabrica.estabelecimento()
    disp, chave = fabrica.dispositivo(est)
    return est, disp, chave


# ---------- contrato (seção 7.2) ----------

def test_vetores_de_teste_da_secao_7_2():
    assert confere_envio("ORK01", "2026-10-08T07:50:00-03:00",
                         "74a7b50b829144a0b5e44210049c7b8ba941e9b1b927f8da2f8bc9aab33a2c71", CHAVE_VETOR)
    ciclo = {"codigo": "ORK01-000128", "contador": 128, "inicio": "2026-10-08T07:42:10-03:00",
             "fim": "2026-10-08T07:42:24-03:00", "temp_min": 81.2, "temp_max": 84.6,
             "segundos_acima_80": 12, "status": "aprovado"}
    assert mensagem_ciclo(ciclo) == (b"ORK01-000128|128|2026-10-08T07:42:10-03:00|2026-10-08T07:42:24-03:00|"
                                     b"81.20|84.60|12|aprovado")
    assert assinar_ciclo(ciclo, CHAVE_VETOR) == "d7d02435af15a3b257a765d3e90b17687d780a7620d70b3c76350b9ff8f9d24d"
    assert confere_ciclo({**ciclo, "assinatura": "D7D02435AF15A3B257A765D3E90B17687D780A7620D70B3C76350B9FF8F9D24D"},
                         CHAVE_VETOR)


def test_chave_do_dispositivo_fica_cifrada_no_banco(ponto):
    _, disp, chave = ponto
    assert chave.decode() not in disp.chave_hmac_cifrada


# ---------- recebimento e idempotência ----------

def test_50_ciclos_validos_sao_gravados(cliente, sessao, ponto):
    _, _, chave = ponto
    ciclos = [ciclo_assinado("ORK01", n, chave) for n in range(1, 51)]
    resposta = enviar(cliente, "ORK01", chave, ciclos)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert len(corpo["recebidos"]) == 50 and corpo["recusados"] == []
    assert corpo["hora_servidor"].endswith("Z")
    assert contar(sessao, Lote) == 50 and contar(sessao, Ciclo) == 50
    lote = sessao.execute(select(Lote).where(Lote.codigo == "ORK01-000001")).scalar_one()
    assert lote.status.value == "incompleto"


def test_reenvio_em_outra_ordem_nao_duplica(cliente, sessao, ponto):
    _, _, chave = ponto
    ciclos = [ciclo_assinado("ORK01", n, chave) for n in range(1, 51)]
    enviar(cliente, "ORK01", chave, ciclos)
    random.shuffle(ciclos)
    corpo = enviar(cliente, "ORK01", chave, ciclos).get_json()
    assert sorted(corpo["recebidos"]) == sorted(c["codigo"] for c in ciclos)
    assert corpo["recusados"] == []
    assert contar(sessao, Lote) == 50 and contar(sessao, Ciclo) == 50


def test_ciclo_repetido_no_mesmo_envio_grava_uma_vez(cliente, sessao, ponto):
    _, _, chave = ponto
    ciclo = ciclo_assinado("ORK01", 1, chave)
    corpo = enviar(cliente, "ORK01", chave, [ciclo, ciclo]).get_json()
    assert corpo["recebidos"] == ["ORK01-000001", "ORK01-000001"]
    assert contar(sessao, Ciclo) == 1


def test_ciclo_adulterado_e_recusado_e_nada_e_gravado(cliente, sessao, ponto):
    _, _, chave = ponto
    ciclo = ciclo_assinado("ORK01", 1, chave, status="reprovado", segundos=4)
    ciclo["status"], ciclo["segundos_acima_80"] = "aprovado", 12  # "reprovado" virou "aprovado" no cartão
    corpo = enviar(cliente, "ORK01", chave, [ciclo]).get_json()
    assert corpo["recusados"] == [{"codigo": "ORK01-000001", "motivo": "assinatura_invalida"}]
    assert contar(sessao, Lote) == 0


def test_mesmo_codigo_com_assinatura_diferente_e_conflito(cliente, sessao, ponto):
    _, _, chave = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave, temp_max=84.6)])
    outro = ciclo_assinado("ORK01", 1, chave, temp_max=90.0)  # assinado de verdade, conteúdo diferente
    corpo = enviar(cliente, "ORK01", chave, [outro]).get_json()
    assert corpo["recusados"] == [{"codigo": "ORK01-000001", "motivo": "conflito"}]
    assert sessao.scalar(select(Ciclo.temp_max)) == Decimal("84.60")


def test_um_ciclo_ruim_nao_derruba_os_outros(cliente, sessao, ponto):
    _, _, chave = ponto
    ruim = ciclo_assinado("ORK01", 2, chave)
    ruim["temp_max"] = 99.9
    corpo = enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave), ruim,
                                             ciclo_assinado("ORK01", 3, chave)]).get_json()
    assert corpo["recebidos"] == ["ORK01-000001", "ORK01-000003"]
    assert corpo["recusados"] == [{"codigo": "ORK01-000002", "motivo": "assinatura_invalida"}]


# ---------- envelope e autenticação ----------

def test_51_ciclos_e_400(cliente, ponto):
    _, _, chave = ponto
    resposta = enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", n, chave) for n in range(1, 52)])
    assert resposta.status_code == 400
    assert resposta.get_json()["erro"] == "envelope_invalido"


def test_dispositivo_inexistente_e_assinatura_errada_tem_a_mesma_resposta(cliente, ponto):
    _, _, chave = ponto
    inexistente = enviar(cliente, "ORK99", chave, [])
    corpo = envelope("ORK01", chave, [])
    corpo["assinatura_envio"] = "0" * 64
    errada = cliente.post("/api/ciclos", json=corpo)
    assert inexistente.status_code == errada.status_code == 401
    assert inexistente.get_json() == errada.get_json() == {"erro": "nao_autorizado"}


def test_envio_de_outro_dispositivo_com_chave_errada_e_401(cliente, fabrica, ponto):
    est, _, chave_ork01 = ponto
    fabrica.dispositivo(est, "ORK02")
    assert enviar(cliente, "ORK02", chave_ork01, []).status_code == 401


def test_corpo_que_nao_e_json_e_415(cliente):
    resposta = cliente.post("/api/ciclos", data="dispositivo=ORK01", content_type="application/x-www-form-urlencoded")
    assert resposta.status_code == 415


def test_envelope_sem_offset_e_400(cliente, ponto):
    _, _, chave = ponto
    corpo = envelope("ORK01", chave, [])
    corpo["enviado_em"] = "2026-10-08T07:50:00"
    assert cliente.post("/api/ciclos", json=corpo).status_code == 400


# ---------- relógio e heartbeat ----------

def test_relogio_10_min_fora_marca_os_ciclos(cliente, sessao, ponto, relogio):
    _, _, chave = ponto
    atrasado = relogio.instante - timedelta(minutes=10)
    corpo = enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave, inicio=atrasado)],
                   enviado_em=atrasado).get_json()
    assert corpo["recebidos"] == ["ORK01-000001"]
    assert corpo["hora_servidor"] == regras.iso_utc(relogio.instante)
    assert sessao.scalar(select(Ciclo.relogio_divergente)) is True


def test_relogio_dentro_da_tolerancia_nao_marca(cliente, sessao, ponto, relogio):
    _, _, chave = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)],
           enviado_em=relogio.instante - timedelta(seconds=90))
    assert sessao.scalar(select(Ciclo.relogio_divergente)) is False


def test_lista_vazia_funciona_como_heartbeat(cliente, sessao, ponto, relogio):
    _, disp, chave = ponto
    resposta = enviar(cliente, "ORK01", chave, [])
    assert resposta.status_code == 200
    assert resposta.get_json()["recebidos"] == []
    sessao.refresh(disp)
    assert disp.ultimo_contato == relogio.instante


# ---------- validação de cada ciclo (seção 7.4) ----------

def test_aprovado_com_9_segundos_e_status_inconsistente(cliente, ponto):
    _, _, chave = ponto
    ciclo = ciclo_assinado("ORK01", 1, chave, segundos=9)
    corpo = enviar(cliente, "ORK01", chave, [ciclo]).get_json()
    assert corpo["recusados"] == [{"codigo": "ORK01-000001", "motivo": "status_inconsistente"}]


def test_hora_sem_offset_e_formato_invalido(cliente, ponto):
    _, _, chave = ponto
    ciclo = ciclo_assinado("ORK01", 1, chave)
    ciclo["inicio"] = ciclo["inicio"][:19]  # tira o "-03:00"
    ciclo["assinatura"] = assinar_ciclo(ciclo, chave)
    corpo = enviar(cliente, "ORK01", chave, [ciclo]).get_json()
    assert corpo["recusados"] == [{"codigo": "ORK01-000001", "motivo": "formato_invalido"}]


@pytest.mark.parametrize("campo, valor, motivo", [
    ("codigo", "ORK01-128", "codigo_invalido"),
    ("codigo", "ORK02-000001", "codigo_invalido"),
    ("contador", 0, "formato_invalido"),
    ("contador", True, "formato_invalido"),
    ("temp_max", float("nan"), "formato_invalido"),
    ("temp_max", 130, "formato_invalido"),
    ("temp_min", 90, "formato_invalido"),  # maior que temp_max
    ("segundos_acima_80", 40000, "formato_invalido"),
    ("status", "talvez", "formato_invalido"),
    ("fim", "2020-01-01T00:00:00-03:00", "formato_invalido"),  # antes do início
    ("assinatura", "xyz", "assinatura_invalida"),
])
def test_validacao_de_cada_campo(cliente, sessao, ponto, campo, valor, motivo):
    _, _, chave = ponto
    ciclo = ciclo_assinado("ORK01", 1, chave)
    ciclo[campo] = valor
    resposta = cliente.post("/api/ciclos", data=_json_com_nan(envelope("ORK01", chave, [ciclo])),
                            content_type="application/json")
    assert resposta.get_json()["recusados"][0]["motivo"] == motivo
    assert contar(sessao, Ciclo) == 0


def _json_com_nan(corpo):
    return json.dumps(corpo, allow_nan=True)  # NaN não é JSON válido, mas o parser do Python aceita


# ---------- integridade no banco ----------

def test_ciclo_e_imutavel_no_banco(cliente, sessao, ponto):
    _, _, chave = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    with pytest.raises(DBAPIError, match="imutáveis"):
        with sessao.begin_nested():
            sessao.execute(text("UPDATE ciclos SET status = 'aprovado'"))
    with pytest.raises(DBAPIError, match="imutáveis"):
        with sessao.begin_nested():
            sessao.execute(text("DELETE FROM ciclos"))


def test_consulta_de_lacuna_do_anexo_a(cliente, sessao, ponto):
    _, disp, chave = ponto
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", n, chave) for n in (1, 2, 4, 7)])
    faixas = [(l.faltando_de, l.faltando_ate) for l in lacunas(sessao)]
    assert faixas == [(3, 3), (5, 6)]
    assert lacunas(sessao)[0].descricao == "ORK01: contadores 3 a 3 ausentes"


def test_limite_de_60_envios_por_minuto(cliente, ponto):
    _, _, chave = ponto
    for _ in range(60):
        assert enviar(cliente, "ORK01", chave, []).status_code == 200
    resposta = enviar(cliente, "ORK01", chave, [])
    assert resposta.status_code == 429
    assert resposta.get_json()["erro"] == "limite_de_tentativas"


def test_iso_do_simulador_tem_offset_de_belem(relogio):
    assert iso(relogio.instante).endswith("-03:00")
