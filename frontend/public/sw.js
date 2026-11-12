// OR-20: Service Worker do Oriki. O app abre sem internet e mostra a última cópia dos dados do batedor.
// Gravar lote sem internet é com a fila do IndexedDB (src/fila.js); aqui só entram leituras (GET).
// Ao mudar o que fica guardado, troque a VERSAO para os celulares descartarem a cópia antiga.
const VERSAO = "v2";
const CACHE_APP = `oriki-app-${VERSAO}`;
const CACHE_API = "oriki-api-v1"; // mesmo nome em src/api.js, que apaga este cache ao sair
const PAGINA = "/"; // o React decide a rota; toda navegação usa o mesmo index.html

// Leituras da API que o batedor precisa ver sem internet. Relatório em PDF fica de fora (gerado na hora).
const API_GUARDADA = [
  /^\/api\/me$/,
  /^\/api\/batedor\/resumo$/,
  /^\/api\/batedor\/lotes$/,
  /^\/api\/batedor\/qr\.svg$/,
  /^\/api\/lotes\/[^/]+$/,
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE_APP)
      .then((cache) => cache.addAll([PAGINA, "/manifest.webmanifest", "/icone.svg", "/icone-192.png"]))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(
        nomes.filter((nome) => nome.startsWith("oriki-app-") && nome !== CACHE_APP).map((nome) => caches.delete(nome)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const { request } = evento;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    if (API_GUARDADA.some((regra) => regra.test(url.pathname))) {
      evento.respondWith(redePrimeiro(request, CACHE_API, request, semInternet));
    }
    return; // o resto da API vai direto para a rede
  }
  if (request.mode === "navigate") {
    evento.respondWith(redePrimeiro(request, CACHE_APP, PAGINA, () => caches.match(PAGINA, { cacheName: CACHE_APP })));
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    evento.respondWith(cachePrimeiro(request)); // nomes com hash do Vite: o conteúdo nunca muda
    return;
  }
  evento.respondWith(redePrimeiro(request, CACHE_APP, request));
});

// Busca na rede e guarda a cópia; sem rede, usa a última cópia guardada.
async function redePrimeiro(request, nomeCache, chave, semCopia) {
  const cache = await caches.open(nomeCache);
  try {
    const resposta = await fetch(request);
    if (resposta.ok) await cache.put(chave, resposta.clone());
    return resposta;
  } catch (erro) {
    const copia = await cache.match(chave);
    if (copia) return copia;
    if (semCopia) return (await semCopia()) || Response.error();
    throw erro;
  }
}

async function cachePrimeiro(request) {
  const cache = await caches.open(CACHE_APP);
  const copia = await cache.match(request);
  if (copia) return copia;
  const resposta = await fetch(request);
  if (resposta.ok) await cache.put(request, resposta.clone());
  return resposta;
}

// Mesmo formato de erro da API: o app mostra "sem internet" (src/fila.js, semConexao).
function semInternet() {
  return new Response(JSON.stringify({ erro: "offline" }), {
    status: 503,
    headers: { "Content-Type": "application/json" },
  });
}
