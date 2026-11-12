"""Regras puras (seção 9): situação da licença e limites do dia em Belém."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app import regras

HOJE = date(2026, 10, 15)


@pytest.mark.parametrize("validade, esperado", [
    (HOJE + timedelta(days=31), "em_dia"),
    (HOJE + timedelta(days=30), "vence_em_breve"),
    (HOJE, "vence_em_breve"),
    (HOJE - timedelta(days=1), "vencida"),
])
def test_situacao_licenca_nas_fronteiras(validade, esperado):
    assert regras.situacao_licenca(validade, HOJE) == esperado


def test_dia_de_belem_comeca_as_3h_utc():
    inicio, fim = regras.intervalo_dias(HOJE, HOJE)
    assert inicio.astimezone(UTC) == datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
    assert fim.astimezone(UTC) == datetime(2026, 10, 16, 3, 0, tzinfo=UTC)


def test_lote_so_e_completo_com_origem_e_quantidade():
    assert regras.lote_completo("Ilha do Combu", 3)
    assert not regras.lote_completo(None, 3)
    assert not regras.lote_completo("Ilha do Combu", None)
