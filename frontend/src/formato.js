// Datas da API vêm em UTC ("2026-10-08T10:42:10Z"); a tela mostra sempre a hora de Belém.
const FUSO = "America/Belem";

export function horaLocal(iso) {
  return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
}

export function dataLocal(iso) {
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit", year: "numeric" });
}

export function diaMesLocal(iso) {
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit" });
}

// "2027-03-31" (data sem hora) → "31/03/2027", sem passar por Date para não mudar de dia com o fuso.
export function dataCurta(aaaaMmDd, comAno = true) {
  const [ano, mes, dia] = aaaaMmDd.split("-");
  return comAno ? `${dia}/${mes}/${ano}` : `${dia}/${mes}`;
}

// "Hoje" no fuso de Belém, como "AAAA-MM-DD" (o en-CA formata nessa ordem).
export function hojeEmBelem() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO }).format(new Date());
}

export function somarDias(aaaaMmDd, dias) {
  const [ano, mes, dia] = aaaaMmDd.split("-").map(Number);
  return new Date(Date.UTC(ano, mes - 1, dia + dias)).toISOString().slice(0, 10);
}

export function diasNoPeriodo(de, ate) {
  return Math.round((Date.parse(ate) - Date.parse(de)) / 86_400_000) + 1;
}

// OR-30: por que o ciclo foi reprovado, a partir do que o dispositivo mediu.
export function motivoReprovado(ciclo) {
  if (ciclo.temp_max < 80) return `A água não chegou a 80 °C (máxima de ${temperatura(ciclo.temp_max)}).`;
  return `A água esfriou antes dos 10 s: ficou só ${ciclo.segundos_acima_80} s a 80 °C ou mais.`;
}

export function temperatura(valor) {
  // Espaço que não quebra: "°C" nunca vai sozinho para a linha de baixo.
  return `${valor.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}\u00a0°C`;
}
