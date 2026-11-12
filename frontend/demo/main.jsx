/* eslint-disable react-refresh/only-export-components -- arquivo de entrada da demonstração */
// Demonstração do Oriki dentro do Claude: o app de verdade (src/) num celular, com o servidor e o ESP32
// simulados no navegador. Nada aqui muda o app; só troca o "outro lado" do fetch.
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import "../src/estilo.css";
import "./demo.css";
import { atender, reiniciarBanco } from "./servidor.js";
import { Dispositivo } from "./dispositivo.js";
import Bancada from "./Bancada.jsx";
import { QR_SVG } from "./qr.js";
import App from "../src/App.jsx";
import { LayoutProvider } from "../src/layout.jsx";
import { iniciarSincronizacao } from "../src/fila.js";

// ---------- o "outro lado" do app: fetch, internet do celular, layout e imagem do QR ----------
const demo = { celularOnline: true };
const fetchOriginal = window.fetch.bind(window);

// O Claude não deixa a página registrar o Service Worker (public/sw.js). Este cache faz o papel dele:
// guarda as mesmas leituras (rede primeiro; sem rede, a última cópia) e, como a Home faz com o SW ativo,
// já guarda os lotes a completar para o formulário abrir sem internet.
const API_GUARDADA = [/^\/api\/me$/, /^\/api\/batedor\/resumo$/, /^\/api\/batedor\/lotes$/, /^\/api\/lotes\/[^/]+$/];
const copias = new Map();
const resposta = (status, corpo) => new Response(status === 204 ? null : JSON.stringify(corpo), {
  status, headers: { "Content-Type": "application/json" },
});

window.fetch = async (entrada, opcoes = {}) => {
  const url = typeof entrada === "string" ? entrada : entrada.url;
  if (!url.startsWith("/api")) return fetchOriginal(entrada, opcoes);
  const metodo = (opcoes.method || "GET").toUpperCase();
  const caminho = url.split("?")[0];
  const guardavel = metodo === "GET" && API_GUARDADA.some((re) => re.test(caminho));
  await new Promise((ok) => setTimeout(ok, 120)); // um pouco de rede, como no celular
  if (!demo.celularOnline) {
    if (guardavel && copias.has(url)) return resposta(200, copias.get(url));
    throw new TypeError("Failed to fetch");
  }
  let corpo;
  try {
    corpo = opcoes.body ? JSON.parse(opcoes.body) : undefined;
  } catch {
    corpo = undefined;
  }
  const r = await atender(metodo, url, corpo);
  if (caminho === "/api/login" || caminho === "/api/logout") copias.clear(); // celular pode ser emprestado
  if (guardavel && r.status === 200) {
    copias.set(url, r.corpo);
    if (caminho === "/api/batedor/resumo") {
      for (const lote of r.corpo.lotes_a_completar.slice(0, 20)) {
        const urlLote = `/api/lotes/${encodeURIComponent(lote.codigo)}`;
        if (!copias.has(urlLote)) atender("GET", urlLote).then((x) => x.status === 200 && copias.set(urlLote, x.corpo));
      }
    }
  }
  return resposta(r.status, r.corpo);
};
try {
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => demo.celularOnline });
} catch {
  // navegador que não deixa trocar: o app ainda percebe pela falha do fetch
}
function definirInternet(ligada) {
  demo.celularOnline = ligada;
  window.dispatchEvent(new Event(ligada ? "online" : "offline"));
}

// O app escolhe o layout pela largura da janela; aqui ele está sempre num celular.
const matchMediaOriginal = window.matchMedia?.bind(window);
window.matchMedia = (consulta) => (consulta.includes("1024px")
  ? { matches: false, media: consulta, addEventListener() {}, removeEventListener() {} }
  : matchMediaOriginal(consulta));
try {
  localStorage.setItem("oriki-layout", "mobile");
} catch {
  // sem armazenamento: o matchMedia acima já resolve
}

