"""seed.py: ciclos de demonstração relativos a hoje, sem lacuna e com assinatura verdadeira."""
from collections import Counter
from datetime import UTC, date, datetime

import pytest

import seed
from app import regras
from app.assinatura import confere_ciclo

CHAVE = seed.CHAVE_DEMO_ORK01.encode()


def _por_dia(ciclos) -> Counter:
    return Counter((date.fromisoformat(c["inicio"][:10]), c["status"]) for c in ciclos)


@pytest.mark.parametrize("agora, dia_demo", [
    (datetime(2026, 10, 22, 15, 0, tzinfo=UTC), date(2026, 10, 22)),  # meio-dia em Belém
    (datetime(2026, 10, 22, 8, 0, tzinfo=UTC), date(2026, 10, 21)),   # 05h em Belém: usa ontem
])
def test_ciclos_do_seed(relogio, agora, dia_demo):
    relogio.ajustar(agora)
    ciclos = seed.gerar_ciclos(CHAVE)

    assert [c["contador"] for c in ciclos] == list(range(1, len(ciclos) + 1))
    assert all(c["codigo"] == f"ORK01-{c['contador']:06d}" and confere_ciclo(c, CHAVE) for c in ciclos)
    por_dia = _por_dia(ciclos)
    assert por_dia[(dia_demo, "aprovado")] == 6 and por_dia[(dia_demo, "reprovado")] == 1
    dias_anteriores = [por_dia[(date.fromordinal(dia_demo.toordinal() - n), "aprovado")] for n in range(1, 7)]
    assert 0 in dias_anteriores and all(0 <= n <= 9 for n in dias_anteriores)
    assert max(datetime.fromisoformat(c["inicio"]) for c in ciclos) < regras.agora()


def test_recriar_apaga_tambem_os_envios_recusados(fabrica, sessao):
    """--recriar depois do teste de adulteração: a recusa (OR-31) não pode travar a limpeza."""
    from sqlalchemy import select

    from app.models import Estabelecimento, RecusaEnvio
    est = fabrica.estabelecimento()
    dispositivo, _ = fabrica.dispositivo(est)
    sessao.add(RecusaEnvio(dispositivo_id=dispositivo.id, codigo="ORK01-000033", motivo="assinatura_invalida"))
    sessao.flush()

    seed.apagar_exemplo()

    assert sessao.execute(select(Estabelecimento).where(Estabelecimento.slug_qr == seed.SLUG)).first() is None
    assert sessao.execute(select(RecusaEnvio)).first() is None
