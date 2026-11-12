"""F4: alertas, painel do fiscal, histórico do batedor e relatório PDF (seção 13.2)."""
import io
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader

from app.models import PerfilUsuario
from conftest import ciclo_assinado, enviar, logar

T = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)  # 12:00 em Belém


@pytest.fixture
def fiscal(fabrica):
    return fabrica.usuario(PerfilUsuario.FISCAL, nome="Fiscal Teste")


def _alertas_por_ponto(cliente):
    return Counter((a["estabelecimento"]["nome"], a["tipo"]) for a in cliente.get("/api/fiscal/alertas").get_json())


def test_cenario_com_cada_alerta_aparecendo_uma_vez(cliente, fabrica, fiscal, relogio):
    a = fabrica.estabelecimento(slug="ponto-a", nome="A Lacuna")
    b = fabrica.estabelecimento(slug="ponto-b", nome="B Licença", licenca_validade=T.date() + timedelta(days=10))
    c = fabrica.estabelecimento(slug="ponto-c", nome="C Parado")
    d = fabrica.estabelecimento(slug="ponto-d", nome="D Relógio")
    chaves = {ident: fabrica.dispositivo(est, ident)[1]
              for ident, est in (("ORKA", a), ("ORKB", b), ("ORKC", c), ("ORKD", d))}

    relogio.ajustar(T - timedelta(days=4))      # C: último ciclo há 4 dias
    enviar(cliente, "ORKC", chaves["ORKC"], [ciclo_assinado("ORKC", 1, chaves["ORKC"])])
    relogio.ajustar(T - timedelta(hours=2))     # A: contadores 1, 2 e 4 recebidos há 2 h
    enviar(cliente, "ORKA", chaves["ORKA"], [ciclo_assinado("ORKA", n, chaves["ORKA"]) for n in (1, 2, 4)])
    relogio.ajustar(T)
    enviar(cliente, "ORKB", chaves["ORKB"], [ciclo_assinado("ORKB", 1, chaves["ORKB"])])
    enviar(cliente, "ORKD", chaves["ORKD"], [ciclo_assinado("ORKD", 1, chaves["ORKD"])],
           enviado_em=T - timedelta(minutes=10))  # RTC 10 min atrasado
    for ident in ("ORKA", "ORKC"):              # heartbeat: dispositivos com contato
        enviar(cliente, ident, chaves[ident], [])

    logar(cliente, fiscal)
    assert _alertas_por_ponto(cliente) == Counter({
        ("A Lacuna", "lacuna_contador"): 1,
        ("B Licença", "licenca_vence_em_breve"): 1,
        ("C Parado", "sem_registro"): 1,
        ("D Relógio", "relogio_divergente"): 1,
    })
    lacuna = next(x for x in cliente.get("/api/fiscal/alertas").get_json() if x["tipo"] == "lacuna_contador")
    assert lacuna["detalhe"] == "ORKA: contadores 3 a 3 ausentes"
    assert lacuna["desde"] == "2026-10-08"


def test_lacuna_recente_espera_a_sincronizacao(cliente, fabrica, fiscal, relogio):
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", n, chave) for n in (1, 3)])
    logar(cliente, fiscal)
    assert ("Açaí da Dona Rosa (exemplo)", "lacuna_contador") not in _alertas_por_ponto(cliente)
    relogio.avancar(timedelta(hours=1, minutes=1))
    assert _alertas_por_ponto(cliente)[("Açaí da Dona Rosa (exemplo)", "lacuna_contador")] == 1


def test_reprovados_sem_contato_e_licenca_vencida(cliente, fabrica, fiscal, relogio):
    relogio.ajustar(T)
    est = fabrica.estabelecimento(licenca_validade=T.date() - timedelta(days=1))
    _, chave = fabrica.dispositivo(est)
    fabrica.dispositivo(est, "ORK02")  # nunca se comunicou
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave, status="reprovado", segundos=5),
                                     ciclo_assinado("ORK01", 2, chave, status="reprovado", segundos=0)])
    logar(cliente, fiscal)
    alertas = cliente.get("/api/fiscal/alertas").get_json()
    tipos = Counter(a["tipo"] for a in alertas)
    assert tipos == Counter({"licenca_vencida": 1, "ciclos_reprovados": 1, "dispositivo_sem_contato": 1})
    reprovados = next(a for a in alertas if a["tipo"] == "ciclos_reprovados")
    assert reprovados["detalhe"].startswith("2 ciclo(s) reprovado(s)")
    sem_contato = next(a for a in alertas if a["tipo"] == "dispositivo_sem_contato")
    assert sem_contato["detalhe"] == "ORK02: nunca se comunicou"


