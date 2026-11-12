export class ErroApi extends Error {
  constructor(status, corpo) {
    super(corpo?.erro || `HTTP ${status}`);
    this.status = status;
    this.erro = corpo?.erro;
    this.detalhes = corpo?.detalhes;
  }
}

async function chamar(caminho, { metodo = "GET", corpo } = {}) {
  const resp = await fetch(`/api${caminho}`, {
    method: metodo,
    credentials: "same-origin",
    headers: corpo !== undefined ? { "Content-Type": "application/json" } : {},
    body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
  });
  const ehJson = resp.headers.get("content-type")?.includes("application/json");
  const dados = ehJson ? await resp.json() : null;
  if (!resp.ok) throw new ErroApi(resp.status, dados);
  return dados;
}

export const login = (email, senha) => chamar("/login", { metodo: "POST", corpo: { email, senha } });
// O backend exige Content-Type: application/json em todo POST (proteção CSRF; sem ele, 415): por isso o {}.
export const logout = () => chamar("/logout", { metodo: "POST", corpo: {} });
export const me = () => chamar("/me");
export const aceitarTermo = () => chamar("/batedor/termo", { metodo: "POST", corpo: {} });
export const resumo = () => chamar("/batedor/resumo");
export const obterLote = (codigo) => chamar(`/lotes/${encodeURIComponent(codigo)}`);
export const salvarLote = (codigo, campos) =>
  chamar(`/lotes/${encodeURIComponent(codigo)}`, { metodo: "PATCH", corpo: campos });
// OR-19: a fila offline (IndexedDB) envolve salvarLote em fila.js.

function consulta(parametros) {
  const preenchidos = Object.entries(parametros).filter(([, valor]) => valor !== "" && valor != null);
  return new URLSearchParams(preenchidos).toString();
}

export const listarLotes = ({ de, ate, status, pagina }) =>
  chamar(`/batedor/lotes?${consulta({ de, ate, status, pagina })}`);

// Arquivos (PDF): devolve o conteúdo e o nome sugerido pelo servidor no Content-Disposition.
async function baixar(caminho) {
  const resp = await fetch(`/api${caminho}`, { credentials: "same-origin" });
  if (!resp.ok) {
    const ehJson = resp.headers.get("content-type")?.includes("application/json");
    throw new ErroApi(resp.status, ehJson ? await resp.json() : null);
  }
  const nome = /filename="([^"]+)"/.exec(resp.headers.get("content-disposition") || "")?.[1];
  return { blob: await resp.blob(), nome };
}

// Página pública do QR (sem login). Só conta o acesso quando a página foi aberta pelo QR (?origem=qr).
export const paginaPublica = (slug, doQr) =>
  chamar(`/publico/${encodeURIComponent(slug)}${doQr ? "?origem=qr" : ""}`);

// Painel do fiscal
export const alertasFiscal = () => chamar("/fiscal/alertas");
export const pontosFiscal = (busca) => chamar(`/fiscal/estabelecimentos?${consulta({ busca })}`);
export const detalhePonto = (id, { de, ate } = {}) => chamar(`/fiscal/estabelecimentos/${id}?${consulta({ de, ate })}`);
export const registrarVistoria = (id, vistoria) =>
  chamar(`/fiscal/estabelecimentos/${id}/vistorias`, { metodo: "POST", corpo: vistoria });

export const baixarRelatorio = (de, ate) => baixar(`/batedor/relatorio.pdf?${consulta({ de, ate })}`);
export const URL_QR = "/api/batedor/qr.svg";

// Cópias da API guardadas pelo Service Worker (public/sw.js usa o mesmo nome) para abrir sem internet.
const CACHE_API = "oriki-api-v1";

// Ao sair, os dados do ponto não ficam no aparelho (celular pode ser emprestado).
export async function limparDadosDaSessao() {
  if ("caches" in window) await caches.delete(CACHE_API);
}
