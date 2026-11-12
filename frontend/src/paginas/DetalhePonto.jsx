// OR-29/31/32: histórico de um ponto para o fiscal — dispositivos, alertas do período, ciclos × rasas,
// lacunas de contador, recusas da API, acessos do QR e vistorias (com o registro de uma nova).
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { detalhePonto, registrarVistoria } from "../api.js";
import { BarraApp, BotaoSair, Carregando, Chip, ChipCiclo, ChipLicencaCurta as ChipLicenca } from "../componentes.jsx";
import { dataCurta, dataLocal, diasNoPeriodo, hojeEmBelem, horaLocal, somarDias, temperatura } from "../formato.js";

const MOTIVOS = {
  assinatura_invalida: "assinatura não confere (registro alterado)",
  conflito: "código já recebido com outro conteúdo",
  codigo_invalido: "código fora do padrão",
  formato_invalido: "dado fora do formato",
  status_inconsistente: "aprovado com menos de 10 s",
};
const RESULTADOS = ["regular", "regular com ressalvas", "irregular", "interditado"];
const SEM_CONTATO_MS = 2 * 86_400_000;

function quando(iso) {
  return iso ? `${dataLocal(iso)} ${horaLocal(iso)}` : "nunca";
}

export default function DetalhePonto() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [parametros, setParametros] = useSearchParams();
  const hoje = hojeEmBelem();
  const de = parametros.get("de") || somarDias(hoje, -29);
  const ate = parametros.get("ate") || hoje;
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(() => {
    if (de > ate) return setErro("A data inicial precisa ser antes da final.");
    if (diasNoPeriodo(de, ate) > 92) return setErro("Escolha no máximo 92 dias.");
    setErro("");
    detalhePonto(id, { de, ate })
      .then(setDados)
      .catch((falha) => {
        if (falha.status === 401) navigate("/login", { replace: true });
        else if (falha.status === 404) setErro("Ponto não encontrado.");
        else setErro("Não foi possível carregar o ponto. Tente de novo.");
      });
  }, [id, de, ate, navigate]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function mudar(nome, valor) {
    const novos = new URLSearchParams(parametros);
    novos.set("de", de);
    novos.set("ate", ate);
    novos.set(nome, valor);
    setParametros(novos, { replace: true });
  }

  return (
    <main className="tela tela-larga">
      <BarraApp titulo={dados?.estabelecimento.nome || "Ponto"} voltarPara="/fiscal" acao={<BotaoSair />} />
      <div className="conteudo">
        <section className="card filtros" aria-label="Período">
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
        </section>
        {erro ? <p className="erro-formulario" role="alert">{erro}</p> : !dados ? <Carregando /> : (
          <Conteudo dados={dados} aoRegistrar={carregar} />
        )}
      </div>
    </main>
  );
}

