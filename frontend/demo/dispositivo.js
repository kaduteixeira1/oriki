// ESP32 de mentira: a mesma lógica do firmware/oriki_esp32 (branqueamento.ino, fila e envio), em JavaScript,
// ligada a um tanque simulado. Assina cada ciclo com HMAC-SHA256 e envia para o servidor da demonstração
// pelo mesmo contrato do POST /api/ciclos (seção 7 do plano).
import { assinarCiclo, assinarEnvio, atender, CHAVE_DEMO } from "./servidor.js";

const LIMIAR_C = 80;
const TEMPO_MIN_S = 10;
const IMERSAO_MAX_MS = 60_000;
const TEMPO_RESULTADO_MS = 3000;
const INTERVALO_ENVIO_MS = 5 * 60_000;
const ENVIO_APOS_CICLO_MS = 10_000;
const MAX_POR_ENVIO = 50;
const AMBIENTE = 28;
const OFFSET_BELEM = -3 * 3_600_000;

const ESTADOS = { OCIOSO: "parado", PREPARANDO: "preparando", IMERSAO: "imersão", RESULTADO: "resultado",
  TERMOMETRO: "termômetro" };

function isoBelem(ms) {
  return new Date(Math.floor(ms / 1000) * 1000 + OFFSET_BELEM).toISOString().slice(0, 19) + "-03:00";
}

export class Dispositivo {
  constructor({ identificador = "ORK01", chave = CHAVE_DEMO, contadorInicial = 31 } = {}) {
    this.identificador = identificador;
    this.chave = chave;
    this.ouvintes = new Set();
    this.serial = [];
    this.eventos = [];
    this.tanque = { temperatura: 86, setpoint: 86, aquecedor: true, esquentando: false, cesto: false, queda: 3,
      sensor: true, manual: null };
    this.proximoContador = contadorInicial;
    this.pendentes = [];
    this.enviados = 0;
    this.recusados = [];
    this.wifi = true;
    this.rtcOffset = 0; // ms somados à hora real (o DS3231 adiantado ou atrasado)
    this.estado = "OCIOSO";
    this.leds = { verde: false, vermelho: false };
    this.buzzerAte = 0;
    this.ultimoEnvio = null;
    this.proximoEnvio = Date.now() + 3000;
    this.enviando = false;
    this.estavaConectado = true;
    this.lote = null; // ciclo em andamento
    this.automatico = null;
    this.ultimoPrint = 0;
    this.ultimoToque = 0;
    this.ultimoPasso = Date.now();
    this.prontoAvisado = false;
    this.print("Oriki ORK01 ligado. Toque o botao para um novo lote. Digite 'ajuda' para os comandos.");
    this.relogio = setInterval(() => this.passo(), 50);
  }

  desligar() {
    clearInterval(this.relogio);
  }

  // ---------- avisos para a tela ----------
  assinar(funcao) {
    this.ouvintes.add(funcao);
    return () => this.ouvintes.delete(funcao);
  }
  avisar() {
    this.ouvintes.forEach((f) => f());
  }
  print(linha) {
    this.serial.push(linha);
    if (this.serial.length > 300) this.serial.splice(0, this.serial.length - 300);
    this.avisar();
  }
  evento(texto) {
    const hora = new Date().toLocaleTimeString("pt-BR", { timeZone: "America/Belem" });
    this.eventos.unshift(`${hora} ${texto}`);
    this.eventos.length = Math.min(this.eventos.length, 30);
    this.avisar();
  }
  bip(ms) {
    this.buzzerAte = Date.now() + ms;
  }

  // ---------- tanque (mesma física da bancada.py) ----------
  fisica(dt) {
    const t = this.tanque;
    if (t.manual != null) {
      t.temperatura = t.manual;
      t.esquentando = false;
      return;
    }
    if (t.aquecedor) {
      if (t.temperatura < t.setpoint - 0.4) t.esquentando = true;
      else if (t.temperatura > t.setpoint + 0.4) t.esquentando = false;
    } else t.esquentando = false;
    let variacao = -0.008 * (t.temperatura - AMBIENTE);
    if (t.esquentando) variacao += 0.8;
    if (t.cesto) variacao -= 0.12;
    t.temperatura = Math.min(100, Math.max(AMBIENTE - 5, t.temperatura + variacao * dt));
  }
  lerTemperatura() {
    if (!this.tanque.sensor) return NaN;
    const ruido = (Math.random() + Math.random() + Math.random() - 1.5) * 0.06;
    return Math.round((this.tanque.temperatura + ruido) * 16) / 16; // DS18B20: degraus de 0,0625 °C
  }
  mergulhar() {
    if (this.tanque.cesto) return;
    this.tanque.cesto = true;
    if (this.tanque.manual == null) this.tanque.temperatura -= this.tanque.queda;
    this.avisar();
  }
  retirar() {
    this.tanque.cesto = false;
    this.avisar();
  }

