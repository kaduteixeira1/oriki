import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { listarLotes } from "../api.js";
import { BarraApp, Carregando, ChipCiclo } from "../componentes.jsx";
import { dataCurta, diaMesLocal, diasNoPeriodo, hojeEmBelem, horaLocal, motivoReprovado, somarDias } from "../formato.js";

const MAXIMO_DIAS = 92;
const FILTROS = [
  ["", "Todos"],
  ["incompleto", "A completar"],
  ["completo", "Completos"],
];

function problemaNoPeriodo(de, ate) {
  if (!de || !ate) return "Escolha as duas datas.";
  if (de > ate) return "A data inicial precisa ser antes da final.";
  if (diasNoPeriodo(de, ate) > MAXIMO_DIAS) return `Escolha no máximo ${MAXIMO_DIAS} dias.`;
  return "";
}

export default function Historico() {
  const navigate = useNavigate();
  const location = useLocation();
  const [parametros, setParametros] = useSearchParams();
  const hoje = hojeEmBelem();
  const de = parametros.get("de") || somarDias(hoje, -29);
  const ate = parametros.get("ate") || hoje;
  const status = parametros.get("status") || "";
  const pagina = Number(parametros.get("pagina")) || 1;
  const problema = problemaNoPeriodo(de, ate);

  const [resultado, setResultado] = useState(null); // { chave, dados } ou { chave, erro }
  const chave = `${de}|${ate}|${status}|${pagina}`;

  useEffect(() => {
    if (problema) return;
    let ativo = true;
    listarLotes({ de, ate, status, pagina })
      .then((dados) => ativo && setResultado({ chave, dados }))
      .catch((erro) => {
        if (!ativo) return;
        if (erro.status === 401) return navigate("/login", { replace: true });
        if (erro.status === 403) return navigate("/", { replace: true });
        setResultado({ chave, erro: "Não foi possível carregar o histórico. Verifique a internet e tente de novo." });
      });
    return () => {
      ativo = false;
    };
  }, [de, ate, status, pagina, chave, problema, navigate]);

  function mudar(nome, valor) {
    const novos = new URLSearchParams(parametros);
    novos.set("de", de);
    novos.set("ate", ate);
    if (valor) novos.set(nome, valor);
    else novos.delete(nome);
    if (nome !== "pagina") novos.delete("pagina");
    setParametros(novos, { replace: true });
  }

  const atual = resultado?.chave === chave ? resultado : null;
  const voltar = `${location.pathname}${location.search}`;

  return (
    <main className="tela">
      <BarraApp titulo="Histórico de lotes" voltarPara="/batedor" />
      <div className="conteudo colunas colunas-filtro">
        <div className="coluna coluna-fixa">
        <section className="card filtros" aria-label="Filtros">
          <div className="linha-datas">
            <label className="campo">
              <span className="rotulo">De</span>
              <input type="date" value={de} max={hoje} onChange={(e) => mudar("de", e.target.value)} />
            </label>
            <label className="campo">
              <span className="rotulo">Até</span>
              <input type="date" value={ate} max={hoje} onChange={(e) => mudar("ate", e.target.value)} />
            </label>
          </div>
          <div className="segmentos" role="group" aria-label="Situação do lote">
            {FILTROS.map(([valor, rotulo]) => (
              <button key={valor || "todos"} type="button" aria-pressed={status === valor}
                      className={`segmento${status === valor ? " ativo" : ""}`} onClick={() => mudar("status", valor)}>
                {rotulo}
              </button>
            ))}
          </div>
        </section>
        </div>

        <div className="coluna">
        {problema ? (
          <p className="erro-formulario" role="alert">{problema}</p>
        ) : !atual ? (
          <Carregando />
        ) : atual.erro ? (
          <p className="aviso-centro">{atual.erro}</p>
        ) : (
          <Lista dados={atual.dados} voltar={voltar} aoMudarPagina={(nova) => mudar("pagina", String(nova))} />
        )}
        </div>
      </div>
    </main>
  );
}

function Lista({ dados, voltar, aoMudarPagina }) {
  const paginas = Math.max(1, Math.ceil(dados.total / dados.por_pagina));
  if (dados.total === 0) return <p className="card texto-2">Nenhum lote neste período.</p>;
  return (
    <>
      <p className="texto-pequeno texto-2" role="status">
        {dados.total} {dados.total === 1 ? "lote" : "lotes"} de {dataCurta(dados.de)} a {dataCurta(dados.ate)}
      </p>
      <ul className="lista-lotes">
        {dados.itens.map((lote) => (
          <li key={lote.codigo}>
            <ItemHistorico lote={lote} voltar={voltar} />
          </li>
        ))}
      </ul>
      {paginas > 1 && (
        <nav className="paginacao" aria-label="Páginas">
          <button type="button" className="botao-secundario" disabled={dados.pagina <= 1}
                  onClick={() => aoMudarPagina(dados.pagina - 1)}>
            Mais recentes
          </button>
          <span className="texto-pequeno texto-2">Página {dados.pagina} de {paginas}</span>
          <button type="button" className="botao-secundario" disabled={dados.pagina >= paginas}
                  onClick={() => aoMudarPagina(dados.pagina + 1)}>
            Mais antigos
          </button>
        </nav>
      )}
    </>
  );
}

function ItemHistorico({ lote, voltar }) {
  const { ciclo } = lote;
  const detalhe = lote.status === "completo"
    ? [lote.origem_fruto, `${lote.quantidade_rasas.toLocaleString("pt-BR")} rasas`].join(" · ")
    : "A completar";
  return (
    <Link to={`/batedor/lotes/${encodeURIComponent(lote.codigo)}`} state={{ voltar }}
          className={`card item-historico${ciclo.status === "reprovado" ? " item-reprovado" : ""}`}>
      <div className="linha-ciclo">
        <p className="codigo">{lote.codigo}</p>
        <ChipCiclo status={ciclo.status} />
      </div>
      <p className="texto-pequeno texto-2">
        {diaMesLocal(ciclo.inicio)} · {horaLocal(ciclo.inicio)}
      </p>
      {ciclo.status === "reprovado" && <p className="texto-pequeno texto-erro">{motivoReprovado(ciclo)}</p>}
      <p className={`texto-pequeno${lote.status === "completo" ? "" : " texto-alerta"}`}>{detalhe}</p>
    </Link>
  );
}
