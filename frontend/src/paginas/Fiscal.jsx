// OR-29: painel do fiscal — alertas de todos os pontos e a lista de pontos, com busca.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { alertasFiscal, pontosFiscal } from "../api.js";
import { ALERTAS, ORDEM_ALERTAS as ORDEM } from "../alertas.js";
import { BarraApp, BotaoSair, Carregando, Chip, ChipAlerta, ChipLicencaCurta as ChipLicenca } from "../componentes.jsx";
import { dataCurta, dataLocal, horaLocal } from "../formato.js";

function quando(iso) {
  return iso ? `${dataLocal(iso)} ${horaLocal(iso)}` : "nunca";
}

export default function Fiscal() {
  const navigate = useNavigate();
  const usuario = useOutletContext();
  const [alertas, setAlertas] = useState(null);
  const [pontos, setPontos] = useState(null);
  const [busca, setBusca] = useState("");
  const [falhou, setFalhou] = useState(false);
  const [filtroTipo, setFiltroTipo] = useState("");

  useEffect(() => {
    alertasFiscal().then(setAlertas).catch(tratar);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const espera = setTimeout(() => pontosFiscal(busca.trim()).then(setPontos).catch(tratar), busca ? 250 : 0);
    return () => clearTimeout(espera);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  function tratar(erro) {
    if (erro.status === 401) navigate("/login", { replace: true });
    else if (erro.status === 403) navigate("/", { replace: true });
    else setFalhou(true);
  }

  const contagem = useMemo(() => {
    const c = {};
    (alertas || []).forEach((a) => (c[a.tipo] = (c[a.tipo] || 0) + 1));
    return c;
  }, [alertas]);

  const porPonto = useMemo(() => {
    const grupos = new Map();
    (alertas || []).filter((a) => !filtroTipo || a.tipo === filtroTipo).forEach((a) => {
      const g = grupos.get(a.estabelecimento.id) || { ponto: a.estabelecimento, itens: [] };
      g.itens.push(a);
      grupos.set(a.estabelecimento.id, g);
    });
    return [...grupos.values()].map((g) => ({
      ...g, itens: g.itens.sort((x, y) => ORDEM.indexOf(x.tipo) - ORDEM.indexOf(y.tipo)),
    }));
  }, [alertas, filtroTipo]);

  return (
    <main className="tela tela-larga">
      <BarraApp titulo="Painel do fiscal" acao={<BotaoSair />} />
      {falhou ? (
        <p className="aviso-centro">Não foi possível carregar o painel. Verifique a internet e tente de novo.</p>
      ) : (
        <div className="conteudo colunas">
          <div className="coluna">
            <p className="texto-pequeno texto-2">Olá, {usuario.nome}. Alertas de todos os pontos, do mais grave para o menos.</p>
            <section className="card" aria-labelledby="titulo-alertas">
              <h2 id="titulo-alertas" className="titulo-card">Alertas {alertas && `(${alertas.length})`}</h2>
              {alertas && alertas.length > 0 && (
                <div className="filtro-chips" role="group" aria-label="Filtrar por tipo">
                  <button type="button" className={`chip-filtro${!filtroTipo ? " ativo" : ""}`} onClick={() => setFiltroTipo("")}>
                    Todos
                  </button>
                  {ORDEM.filter((t) => contagem[t]).map((t) => (
                    <button key={t} type="button" className={`chip-filtro${filtroTipo === t ? " ativo" : ""}`}
                            aria-pressed={filtroTipo === t} onClick={() => setFiltroTipo(filtroTipo === t ? "" : t)}>
                      {ALERTAS[t].rotulo} · {contagem[t]}
                    </button>
                  ))}
                </div>
              )}
            </section>
            {!alertas ? (
              <Carregando />
            ) : porPonto.length === 0 ? (
              <p className="card texto-2">Nenhum alerta. Todos os pontos estão em dia.</p>
            ) : (
              <ul className="lista-lotes">
                {porPonto.map(({ ponto, itens }) => (
                  <li key={ponto.id}>
                    <Link to={`/fiscal/pontos/${ponto.id}`}
                          className={`card item-alerta${itens.some((a) => ALERTAS[a.tipo]?.tipo === "erro") ? " item-reprovado" : " item-atencao"}`}>
                      <p className="titulo-card">{ponto.nome}</p>
                      <ul className="alertas-do-ponto">
                        {itens.map((a) => (
                          <li key={a.tipo + a.detalhe}>
                            <ChipAlerta tipo={a.tipo} />
                            <span className="texto-pequeno">{a.detalhe}</span>
                            {a.desde && <span className="texto-pequeno texto-2">desde {dataCurta(a.desde)}</span>}
                          </li>
                        ))}
                      </ul>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="coluna">
            <section className="card filtros" aria-label="Pontos">
              <h2 className="titulo-card">Pontos de venda {pontos && `(${pontos.length})`}</h2>
              <label className="campo">
                <span className="rotulo">Buscar pelo nome</span>
                <input type="search" value={busca} maxLength={100} placeholder="Ex.: Dona Rosa"
                       onChange={(e) => setBusca(e.target.value)} />
              </label>
            </section>
            {!pontos ? (
              <Carregando />
            ) : pontos.length === 0 ? (
              <p className="card texto-2">Nenhum ponto encontrado.</p>
            ) : (
              <ul className="lista-lotes">
                {pontos.map((p) => (
                  <li key={p.id}>
                    <Link to={`/fiscal/pontos/${p.id}`} className="card item-historico">
                      <div className="linha-ciclo">
                        <p className="titulo-card">{p.nome}</p>
                        {p.alertas > 0 ? <Chip tipo="erro">{p.alertas} alerta(s)</Chip> : <Chip tipo="sucesso">Sem alertas</Chip>}
                      </div>
                      <p className="texto-pequeno texto-2">{p.endereco}</p>
                      <div className="item-lote-detalhe">
                        <ChipLicenca situacao={p.licenca_situacao} validade={p.licenca_validade} />
                      </div>
                      <p className="texto-pequeno texto-2">
                        Último ciclo: {quando(p.ultimo_ciclo)} · Dispositivo: {p.ultimo_contato ? `contato ${quando(p.ultimo_contato)}` : "sem dispositivo ou sem contato"}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