  // ---------- firmware: branqueamento.ino ----------
  agoraRtc() {
    return Date.now() + this.rtcOffset;
  }
  toque() {
    this.eventoBotao = "toque";
  }
  segurou() {
    this.eventoBotao = "segurou";
  }

  passo() {
    const agora = Date.now();
    this.fisica((agora - this.ultimoPasso) / 1000);
    this.ultimoPasso = agora;
    const ev = this.eventoBotao;
    this.eventoBotao = null;
    const t = this.lerTemperatura();
    this.tAtual = t;
    const semSensor = Number.isNaN(t);

    switch (this.estado) {
      case "OCIOSO":
        if (ev === "toque") {
          this.print("Novo lote: preparando. Aguarde a agua chegar a 80 C.");
          this.prontoAvisado = false;
          this.estado = "PREPARANDO";
        } else if (ev === "segurou") {
          this.print("Modo termometro (dois toques rapidos para sair).");
          this.ultimoToque = 0;
          this.estado = "TERMOMETRO";
        }
        break;
      case "PREPARANDO":
        if (semSensor) this.leds = { verde: false, vermelho: Math.floor(agora / 125) % 2 === 0 };
        else if (t < LIMIAR_C) {
          this.leds = { verde: false, vermelho: true };
          this.prontoAvisado = false;
        } else {
          this.leds = { verde: Math.floor(agora / 250) % 2 === 0, vermelho: false };
          if (!this.prontoAvisado) {
            this.prontoAvisado = true;
            this.bip(150);
            this.print("Agua pronta (>= 80 C). Mergulhe o cesto e toque o botao.");
          }
        }
        if (ev === "toque") {
          if (semSensor) this.print("Sensor sem leitura: confira o DS18B20.");
          else if (t < LIMIAR_C) this.print("Agua abaixo de 80 C. Aguarde aquecer.");
          else this.iniciarImersao(agora, t);
        } else if (ev === "segurou") {
          this.print("Lote cancelado (nada foi registrado).");
          this.voltarOcioso();
        }
        break;
      case "IMERSAO": {
        if (semSensor) {
          this.fecharCiclo(agora, "sensor sem leitura");
          break;
        }
        const c = Math.round(t * 100);
        this.lote.tMin = Math.min(this.lote.tMin, c);
        this.lote.tMax = Math.max(this.lote.tMax, c);
        const decorrido = agora - this.lote.inicioMs;
        if (!this.lote.dezAvisado && decorrido >= TEMPO_MIN_S * 1000) {
          this.lote.dezAvisado = true;
          this.bip(600);
          this.print("10 s acima de 80 C: pode tirar o cesto e tocar o botao.");
        }
        if (t < LIMIAR_C) this.fecharCiclo(agora, "agua abaixo de 80 C");
        else if (ev === "toque") this.fecharCiclo(agora, "cesto retirado");
        else if (decorrido >= IMERSAO_MAX_MS) this.fecharCiclo(agora, "tempo maximo");
        break;
      }
      case "RESULTADO":
        if (agora - this.inicioResultado >= TEMPO_RESULTADO_MS) {
          this.voltarOcioso();
          this.print("Pronto para o proximo lote.");
        }
        break;
      case "TERMOMETRO":
        if (semSensor) this.leds = { verde: false, vermelho: Math.floor(agora / 125) % 2 === 0 };
        else this.leds = { verde: t >= LIMIAR_C, vermelho: t < LIMIAR_C };
        if (ev === "toque") {
          if (this.ultimoToque && agora - this.ultimoToque <= 700) {
            this.print("Saindo do modo termometro.");
            this.voltarOcioso();
          } else this.ultimoToque = agora;
        }
        break;
      default:
    }
    if (["PREPARANDO", "IMERSAO", "TERMOMETRO"].includes(this.estado) && agora - this.ultimoPrint >= 1000) {
      this.ultimoPrint = agora;
      const prefixo = this.estado === "IMERSAO" ? `Imersao ${Math.floor((agora - this.lote.inicioMs) / 1000)} s | ` : "";
      this.print(`${prefixo}Temperatura: ${semSensor ? "sensor sem leitura" : `${t.toFixed(1)} C`}`);
    }
    this.envioLoop(agora);
    this.avisar();
  }

