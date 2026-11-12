import { useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { limparDadosDaSessao, logout } from "./api.js";
import { ALERTAS } from "./alertas.js";
import { dataCurta } from "./formato.js";
import { BotaoLayout, useLayout } from "./layout.jsx";

const ICONES = {
  sucesso: <path d="M3.5 8.5l3 3 6-7" />,
  erro: <path d="M4.5 4.5l7 7m0-7l-7 7" />,
  alerta: <path d="M8 3.5v5.5m0 3v.01" />,
};

export function Chip({ tipo = "neutro", children }) {
  return (
    <span className={`chip chip-${tipo}`}>
      {ICONES[tipo] && (
        <svg viewBox="0 0 16 16" aria-hidden="true" className="chip-icone">
          {ICONES[tipo]}
        </svg>
      )}
      {children}
    </span>
  );
}

export function ChipCiclo({ status }) {
  return status === "aprovado" ? <Chip tipo="sucesso">Aprovado</Chip> : <Chip tipo="erro">Reprovado</Chip>;
}

// Menu da barra no layout web (no celular, a navegação é pelos cartões e pelo botão voltar).
const MENUS = {
  batedor: [
    ["/batedor", "Início", true],
    ["/batedor/historico", "Histórico"],
    ["/batedor/relatorio", "Relatório"],
    ["/batedor/qr", "QR do ponto"],
  ],
  fiscal: [
    ["/fiscal", "Alertas e pontos", true],
  ],
};

export function BarraApp({ titulo = "Oriki", voltarPara, acao }) {
  const { modo } = useLayout();
  const { pathname } = useLocation();
  const area = pathname.startsWith("/batedor") ? "batedor" : pathname.startsWith("/fiscal") ? "fiscal" : null;
  const menu = modo === "web" && area ? MENUS[area] : null;
  return (
    <header className="barra-app">
      <div className="barra-interna">
        {voltarPara && (
          <Link to={voltarPara} className="barra-voltar" aria-label="Voltar">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M19 12H5m6-6l-6 6 6 6" />
            </svg>
          </Link>
        )}
        {menu ? (
          <>
            <Link to={`/${area}`} className="barra-marca barra-marca-curta">Oriki</Link>
            <nav className="menu-barra" aria-label="Menu">
              {menu.map(([para, rotulo, fim]) => (
                <NavLink key={para} to={para} end={fim} className="link-barra">{rotulo}</NavLink>
              ))}
            </nav>
            {titulo !== "Oriki" && <h1 className="barra-titulo barra-titulo-web">{titulo}</h1>}
          </>
        ) : (
          <h1 className={voltarPara ? "barra-titulo" : "barra-marca"}>{titulo}</h1>
        )}
        <BotaoLayout />
        {acao}
      </div>
    </header>
  );
}

export function BotaoSair({ className = "botao-barra" }) {
  const navigate = useNavigate();
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    setSaindo(true);
    try {
      await logout();
    } catch {
      // Sem rede ou sessão já expirada: a tela de login resolve do mesmo jeito.
    }
    await limparDadosDaSessao().catch(() => {});
    navigate("/login", { replace: true });
  }

  return (
    <button type="button" className={className} onClick={sair} disabled={saindo}>
      Sair
    </button>
  );
}

export function Carregando() {
  return <p className="aviso-centro" role="status">Carregando…</p>;
}

export function ChipAlerta({ tipo }) {
  const info = ALERTAS[tipo] || { rotulo: tipo, tipo: "neutro" };
  return <Chip tipo={info.tipo}>{info.rotulo}</Chip>;
}

export function ChipLicencaCurta({ situacao, validade }) {
  if (situacao === "em_dia") return <Chip tipo="sucesso">Licença em dia</Chip>;
  if (situacao === "vence_em_breve") return <Chip tipo="alerta">Vence em {dataCurta(validade)}</Chip>;
  return <Chip tipo="erro">Licença vencida</Chip>;
}
