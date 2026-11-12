"""Teste nos dois lados (seção 16): o JSON que o firmware do Tinkercad imprime confere com o backend.

As saídas em tests/dados/ foram copiadas do Monitor serial do firmware de demonstração (Tinkercad), assinadas
com a chave de demonstração. O código do firmware fica fora deste repositório.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from app.assinatura import assinar_ciclo, assinar_envio
from app.contrato import validar_ciclo

DADOS = Path(__file__).parent / "dados"
CHAVE_DEMO = b"7f5f1804ca51c2c77b5371a984cc330aa45570a122f8319e66160fc41201666f"

_spec = importlib.util.spec_from_file_location(
    "conferir_envio", Path(__file__).parent.parent / "scripts" / "conferir_envio.py")
conferir_envio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conferir_envio)


def _linha(nome: str) -> str:
    [linha] = conferir_envio.ler_envios((DADOS / nome).read_text(encoding="utf-8"))
    return linha


def test_vetores_da_secao_7_2():
    chave = b"chave-de-teste"
    assert assinar_envio("ORK01", "2026-10-08T07:50:00-03:00", chave) == \
        "74a7b50b829144a0b5e44210049c7b8ba941e9b1b927f8da2f8bc9aab33a2c71"
    ciclo = {"codigo": "ORK01-000128", "contador": 128, "inicio": "2026-10-08T07:42:10-03:00",
             "fim": "2026-10-08T07:42:24-03:00", "temp_min": 81.2, "temp_max": 84.6,
             "segundos_acima_80": 12, "status": "aprovado"}
    assert assinar_ciclo(ciclo, chave) == "d7d02435af15a3b257a765d3e90b17687d780a7620d70b3c76350b9ff8f9d24d"


def test_envio_do_tinkercad_confere_inteiro():
    envelope_ok, resultados = conferir_envio.conferir(_linha("tinkercad_envio_ok.txt"), CHAVE_DEMO)
    assert envelope_ok
    assert resultados == [
        ("ORK01-000001", "aprovado", "ok"),
        ("ORK01-000002", "reprovado", "ok"),
        ("ORK01-000003", "reprovado", "ok"),
        ("ORK01-000004", "aprovado", "ok"),
    ]


def test_ciclo_adulterado_na_memoria_do_dispositivo_e_recusado():
    # ORK01-000002 virou "aprovado" com 10 s depois de assinado; a assinatura_envio continua válida.
    envelope_ok, resultados = conferir_envio.conferir(_linha("tinkercad_envio_adulterado.txt"), CHAVE_DEMO)
    assert envelope_ok
    assert {codigo: resultado for codigo, _, resultado in resultados} == {
        "ORK01-000001": "ok", "ORK01-000002": "assinatura_invalida", "ORK01-000003": "ok", "ORK01-000004": "ok"}


def test_chave_errada_recusa_tudo():
    envelope_ok, resultados = conferir_envio.conferir(_linha("tinkercad_envio_ok.txt"), b"0" * 64)
    assert not envelope_ok
    assert {resultado for _, _, resultado in resultados} == {"assinatura_invalida"}


@pytest.mark.parametrize("mudanca, motivo", [
    ({"inicio": "2026-10-22T07:30:05"}, "formato_invalido"),           # sem offset
    ({"segundos_acima_80": 9}, "status_inconsistente"),                 # aprovado com menos de 10 s
    ({"codigo": "ORK01-1"}, "codigo_invalido"),
    ({"temp_min": 90.0}, "formato_invalido"),                           # mínima acima da máxima
])
def test_regras_do_ciclo_vem_antes_da_assinatura(mudanca, motivo):
    ciclo = json.loads(_linha("tinkercad_envio_ok.txt"))["ciclos"][0]  # ORK01-000001, aprovado, 12 s
    assert validar_ciclo("ORK01", ciclo, CHAVE_DEMO) is None
    assert validar_ciclo("ORK01", {**ciclo, **mudanca}, CHAVE_DEMO) == motivo


def test_script_sai_com_0_so_quando_tudo_confere(capsys):
    chave = CHAVE_DEMO.decode()
    assert conferir_envio.main([str(DADOS / "tinkercad_envio_ok.txt"), "--chave", chave]) == 0
    assert "Tudo confere." in capsys.readouterr().out
    assert conferir_envio.main([str(DADOS / "tinkercad_envio_adulterado.txt"), "--chave", chave]) == 1
    saida = capsys.readouterr().out
    assert "ORK01-000002 | aprovado  | assinatura_invalida" in saida