def test_batedor_no_painel_do_fiscal_e_403(cliente, fabrica):
    est = fabrica.estabelecimento()
    logar(cliente, fabrica.usuario(est=est))
    for rota in ("/api/fiscal/alertas", "/api/fiscal/estabelecimentos", f"/api/fiscal/estabelecimentos/{est.id}"):
        assert cliente.get(rota).status_code == 403
    assert cliente.post(f"/api/fiscal/estabelecimentos/{est.id}/vistorias",
                        json={"data": "2026-10-01", "resultado": "regular"}).status_code == 403


def test_painel_do_fiscal_sem_login_e_401(cliente):
    assert cliente.get("/api/fiscal/alertas").status_code == 401


def test_admin_tambem_acessa_o_painel(cliente, fabrica):
    logar(cliente, fabrica.usuario(PerfilUsuario.ADMIN))
    assert cliente.get("/api/fiscal/alertas").status_code == 200


# ---------- lista, detalhe e vistorias ----------

def test_lista_com_busca_e_contagem_de_alertas(cliente, fabrica, fiscal, relogio):
    rosa = fabrica.estabelecimento()
    fabrica.estabelecimento(slug="acai-do-ze", nome="Açaí do Zé")
    _, chave = fabrica.dispositivo(rosa)
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", 1, chave)])
    logar(cliente, fiscal)
    lista = cliente.get("/api/fiscal/estabelecimentos?busca=ROSA").get_json()
    assert [e["nome"] for e in lista] == ["Açaí da Dona Rosa (exemplo)"]
    assert lista[0]["ultimo_ciclo"] is not None and lista[0]["ultimo_contato"] is not None
    assert lista[0]["alertas"] == 0
    assert cliente.get("/api/fiscal/estabelecimentos?busca=%25").get_json() == []  # % é literal
    ze = cliente.get("/api/fiscal/estabelecimentos?busca=zé").get_json()
    assert ze[0]["alertas"] == 1  # sem_registro (nenhum ciclo)


def test_detalhe_traz_historico_por_dia_e_lacunas(cliente, fabrica, fiscal, relogio):
    relogio.ajustar(T)
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    enviar(cliente, "ORK01", chave, [ciclo_assinado("ORK01", n, chave) for n in (1, 2, 5)])
    logar(cliente, fabrica.usuario(est=est))
    cliente.patch("/api/lotes/ORK01-000001", json={"origem_fruto": "Combu", "quantidade_rasas": 2})
    cliente.post("/api/logout", json={})

    logar(cliente, fiscal)
    detalhe = cliente.get(f"/api/fiscal/estabelecimentos/{est.id}?de=2026-10-01&ate=2026-10-08").get_json()
    assert detalhe["estabelecimento"]["licenca_numero"] == est.licenca_numero
    assert detalhe["dispositivos"] == [{"identificador": "ORK01", "ultimo_contato": "2026-10-08T15:00:00Z"}]
    assert len(detalhe["lotes"]) == 3 and detalhe["lotes"][0]["dispositivo"] == "ORK01"
    assert len(detalhe["por_dia"]) == 8
    assert detalhe["por_dia"][0] == {"data": "2026-10-08", "ciclos": 3, "aprovados": 3, "reprovados": 0,
                                     "lotes_completos": 1, "rasas_declaradas": 2.0}
    assert detalhe["lacunas"] == ["ORK01: contadores 3 a 4 ausentes"]
    assert "chave" not in str(detalhe)
    assert cliente.get("/api/fiscal/estabelecimentos/999999").status_code == 404


def test_vistoria_e_criada_e_vira_ultima_vistoria(cliente, fabrica, fiscal, relogio):
    relogio.ajustar(T)
    est = fabrica.estabelecimento()
    logar(cliente, fiscal)
    resposta = cliente.post(f"/api/fiscal/estabelecimentos/{est.id}/vistorias",
                            json={"data": "2026-10-08", "resultado": "regular",
                                  "observacoes": "Tanque e haste em ordem."})
    assert resposta.status_code == 201
    assert resposta.get_json()["fiscal"] == {"id": fiscal.id, "nome": "Fiscal Teste"}
    assert cliente.get(f"/api/publico/{est.slug_qr}").get_json()["ultima_vistoria"] == "2026-10-08"
    detalhe = cliente.get(f"/api/fiscal/estabelecimentos/{est.id}").get_json()
    assert detalhe["vistorias"][0]["resultado"] == "regular"


