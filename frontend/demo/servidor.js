// Servidor de mentira da demonstração: a mesma API do backend (rotas, formatos e regras), rodando no
// navegador. Os dados ficam na memória da página: recarregar começa de novo, com o mesmo seed.py.
// Fonte da verdade continua sendo o backend Flask; isto só existe para testar dentro do Claude.

const SENHA = "oriki-dev-2026";
export const CHAVE_DEMO = "7f5f1804ca51c2c77b5371a984cc330aa45570a122f8319e66160fc41201666f";
const HORA = 3_600_000;
const DIA = 24 * HORA;
const OFFSET_BELEM = -3 * HORA; // Belém: UTC−3, sem horário de verão
const AVISO_PUBLICO = "Registros do próprio estabelecimento, medidos pelo dispositivo no tanque. "
  + "Não é selo oficial: a fonte oficial é a licença da Sesma.";
const DIAS_PAGINA_PUBLICA = 7;
const PERIODO_MAXIMO_DIAS = 92;
const TOLERANCIA_RELOGIO_MS = 120_000;

// ---------- datas (sempre no fuso de Belém, como o regras.py) ----------
export const agora = () => Date.now();
export const diaLocal = (ms) => new Date(ms + OFFSET_BELEM).toISOString().slice(0, 10);
export const hoje = () => diaLocal(agora());
const horaLocal = (ms) => new Date(ms + OFFSET_BELEM).toISOString().slice(11, 16);
const isoUtc = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const inicioDoDia = (aaaaMmDd) => Date.parse(`${aaaaMmDd}T00:00:00Z`) - OFFSET_BELEM;
const somarDias = (aaaaMmDd, n) => new Date(Date.parse(`${aaaaMmDd}T00:00:00Z`) + n * DIA).toISOString().slice(0, 10);
const dataBr = (aaaaMmDd) => aaaaMmDd.split("-").reverse().join("/");

function situacaoLicenca(validade) {
  const h = hoje();
  if (validade < h) return "vencida";
  if (validade <= somarDias(h, 30)) return "vence_em_breve";
  return "em_dia";
}

