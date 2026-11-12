// Console de teste do backend Oriki (só desenvolvimento). Servido pelo Flask via FRONTEND_DIST=dev-console.
"use strict";

const $ = (id) => document.getElementById(id);
const saida = $("saida");

// Explicação dos erros esperados (tabela de permissões da seção 8.3 do plano).
const DICAS = {
  sem_permissao: "Esperado: este perfil não usa esta rota. Rotas do batedor (/api/batedor, /api/lotes) são só do " +
                 "batedor, porque mostram dados do estabelecimento dele; /api/fiscal é para fiscal e admin.",
  nao_autenticado: "Faça login primeiro.",
  termo_pendente: "O batedor precisa aceitar o termo de uso (botão 'Aceitar termo') antes de usar o app.",
  limite_de_tentativas: "Muitas tentativas erradas em 1 minuto. Espere o minuto acabar.",
  credenciais_invalidas: "E-mail ou senha errados (a resposta é a mesma nos dois casos, de propósito).",
  nao_encontrado: "Não existe, ou é de outro estabelecimento (a API não diferencia, de propósito).",
};

// ---------- chamadas à API ----------

function registrar(metodo, url, status, corpo) {
  const div = document.createElement("div");
  div.className = "entrada";
  const titulo = document.createElement("div");
  const codigo = document.createElement("span");
  codigo.className = "s" + String(status)[0];
  codigo.textContent = status;
  titulo.append(codigo, ` ${metodo} ${url}  ·  ${new Date().toLocaleTimeString("pt-BR")}`);
  const pre = document.createElement("pre");
  pre.textContent = typeof corpo === "string" ? corpo : JSON.stringify(corpo, null, 2);
  div.append(titulo, pre);
  const dica = DICAS[corpo && corpo.erro];
  if (dica) {
    const p = document.createElement("small");
    p.className = "dica";
    p.textContent = "ℹ " + dica;
    div.append(p);
  }
  saida.prepend(div);
}

async function api(metodo, url, corpo) {
  const opcoes = { method: metodo, headers: {}, credentials: "same-origin" };
  if (metodo !== "GET") {
    opcoes.headers["Content-Type"] = "application/json"; // a API exige JSON em toda alteração (CSRF)
    opcoes.body = JSON.stringify(corpo ?? {});
  }
  const resposta = await fetch(url, opcoes);
  let dados = null;
  const tipo = resposta.headers.get("Content-Type") || "";
  if (tipo.includes("json")) dados = await resposta.json();
  else if (resposta.status !== 204) dados = await resposta.text();
  registrar(metodo, url, resposta.status, dados ?? "(sem corpo)");
  return { status: resposta.status, dados };
}

// ---------- sessão ----------

async function atualizarSessao() {
  const resposta = await fetch("/api/me", { credentials: "same-origin" });
  const alvo = $("sessao");
  if (resposta.status !== 200) {
    alvo.textContent = "Ninguém logado";
    return;
  }
  const eu = await resposta.json();
  const ponto = eu.estabelecimento ? ` · ${eu.estabelecimento.nome}` : "";
  const termo = eu.perfil === "batedor" && !eu.termo_aceito ? " · termo pendente" : "";
  alvo.textContent = `${eu.nome} (${eu.perfil})${ponto}${termo}`;
}

async function entrar(email) {
  const { status } = await api("POST", "/api/login", { email, senha: $("senha").value });
  await atualizarSessao();
  if (status === 200 && email.startsWith("rosa")) await resumo();
}

document.querySelectorAll("[data-login]").forEach((botao) =>
  botao.addEventListener("click", () => {
    $("email").value = botao.dataset.login;
    entrar(botao.dataset.login);
  }));
$("btn-login").onclick = () => entrar($("email").value);
$("btn-logout").onclick = async () => { await api("POST", "/api/logout"); await atualizarSessao(); };

// ---------- simulador do ESP32 (mesmo contrato da seção 7) ----------

const chaveSalva = localStorage.getItem("oriki-chave");
if (chaveSalva) $("chave").value = chaveSalva;
const contadorSalvo = localStorage.getItem("oriki-contador");
if (contadorSalvo) $("contador").value = contadorSalvo;
let ultimoEnvio = [];