function Conteudo({ dados, aoRegistrar }) {
  const { estabelecimento: est, dispositivos, por_dia: porDia, lotes, vistorias, lacunas, recusas = [],
    acessos_qr: acessos } = dados;
  const ciclos = porDia.reduce((s, d) => s + d.ciclos, 0);
  const reprovados = porDia.reduce((s, d) => s + d.reprovados, 0);
  const rasas = porDia.reduce((s, d) => s + d.rasas_declaradas, 0);
  const comCiclos = porDia.filter((d) => d.ciclos > 0);

  return (
    <div className="colunas">
      <div className="coluna">
        <section className="card card-ponto">
          <h2 className="titulo-card">{est.nome}</h2>
          <p className="texto-pequeno texto-2">{est.endereco}</p>
          <ChipLicenca situacao={est.licenca_situacao} validade={est.licenca_validade} />
          <dl className="lista-dados">
            <div><dt className="legenda">Licença</dt><dd>nº {est.licenca_numero}, válida até {dataCurta(est.licenca_validade)}</dd></div>
            <div><dt className="legenda">Curso da Casa do Açaí</dt>
              <dd>{est.curso_casa_acai_em ? dataCurta(est.curso_casa_acai_em) : "não informado"}</dd></div>
          </dl>
          <a className="botao-secundario" href={`/p/${est.slug_qr}`} target="_blank" rel="noreferrer">Ver a página do QR</a>
        </section>

        <section className="card" aria-labelledby="titulo-periodo">
          <h2 id="titulo-periodo" className="legenda">{dataCurta(dados.periodo.de)} a {dataCurta(dados.periodo.ate)}</h2>
          <div className="kpis kpis-3">
            <div className="kpi"><span className="kpi-numero">{ciclos}</span><span className="kpi-rotulo">ciclos</span></div>
            <div className="kpi">
              <span className={`kpi-numero${reprovados ? " texto-erro" : ""}`}>{reprovados}</span>
              <span className="kpi-rotulo">reprovados</span>
            </div>
            <div className="kpi"><span className="kpi-numero">{rasas.toLocaleString("pt-BR")}</span><span className="kpi-rotulo">rasas declaradas</span></div>
          </div>
          <p className="texto-pequeno texto-2">
            Escaneamentos do QR no período: <b>{acessos?.total ?? 0}</b>
          </p>
        </section>

        <section className="card" aria-labelledby="titulo-dispositivos">
          <h2 id="titulo-dispositivos" className="titulo-card">Dispositivos</h2>
          {dispositivos.length === 0 ? <p className="texto-2">Nenhum dispositivo neste ponto.</p> : (
            <ul className="lista-simples">
              {dispositivos.map((d) => {
                const semContato = !d.ultimo_contato || Date.now() - Date.parse(d.ultimo_contato) > SEM_CONTATO_MS;
                return (
                  <li key={d.identificador} className="linha-ciclo">
                    <span className="codigo">{d.identificador}</span>
                    <span className="texto-pequeno texto-2">último contato {quando(d.ultimo_contato)}</span>
                    {semContato ? <Chip tipo="alerta">Sem contato</Chip> : <Chip tipo="sucesso">Comunicando</Chip>}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className={`card${lacunas.length || recusas.length ? " item-reprovado" : ""}`} aria-labelledby="titulo-integridade">
          <h2 id="titulo-integridade" className="titulo-card">Integridade dos registros</h2>
          {lacunas.length === 0 && recusas.length === 0 && (
            <p className="texto-pequeno texto-2">Sem lacunas de contador e sem envios recusados no período.</p>
          )}
          {lacunas.length > 0 && (
            <>
              <p className="rotulo">Registros faltando (lacuna de contador)</p>
              <ul className="lista-simples">{lacunas.map((l) => <li key={l} className="texto-pequeno texto-erro">{l}</li>)}</ul>
              <p className="texto-pequeno texto-2">Pode ser um ciclo apagado do dispositivo ou ainda na fila sem internet.</p>
            </>
          )}
          {recusas.length > 0 && (
            <>
              <p className="rotulo">Recusados pela API ({recusas.length})</p>
              <ul className="lista-simples">
                {recusas.slice(0, 20).map((r, i) => (
                  <li key={i} className="texto-pequeno">
                    <b>{r.codigo || "sem código"}</b> · {MOTIVOS[r.motivo] || r.motivo}
                    <span className="texto-2"> · {quando(r.quando)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <Vistorias pontoId={est.id} vistorias={vistorias} aoRegistrar={aoRegistrar} />
      </div>

      <div className="coluna">
        <section className="card" aria-labelledby="titulo-por-dia">
          <h2 id="titulo-por-dia" className="titulo-card">Ciclos × rasas por dia</h2>
          <p className="texto-pequeno texto-2">Muitos ciclos com pouca rasa declarada pode indicar ciclo “de fachada”.</p>
          {comCiclos.length === 0 ? <p className="texto-2">Nenhum ciclo no período.</p> : (
            <div className="tabela-rolavel">
              <table className="tabela">
                <thead><tr><th>Dia</th><th>Ciclos</th><th>Aprov.</th><th>Reprov.</th><th>Completos</th><th>Rasas</th></tr></thead>
                <tbody>
                  {comCiclos.map((d) => (
                    <tr key={d.data} className={d.reprovados ? "linha-reprovada" : ""}>
                      <td>{dataCurta(d.data, false)}</td><td>{d.ciclos}</td><td>{d.aprovados}</td>
                      <td className={d.reprovados ? "texto-erro" : ""}>{d.reprovados}</td>
                      <td>{d.lotes_completos}</td><td>{d.rasas_declaradas.toLocaleString("pt-BR")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card" aria-labelledby="titulo-lotes">
          <h2 id="titulo-lotes" className="titulo-card">Lotes ({lotes.length})</h2>
          {lotes.length === 0 ? <p className="texto-2">Nenhum lote no período.</p> : (
            <div className="tabela-rolavel">
              <table className="tabela">
                <thead><tr><th>Lote</th><th>Início</th><th>Máx.</th><th>s ≥ 80</th><th>Ciclo</th><th>Lote</th></tr></thead>
                <tbody>
                  {lotes.slice(0, 200).map((l) => (
                    <tr key={l.codigo} className={l.ciclo.status === "reprovado" ? "linha-reprovada" : ""}>
                      <td className="codigo-tabela">{l.codigo}{l.ciclo.relogio_divergente && <span title="relógio fora de hora"> ⏱</span>}</td>
                      <td>{dataLocal(l.ciclo.inicio).slice(0, 5)} {horaLocal(l.ciclo.inicio)}</td>
                      <td>{temperatura(l.ciclo.temp_max)}</td>
                      <td>{l.ciclo.segundos_acima_80}</td>
                      <td><ChipCiclo status={l.ciclo.status} /></td>
                      <td>{l.status === "completo" ? `${l.quantidade_rasas.toLocaleString("pt-BR")} rasas` : <span className="texto-alerta">a completar</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {lotes.length > 200 && <p className="texto-pequeno texto-2">Mostrando os 200 mais recentes.</p>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Vistorias({ pontoId, vistorias, aoRegistrar }) {
  const hoje = hojeEmBelem();
  const [campos, setCampos] = useState({ data: hoje, resultado: RESULTADOS[0], observacoes: "" });
  const [enviando, setEnviando] = useState(false);
  const [mensagem, setMensagem] = useState(null);

  async function enviar(evento) {
    evento.preventDefault();
    setEnviando(true);
    setMensagem(null);
    try {
      await registrarVistoria(pontoId, { ...campos, observacoes: campos.observacoes.trim() || null });
      setMensagem({ tipo: "sucesso", texto: "Vistoria registrada. Ela aparece na página do QR." });
      setCampos({ ...campos, observacoes: "" });
      aoRegistrar();
    } catch (erro) {
      setMensagem({ tipo: "erro", texto: erro.erro === "data_futura" ? "A data não pode ser no futuro."
        : "Não foi possível registrar. Tente de novo." });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="card" aria-labelledby="titulo-vistorias">
      <h2 id="titulo-vistorias" className="titulo-card">Vistorias</h2>
      {vistorias.length === 0 ? <p className="texto-pequeno texto-2">Nenhuma vistoria registrada no Oriki.</p> : (
        <ul className="lista-simples">
          {vistorias.slice(0, 10).map((v) => (
            <li key={v.id} className="texto-pequeno">
              <b>{dataCurta(v.data)}</b> · {v.resultado} <span className="texto-2">· {v.fiscal.nome}</span>
              {v.observacoes && <p className="texto-2">{v.observacoes}</p>}
            </li>
          ))}
        </ul>
      )}
      <form className="formulario formulario-vistoria" onSubmit={enviar}>
        <p className="rotulo">Registrar vistoria</p>
        <div className="linha-datas">
          <label className="campo">
            <span className="rotulo">Data</span>
            <input type="date" required value={campos.data} max={hoje} onChange={(e) => setCampos({ ...campos, data: e.target.value })} />
          </label>
          <label className="campo">
            <span className="rotulo">Resultado</span>
            <select value={campos.resultado} onChange={(e) => setCampos({ ...campos, resultado: e.target.value })}>
              {RESULTADOS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
        </div>
        <label className="campo">
          <span className="rotulo">Observações</span>
          <textarea rows={3} maxLength={2000} value={campos.observacoes} placeholder="Ex.: tanque e haste em ordem."
                    onChange={(e) => setCampos({ ...campos, observacoes: e.target.value })} />
        </label>
        {mensagem && <p className={mensagem.tipo === "sucesso" ? "sucesso-formulario" : "erro-formulario"} role="status">{mensagem.texto}</p>}
        <button type="submit" className="botao-principal" disabled={enviando}>{enviando ? "Registrando…" : "Registrar vistoria"}</button>
      </form>
    </section>
  );
}