// ---------- HMAC-SHA256 (o mesmo contrato da seção 7.2 do plano) ----------
const codificador = new TextEncoder();
const chavesCripto = new Map();
async function hmacHex(chave, mensagem) {
  if (!chavesCripto.has(chave)) {
    chavesCripto.set(chave, crypto.subtle.importKey("raw", codificador.encode(chave), { name: "HMAC", hash: "SHA-256" },
      false, ["sign"]));
  }
  const assinatura = await crypto.subtle.sign("HMAC", await chavesCripto.get(chave), codificador.encode(mensagem));
  return [...new Uint8Array(assinatura)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export const mensagemCiclo = (c) => [c.codigo, c.contador, c.inicio, c.fim, Number(c.temp_min).toFixed(2),
  Number(c.temp_max).toFixed(2), c.segundos_acima_80, c.status].join("|");
export const assinarCiclo = (c, chave) => hmacHex(chave, mensagemCiclo(c));
export const assinarEnvio = (dispositivo, enviadoEm, chave) => hmacHex(chave, `${dispositivo}|${enviadoEm}`);

// ---------- estado (o equivalente ao seed.py) ----------
let banco;

function aleatorio(semente) {
  let s = semente;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

function criarBanco() {
  const ests = [
    { id: 1, nome: "Açaí da Dona Rosa (exemplo)", endereco: "Rua Exemplo, 100 · Guamá, Belém",
      licenca_numero: "SESMA-0001-EXEMPLO", licenca_validade: "2027-03-31", curso_casa_acai_em: "2025-05-12",
      slug_qr: "acai-da-dona-rosa", criado: agora() - 60 * DIA },
    { id: 2, nome: "Açaí do Zé (exemplo)", endereco: "Travessa Exemplo, 20 · Jurunas, Belém",
      licenca_numero: "SESMA-0002-EXEMPLO", licenca_validade: "2026-11-10", curso_casa_acai_em: null,
      slug_qr: "acai-do-ze", criado: agora() - 60 * DIA },
  ];
  const usuarios = [
    { id: 1, nome: "Rosa (exemplo)", email: "rosa@exemplo.com", perfil: "batedor", est: 1, termo: true },
    { id: 2, nome: "Zé (exemplo)", email: "ze@exemplo.com", perfil: "batedor", est: 2, termo: true },
    { id: 3, nome: "Fiscal (exemplo)", email: "fiscal@exemplo.com", perfil: "fiscal", est: null, termo: false },
    { id: 4, nome: "Admin (exemplo)", email: "admin@exemplo.com", perfil: "admin", est: null, termo: false },
    { id: 5, nome: "Teste (novo batedor)", email: "teste@exemplo.com", perfil: "batedor", est: 2, termo: false },
  ];
  const dispositivos = [{ id: 1, est: 1, identificador: "ORK01", chave: CHAVE_DEMO, ultimo_contato: agora() - 5 * 60_000 }];

  // Ciclos como o seed.py: hoje 6 aprovados e 1 reprovado; nos 6 dias anteriores de 0 a 9 aprovados,
  // com um dia sem registro; os 3 mais recentes ficam a completar.
  const sorte = aleatorio(20261112);
  const momento = agora();
  let diaDemo = hoje();
  if (momento - inicioDoDia(diaDemo) < 7 * HORA) diaDemo = somarDias(diaDemo, -1); // antes das 07h: usa ontem
  const instantes = [];
  const porDia = [0, 3, 0, 7, 7, 4, 2]; // aprovados por "dias atrás" (1 = ontem); anteontem fica sem registro
  for (let i = 6; i >= 1; i--) {
    const dia = somarDias(diaDemo, -i);
    const n = porDia[i];
    for (let k = 0; k < n; k++) {
      instantes.push({ ms: inicioDoDia(dia) + (7 + (k * 9) / Math.max(n, 1) + sorte()) * HORA, aprovado: true });
    }
  }
  const fimHoje = Math.min(momento - 20 * 60_000, inicioDoDia(diaDemo) + 22 * HORA);
  const comecoHoje = inicioDoDia(diaDemo) + 6 * HORA;
  for (let k = 0; k < 7; k++) {
    instantes.push({ ms: comecoHoje + ((fimHoje - comecoHoje) * (k + sorte() * 0.5)) / 7.5, aprovado: k !== 5 });
  }
  instantes.sort((a, b) => a.ms - b.ms);
  const lotes = instantes.map((item, i) => {
    const contador = i + 1;
    const segundos = item.aprovado ? 12 + Math.floor(sorte() * 9) : 2 + Math.floor(sorte() * 5);
    const tMax = 82 + sorte() * 4.5;
    const completo = i < instantes.length - 3;
    return {
      codigo: `ORK01-${String(contador).padStart(6, "0")}`, dispositivo: 1, contador,
      origem_fruto: completo ? ["Ilha do Combu", "Abaetetuba", "Ilha das Onças", "Igarapé-Miri"][i % 4] : null,
      quantidade_rasas: completo ? 2 + (i % 3) : null,
      catacao: completo, sanitizacao: completo, resfriamento: completo && i % 5 !== 0,
      ciclo: {
        inicio: item.ms, fim: item.ms + segundos * 1000 + 2000, temp_min: +(80.2 + sorte() * 1.5).toFixed(2),
        temp_max: +tMax.toFixed(2), segundos_acima_80: segundos, status: item.aprovado ? "aprovado" : "reprovado",
        relogio_divergente: false, assinatura: "seed", recebido: item.ms + 60_000,
      },
    };
  });
  return {
    ests, usuarios, dispositivos, lotes,
    vistorias: [{ id: 1, est: 1, data: somarDias(hoje(), -20), resultado: "regular",
      observacoes: "Tanque e haste em ordem.", fiscal: 3 }],
    acessos: {}, // "estId|dia" → total
    recusas: [],
    sessao: null,
    tentativasLogin: [],
  };
}
banco = criarBanco();

export function reiniciarBanco() {
  banco = criarBanco();
}

// ---------- utilidades da API ----------
class ErroApi extends Error {
  constructor(status, erro, detalhes) {
    super(erro);
    this.status = status;
    this.corpo = detalhes ? { erro, detalhes } : { erro };
  }
}
const usuarioAtual = () => banco.usuarios.find((u) => u.id === banco.sessao) || null;
function exigir(...perfis) {
  const u = usuarioAtual();
  if (!u) throw new ErroApi(401, "nao_autenticado");
  if (!perfis.includes(u.perfil)) throw new ErroApi(403, "sem_permissao");
  return u;
}
const estDe = (id) => banco.ests.find((e) => e.id === id);
const lotesDoEst = (estId) => {
  const disps = new Set(banco.dispositivos.filter((d) => d.est === estId).map((d) => d.id));
  return banco.lotes.filter((l) => disps.has(l.dispositivo));
};
const identificadorDe = (dispId) => banco.dispositivos.find((d) => d.id === dispId)?.identificador;
const statusLote = (l) => (l.origem_fruto && l.quantidade_rasas != null ? "completo" : "incompleto");

function meJson(u) {
  const est = u.est ? estDe(u.est) : null;
  return { id: u.id, nome: u.nome, perfil: u.perfil,
    estabelecimento: est ? { nome: est.nome, slug_qr: est.slug_qr } : null, termo_aceito: u.termo };
}

function loteJson(l, completoCiclo = true) {
  const c = l.ciclo;
  const ciclo = completoCiclo
    ? { inicio: isoUtc(c.inicio), fim: isoUtc(c.fim), temp_min: c.temp_min, temp_max: c.temp_max,
      segundos_acima_80: c.segundos_acima_80, status: c.status, relogio_divergente: c.relogio_divergente }
    : { inicio: isoUtc(c.inicio), temp_max: c.temp_max, segundos_acima_80: c.segundos_acima_80, status: c.status,
      relogio_divergente: c.relogio_divergente };
  return { codigo: l.codigo, status: statusLote(l), origem_fruto: l.origem_fruto, quantidade_rasas: l.quantidade_rasas,
    catacao: l.catacao, sanitizacao: l.sanitizacao, resfriamento: l.resfriamento, ciclo };
}

function lerData(texto, campo) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto) || Number.isNaN(Date.parse(texto))) {
    throw new ErroApi(400, "data_invalida", { campo, formato: "AAAA-MM-DD" });
  }
  return texto;
}
function periodo(params, padraoDias = 30) {
  const ate = params.get("ate") ? lerData(params.get("ate"), "ate") : hoje();
  const de = params.get("de") ? lerData(params.get("de"), "de") : somarDias(ate, -(padraoDias - 1));
  if (de > ate) throw new ErroApi(422, "periodo_invalido", { motivo: "'de' depois de 'ate'" });
  if ((Date.parse(ate) - Date.parse(de)) / DIA + 1 > PERIODO_MAXIMO_DIAS) {
    throw new ErroApi(422, "periodo_muito_longo", { maximo_dias: PERIODO_MAXIMO_DIAS });
  }
  return { de, ate, ini: inicioDoDia(de), fim: inicioDoDia(somarDias(ate, 1)) };
}

