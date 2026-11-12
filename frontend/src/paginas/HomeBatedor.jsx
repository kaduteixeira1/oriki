import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { obterLote, resumo as buscarResumo } from "../api.js";
import { BarraApp, BotaoSair, Carregando, Chip, ChipCiclo } from "../componentes.jsx";
import { useFila } from "../fila.js";
import { dataCurta, horaLocal, motivoReprovado, temperatura } from "../formato.js";

function ChipLicenca({ situacao, validade }) {
  if (situacao === "em_dia") return <Chip tipo="sucesso">Licença em dia</Chip>;
  if (situacao === "vence_em_breve") return <Chip tipo="alerta">Licença vence em {dataCurta(validade)}</Chip>;
  return <Chip tipo="erro">Licença vencida</Chip>;
}

function ItemMenu({ para, titulo, descricao }) {
  return (
    <Link to={para} className="item-menu">
      <span className="item-menu-texto">
        <span className="titulo-card">{titulo}</span>
        <span className="texto-pequeno texto-2">{descricao}</span>
      </span>
      <svg viewBox="0 0 24 24" aria-hidden="true" className="seta">
        <path d="M9 6l6 6-6 6" />
      </svg>
    </Link>
  );
}

// Os ciclos chegam do dispositivo a qualquer hora: com a tela aberta, o resumo é buscado de novo a cada 10 s.
const ATUALIZAR_A_CADA_MS = 10_000;
// Lotes cuja cópia offline já foi pedida nesta sessão (para não repetir a cada atualização).
const lotesGuardados = new Set();

export default function HomeBatedor() {
  const navigate = useNavigate();
  const [dados, setDados] = useState(null);
  const [falhou, setFalhou] = useState(false);
  const [atualizadoEm, setAtualizadoEm] = useState(null);
  const temDados = useRef(false);
  const fila = useFila();
  const [versao, setVersao] = useState(0);
  const tamanhoAnterior = useRef(fila.length);

  // Recarrega quando a internet volta e quando a fila termina de enviar algum lote.
  useEffect(() => {
    const recarregar = () => setVersao((v) => v + 1);
    window.addEventListener("online", recarregar);
    return () => window.removeEventListener("online", recarregar);
  }, []);
  // Atualização automática: só com a aba visível e com internet; ao voltar para a aba, atualiza na hora.
  useEffect(() => {
    const recarregar = () => {
      if (document.visibilityState === "visible" && navigator.onLine) setVersao((v) => v + 1);
    };
    const timer = setInterval(recarregar, ATUALIZAR_A_CADA_MS);
    document.addEventListener("visibilitychange", recarregar);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", recarregar);
    };
  }, []);
  useEffect(() => {
    if (fila.length < tamanhoAnterior.current) setVersao((v) => v + 1);
    tamanhoAnterior.current = fila.length;
  }, [fila.length]);

  // Também remonta ao voltar do formulário, então a lista sempre vem atualizada.
  useEffect(() => {
    buscarResumo()
      .then((resposta) => {
        setDados(resposta);
        setFalhou(false);
        setAtualizadoEm(new Date().toISOString());
        temDados.current = true;
        // Com o Service Worker ativo, cada GET deixa uma cópia: o formulário desses lotes abre sem internet.
        if (navigator.serviceWorker?.controller) {
          resposta.lotes_a_completar.slice(0, 20)
            .filter((lote) => !lotesGuardados.has(lote.codigo))
            .forEach((lote) => {
              lotesGuardados.add(lote.codigo);
              obterLote(lote.codigo).catch(() => lotesGuardados.delete(lote.codigo));
            });
        }
      })
      .catch((erro) => {
        if (erro.status === 401) navigate("/login", { replace: true });
        else if (erro.status === 403) navigate("/", { replace: true });
        else if (!temDados.current) setFalhou(true); // falha numa atualização automática: mantém o que já está na tela
      });
  }, [navigate, versao]);

  return (
    <main className="tela">
      <BarraApp acao={<BotaoSair />} />
      {fila.length > 0 && (
        <p className="faixa-fila" role="status">
          <span className="ponto-fila" aria-hidden="true" />
          {fila.length === 1 ? "1 registro aguardando internet" : `${fila.length} registros aguardando internet`}
        </p>
      )}
      {falhou ? (
        <p className="aviso-centro">Não foi possível carregar o resumo. Verifique a internet e tente de novo.</p>
      ) : !dados ? (
        <Carregando />
      ) : (
        <Conteudo dados={dados} naFila={new Set(fila.map((item) => item.codigo))} atualizadoEm={atualizadoEm} />
      )}
    </main>
  );
}

