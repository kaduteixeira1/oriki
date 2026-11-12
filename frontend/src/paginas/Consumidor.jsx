// OR-21: página que o consumidor abre pelo QR da vitrine. Sem login e sem nenhum dado de pessoas.
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { paginaPublica } from "../api.js";
import { BarraApp, Carregando, Chip } from "../componentes.jsx";
import { dataCurta, hojeEmBelem } from "../formato.js";

const NOME_DIA = new Intl.DateTimeFormat("pt-BR", { weekday: "long", timeZone: "UTC" });

function rotuloDia(aaaaMmDd) {
  const hoje = hojeEmBelem();
  if (aaaaMmDd === hoje) return "Hoje";
  const ontem = new Date(Date.parse(hoje) - 86_400_000).toISOString().slice(0, 10);
  if (aaaaMmDd === ontem) return "Ontem";
  const nome = NOME_DIA.format(new Date(`${aaaaMmDd}T12:00:00Z`));
  return nome.charAt(0).toUpperCase() + nome.slice(1);
}

function ChipLicenca({ licenca }) {
  if (licenca.situacao === "em_dia") return <Chip tipo="sucesso">Licença sanitária em dia</Chip>;
  if (licenca.situacao === "vence_em_breve") return <Chip tipo="alerta">Licença vence em {dataCurta(licenca.validade)}</Chip>;
  return <Chip tipo="erro">Licença vencida</Chip>;
}

export default function Consumidor() {
  const { slug } = useParams();
  const [parametros] = useSearchParams();
  const doQr = parametros.get("origem") === "qr";
  const [estado, setEstado] = useState({ dados: null, erro: null });

  useEffect(() => {
    let ativo = true;
    paginaPublica(slug, doQr)
      .then((dados) => ativo && setEstado({ dados, erro: null }))
      .catch((erro) => ativo && setEstado({ dados: null, erro: erro.status === 404 ? "nao_encontrado" : "falhou" }));
    return () => {
      ativo = false;
    };
  }, [slug, doQr]);

  const { dados, erro } = estado;
  return (
    <main className="tela">
      <BarraApp />
      {erro === "nao_encontrado" ? (
        <p className="aviso-centro">Este QR não corresponde a nenhum ponto cadastrado no Oriki.</p>
      ) : erro ? (
        <p className="aviso-centro">Não foi possível carregar a página. Verifique a internet e tente de novo.</p>
      ) : !dados ? (
        <Carregando />
      ) : (
        <Pagina dados={dados} />
      )}
    </main>
  );
}

function Pagina({ dados }) {
  const hoje = dados.dias[0];
  const totalSemana = dados.dias.reduce((soma, d) => soma + d.aprovados + d.reprovados, 0);
  const reprovadosSemana = dados.dias.reduce((soma, d) => soma + d.reprovados, 0);
  return (
    <div className="conteudo colunas">
      <div className="coluna">
        <section className="card card-ponto">
          <h2 className="titulo-pagina-publica">{dados.nome}</h2>
          <p className="texto-pequeno texto-2">{dados.endereco}</p>
          <ChipLicenca licenca={dados.licenca} />
        </section>

        <section className="card" aria-labelledby="titulo-hoje-publico">
          <h2 id="titulo-hoje-publico" className="legenda">Branqueamento hoje</h2>
          {hoje.aprovados + hoje.reprovados === 0 ? (
            <p className="texto-2">Nenhum lote registrado hoje ainda.</p>
          ) : (
            <div className="kpis">
              <div className="kpi">
                <span className="kpi-numero">{hoje.aprovados}</span>
                <span className="kpi-rotulo">lotes a 80 °C por 10 s</span>
              </div>
              <div className="kpi">
                <span className={`kpi-numero${hoje.reprovados > 0 ? " texto-erro" : ""}`}>{hoje.reprovados}</span>
                <span className="kpi-rotulo">não atingiram</span>
              </div>
            </div>
          )}
          {hoje.ultimo && <p className="texto-pequeno texto-2">Último registro às {hoje.ultimo}</p>}
        </section>

        <section className="card" aria-label="Capacitação e fiscalização">
          <dl className="lista-dados">
            <div>
              <dt className="legenda">Licença da Vigilância Sanitária (Sesma)</dt>
              <dd>
                {dados.licenca.situacao === "vencida" ? "venceu em" : "válida até"} {dataCurta(dados.licenca.validade)}
              </dd>
            </div>
            <div>
              <dt className="legenda">Curso da Casa do Açaí</dt>
              <dd>{dados.curso_casa_acai_em ? `concluído em ${dataCurta(dados.curso_casa_acai_em)}` : "não informado"}</dd>
            </div>
            <div>
              <dt className="legenda">Última vistoria registrada</dt>
              <dd>{dados.ultima_vistoria ? dataCurta(dados.ultima_vistoria) : "nenhuma registrada no Oriki"}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div className="coluna">
        <section className="card" aria-labelledby="titulo-dias">
          <h2 id="titulo-dias" className="titulo-card">Últimos 7 dias</h2>
          <p className="texto-pequeno texto-2">
            {totalSemana === 0 ? "Sem lotes registrados na semana." :
              `${totalSemana} ${totalSemana === 1 ? "lote registrado" : "lotes registrados"}${
                reprovadosSemana ? `, ${reprovadosSemana} abaixo do exigido` : ""}.`}
          </p>
          <ul className="lista-dias">
            {dados.dias.map((dia) => (
              <li key={dia.data} className={`item-dia${dia.reprovados > 0 ? " item-reprovado" : ""}`}>
                <div>
                  <p className="titulo-card">{rotuloDia(dia.data)}</p>
                  <p className="texto-pequeno texto-2">
                    {dataCurta(dia.data, false)}{dia.ultimo ? ` · último às ${dia.ultimo}` : ""}
                  </p>
                </div>
                <div className="chips-dia">
                  {dia.aprovados + dia.reprovados === 0 ? (
                    <Chip>Sem registro</Chip>
                  ) : (
                    <>
                      <Chip tipo="sucesso">{dia.aprovados} ok</Chip>
                      {dia.reprovados > 0 && <Chip tipo="erro">{dia.reprovados} abaixo</Chip>}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
        <p className="aviso-publico">{dados.aviso}</p>
        <p className="texto-pequeno texto-2">
          “Ok” é o lote em que a água ficou a 80 °C ou mais por pelo menos 10 segundos (Decreto Estadual nº 326/2012).
        </p>
      </div>
    </div>
  );
}