function resumoPorDia(estId, de, ate) {
  const dias = [];
  for (let d = ate; d >= de; d = somarDias(d, -1)) {
    const doDia = lotesDoEst(estId).filter((l) => diaLocal(l.ciclo.inicio) === d);
    const ultimo = doDia.reduce((m, l) => Math.max(m, l.ciclo.inicio), 0);
    const completos = doDia.filter((l) => statusLote(l) === "completo");
    dias.push({ data: d, ciclos: doDia.length, aprovados: doDia.filter((l) => l.ciclo.status === "aprovado").length,
      reprovados: doDia.filter((l) => l.ciclo.status === "reprovado").length, ultimo: ultimo || null,
      lotes_completos: completos.length, rasas_declaradas: completos.reduce((s, l) => s + Number(l.quantidade_rasas), 0) });
  }
  return dias;
}

function lacunas(estId, { recebidoAntesDe, ini, fim } = {}) {
  const resultado = [];
  for (const disp of banco.dispositivos.filter((d) => estId == null || d.est === estId)) {
    const ordenados = banco.lotes.filter((l) => l.dispositivo === disp.id).sort((a, b) => a.contador - b.contador);
    for (let i = 1; i < ordenados.length; i++) {
      const anterior = ordenados[i - 1].contador;
      const atual = ordenados[i];
      if (atual.contador - anterior <= 1) continue;
      if (recebidoAntesDe != null && atual.ciclo.recebido > recebidoAntesDe) continue;
      if (ini != null && (atual.ciclo.inicio < ini || atual.ciclo.inicio >= fim)) continue;
      resultado.push({ est: disp.est, inicio: atual.ciclo.inicio,
        descricao: `${disp.identificador}: contadores ${anterior + 1} a ${atual.contador - 1} ausentes` });
    }
  }
  return resultado;
}