  voltarOcioso() {
    this.leds = { verde: false, vermelho: false };
    this.estado = "OCIOSO";
  }

  iniciarImersao(agora, t) {
    const contador = this.proximoContador++;
    this.lote = { contador, inicioMs: agora, inicioRtc: this.agoraRtc(), tMin: Math.round(t * 100),
      tMax: Math.round(t * 100), dezAvisado: false };
    this.print(`Imersao iniciada: ${this.codigo(contador)}`);
    this.leds = { verde: true, vermelho: false };
    this.estado = "IMERSAO";
  }

  codigo(contador) {
    return `${this.identificador}-${String(contador).padStart(6, "0")}`;
  }

  async fecharCiclo(agora, motivo) {
    const l = this.lote;
    const segundos = Math.min(Math.floor((agora - l.inicioMs) / 1000), 32767);
    const aprovado = segundos >= TEMPO_MIN_S && motivo !== "sensor sem leitura";
    this.inicioResultado = agora;
    this.estado = "RESULTADO";
    this.leds = aprovado ? { verde: true, vermelho: false } : { verde: false, vermelho: true };
    if (!aprovado) this.bip(800);
    const inicioIso = isoBelem(l.inicioRtc);
    const registro = { codigo: this.codigo(l.contador), contador: l.contador, inicio: inicioIso,
      fim: isoBelem(Date.parse(inicioIso) + segundos * 1000), temp_min: l.tMin / 100, temp_max: l.tMax / 100,
      segundos_acima_80: segundos, status: aprovado ? "aprovado" : "reprovado" };
    this.print(`REGISTRO ${registro.codigo} | ${segundos} s >= 80 C | min ${registro.temp_min.toFixed(2)} C | max `
      + `${registro.temp_max.toFixed(2)} C | ${aprovado ? "APROVADO" : "REPROVADO"} (${motivo}) | salvo na fila`);
    this.evento(`${registro.codigo} ${aprovado ? "aprovado" : "reprovado"} (${segundos} s). Envio em ~10 s.`);
    registro.assinatura = await assinarCiclo(registro, this.chave);
    this.pendentes.push(registro);
    this.envioAgendar(ENVIO_APOS_CICLO_MS);
  }

  // ---------- firmware: envio.ino ----------
  envioAgendar(ms) {
    this.proximoEnvio = Math.min(this.proximoEnvio, Date.now() + ms);
  }

  envioLoop(agora) {
    if (this.wifi && !this.estavaConectado && this.pendentes.length) {
      this.print("Wi-Fi de volta: enviando a fila.");
      this.envioAgendar(2000);
    }
    this.estavaConectado = this.wifi;
    if (["PREPARANDO", "IMERSAO"].includes(this.estado) || this.enviando) return;
    if (agora < this.proximoEnvio) return;
    this.proximoEnvio = agora + INTERVALO_ENVIO_MS;
    this.enviarAgora();
  }

  async enviarAgora() {
    if (!this.wifi) {
      this.print(`Sem Wi-Fi: ${this.pendentes.length} ciclo(s) seguem na fila.`);
      return;
    }
    this.enviando = true;
    try {
      const lote = this.pendentes.slice(0, MAX_POR_ENVIO);
      const enviadoEm = isoBelem(this.agoraRtc());
      const corpo = { dispositivo: this.identificador, enviado_em: enviadoEm,
        assinatura_envio: await assinarEnvio(this.identificador, enviadoEm, this.chave), ciclos: lote };
      const { status, corpo: r } = await atender("POST", "/api/ciclos", corpo);
      if (status !== 200) {
        this.print(`Envio falhou: HTTP ${status} (${r?.erro || "?"}).`);
        this.ultimoEnvio = `HTTP ${status} · ${r?.erro || "erro"}`;
        return;
      }
      const recebidos = new Set(r.recebidos);
      const recusados = new Map(r.recusados.map((x) => [x.codigo, x.motivo]));
      this.pendentes = this.pendentes.filter((c) => {
        if (recebidos.has(c.codigo)) {
          this.enviados += 1;
          return false;
        }
        if (recusados.has(c.codigo)) {
          this.recusados.push({ codigo: c.codigo, motivo: recusados.get(c.codigo) });
          this.print(`RECUSADO ${c.codigo}: ${recusados.get(c.codigo)}`);
          return false;
        }
        return true;
      });
      if (r.recusados.length) this.bip(300);
      const diferenca = Date.parse(r.hora_servidor) - this.agoraRtc();
      if (Math.abs(diferenca) > 120_000) {
        this.rtcOffset = 0;
        this.print(`Relogio corrigido pela hora do servidor (estava ${Math.round(-diferenca / 60000)} min fora).`);
      }
      this.print(`Envio: ${lote.length} ciclo(s) | ${r.recebidos.length} recebidos | ${r.recusados.length} recusados | `
        + `${this.pendentes.length} ainda pendentes`);
      this.ultimoEnvio = `${new Date().toLocaleTimeString("pt-BR", { timeZone: "America/Belem" })} · `
        + `${r.recebidos.length} recebido(s), ${r.recusados.length} recusado(s)`;
      if (lote.length) this.evento(`Envio para a API: ${r.recebidos.length} recebido(s), ${r.recusados.length} recusado(s)`);
      if (this.pendentes.length) this.envioAgendar(2000);
    } finally {
      this.enviando = false;
    }
  }