function Conteudo({ dados, naFila, atualizadoEm }) {
  const { estabelecimento, hoje, ultimo_ciclo: ultimo, lotes_a_completar: lotes } = dados;
  return (
    <div className="conteudo colunas">
      <div className="coluna">
      <section className="card card-ponto">
        <h2 className="titulo-card">{estabelecimento.nome}</h2>
        <ChipLicenca situacao={estabelecimento.licenca_situacao} validade={estabelecimento.licenca_validade} />
      </section>

      <section className="card" aria-labelledby="titulo-hoje">
        <h2 id="titulo-hoje" className="legenda">Hoje, {dataCurta(hoje.data, false)}</h2>
        <div className="kpis">
          <div className="kpi">
            <span className="kpi-numero">{hoje.aprovados}</span>
            <span className="kpi-rotulo">Aprovados</span>
          </div>
          <div className="kpi">
            <span className={`kpi-numero${hoje.reprovados > 0 ? " texto-erro" : ""}`}>{hoje.reprovados}</span>
            <span className="kpi-rotulo">Reprovados</span>
          </div>
        </div>
      </section>

      <section className="card" aria-labelledby="titulo-ultimo">
        <h2 id="titulo-ultimo" className="legenda">Último ciclo</h2>
        {ultimo ? (
          <div className="linha-ciclo">
            <div>
              <p className="codigo">{ultimo.codigo}</p>
              <p className="texto-pequeno texto-2">Início {horaLocal(ultimo.inicio)}</p>
              <p className="texto-pequeno texto-2">
                Máx. {temperatura(ultimo.temp_max)} · {ultimo.segundos_acima_80}&nbsp;s ≥&nbsp;80&nbsp;°C
              </p>
            </div>
            <ChipCiclo status={ultimo.status} />
          </div>
        ) : (
          <p className="texto-2">Nenhum ciclo registrado ainda.</p>
        )}
        {ultimo?.status === "reprovado" && <p className="texto-pequeno texto-erro">{motivoReprovado(ultimo)}</p>}
      </section>

      <h2 className="titulo-secao so-web">Meu ponto</h2>
      <MenuPonto className="so-web" />
      </div>

      <div className="coluna">
      <h2 className="titulo-secao">Lotes a completar</h2>
      {lotes.length === 0 ? (
        <p className="card texto-2">Tudo completo por aqui.</p>
      ) : (
        <ul className="lista-lotes">
          {lotes.map((lote) => (
            <li key={lote.codigo}>
              <Link to={`/batedor/lotes/${encodeURIComponent(lote.codigo)}`}
                    className={`card item-lote${lote.status_ciclo === "reprovado" ? " item-reprovado" : ""}`}>
                <div className="item-lote-texto">
                  <p className="codigo">{lote.codigo}</p>
                  <p className="texto-pequeno texto-2 item-lote-detalhe">
                    {horaLocal(lote.inicio)} <ChipCiclo status={lote.status_ciclo} />
                    {naFila.has(lote.codigo) && <Chip tipo="alerta">No celular</Chip>}
                  </p>
                </div>
                <span className="botao-secundario" aria-hidden="true">Completar</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {dados.total_a_completar > lotes.length && (
        <p className="texto-pequeno texto-2">
          Mostrando os {lotes.length} mais recentes de {dados.total_a_completar}.
        </p>
      )}

      <h2 className="titulo-secao so-mobile">Meu ponto</h2>
      <MenuPonto className="so-mobile" />
      {atualizadoEm && (
        <p className="texto-pequeno texto-2 centro-texto" aria-live="off">
          Atualiza sozinho a cada 10 s · última às {horaLocal(atualizadoEm)}
        </p>
      )}
      </div>
    </div>
  );
}

function MenuPonto({ className }) {
  return (
    <nav className={`card menu ${className}`} aria-label="Meu ponto">
      <ItemMenu para="/batedor/historico" titulo="Histórico de lotes" descricao="Lotes por período, completos ou não" />
      <ItemMenu para="/batedor/relatorio" titulo="Relatório para vistoria" descricao="PDF do período, para a Sesma" />
      <ItemMenu para="/batedor/qr" titulo="QR do ponto" descricao="Para imprimir e colar na vitrine" />
    </nav>
  );
}