function calcularAlertas() {
  const momento = agora();
  const h = hoje();
  const alertas = [];
  const alerta = (est, tipo, detalhe, desde) => alertas.push({ estabelecimento: { id: est.id, nome: est.nome }, tipo,
    detalhe, desde });
  for (const est of banco.ests) {
    const situacao = situacaoLicenca(est.licenca_validade);
    if (situacao === "vencida") alerta(est, "licenca_vencida", `Licença ${est.licenca_numero} vencida`, est.licenca_validade);
    else if (situacao === "vence_em_breve") {
      alerta(est, "licenca_vence_em_breve", `Licença ${est.licenca_numero} vence em ${dataBr(est.licenca_validade)}`, h);
    }
  }
  for (const est of banco.ests) {
    const ultimo = lotesDoEst(est.id).reduce((m, l) => Math.max(m, l.ciclo.inicio), 0);
    if (!ultimo || ultimo < momento - 3 * DIA) {
      alerta(est, "sem_registro", ultimo ? `Último ciclo em ${dataBr(diaLocal(ultimo))}` : "Nenhum ciclo registrado",
        diaLocal(ultimo || est.criado));
    }
  }
  for (const disp of banco.dispositivos) {
    if (!disp.ultimo_contato || disp.ultimo_contato < momento - 2 * DIA) {
      alerta(estDe(disp.est), "dispositivo_sem_contato", disp.ultimo_contato
        ? `${disp.identificador}: último contato em ${dataBr(diaLocal(disp.ultimo_contato))}`
        : `${disp.identificador}: nunca se comunicou`, diaLocal(disp.ultimo_contato || momento));
    }
  }
  const janelaIni = inicioDoDia(somarDias(h, -6));
  for (const est of banco.ests) {
    const recentes = lotesDoEst(est.id).filter((l) => l.ciclo.inicio >= janelaIni);
    const reprovados = recentes.filter((l) => l.ciclo.status === "reprovado");
    const divergentes = recentes.filter((l) => l.ciclo.relogio_divergente);
    const menorDia = (lista) => lista.map((l) => diaLocal(l.ciclo.inicio)).sort()[0];
    if (reprovados.length) {
      alerta(est, "ciclos_reprovados", `${reprovados.length} ciclo(s) reprovado(s) nos últimos 7 dias`, menorDia(reprovados));
    }
    if (divergentes.length) {
      alerta(est, "relogio_divergente", `${divergentes.length} ciclo(s) com relógio do dispositivo fora de hora`,
        menorDia(divergentes));
    }
    const recusas = banco.recusas.filter((r) => r.est === est.id && r.quando >= janelaIni);
    if (recusas.length) {
      const motivos = [...new Set(recusas.map((r) => r.motivo))].sort().join(", ");
      alerta(est, "envios_recusados", `${recusas.length} ciclo(s) recusado(s) pela API nos últimos 7 dias (${motivos})`,
        recusas.map((r) => diaLocal(r.quando)).sort()[0]);
    }
  }
  for (const lacuna of lacunas(null, { recebidoAntesDe: momento - HORA })) {
    alerta(estDe(lacuna.est), "lacuna_contador", lacuna.descricao, diaLocal(lacuna.inicio));
  }
  return alertas;
}

