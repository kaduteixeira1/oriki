import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { obterLote } from "../api.js";
import { BarraApp, Carregando, ChipCiclo } from "../componentes.jsx";
import { itemDaFila, salvarComFila, semConexao } from "../fila.js";
import { dataLocal, horaLocal, motivoReprovado, temperatura } from "../formato.js";

const CHECKLIST = [
  ["catacao", "Catação"],
  ["sanitizacao", "Sanitização"],
  ["resfriamento", "Resfriamento"],
];

const MENSAGENS_CAMPO = {
  texto_muito_longo: "Use no máximo 150 caracteres.",
  valor_fora_do_limite: "Informe de 0,01 a 9.999,99 rasas.",
};

// Serve para o lote vindo da API e para a versão guardada na fila do celular.
function camposDoLote(lote) {
  return {
    origem_fruto: lote.origem_fruto ?? "",
    quantidade_rasas: lote.quantidade_rasas ?? "",
    catacao: lote.catacao,
    sanitizacao: lote.sanitizacao,
    resfriamento: lote.resfriamento,
  };
}

// Mesmas regras do servidor: sem internet, o servidor só confere quando a fila for enviada.
function validar(campos) {
  if (campos.quantidade_rasas === "") return {};
  const quantidade = Number(campos.quantidade_rasas);
  if (Number.isNaN(quantidade)) return { quantidade_rasas: "Informe um número." };
  if (quantidade < 0.01 || quantidade > 9999.99) return { quantidade_rasas: MENSAGENS_CAMPO.valor_fora_do_limite };
  return {};
}