@pytest.mark.parametrize("corpo, erro", [
    ({"data": "2026-10-09", "resultado": "regular"}, "data_futura"),
    ({"data": "2026-10-08"}, "campo_obrigatorio"),
    ({"data": "2026-10-08", "resultado": "  "}, "campo_obrigatorio"),
    ({"resultado": "regular"}, "campo_obrigatorio"),
    ({"data": "2026-10-08", "resultado": "x" * 41}, "texto_muito_longo"),
])
def test_validacao_da_vistoria(cliente, fabrica, fiscal, relogio, corpo, erro):
    relogio.ajustar(T)
    est = fabrica.estabelecimento()
    logar(cliente, fiscal)
    resposta = cliente.post(f"/api/fiscal/estabelecimentos/{est.id}/vistorias", json=corpo)
    assert resposta.status_code == 422 and resposta.get_json()["erro"] == erro


# ---------- histórico e relatório do batedor ----------

@pytest.fixture
def ponto_com_lotes(cliente, fabrica, relogio):
    relogio.ajustar(T)
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    ciclos = [ciclo_assinado("ORK01", n, chave, inicio=T - timedelta(hours=n)) for n in range(1, 50)]
    ciclos.append(ciclo_assinado("ORK01", 50, chave, inicio=T - timedelta(hours=50), status="reprovado", segundos=4))
    ciclos.append(ciclo_assinado("ORK01", 52, chave, inicio=T - timedelta(minutes=10)))  # lacuna no 51
    enviar(cliente, "ORK01", chave, ciclos[:50])
    enviar(cliente, "ORK01", chave, ciclos[50:])
    relogio.avancar(timedelta(hours=2))
    batedor = fabrica.usuario(est=est)
    logar(cliente, batedor)
    cliente.patch("/api/lotes/ORK01-000001", json={"origem_fruto": "Combu", "quantidade_rasas": 3})
    return est


def test_historico_paginado_e_filtrado(cliente, ponto_com_lotes):
    pagina1 = cliente.get("/api/batedor/lotes?de=2026-10-01&ate=2026-10-08").get_json()
    assert pagina1["total"] == 51 and len(pagina1["itens"]) == 50
    assert pagina1["itens"][0]["codigo"] == "ORK01-000052"  # mais novo primeiro
    pagina2 = cliente.get("/api/batedor/lotes?de=2026-10-01&ate=2026-10-08&pagina=2").get_json()
    assert [i["codigo"] for i in pagina2["itens"]] == ["ORK01-000050"]
    completos = cliente.get("/api/batedor/lotes?de=2026-10-01&ate=2026-10-08&status=completo").get_json()
    assert [i["codigo"] for i in completos["itens"]] == ["ORK01-000001"]
    assert cliente.get("/api/batedor/lotes?status=talvez").status_code == 400
    assert cliente.get("/api/batedor/lotes?pagina=0").status_code == 400


def test_periodo_maior_que_92_dias_e_422(cliente, ponto_com_lotes):
    for rota in ("/api/batedor/lotes", "/api/batedor/relatorio.pdf"):
        resposta = cliente.get(f"{rota}?de=2026-01-01&ate=2026-10-08")
        assert resposta.status_code == 422 and resposta.get_json()["erro"] == "periodo_muito_longo"
    assert cliente.get("/api/batedor/lotes?de=2026-07-09&ate=2026-10-08").status_code == 200  # 92 dias
    assert cliente.get("/api/batedor/lotes?de=2026-10-08&ate=2026-10-01").status_code == 422
    assert cliente.get("/api/batedor/lotes?de=08/10/2026").status_code == 400


def test_relatorio_pdf_abre_com_acentos_e_totais_certos(cliente, ponto_com_lotes):
    resposta = cliente.get("/api/batedor/relatorio.pdf?de=2026-10-01&ate=2026-10-08")
    assert resposta.status_code == 200 and resposta.mimetype == "application/pdf"
    assert "attachment" in resposta.headers["Content-Disposition"]
    leitor = PdfReader(io.BytesIO(resposta.data))
    texto = "\n".join(pagina.extract_text() for pagina in leitor.pages)
    for trecho in ("Açaí da Dona Rosa", "—", "≥", "não substitui a vistoria"):
        assert trecho in texto
    assert "Ciclos aprovados: 50 · reprovados: 1" in texto
    assert "Lotes completos: 1 · incompletos: 50" in texto
    assert "ORK01: contadores 51 a 51 ausentes" in texto
    assert "ORK01-000052" in texto and "ORK01-000050" in texto