// ---------- rotas ----------
const LIMITE_LOGIN = 5;

async function rotear(metodo, caminho, params, corpo) {
  let m;
  if (metodo === "POST" && caminho === "/api/login") {
    const momento = agora();
    banco.tentativasLogin = banco.tentativasLogin.filter((t) => t > momento - 60_000);
    if (banco.tentativasLogin.length >= LIMITE_LOGIN) throw new ErroApi(429, "muitas_tentativas");
    banco.tentativasLogin.push(momento);
    const u = banco.usuarios.find((x) => x.email === String(corpo?.email || "").trim().toLowerCase());
    if (!u || corpo?.senha !== SENHA) throw new ErroApi(401, "credenciais_invalidas");
    banco.sessao = u.id;
    return [200, meJson(u)];
  }
  if (metodo === "POST" && caminho === "/api/logout") {
    banco.sessao = null;
    return [204, null];
  }
  if (metodo === "GET" && caminho === "/api/me") {
    const u = usuarioAtual();
    if (!u) throw new ErroApi(401, "nao_autenticado");
    return [200, meJson(u)];
  }
  if (metodo === "POST" && caminho === "/api/batedor/termo") {
    const u = exigir("batedor");
    u.termo = true;
    return [200, { termo_aceito: true, termo_aceito_em: isoUtc(agora()) }];
  }
  if (metodo === "GET" && caminho === "/api/batedor/resumo") {
    const u = exigir("batedor");
    const est = estDe(u.est);
    const lotes = lotesDoEst(est.id).sort((a, b) => b.ciclo.inicio - a.ciclo.inicio);
    const doDia = lotes.filter((l) => diaLocal(l.ciclo.inicio) === hoje());
    const pendentes = lotes.filter((l) => statusLote(l) === "incompleto");
    const ultimo = lotes[0];
    return [200, {
      estabelecimento: { nome: est.nome, licenca_validade: est.licenca_validade,
        licenca_situacao: situacaoLicenca(est.licenca_validade) },
      hoje: { data: hoje(), aprovados: doDia.filter((l) => l.ciclo.status === "aprovado").length,
        reprovados: doDia.filter((l) => l.ciclo.status === "reprovado").length },
      ultimo_ciclo: ultimo ? { codigo: ultimo.codigo, inicio: isoUtc(ultimo.ciclo.inicio), temp_max: ultimo.ciclo.temp_max,
        segundos_acima_80: ultimo.ciclo.segundos_acima_80, status: ultimo.ciclo.status } : null,
      lotes_a_completar: pendentes.slice(0, 100).map((l) => ({ codigo: l.codigo, inicio: isoUtc(l.ciclo.inicio),
        status_ciclo: l.ciclo.status })),
      total_a_completar: pendentes.length,
    }];
  }
  if ((m = caminho.match(/^\/api\/lotes\/([^/]+)$/))) {
    const u = exigir("batedor");
    const lote = lotesDoEst(u.est).find((l) => l.codigo === decodeURIComponent(m[1]));
    if (!lote) throw new ErroApi(404, "nao_encontrado");
    if (metodo === "GET") return [200, loteJson(lote)];
    if (metodo === "PATCH") {
      const novos = {};
      if ("origem_fruto" in corpo) {
        const texto = corpo.origem_fruto == null ? null : String(corpo.origem_fruto).trim() || null;
        if (texto && texto.length > 150) throw new ErroApi(422, "texto_muito_longo", { campo: "origem_fruto", maximo: 150 });
        novos.origem_fruto = texto;
      }
      if ("quantidade_rasas" in corpo) {
        const v = corpo.quantidade_rasas;
        if (v == null || v === "") novos.quantidade_rasas = null;
        else {
          const q = Math.round(Number(v) * 100) / 100;
          if (Number.isNaN(q)) throw new ErroApi(400, "corpo_invalido", { campo: "quantidade_rasas" });
          if (q < 0.01 || q > 9999.99) {
            throw new ErroApi(422, "valor_fora_do_limite", { campo: "quantidade_rasas", minimo: 0.01, maximo: 9999.99 });
          }
          novos.quantidade_rasas = q;
        }
      }
      for (const campo of ["catacao", "sanitizacao", "resfriamento"]) {
        if (campo in corpo) novos[campo] = Boolean(corpo[campo]);
      }
      Object.assign(lote, novos);
      return [200, loteJson(lote)];
    }
  }
  if (metodo === "GET" && caminho === "/api/batedor/lotes") {
    const u = exigir("batedor");
    const p = periodo(params);
    const status = params.get("status");
    const pagina = Math.max(1, Number(params.get("pagina") || 1));
    let lista = lotesDoEst(u.est).filter((l) => l.ciclo.inicio >= p.ini && l.ciclo.inicio < p.fim)
      .sort((a, b) => b.ciclo.inicio - a.ciclo.inicio);
    if (status) lista = lista.filter((l) => statusLote(l) === status);
    return [200, { de: p.de, ate: p.ate, pagina, por_pagina: 50, total: lista.length,
      itens: lista.slice((pagina - 1) * 50, pagina * 50).map((l) => loteJson(l, false)) }];
  }
  if (metodo === "GET" && caminho === "/api/batedor/relatorio.pdf") {
    exigir("batedor");
    throw new ErroApi(503, "indisponivel_na_demo");
  }
  if ((m = caminho.match(/^\/api\/publico\/([^/]+)$/)) && metodo === "GET") {
    const est = banco.ests.find((e) => e.slug_qr === decodeURIComponent(m[1]));
    if (!est) throw new ErroApi(404, "nao_encontrado");
    const h = hoje();
    if (params.get("origem") === "qr") {
      const chave = `${est.id}|${h}`;
      banco.acessos[chave] = (banco.acessos[chave] || 0) + 1;
    }
    const vistorias = banco.vistorias.filter((v) => v.est === est.id).map((v) => v.data).sort();
    return [200, {
      nome: est.nome, endereco: est.endereco,
      licenca: { validade: est.licenca_validade, situacao: situacaoLicenca(est.licenca_validade) },
      curso_casa_acai_em: est.curso_casa_acai_em, ultima_vistoria: vistorias.at(-1) || null,
      dias: resumoPorDia(est.id, somarDias(h, -(DIAS_PAGINA_PUBLICA - 1)), h).map((d) => ({ data: d.data,
        aprovados: d.aprovados, reprovados: d.reprovados, ultimo: d.ultimo ? horaLocal(d.ultimo) : null })),
      aviso: AVISO_PUBLICO,
    }];
  }
  if (metodo === "GET" && caminho === "/api/fiscal/alertas") {
    exigir("fiscal", "admin");
    return [200, calcularAlertas()];
  }
  if (metodo === "GET" && caminho === "/api/fiscal/estabelecimentos") {
    exigir("fiscal", "admin");
    const busca = (params.get("busca") || "").trim().toLowerCase();
    const alertas = calcularAlertas();
    return [200, banco.ests.filter((e) => !busca || e.nome.toLowerCase().includes(busca))
      .sort((a, b) => a.nome.localeCompare(b.nome)).map((e) => {
        const ultimo = lotesDoEst(e.id).reduce((x, l) => Math.max(x, l.ciclo.inicio), 0);
        const contato = banco.dispositivos.filter((d) => d.est === e.id).reduce((x, d) => Math.max(x, d.ultimo_contato || 0), 0);
        return { id: e.id, nome: e.nome, endereco: e.endereco, licenca_validade: e.licenca_validade,
          licenca_situacao: situacaoLicenca(e.licenca_validade), ultimo_ciclo: ultimo ? isoUtc(ultimo) : null,
          ultimo_contato: contato ? isoUtc(contato) : null,
          alertas: alertas.filter((a) => a.estabelecimento.id === e.id).length };
      })];
  }
  if ((m = caminho.match(/^\/api\/fiscal\/estabelecimentos\/(\d+)$/)) && metodo === "GET") {
    exigir("fiscal", "admin");
    const est = estDe(Number(m[1]));
    if (!est) throw new ErroApi(404, "nao_encontrado");
    const p = periodo(params);
    const lotes = lotesDoEst(est.id).filter((l) => l.ciclo.inicio >= p.ini && l.ciclo.inicio < p.fim)
      .sort((a, b) => b.ciclo.inicio - a.ciclo.inicio);
    const acessos = Object.entries(banco.acessos).map(([k, total]) => ({ est: Number(k.split("|")[0]), data: k.split("|")[1], total }))
      .filter((a) => a.est === est.id && a.data >= p.de && a.data <= p.ate).sort((a, b) => a.data.localeCompare(b.data));
    return [200, {
      estabelecimento: { id: est.id, nome: est.nome, endereco: est.endereco, licenca_numero: est.licenca_numero,
        licenca_validade: est.licenca_validade, licenca_situacao: situacaoLicenca(est.licenca_validade),
        curso_casa_acai_em: est.curso_casa_acai_em, slug_qr: est.slug_qr },
      periodo: { de: p.de, ate: p.ate },
      dispositivos: banco.dispositivos.filter((d) => d.est === est.id)
        .map((d) => ({ identificador: d.identificador, ultimo_contato: d.ultimo_contato ? isoUtc(d.ultimo_contato) : null })),
      lotes: lotes.slice(0, 200).map((l) => ({ ...loteJson(l, false), dispositivo: identificadorDe(l.dispositivo),
        contador: l.contador })),
      vistorias: banco.vistorias.filter((v) => v.est === est.id).sort((a, b) => b.data.localeCompare(a.data))
        .map((v) => ({ id: v.id, data: v.data, resultado: v.resultado, observacoes: v.observacoes,
          fiscal: { id: v.fiscal, nome: banco.usuarios.find((u) => u.id === v.fiscal)?.nome } })),
      por_dia: resumoPorDia(est.id, p.de, p.ate).map((d) => ({ data: d.data, ciclos: d.ciclos, aprovados: d.aprovados,
        reprovados: d.reprovados, lotes_completos: d.lotes_completos, rasas_declaradas: d.rasas_declaradas })),
      lacunas: lacunas(est.id, { ini: p.ini, fim: p.fim }).map((l) => l.descricao),
      recusas: banco.recusas.filter((r) => r.est === est.id && r.quando >= p.ini && r.quando < p.fim)
        .sort((a, b) => b.quando - a.quando)
        .map((r) => ({ quando: isoUtc(r.quando), dispositivo: r.dispositivo, codigo: r.codigo, motivo: r.motivo })),
      acessos_qr: { total: acessos.reduce((s, a) => s + a.total, 0), por_dia: acessos.map((a) => ({ data: a.data, total: a.total })) },
    }];
  }
  if ((m = caminho.match(/^\/api\/fiscal\/estabelecimentos\/(\d+)\/vistorias$/)) && metodo === "POST") {
    const u = exigir("fiscal", "admin");
    const est = estDe(Number(m[1]));
    if (!est) throw new ErroApi(404, "nao_encontrado");
    const data = lerData(String(corpo?.data || ""), "data");
    if (data > hoje()) throw new ErroApi(422, "data_futura", { campo: "data" });
    const resultado = String(corpo?.resultado || "").trim();
    if (!resultado) throw new ErroApi(422, "campo_obrigatorio", { campo: "resultado" });
    const v = { id: banco.vistorias.length + 1, est: est.id, data, resultado,
      observacoes: String(corpo?.observacoes || "").trim() || null, fiscal: u.id };
    banco.vistorias.push(v);
    return [201, { id: v.id, data: v.data, resultado: v.resultado, observacoes: v.observacoes,
      fiscal: { id: u.id, nome: u.nome } }];
  }
  if (metodo === "POST" && caminho === "/api/ciclos") return [200, await receberCiclos(corpo)];
  throw new ErroApi(404, "nao_encontrado");
}

