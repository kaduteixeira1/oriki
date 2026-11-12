"""Relatório em PDF por período, para vistoria e renovação da licença (seção 8.4). Gerado na hora."""
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from . import regras
from .alertas import ESPERA_LACUNA, lacunas
from .consultas import lotes_com_ciclo, no_periodo, totais
from .models import Ciclo, Estabelecimento, Lote, StatusLote

FONTES = Path(__file__).resolve().parent / "fontes"
RODAPE = "Registros do estabelecimento; não substitui a vistoria"
SITUACAO_LICENCA = {"em_dia": "em dia", "vence_em_breve": "vence em breve", "vencida": "vencida"}


class _PDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", size=8)
        self.set_text_color(90)
        self.cell(0, 6, f"{RODAPE} · página {self.page_no()}/{{nb}}", align="C")


def _br(dia: date | None) -> str:
    return f"{dia:%d/%m/%Y}" if dia else "—"


def _rasas(valor) -> str:
    return f"{valor:.2f}".replace(".", ",")


def gerar_relatorio(sessao, est: Estabelecimento, de: date, ate: date) -> bytes:
    consulta = no_periodo(lotes_com_ciclo(est.id), de, ate)
    linhas = sessao.execute(consulta.order_by(Ciclo.inicio, Lote.codigo)).all()
    soma = totais(sessao, consulta)
    lacunas_periodo = lacunas(sessao, estabelecimento_id=est.id, inicio_entre=regras.intervalo_dias(de, ate),
                              recebido_antes_de=regras.agora() - ESPERA_LACUNA)
    hoje = regras.hoje()

    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_title(f"Oriki — relatório {est.nome}")
    pdf.set_author("Oriki")
    pdf.add_font("DejaVu", "", str(FONTES / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTES / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 15)
    pdf.cell(0, 9, "Oriki — Relatório de branqueamento", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 7, est.nome, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    situacao = SITUACAO_LICENCA[regras.situacao_licenca(est.licenca_validade, hoje)]
    for texto in (
        est.endereco,
        f"Licença Sesma nº {est.licenca_numero} · validade {_br(est.licenca_validade)} ({situacao})",
        f"Curso Casa do Açaí: {_br(est.curso_casa_acai_em)}",
        f"Período: {_br(de)} a {_br(ate)} · gerado em {_br(hoje)} {regras.hora_local(regras.agora())}",
    ):
        pdf.multi_cell(0, 5.5, texto, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 7, "Totais", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    pdf.multi_cell(0, 5.5, (
        f"Ciclos aprovados: {soma['aprovados']} · reprovados: {soma['reprovados']}\n"
        f"Lotes completos: {soma['completos']} · incompletos: {soma['incompletos']} · "
        f"rasas declaradas: {_rasas(soma['rasas'])}"
    ), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 7, "Lotes", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=8.5)
    if linhas:
        with pdf.table(col_widths=(20, 32, 16, 18, 20, 22, 18), text_align="CENTER", line_height=5.5,
                       headings_style=FontFace(emphasis="BOLD", fill_color=(235, 235, 235))) as tabela:
            tabela.row(("Data", "Código", "Início", "Máx. (°C)", "s ≥ 80 °C", "Status", "Completo"))
            for l in linhas:
                tabela.row((
                    _br(regras.data_local(l.inicio)),
                    l.codigo,
                    regras.hora_local(l.inicio),
                    f"{l.temp_max:.1f}".replace(".", ","),
                    str(l.segundos_acima_80),
                    l.status_ciclo.value,
                    "sim" if l.status == StatusLote.COMPLETO else "não",
                ))
    else:
        pdf.cell(0, 6, "Nenhum ciclo no período.", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 7, "Lacunas de contador no período", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    if lacunas_periodo:
        for lacuna in lacunas_periodo:
            pdf.multi_cell(0, 5.5, f"— {lacuna.descricao} (antes de {_br(regras.data_local(lacuna.inicio_seguinte))})",
                           new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, "Nenhuma.", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