// <img src="/api/batedor/qr.svg"> não passa pelo fetch: troca pela imagem gerada na hora do build.
const URL_QR_DEMO = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(QR_SVG)}`;
new MutationObserver(() => {
  document.querySelectorAll('img[src="/api/batedor/qr.svg"]').forEach((img) => { img.src = URL_QR_DEMO; });
  document.querySelectorAll('a[href="/api/batedor/qr.svg"]').forEach((a) => { a.href = URL_QR_DEMO; });
}).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["src", "href"] });

// O app só chama o fetch depois de montar, então já encontra o servidor da demonstração.
iniciarSincronizacao();

let dispositivo = new Dispositivo({ contadorInicial: 31 });

const NOMES_ROTA = [
  [/^\/login/, "Login"], [/^\/batedor\/lotes\//, "Completar lote"], [/^\/batedor\/historico/, "Histórico"],
  [/^\/batedor\/relatorio/, "Relatório"], [/^\/batedor\/qr/, "QR do ponto"], [/^\/batedor/, "Tela inicial da batedora"],
  [/^\/p\//, "Página do consumidor"], [/^\/fiscal\/pontos/, "Detalhe do ponto (fiscal)"], [/^\/fiscal/, "Painel do fiscal"],
];

function Atalhos({ online, setOnline, reiniciar }) {
  const navigate = useNavigate();
  const local = useLocation();
  const tela = NOMES_ROTA.find(([re]) => re.test(local.pathname))?.[1] || local.pathname;

  async function entrar(email) {
    const post = (caminho, corpo) => fetch(caminho, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo) });
    await post("/api/logout", {});
    await post("/api/login", { email, senha: "oriki-dev-2026" });
    navigate("/", { replace: true });
  }

  return (
    <section className="d-card">
      <h2 className="d-titulo">Celular</h2>
      <p className="d-dica">Na tela: <b>{tela}</b>. Senha de todas as contas: <code>oriki-dev-2026</code>.</p>
      <div className="d-linha">
        <button type="button" className="d-botao d-principal" onClick={() => entrar("rosa@exemplo.com")}>Entrar como Rosa (batedora)</button>
        <button type="button" className="d-botao" onClick={() => entrar("fiscal@exemplo.com")}>Entrar como fiscal</button>
        <button type="button" className="d-botao" onClick={() => entrar("ze@exemplo.com")}>Entrar como Zé</button>
        <button type="button" className="d-botao" onClick={() => entrar("teste@exemplo.com")}>Batedor novo (termo de uso)</button>
      </div>
      <div className="d-linha">
        <button type="button" className="d-botao" onClick={() => navigate("/p/acai-da-dona-rosa?origem=qr")}>
          Escanear o QR da Dona Rosa (consumidor)
        </button>
        <button type="button" className="d-botao" onClick={() => navigate("/p/acai-do-ze?origem=qr")}>QR do Zé</button>
      </div>
      <label className="d-check">
        <input type="checkbox" checked={online} onChange={(e) => setOnline(e.target.checked)} /> internet do celular ligada
      </label>
      <p className="d-dica">
        Desligue para testar o lote salvo sem internet: o app guarda no celular e envia quando a internet volta.
      </p>
      <button type="button" className="d-botao d-perigo" onClick={reiniciar}>Recomeçar a demonstração</button>
    </section>
  );
}

function Demo() {
  const [online, setOnlineEstado] = useState(true);
  const [disp, setDisp] = useState(dispositivo);
  const [geracao, setGeracao] = useState(0);
  const navigate = useNavigate();

  // Links comuns do app para uma página dele (ex.: "Ver a página do QR" do fiscal) abrem dentro do celular.
  useEffect(() => {
    const clicar = (e) => {
      const link = e.target.closest?.(".d-tela-app a[href^='/']");
      if (!link || link.hasAttribute("download")) return;
      e.preventDefault();
      navigate(link.getAttribute("href"));
    };
    document.addEventListener("click", clicar, true);
    return () => document.removeEventListener("click", clicar, true);
  }, [navigate]);

  const setOnline = (ligada) => {
    definirInternet(ligada);
    setOnlineEstado(ligada);
  };
  const reiniciar = () => {
    reiniciarBanco();
    copias.clear();
    dispositivo.desligar();
    dispositivo = new Dispositivo({ contadorInicial: 31 });
    setDisp(dispositivo);
    setGeracao((g) => g + 1);
    setOnline(true);
    navigate("/login", { replace: true });
  };

  return (
    <div className="d-pagina">
      <header className="d-cabecalho">
        <h1>Oriki · demonstração</h1>
        <p>
          O app de verdade no celular, ao lado do tanque com o ESP32 simulado. O servidor também é simulado aqui
          na página, com as mesmas regras da API: recarregar a página recomeça tudo.
        </p>
      </header>
      <div className="d-colunas">
        <div className="d-coluna-celular">
          <div className="d-telefone">
            <div className="d-tela-app">
              <LayoutProvider>
                <App />
              </LayoutProvider>
            </div>
          </div>
          <Atalhos online={online} setOnline={setOnline} reiniciar={reiniciar} />
          <section className="d-card d-aviso">
            <h2 className="d-titulo">O que não funciona aqui dentro</h2>
            <p className="d-dica">
              O Claude bloqueia downloads e impressão, então o PDF do relatório, &quot;Baixar arquivo&quot; e
              &quot;Imprimir&quot; do QR só funcionam rodando o projeto no computador. Os alertas de &quot;Registro
              faltando&quot; aparecem 1 hora depois, como no servidor de verdade (o detalhe do ponto mostra a lacuna na hora).
            </p>
          </section>
        </div>
        <Bancada key={geracao} disp={disp} />
      </div>
    </div>
  );
}

createRoot(document.getElementById("demo")).render(
  <StrictMode>
    <MemoryRouter initialEntries={[location.hash === "#consumidor" ? "/p/acai-da-dona-rosa?origem=qr" : "/login"]}>
      <Demo />
    </MemoryRouter>
  </StrictMode>,
);