// ---------- POST /api/ciclos (seção 7 do plano) ----------
const RE_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$/;

async function receberCiclos(corpo) {
  const { dispositivo: ident, enviado_em: enviadoEm, assinatura_envio: assinaturaEnvio, ciclos } = corpo || {};
  if (typeof ident !== "string" || !RE_ISO.test(enviadoEm || "") || !/^[0-9a-f]{64}$/.test(assinaturaEnvio || "")
      || !Array.isArray(ciclos) || ciclos.length > 50) {
    throw new ErroApi(400, "envelope_invalido");
  }
  const disp = banco.dispositivos.find((d) => d.identificador === ident);
  if (!disp || (await assinarEnvio(ident, enviadoEm, disp.chave)) !== assinaturaEnvio) {
    throw new ErroApi(401, "assinatura_invalida");
  }
  const momento = agora();
  const divergente = Math.abs(Date.parse(enviadoEm) - momento) > TOLERANCIA_RELOGIO_MS;
  const recebidos = [];
  const recusados = [];
  const recusar = (codigo, motivo) => {
    recusados.push({ codigo, motivo });
    banco.recusas.push({ est: disp.est, dispositivo: ident, codigo, motivo, quando: momento });
  };
  for (const c of ciclos) {
    const codigoEsperado = `${ident}-${String(c.contador).padStart(6, "0")}`;
    if (c.codigo !== codigoEsperado) { recusar(c.codigo ?? null, "codigo_invalido"); continue; }
    const inicio = Date.parse(c.inicio);
    const fim = Date.parse(c.fim);
    if (!Number.isInteger(c.contador) || c.contador < 1 || !RE_ISO.test(c.inicio) || !RE_ISO.test(c.fim) || fim < inicio
        || !(c.temp_min <= c.temp_max)) { recusar(c.codigo, "formato_invalido"); continue; }
    if (!["aprovado", "reprovado"].includes(c.status) || (c.status === "aprovado" && c.segundos_acima_80 < 10)) {
      recusar(c.codigo, "status_inconsistente"); continue;
    }
    if ((await assinarCiclo(c, disp.chave)) !== c.assinatura) { recusar(c.codigo, "assinatura_invalida"); continue; }
    const existente = banco.lotes.find((l) => l.codigo === c.codigo);
    if (existente) {
      if (existente.ciclo.assinatura === c.assinatura) recebidos.push(c.codigo); // reenvio: não duplica
      else recusar(c.codigo, "conflito");
      continue;
    }
    banco.lotes.push({ codigo: c.codigo, dispositivo: disp.id, contador: c.contador, origem_fruto: null,
      quantidade_rasas: null, catacao: false, sanitizacao: false, resfriamento: false,
      ciclo: { inicio, fim, temp_min: Number(c.temp_min), temp_max: Number(c.temp_max),
        segundos_acima_80: c.segundos_acima_80, status: c.status, relogio_divergente: divergente,
        assinatura: c.assinatura, recebido: momento } });
    recebidos.push(c.codigo);
  }
  disp.ultimo_contato = momento;
  return { recebidos, recusados, hora_servidor: isoUtc(momento) };
}

// ---------- ponto de entrada: o mesmo jeito que o fetch chamaria o Flask ----------
export async function atender(metodo, url, corpo) {
  const endereco = new URL(url, "https://demo.oriki");
  try {
    const [status, resposta] = await rotear(metodo.toUpperCase(), endereco.pathname, endereco.searchParams, corpo ?? {});
    return { status, corpo: resposta };
  } catch (erro) {
    if (erro instanceof ErroApi) return { status: erro.status, corpo: erro.corpo };
    console.error(erro);
    return { status: 500, corpo: { erro: "erro_interno" } };
  }
}
