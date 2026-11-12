import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { baixarRelatorio } from "../api.js";
import { salvarNoAparelho } from "../arquivo.js";
import { BarraApp } from "../componentes.jsx";
import { diasNoPeriodo, hojeEmBelem, somarDias } from "../formato.js";

const MAXIMO_DIAS = 92;

function mensagemDeErro(erro) {
  if (erro.erro === "periodo_muito_longo") return `Escolha no máximo ${MAXIMO_DIAS} dias.`;
  if (erro.erro === "periodo_invalido") return "A data inicial precisa ser antes da final.";
  if (erro instanceof TypeError) return "Sem internet. O relatório é gerado no servidor; tente quando a conexão voltar.";
  return "Não foi possível gerar o relatório. Tente de novo.";
}

export default function Relatorio() {
  const navigate = useNavigate();
  const hoje = hojeEmBelem();
  const [de, setDe] = useState(somarDias(hoje, -29));
  const [ate, setAte] = useState(hoje);
  const [gerando, setGerando] = useState(false);
  const [mensagem, setMensagem] = useState(null); // { tipo: "erro" | "sucesso", texto }

  const problema = !de || !ate ? "Escolha as duas datas."
    : de > ate ? "A data inicial precisa ser antes da final."
    : diasNoPeriodo(de, ate) > MAXIMO_DIAS ? `Escolha no máximo ${MAXIMO_DIAS} dias.` : "";

  // A mensagem do último download não vale mais para um período novo.
  function mudar(definir, valor) {
    definir(valor);
    setMensagem(null);
  }

  async function gerar(evento) {
    evento.preventDefault();
    setMensagem(null);
    setGerando(true);
    try {
      const { blob, nome } = await baixarRelatorio(de, ate);
      salvarNoAparelho(blob, nome || `relatorio-${de}-a-${ate}.pdf`);
      setMensagem({ tipo: "sucesso", texto: "Relatório baixado. Procure na pasta de downloads." });
    } catch (erro) {
      if (erro.status === 401) return navigate("/login", { replace: true });
      setMensagem({ tipo: "erro", texto: mensagemDeErro(erro) });
    } finally {
      setGerando(false);
    }
  }

  return (
    <main className="tela">
      <BarraApp titulo="Relatório para vistoria" voltarPara="/batedor" />
      <form className="conteudo formulario" onSubmit={gerar} noValidate>
        <section className="card">
          <p>
            PDF com todos os ciclos e lotes do período, com os totais. Leve na vistoria da Sesma ou na renovação da
            licença.
          </p>
          <p className="texto-pequeno texto-2">Até {MAXIMO_DIAS} dias por relatório.</p>
        </section>
        <div className="linha-datas">
          <label className="campo">
            <span className="rotulo">De</span>
            <input type="date" value={de} max={hoje} onChange={(e) => mudar(setDe, e.target.value)} />
          </label>
          <label className="campo">
            <span className="rotulo">Até</span>
            <input type="date" value={ate} max={hoje} onChange={(e) => mudar(setAte, e.target.value)} />
          </label>
        </div>
        {(problema || mensagem) && (
          <p className={!problema && mensagem.tipo === "sucesso" ? "sucesso-formulario" : "erro-formulario"}
             role={problema || mensagem.tipo === "erro" ? "alert" : "status"}>
            {problema || mensagem.texto}
          </p>
        )}
        <button type="submit" className="botao-principal" disabled={gerando || !!problema}>
          {gerando ? "Gerando…" : "Baixar PDF"}
        </button>
      </form>
    </main>
  );
}
