// OR-19: alterações de lote que não chegaram ao servidor ficam no IndexedDB do celular e são
// reenviadas quando a conexão volta. O PATCH é idempotente, então reenviar é seguro.
import { useEffect, useState } from "react";
import { ErroApi, salvarLote } from "./api.js";

const BANCO = "oriki";
const LOJA = "fila";
const EVENTO = "oriki:fila";
const INTERVALO_MS = 30_000;
// Recusas que não mudam com reenvio (dado inválido, lote de outro ponto): saem da fila.
const DEFINITIVOS = new Set([400, 404, 409, 413, 415, 422]);

function abrir() {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(BANCO, 1);
    pedido.onupgradeneeded = () => pedido.result.createObjectStore(LOJA, { keyPath: "codigo" });
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(pedido.error);
  });
}

async function operar(modo, acao) {
  const banco = await abrir();
  try {
    return await new Promise((resolve, reject) => {
      const transacao = banco.transaction(LOJA, modo);
      const pedido = acao(transacao.objectStore(LOJA));
      transacao.oncomplete = () => resolve(pedido.result);
      transacao.onerror = () => reject(transacao.error);
    });
  } finally {
    banco.close();
  }
}

const avisar = () => window.dispatchEvent(new Event(EVENTO));

export const listarFila = () => operar("readonly", (loja) => loja.getAll());
export const itemDaFila = (codigo) => operar("readonly", (loja) => loja.get(codigo));

async function guardar(codigo, campos) {
  // Uma entrada por lote: salvar de novo substitui a versão anterior.
  await operar("readwrite", (loja) => loja.put({ codigo, campos, salvo_em: new Date().toISOString() }));
  avisar();
}

// Só remove se ninguém salvou uma versão mais nova do lote enquanto o envio estava em curso.
async function removerSeIgual(codigo, salvoEm) {
  const atual = await itemDaFila(codigo);
  if (!atual || (salvoEm && atual.salvo_em !== salvoEm)) return;
  await operar("readwrite", (loja) => loja.delete(codigo));
  avisar();
}

export function semConexao(erro) {
  return erro instanceof TypeError || (erro instanceof ErroApi && erro.erro === "offline");
}

// Salva no servidor; sem internet, guarda no celular. Devolve { lote } ou { enfileirado: true }.
export async function salvarComFila(codigo, campos) {
  try {
    const lote = await salvarLote(codigo, campos);
    await removerSeIgual(codigo).catch(() => {}); // a versão antiga da fila não pode sobrescrever esta
    return { lote };
  } catch (erro) {
    if (!semConexao(erro)) throw erro;
    await guardar(codigo, campos);
    return { enfileirado: true };
  }
}

async function enviarFila() {
  for (const item of await listarFila()) {
    try {
      await salvarLote(item.codigo, item.campos);
    } catch (erro) {
      if (erro instanceof ErroApi && DEFINITIVOS.has(erro.status)) {
        console.warn(`Lote ${item.codigo} recusado (${erro.erro}); saiu da fila.`);
      } else {
        return; // sem conexão ou sessão expirada: tenta de novo depois
      }
    }
    await removerSeIgual(item.codigo, item.salvo_em);
  }
}

let emAndamento = null;

export function sincronizar() {
  emAndamento ??= enviarFila()
    .catch(() => {}) // IndexedDB indisponível (aba anônima): não há fila para enviar
    .finally(() => {
      emAndamento = null;
    });
  return emAndamento;
}

export function iniciarSincronizacao() {
  sincronizar();
  window.addEventListener("online", sincronizar);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && sincronizar());
  setInterval(sincronizar, INTERVALO_MS);
}

// Lotes que estão no celular esperando internet; atualiza sozinho quando a fila muda.
export function useFila() {
  const [itens, setItens] = useState([]);
  useEffect(() => {
    let ativo = true;
    const ler = () => listarFila().then((lista) => ativo && setItens(lista)).catch(() => {});
    ler();
    window.addEventListener(EVENTO, ler);
    return () => {
      ativo = false;
      window.removeEventListener(EVENTO, ler);
    };
  }, []);
  return itens;
}