async function hmac(chave, mensagem) {
  const codificador = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", codificador.encode(chave), { name: "HMAC", hash: "SHA-256" },
                                          false, ["sign"]);
  const assinatura = await crypto.subtle.sign("HMAC", k, codificador.encode(mensagem));
  return [...new Uint8Array(assinatura)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Hora do RTC com offset de Belém (UTC−3, sem horário de verão), como o firmware envia.
function isoBelem(data) {
  return new Date(data.getTime() - 3 * 3600e3).toISOString().slice(0, 19) + "-03:00";
}

const duas = (x) => Math.round(x * 100) / 100;
const sorteio = (min, max) => min + Math.random() * (max - min);

async function gerarCiclo(dispositivo, contador, inicio, chave, reprovado) {
  const segundos = reprovado ? Math.floor(sorteio(2, 9)) : Math.floor(sorteio(10, 25));
  const ciclo = {
    codigo: `${dispositivo}-${String(contador).padStart(6, "0")}`,
    contador,
    inicio: isoBelem(inicio),
    fim: isoBelem(new Date(inicio.getTime() + (segundos + 3) * 1000)),
    temp_min: duas(reprovado ? sorteio(76, 79.5) : sorteio(80.1, 82)),
    temp_max: duas(reprovado ? sorteio(79.6, 81) : sorteio(83, 87)),
    segundos_acima_80: segundos,
    status: reprovado ? "reprovado" : "aprovado",
  };
  const mensagem = [ciclo.codigo, ciclo.contador, ciclo.inicio, ciclo.fim, ciclo.temp_min.toFixed(2),
                    ciclo.temp_max.toFixed(2), ciclo.segundos_acima_80, ciclo.status].join("|");
  ciclo.assinatura = await hmac(chave, mensagem);
  return ciclo;
}

async function enviarCiclos({ quantidade, pular = 0, reprovado = false, adulterar = false, repetir = false,
                              atrasoSegundos = 0 }) {
  const dispositivo = $("disp").value.trim().toUpperCase();
  const chave = $("chave").value.trim();
  if (!chave) {
    registrar("—", "simulador", 400, "Cole a chave do dispositivo no campo 'Chave' (sai do seed.py ou do flask criar-dispositivo).");
    return;
  }
  localStorage.setItem("oriki-chave", chave);
  const rtc = new Date(Date.now() - atrasoSegundos * 1000);
  let ciclos;
  if (repetir) {
    ciclos = ultimoEnvio;
  } else {
    let contador = Number($("contador").value) + pular;
    ciclos = [];
    for (let i = 0; i < quantidade; i++) {
      const inicio = new Date(rtc.getTime() - (quantidade - i) * 3 * 60e3);
      ciclos.push(await gerarCiclo(dispositivo, contador + i, inicio, chave, reprovado));
    }
    if (adulterar && ciclos.length) {
      const alvo = ciclos[ciclos.length - 1];
      alvo.temp_max = 90; // muda depois de assinar: o servidor deve recusar
    }
    if (ciclos.length) {
      ultimoEnvio = ciclos;
      $("contador").value = ciclos[ciclos.length - 1].contador + 1;
      localStorage.setItem("oriki-contador", $("contador").value);
    }
  }
  const enviadoEm = isoBelem(rtc);
  await api("POST", "/api/ciclos", {
    dispositivo, enviado_em: enviadoEm, assinatura_envio: await hmac(chave, `${dispositivo}|${enviadoEm}`), ciclos,
  });
}

$("sim-enviar").onclick = () => enviarCiclos({ quantidade: Number($("qtd").value) });
$("sim-lacuna").onclick = () => enviarCiclos({ quantidade: 1, pular: 2 });
$("sim-reprovado").onclick = () => enviarCiclos({ quantidade: 1, reprovado: true });
$("sim-adulterar").onclick = () => enviarCiclos({ quantidade: 1, adulterar: true });
$("sim-repetir").onclick = () => enviarCiclos({ repetir: true });
$("sim-relogio").onclick = () => enviarCiclos({ quantidade: 1, atrasoSegundos: 600 });
$("sim-heartbeat").onclick = () => enviarCiclos({ quantidade: 0 });

// ---------- batedor ----------

let loteAberto = null;

async function resumo() {
  const { status, dados } = await api("GET", "/api/batedor/resumo");
  const alvo = $("lotes");
  alvo.replaceChildren();
  if (status !== 200) return;
  const titulo = document.createElement("p");
  titulo.textContent = `Hoje (${dados.hoje.data}): ${dados.hoje.aprovados} aprovados, ${dados.hoje.reprovados} reprovados · ` +
                       `${dados.total_a_completar} lote(s) a completar · licença ${dados.estabelecimento.licenca_situacao}`;
  alvo.append(titulo);
  const tabela = document.createElement("table");
  tabela.innerHTML = "<tr><th>Lote</th><th>Início</th><th>Ciclo</th><th></th></tr>";
  for (const lote of dados.lotes_a_completar.slice(0, 10)) {
    const linha = tabela.insertRow();
    linha.insertCell().textContent = lote.codigo;
    linha.insertCell().textContent = new Date(lote.inicio).toLocaleString("pt-BR");
    linha.insertCell().textContent = lote.status_ciclo;
    const botao = document.createElement("button");
    botao.textContent = "Completar";
    botao.onclick = () => abrirLote(lote.codigo);
    linha.insertCell().append(botao);
  }
  alvo.append(tabela);
}

async function abrirLote(codigo) {
  const { status } = await api("GET", `/api/lotes/${encodeURIComponent(codigo)}`);
  if (status !== 200) return;
  loteAberto = codigo;
  $("form-codigo").textContent = codigo;
  $("form-lote").hidden = false;
}

$("f-salvar").onclick = async () => {
  if (!loteAberto) return;
  const quantidade = $("f-qtd").value === "" ? null : Number($("f-qtd").value);
  const { status } = await api("PATCH", `/api/lotes/${encodeURIComponent(loteAberto)}`, {
    origem_fruto: $("f-origem").value, quantidade_rasas: quantidade,
    catacao: $("f-catacao").checked, sanitizacao: $("f-sanitizacao").checked,
    resfriamento: $("f-resfriamento").checked,
  });
  if (status === 200) { $("form-lote").hidden = true; await resumo(); }
};

$("bat-resumo").onclick = resumo;
$("bat-historico").onclick = () => api("GET", "/api/batedor/lotes");
$("bat-termo").onclick = async () => { await api("POST", "/api/batedor/termo"); await atualizarSessao(); };
$("bat-qr").onclick = () => {
  const img = document.createElement("img");
  img.alt = "QR do estabelecimento";
  img.src = `/api/batedor/qr.svg?t=${Date.now()}`;
  img.onerror = () => registrar("GET", "/api/batedor/qr.svg", 401, "Entre como batedora para ver o QR.");
  $("qr").replaceChildren(img);
};

const hoje = new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10);
$("pdf-ate").value = hoje;
$("pdf-de").value = new Date(Date.now() - 3 * 3600e3 - 29 * 86400e3).toISOString().slice(0, 10);
$("bat-pdf").onclick = async () => {
  const url = `/api/batedor/relatorio.pdf?de=${$("pdf-de").value}&ate=${$("pdf-ate").value}`;
  const resposta = await fetch(url, { credentials: "same-origin" });
  if (resposta.ok) {
    registrar("GET", url, resposta.status, "PDF aberto em nova aba.");
    window.open(URL.createObjectURL(await resposta.blob()), "_blank");
  } else {
    registrar("GET", url, resposta.status, await resposta.json());
  }
};

// ---------- fiscal e público ----------

$("fis-alertas").onclick = () => api("GET", "/api/fiscal/alertas");
$("fis-lista").onclick = () => api("GET", "/api/fiscal/estabelecimentos");
$("fis-detalhe").onclick = () => api("GET", `/api/fiscal/estabelecimentos/${Number($("fis-id").value)}`);
$("fis-vistoria").onclick = () => api("POST", `/api/fiscal/estabelecimentos/${Number($("fis-id").value)}/vistorias`, {
  data: hoje, resultado: $("vis-resultado").value, observacoes: $("vis-obs").value,
});
$("pub-ver").onclick = () => api("GET", `/api/publico/${encodeURIComponent($("slug").value)}`);
$("pub-qr").onclick = () => api("GET", `/api/publico/${encodeURIComponent($("slug").value)}?origem=qr`);

$("limpar").onclick = () => saida.replaceChildren();
atualizarSessao();