  // ---------- firmware: comandos.ino ----------
  comando(texto) {
    const c = texto.trim();
    if (!c) return;
    this.print(`> ${c}`);
    if (c === "ajuda") {
      ["Comandos:", "  fila ............. pendentes, enviados e recusados", "  enviar ........... envia a fila agora",
        "  adulterar N ...... altera o ciclo N na fila sem assinar (teste de integridade)"].forEach((l) => this.print(l));
    } else if (c === "fila") {
      this.print(`Pendentes: ${this.pendentes.length} | enviados: ${this.enviados} | recusados: ${this.recusados.length}`
        + ` | ultimo contador: ${this.proximoContador - 1}`);
      this.pendentes.slice(0, 10).forEach((p) => this.print(`  ${p.codigo} ${p.status} ${p.segundos_acima_80} s`));
    } else if (c === "enviar") {
      this.envioAgendar(0);
    } else if (/^adulterar \d+$/.test(c)) {
      const n = Number(c.split(" ")[1]);
      const alvo = this.pendentes.find((p) => p.contador === n);
      if (!alvo) this.print(`Ciclo ${n} nao esta na fila de pendentes (desligue o Wi-Fi antes de fazer o lote).`);
      else {
        alvo.status = "aprovado";
        alvo.segundos_acima_80 = Math.max(alvo.segundos_acima_80, 12);
        alvo.temp_max = +(alvo.temp_max + 2).toFixed(2);
        this.print(`Ciclo ${alvo.codigo} alterado na memoria sem nova assinatura (teste de integridade).`);
      }
    } else this.print("Comando desconhecido. Digite 'ajuda'.");
  }

  // ---------- controles da bancada ----------
  ligarWifi(ligado) {
    this.wifi = ligado;
    this.evento(ligado ? "Roteador ligado" : "Roteador desligado: o dispositivo fica offline");
  }
  ajustarRelogio(ms) {
    this.rtcOffset += ms;
    this.evento(`Relógio do dispositivo ${ms > 0 ? "adiantado" : "atrasado"} ${Math.abs(ms / 60000)} min`);
  }

  // Um lote inteiro, como o batedor faz: novo lote, cesto na água, toque aos 12 s (ou aos 5 s) e cesto fora.
  async loteCompleto(resultado) {
    if (this.automatico || this.estado !== "OCIOSO") return false;
    const imersao = resultado === "reprovado" ? 5 : 12;
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
    this.automatico = resultado;
    this.evento(`Lote ${resultado}: novo lote, cesto na água e toque no botão aos ${imersao} s`);
    try {
      Object.assign(this.tanque, { manual: null, aquecedor: true, setpoint: Math.max(this.tanque.setpoint, 86) });
      if (this.tanque.temperatura < 85) this.tanque.temperatura = 86;
      this.retirar();
      this.toque();
      await espera(1200);
      this.toque();
      await espera(150);
      this.mergulhar();
      await espera(imersao * 1000 + 200);
      if (this.estado === "IMERSAO") this.toque();
      await espera(1500);
      this.retirar();
    } finally {
      this.automatico = null;
      this.avisar();
    }
    return true;
  }

  rotuloEstado() {
    return ESTADOS[this.estado];
  }
}