export default function FormularioLote() {
  const { codigo } = useParams();
  const navigate = useNavigate();
  // Volta para onde veio (Home ou histórico com os filtros).
  const voltar = useLocation().state?.voltar || "/batedor";
  const [lote, setLote] = useState(null);
  const [campos, setCampos] = useState(null);
  const [errosCampo, setErrosCampo] = useState({});
  const [mensagem, setMensagem] = useState(null); // { tipo: "erro" | "sucesso", texto }
  const [enviando, setEnviando] = useState(false);
  const [naFila, setNaFila] = useState(false);
  const volta = useRef(null);

  useEffect(() => {
    Promise.all([obterLote(codigo), itemDaFila(codigo).catch(() => null)])
      .then(([dados, guardado]) => {
        setLote(dados);
        // Uma alteração ainda não enviada é mais nova que o que o servidor tem.
        setCampos(camposDoLote(guardado ? guardado.campos : dados));
        setNaFila(!!guardado);
      })
      .catch((erro) => {
        if (erro.status === 401) navigate("/login", { replace: true });
        else if (erro.status === 403) navigate("/", { replace: true });
        else if (erro.status === 404) setMensagem({ tipo: "erro", texto: "Lote não encontrado." });
        else if (semConexao(erro)) {
          setMensagem({ tipo: "erro", texto: "Sem internet, e este lote ainda não foi aberto neste celular." });
        } else setMensagem({ tipo: "erro", texto: "Não foi possível carregar o lote." });
      });
    return () => clearTimeout(volta.current);
  }, [codigo, navigate]);

  function alterar(nome, valor) {
    setCampos((atuais) => ({ ...atuais, [nome]: valor }));
    setErrosCampo((atuais) => ({ ...atuais, [nome]: undefined }));
  }

  async function salvar(evento) {
    evento.preventDefault();
    setMensagem(null);
    const erros = validar(campos);
    setErrosCampo(erros);
    if (Object.keys(erros).length) return;
    const quantidade = campos.quantidade_rasas === "" ? null : Number(campos.quantidade_rasas);
    setEnviando(true);
    try {
      // Envia todos os campos: o PATCH é idempotente e o servidor recalcula o status do lote.
      const resultado = await salvarComFila(codigo, { ...campos, quantidade_rasas: quantidade });
      if (resultado.enfileirado) {
        setNaFila(true);
        setMensagem({ tipo: "sucesso", texto: "Salvo no celular. Será enviado quando a internet voltar." });
        volta.current = setTimeout(() => navigate(voltar), 1500);
      } else {
        setLote(resultado.lote);
        setNaFila(false);
        setMensagem({ tipo: "sucesso", texto: "Lote salvo." });
        volta.current = setTimeout(() => navigate(voltar), 800);
      }
    } catch (erro) {
      setEnviando(false);
      if (erro.status === 401) return navigate("/login", { replace: true });
      if (erro.status === 404) return setMensagem({ tipo: "erro", texto: "Lote não encontrado." });
      const campo = erro.detalhes?.campo;
      if ((erro.status === 400 || erro.status === 422) && campo) {
        return setErrosCampo({ [campo]: MENSAGENS_CAMPO[erro.erro] || "Valor inválido." });
      }
      setMensagem({ tipo: "erro", texto: "Não foi possível salvar. Tente de novo." });
    }
  }

  return (
    <main className="tela">
      <BarraApp titulo={`Lote ${codigo}`} voltarPara={voltar} />
      {!lote ? (
        mensagem ? (
          <div className="conteudo">
            <p className="aviso-centro">{mensagem.texto}</p>
            <Link to={voltar} className="botao-secundario centro">Voltar</Link>
          </div>
        ) : (
          <Carregando />
        )
      ) : (
        <form className="conteudo formulario colunas" onSubmit={salvar} noValidate>
          <div className="coluna">
          <ResumoCiclo ciclo={lote.ciclo} />
          {naFila && !mensagem && (
            <p className="aviso-fila" role="status">
              Há uma alteração deste lote salva no celular, esperando internet para ser enviada.
            </p>
          )}
          </div>

          <div className="coluna formulario">
          <label className="campo">
            <span className="rotulo">Origem do fruto</span>
            <input type="text" maxLength={150} placeholder="Ex.: Ilha do Combu" value={campos.origem_fruto}
                   aria-invalid={!!errosCampo.origem_fruto} aria-describedby="erro-origem"
                   onChange={(e) => alterar("origem_fruto", e.target.value)} />
            {errosCampo.origem_fruto && <span id="erro-origem" className="erro-campo">{errosCampo.origem_fruto}</span>}
          </label>

          <label className="campo">
            <span className="rotulo">Quantidade (rasas)</span>
            <span className="entrada-com-sufixo">
              <input type="number" step="0.5" min="0.01" inputMode="decimal" value={campos.quantidade_rasas}
                     aria-invalid={!!errosCampo.quantidade_rasas} aria-describedby="erro-quantidade"
                     onChange={(e) => alterar("quantidade_rasas", e.target.value)} />
              <span className="sufixo" aria-hidden="true">rasas</span>
            </span>
            {errosCampo.quantidade_rasas && (
              <span id="erro-quantidade" className="erro-campo">{errosCampo.quantidade_rasas}</span>
            )}
          </label>

          <fieldset className="grupo-checklist">
            <legend className="rotulo">Etapas do processo</legend>
            <div className="card checklist">
              {CHECKLIST.map(([nome, rotulo]) => (
                <label key={nome} className="item-checklist">
                  <input type="checkbox" checked={campos[nome]} onChange={(e) => alterar(nome, e.target.checked)} />
                  <span>{rotulo}</span>
                  {errosCampo[nome] && <span className="erro-campo">{errosCampo[nome]}</span>}
                </label>
              ))}
            </div>
          </fieldset>

          {mensagem && (
            <p className={mensagem.tipo === "sucesso" ? "sucesso-formulario" : "erro-formulario"} role="status">
              {mensagem.texto}
            </p>
          )}
          <button type="submit" className="botao-principal" disabled={enviando}>
            {enviando ? "Salvando…" : "Salvar"}
          </button>
          </div>
        </form>
      )}
    </main>
  );
}

function ResumoCiclo({ ciclo }) {
  return (
    <section className={`card${ciclo.status === "reprovado" ? " item-reprovado" : ""}`} aria-label="Ciclo de branqueamento">
      <div className="linha-ciclo">
        <p className="legenda">{dataLocal(ciclo.inicio)}</p>
        <ChipCiclo status={ciclo.status} />
      </div>
      <p className="texto-2">Início {horaLocal(ciclo.inicio)} · Fim {horaLocal(ciclo.fim)}</p>
      <p className="texto-2">Mín. {temperatura(ciclo.temp_min)} · Máx. {temperatura(ciclo.temp_max)}</p>
      <p className="texto-pequeno texto-2">{ciclo.segundos_acima_80} segundos ≥&nbsp;80&nbsp;°C</p>
      {ciclo.status === "reprovado" && (
        <p className="aviso-erro">
          Este lote não passou no branqueamento. {motivoReprovado(ciclo)}
        </p>
      )}
      {ciclo.relogio_divergente && (
        <p className="aviso-alerta">Relógio do dispositivo estava fora de hora neste registro.</p>
      )}
    </section>
  );
}
