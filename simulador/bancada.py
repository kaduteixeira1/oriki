"""Bancada virtual do Oriki: roda o firmware (.ino) no PC com um tanque, botão, LEDs, buzzer e Wi-Fi de mentira.

    python bancada.py                                   # firmware/oriki_esp32, painel em http://localhost:8090
    python bancada.py firmware/oriki_tinkercad          # o sketch do Tinkercad (placa detectada: Uno)
    python bancada.py meu_sketch/ --api http://127.0.0.1:5000 --velocidade 2

O que a bancada faz:
  - compila o sketch com o núcleo de mentira (compilar.py) e liga o "dispositivo";
  - simula a água do tanque (aquecedor com termostato, queda de temperatura ao mergulhar o cesto);
  - leva os pedidos HTTP do firmware para a API de verdade (troca o endereço do firmware pelo --api);
  - para sketches sem Wi-Fi (Tinkercad), lê o JSON que o firmware imprime no Serial, envia para a API e
    responde "ok N" para cada ciclo recebido (a "ponte serial", que faz o papel do conferir_envio.py);
  - mostra tudo no painel e roda os testes do documento do projeto (cenarios.py).

Sem dependências fora da biblioteca padrão do Python (3.10+).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
import compilar  # noqa: E402

BELEM = timezone(timedelta(hours=-3))

# Pinos que o painel desenha como LED, buzzer e botão (os do circuito de cada placa).
PINOS_PADRAO = {
    "esp32": {"botao": 33, "verde": 26, "vermelho": 27, "laranja": None, "buzzer": 25},
    "uno": {"botao": 2, "verde": 4, "vermelho": 5, "laranja": 6, "buzzer": 8},
}


def agora_belem() -> datetime:
    return datetime.now(BELEM)


def detectar_placa(sketch: Path) -> str:
    """Pelos #include: Wi-Fi/HTTP/LittleFS = ESP32; EEPROM ou avr/ sem nada do ESP32 = Uno (Tinkercad)."""
    try:
        _, abas = compilar.abas_do_sketch(sketch)
        texto = "\n".join(a.read_text(encoding="utf-8", errors="replace") for a in abas)
    except compilar.ErroCompilacao:
        return "esp32"
    inclui = set(re.findall(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', texto, re.M))
    do_esp32 = {"WiFi.h", "HTTPClient.h", "LittleFS.h", "SPIFFS.h", "Preferences.h", "WiFiManager.h",
                "WiFiClientSecure.h", "mbedtls/md.h"}
    if inclui & do_esp32:
        return "esp32"
    if "EEPROM.h" in inclui or any(i.startswith("avr/") for i in inclui):
        return "uno"
    return "esp32"


# =====================================================================
# Tanque (física bem simples, o bastante para os testes do ciclo)
# =====================================================================
class Tanque:
    AMBIENTE = 28.0

    def __init__(self):
        self.temperatura = 86.0
        self.setpoint = 86.0
        self.aquecedor = True          # chave geral do aquecedor (o termostato liga e desliga)
        self.esquentando = False
        self.potencia = 0.8            # °C/s com o aquecedor ligando
        self.perda = 0.008             # perda para o ambiente, por °C acima dele, por segundo
        self.cesto_dentro = False
        self.queda = 3.0               # °C que caem ao mergulhar o cesto com o fruto
        self.carga = 0.12              # °C/s que o fruto tira enquanto está na água
        self.manual = None             # °C fixa (modo manual) ou None
        self.ruido = 0.05
        self.sensor_conectado = True

    def passo(self, dt: float):
        if self.manual is not None:
            self.temperatura = self.manual
            self.esquentando = False
            return
        if self.aquecedor:
            if self.temperatura < self.setpoint - 0.4:
                self.esquentando = True
            elif self.temperatura > self.setpoint + 0.4:
                self.esquentando = False
        else:
            self.esquentando = False
        variacao = -self.perda * (self.temperatura - self.AMBIENTE)
        if self.esquentando:
            variacao += self.potencia
        if self.cesto_dentro:
            variacao -= self.carga
        self.temperatura = min(100.0, max(self.AMBIENTE - 5, self.temperatura + variacao * dt))

    def leitura(self) -> float:
        return self.temperatura + random.gauss(0, self.ruido)

    def mergulhar(self):
        if not self.cesto_dentro:
            self.cesto_dentro = True
            if self.manual is None:
                self.temperatura -= self.queda

    def retirar(self):
        self.cesto_dentro = False

    def estado(self) -> dict:
        return {"temperatura": round(self.temperatura, 2), "setpoint": self.setpoint, "aquecedor": self.aquecedor,
                "esquentando": self.esquentando, "cesto_dentro": self.cesto_dentro, "queda": self.queda,
                "manual": self.manual, "sensor_conectado": self.sensor_conectado}


# =====================================================================
# Dispositivo: o firmware compilado rodando como processo filho
# =====================================================================
class Dispositivo:
    MAX_SERIAL = 4000

    def __init__(self, args):
        self.args = args
        self.trava = threading.RLock()
        self.sketch = Path(args.sketch).resolve()
        self.placa = args.placa if args.placa != "auto" else detectar_placa(self.sketch)
        self.pinos = dict(PINOS_PADRAO[self.placa])
        self.api = args.api.rstrip("/")
        self.backend = Path(args.backend).resolve()
        self.velocidade = args.velocidade
        self.tanque = Tanque()
        self.wifi = True
        self.ponte_serial = self.placa == "uno"
        self.envio_auto_s = 300 if self.placa == "uno" else 0
        self.acertar_hora = self.placa == "uno"
        self.proc: subprocess.Popen | None = None
        self.saida_fila: queue.Queue[str] = queue.Queue()
        self.serial: list[str] = []          # pedaços de texto, na ordem
        self.serial_base = 0                 # índice do primeiro pedaço guardado
        self.http: list[dict] = []           # últimos pedidos à API
        self.eventos: list[dict] = []        # reinício, compilação, avisos
        self.saidas: dict[int, int] = {}     # nível de cada pino de saída
        self.modos: dict[int, str] = {}
        self.tons: dict[int, dict] = {}      # pino -> {"f", "ate"}
        self.wifi_conectado = False
        self.compilacao = {"estado": "parado", "mensagem": ""}
        self.rodando = False
        self.botao_apertado = False
        self.linha_serial = ""               # para achar as linhas completas (ponte serial e cenários)
        self.ouvintes: list = []             # funções chamadas a cada linha completa do Serial
        self.ultimo_envio_auto = time.monotonic()
        self.inicio_real = time.monotonic()
        self.desligando = False
        self.pronto = threading.Event()      # o setup() terminou (o firmware pediu o primeiro toque)

    def aguardar_pronto(self, timeout: float = 8.0) -> bool:
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self.pronto.wait(0.1) and getattr(self, "_contador_uno", None) is None:
                time.sleep(0.3)
                if self.pronto.is_set():
                    return True
        return self.rodando

    @property
    def dados(self) -> Path:
        pasta = Path(self.args.dados) if self.args.dados else RAIZ / "dados" / f"{self.sketch.name}-{self.placa}"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    # ---------- ciclo de vida ----------
    def evento(self, tipo: str, texto: str):
        with self.trava:
            self.eventos.append({"t": time.time(), "tipo": tipo, "texto": texto})
            self.eventos = self.eventos[-200:]
        print(f"[bancada] {texto}", flush=True)

    def compilar_e_ligar(self):
        self.desligar()
        with self.trava:
            self.compilacao = {"estado": "compilando", "mensagem": f"Compilando {self.sketch.name} ({self.placa})…"}
        self.evento("compilacao", f"Compilando {self.sketch} para {self.placa}")
        try:
            binario = compilar.compilar(self.sketch, self.placa)
        except compilar.ErroCompilacao as erro:
            with self.trava:
                self.compilacao = {"estado": "erro", "mensagem": str(erro)}
            self.evento("erro", "O firmware não compilou (veja o painel).")
            print(erro, file=sys.stderr, flush=True)
            return False
        with self.trava:
            self.compilacao = {"estado": "ok", "mensagem": f"Compilado: {binario.name}"}
            self.binario = binario
        self.ligar()
        return True

    def ligar(self):
        ambiente = dict(os.environ, ORIKI_DADOS=str(self.dados), ORIKI_VELOCIDADE=str(self.velocidade),
                        ORIKI_TEMPERATURA=f"{self.tanque.temperatura:.2f}")
        self.proc = subprocess.Popen([str(self.binario)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=ambiente, cwd=str(self.dados),
                                     bufsize=0)
        with self.trava:
            self.saidas.clear()
            self.modos.clear()
            self.tons.clear()
            self.wifi_conectado = False
            self.linha_serial = ""
            self.rodando = True
            self.inicio_real = time.monotonic()
        self.pronto.clear()
        proc = self.proc
        threading.Thread(target=self._ler, args=(proc,), daemon=True).start()
        threading.Thread(target=self._ler_erros, args=(proc,), daemon=True).start()
        self.enviar(f"W {1 if self.wifi else 0}")
        self.enviar(f"D {1 if self.tanque.sensor_conectado else 0}")
        if self.botao_apertado:
            self.enviar(f"P {self.pinos['botao']} 0")
        self.evento("inicio", f"Dispositivo ligado ({self.placa}, velocidade {self.velocidade}x)")
        if getattr(self, "_contador_uno", None) is not None:
            threading.Thread(target=self._ajustar_contador_uno, daemon=True).start()
        elif self.acertar_hora:
            threading.Timer(0.6, lambda: self.serial_digitar(
                "hora " + agora_belem().strftime("%Y-%m-%d %H:%M:%S"))).start()

    def desligar(self):
        proc, self.proc = self.proc, None
        with self.trava:
            self.rodando = False
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    def reiniciar(self):
        """Como apertar o reset da placa: a memória (EEPROM/LittleFS/NVS) continua."""
        self.desligar()
        if getattr(self, "binario", None):
            self.ligar()

    def apagar_memoria(self, contador_inicial: int | None = None):
        self.desligar()
        for arquivo in sorted(self.dados.rglob("*"), reverse=True):
            if arquivo.is_file():
                arquivo.unlink()
            elif arquivo.is_dir():
                arquivo.rmdir()
        self.evento("aviso", "Memória do dispositivo apagada (EEPROM, LittleFS, NVS e ajuste do RTC).")
        if contador_inicial and contador_inicial > 1:
            self.preparar_contador(contador_inicial)
        if getattr(self, "binario", None):
            self.ligar()

    def recomecar_dados(self) -> dict:
        """O botão "Recomeçar os dados": seed.py --recriar no backend e memória nova (contador 31)."""
        pasta = self.backend
        python = next((p for p in (pasta / ".venv" / "Scripts" / "python.exe", pasta / ".venv" / "bin" / "python")
                       if p.exists()), Path(sys.executable))
        if not (pasta / "seed.py").exists():
            return {"erro": f"não achei {pasta / 'seed.py'} (use --backend com a pasta do backend)"}
        try:
            r = subprocess.run([str(python), "seed.py", "--recriar"], cwd=pasta, capture_output=True, text=True,
                               timeout=120, encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as erro:
            return {"erro": str(erro)}
        if r.returncode != 0:
            ultima = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["erro desconhecido"]
            self.evento("aviso", f"seed.py --recriar falhou: {ultima[0]}")
            return {"erro": f"{ultima[0]} (o banco está ligado? o iniciar.bat precisa estar aberto)"}
        self.evento("aviso", "Dados de exemplo recriados (seed.py --recriar).")
        self.apagar_memoria(31)
        return {"ok": True}

    def memoria_vazia(self) -> bool:
        return not any(p.is_file() for p in self.dados.rglob("*"))

    def preparar_contador(self, proximo: int):
        """Memória nova que continua a numeração (ex.: 31 depois dos 30 ciclos do seed.py).

        ESP32 (oriki_esp32): chave "contador" da NVS "oriki". Uno (oriki_tinkercad): o firmware formata a
        EEPROM no primeiro boot; a bancada depois grava o contador nos bytes 2..5, como o sketch faz.
        """
        ultimo = proximo - 1
        if self.placa == "esp32":
            nvs = self.dados / "nvs"
            nvs.mkdir(parents=True, exist_ok=True)
            (nvs / "oriki.txt").write_text(f"contador={ultimo}\n", encoding="utf-8")
            self.evento("aviso", f"Contador do dispositivo começa em {proximo}.")
        else:
            self._contador_uno = ultimo

    def _ajustar_contador_uno(self):
        ultimo = getattr(self, "_contador_uno", None)
        if ultimo is None:
            return
        self._contador_uno = None
        eeprom = self.dados / "eeprom.bin"
        time.sleep(1.0)
        self.desligar()
        dados = bytearray(eeprom.read_bytes()) if eeprom.exists() else bytearray()
        if len(dados) >= 6 and dados[0:2] == b"\x31\x4f":
            dados[2:6] = ultimo.to_bytes(4, "little")
            eeprom.write_bytes(bytes(dados))
            self.evento("aviso", f"Contador da EEPROM ajustado: o próximo ciclo é o {ultimo + 1}.")
        else:
            self.evento("erro", "Não reconheci a EEPROM deste sketch: o contador não foi ajustado.")
        self.ligar()

    def enviar(self, linha: str):
        proc = self.proc
        if not proc or proc.poll() is not None:
            return
        try:
            proc.stdin.write((linha + "\n").encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    # ---------- leitura do firmware ----------
    def _ler_erros(self, proc):
        for linha in proc.stderr:
            texto = linha.decode("utf-8", "replace").rstrip()
            if texto:
                self.evento("erro", f"stderr do firmware: {texto}")

    def _ler(self, proc):
        for bruto in proc.stdout:
            try:
                msg = json.loads(bruto.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            self._tratar(msg)
        codigo = proc.wait()
        if proc is self.proc and not self.desligando:
            with self.trava:
                self.rodando = False
            if codigo == 3:
                self.evento("inicio", "O firmware chamou ESP.restart(): religando.")
                self.ligar()
            else:
                self.evento("erro", f"O firmware parou (código {codigo}). Use Reiniciar no painel.")

    def _tratar(self, msg: dict):
        t = msg.get("t")
        if t == "s":
            self._serial(msg["d"])
        elif t == "p":
            with self.trava:
                self.saidas[msg["p"]] = msg["v"]
        elif t == "m":
            with self.trava:
                self.modos[msg["p"]] = msg["m"]
        elif t == "tom":
            with self.trava:
                if msg["f"]:
                    # duração em ms do firmware; 0 = até o noTone()
                    segundos = msg["d"] / 1000 / self.velocidade if msg["d"] else 3600
                    self.tons[msg["p"]] = {"f": msg["f"], "ate": time.monotonic() + segundos}
                else:
                    self.tons.pop(msg["p"], None)
        elif t == "h":
            threading.Thread(target=self._http, args=(msg,), daemon=True).start()
        elif t == "wifi":
            with self.trava:
                self.wifi_conectado = msg["conectado"]
        elif t == "rtc":
            self.evento("rtc", f"O firmware acertou o RTC (ajuste de {msg['ajuste']} s sobre a hora do PC)")
        elif t == "inicio":
            pass

    def _serial(self, texto: str):
        with self.trava:
            self.serial.append(texto)
            excesso = len(self.serial) - self.MAX_SERIAL
            if excesso > 0:
                del self.serial[:excesso]
                self.serial_base += excesso
            self.linha_serial += texto
            linhas = self.linha_serial.split("\n")
            self.linha_serial = linhas.pop()
            ouvintes = list(self.ouvintes)
        for linha in linhas:
            linha = linha.rstrip("\r")
            if not self.pronto.is_set() and ("Toque o botao" in linha or "pronto" in linha.lower()):
                if getattr(self, "_contador_uno", None) is None:
                    self.pronto.set()
            if self.ponte_serial and linha.startswith('{"dispositivo"'):
                threading.Thread(target=self._ponte, args=(linha,), daemon=True).start()
            for ouvinte in ouvintes:
                try:
                    ouvinte(linha)
                except Exception as erro:  # noqa: BLE001 - um cenário com erro não derruba a bancada
                    self.evento("erro", f"cenário: {erro}")

    def serial_digitar(self, texto: str):
        self.enviar("S " + texto)

    # ---------- rede ----------
    def url_destino(self, url: str) -> str:
        partes = urllib.parse.urlsplit(url)
        if self.args.usar_url_do_firmware:
            return url
        base = urllib.parse.urlsplit(self.api)
        return urllib.parse.urlunsplit((base.scheme, base.netloc, partes.path, partes.query, ""))

    def requisitar(self, metodo: str, url: str, cabecalhos: list, corpo: bytes | None) -> tuple[int, bytes]:
        pedido = urllib.request.Request(url, data=corpo, method=metodo)
        for nome, valor in cabecalhos:
            pedido.add_header(nome, valor)
        try:
            with urllib.request.urlopen(pedido, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as erro:
            return erro.code, erro.read()
        except (urllib.error.URLError, OSError) as erro:
            self.evento("erro", f"API fora do ar em {url}: {erro}")
            return -1, b""

    def _registrar_http(self, origem: str, metodo: str, url: str, corpo: str, status: int, resposta: bytes):
        try:
            enviado = json.loads(corpo) if corpo else None
        except json.JSONDecodeError:
            enviado = None
        try:
            recebido = json.loads(resposta) if resposta else None
        except json.JSONDecodeError:
            recebido = None
        item = {"t": time.time(), "origem": origem, "metodo": metodo, "url": url, "status": status,
                "n_ciclos": len(enviado.get("ciclos", [])) if isinstance(enviado, dict) else None,
                "recebidos": recebido.get("recebidos") if isinstance(recebido, dict) else None,
                "recusados": recebido.get("recusados") if isinstance(recebido, dict) else None,
                "corpo": corpo[:20000], "resposta": resposta.decode("utf-8", "replace")[:5000]}
        with self.trava:
            self.http.append(item)
            self.http = self.http[-60:]
        return recebido

    def _http(self, msg: dict):
        url = self.url_destino(msg["u"])
        corpo = msg.get("b") or ""
        if not self.wifi:
            status, resposta = -1, b""
        else:
            status, resposta = self.requisitar(msg["m"], url, msg.get("c") or [], corpo.encode() if corpo else None)
        self._registrar_http("firmware", msg["m"], url, corpo, status, resposta)
        self.enviar(f"H {msg['id']} {status} {resposta.hex() or '-'}")

    def _ponte(self, linha: str):
        """Tinkercad: o JSON impresso no Serial vai para a API; cada ciclo recebido vira 'ok N'."""
        if not self.wifi:
            self.evento("aviso", "Ponte serial: Wi-Fi desligado, o envio ficou só no Serial (como no Tinkercad).")
            return
        url = self.api + "/api/ciclos"
        status, resposta = self.requisitar("POST", url, [("Content-Type", "application/json")], linha.encode())
        recebido = self._registrar_http("ponte serial", "POST", url, linha, status, resposta)
        if status == 200 and isinstance(recebido, dict):
            for codigo in recebido.get("recebidos", []):
                time.sleep(0.25)
                self.serial_digitar(f"ok {codigo}")

    # ---------- relógio da física e envio automático ----------
    def laco_fisica(self):
        anterior = time.monotonic()
        while not self.desligando:
            time.sleep(0.1)
            agora = time.monotonic()
            dt = (agora - anterior) * self.velocidade
            anterior = agora
            with self.trava:
                self.tanque.passo(dt)
                leitura = self.tanque.leitura()
            self.enviar(f"T {leitura:.3f}")
            if (self.ponte_serial and self.envio_auto_s and self.wifi and self.rodando
                    and (agora - self.ultimo_envio_auto) * self.velocidade >= self.envio_auto_s):
                self.ultimo_envio_auto = agora
                self.serial_digitar("enviar")

    # ---------- painel ----------
    def estado(self, desde: int) -> dict:
        with self.trava:
            agora = time.monotonic()
            tons = {p: v["f"] for p, v in self.tons.items() if v["ate"] > agora}
            inicio = max(desde - self.serial_base, 0)
            buz = self.pinos.get("buzzer")
            return {
                "placa": self.placa, "sketch": str(self.sketch), "nome": self.sketch.name, "api": self.api,
                "velocidade": self.velocidade, "rodando": self.rodando, "compilacao": self.compilacao,
                "tanque": self.tanque.estado(), "wifi": self.wifi, "wifi_conectado": self.wifi_conectado,
                "ponte_serial": self.ponte_serial, "envio_auto_s": self.envio_auto_s,
                "pinos": self.pinos, "saidas": self.saidas, "modos": self.modos, "tons": tons,
                "buzzer_ligado": bool(buz is not None and (self.saidas.get(buz) or buz in tons)),
                "botao_apertado": self.botao_apertado,
                "serial": self.serial[inicio:], "serial_proximo": self.serial_base + len(self.serial),
                "http": self.http[-15:], "eventos": self.eventos[-30:],
                "hora_pc": agora_belem().strftime("%d/%m/%Y %H:%M:%S"),
                "sketches": listar_sketches(), "dados": str(self.dados),
            }

    def acao(self, dados: dict) -> dict:
        a = dados.get("acao")
        t = self.tanque
        if a == "botao":
            self.botao_apertado = bool(dados.get("apertado"))
            self.enviar(f"P {self.pinos['botao']} {0 if self.botao_apertado else 1}")
        elif a == "toque":
            self.tocar()
        elif a == "mergulhar":
            with self.trava:
                t.mergulhar()
        elif a == "retirar":
            with self.trava:
                t.retirar()
        elif a == "aquecedor":
            t.aquecedor = bool(dados.get("ligado"))
        elif a == "setpoint":
            t.setpoint = float(dados["valor"])
        elif a == "queda":
            t.queda = float(dados["valor"])
        elif a == "manual":
            t.manual = None if dados.get("valor") is None else float(dados["valor"])
        elif a == "temperatura":
            t.temperatura = float(dados["valor"])
        elif a == "sensor":
            t.sensor_conectado = bool(dados.get("conectado"))
            self.enviar(f"D {1 if t.sensor_conectado else 0}")
        elif a == "wifi":
            self.wifi = bool(dados.get("ligado"))
            self.enviar(f"W {1 if self.wifi else 0}")
            self.evento("wifi", "Roteador ligado" if self.wifi else "Roteador desligado: o dispositivo fica offline")
        elif a == "serial":
            self.serial_digitar(str(dados.get("texto", "")))
        elif a == "rtc":
            self.enviar(f"R {int(dados.get('segundos', 0))}")
            self.evento("rtc", f"Relógio do dispositivo {'adiantado' if int(dados.get('segundos', 0)) > 0 else 'atrasado'}"
                               f" {abs(int(dados.get('segundos', 0)))} s")
        elif a == "api":
            self.api = str(dados["url"]).rstrip("/")
        elif a == "ponte":
            self.ponte_serial = bool(dados.get("ligada"))
        elif a == "envio_auto":
            self.envio_auto_s = int(dados.get("segundos") or 0)
        elif a == "reiniciar":
            self.reiniciar()
        elif a == "recomecar_dados":
            return self.recomecar_dados()
        elif a == "apagar_memoria":
            self.apagar_memoria(int(dados.get("contador_inicial") or 0) or None)
        elif a == "compilar":
            if dados.get("sketch"):
                novo = (RAIZ / "firmware" / dados["sketch"]).resolve()
                if novo.parent != (RAIZ / "firmware").resolve() or not novo.is_dir():
                    return {"erro": "sketch_invalido"}
                self.sketch = novo
                self.placa = dados.get("placa") or detectar_placa(novo)
                self.pinos = dict(PINOS_PADRAO[self.placa])
                self.ponte_serial = self.placa == "uno"
                self.envio_auto_s = 300 if self.placa == "uno" else 0
                self.acertar_hora = self.placa == "uno"
            threading.Thread(target=self.compilar_e_ligar, daemon=True).start()
        elif a == "lote_completo":
            import cenarios
            return cenarios.lote_completo(self, str(dados.get("resultado") or "aprovado"))
        elif a == "cenario":
            import cenarios
            return cenarios.iniciar(self, dados.get("nome"), dados)
        else:
            return {"erro": "acao_desconhecida"}
        return {"ok": True}

    def tocar(self, duracao: float = 0.15):
        """Toque rápido no botão (aperta e solta)."""
        self.enviar(f"P {self.pinos['botao']} 0")
        time.sleep(max(duracao / self.velocidade, 0.06))
        self.enviar(f"P {self.pinos['botao']} 1")


def listar_sketches() -> list[str]:
    pasta = RAIZ / "firmware"
    return sorted(p.name for p in pasta.iterdir() if p.is_dir() and any(p.glob("*.ino"))) if pasta.is_dir() else []


# =====================================================================
# Editor de código do painel (só arquivos .ino/.h/.cpp das pastas de firmware/)
# =====================================================================
def arquivo_seguro(sketch: str, nome: str) -> Path | None:
    pasta = (RAIZ / "firmware" / sketch).resolve()
    if pasta.parent != (RAIZ / "firmware").resolve():
        return None
    caminho = (pasta / nome).resolve()
    if caminho.parent != pasta or caminho.suffix not in (".ino", ".h", ".cpp", ".c"):
        return None
    return caminho


# =====================================================================
# Servidor do painel
# =====================================================================
def criar_servidor(disp: Dispositivo, porta: int) -> ThreadingHTTPServer:
    painel = RAIZ / "painel" / "index.html"

    class Manipulador(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silencioso
            pass

        def _json(self, dados, status=200):
            corpo = json.dumps(dados, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _corpo(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            consulta = urllib.parse.parse_qs(url.query)
            if url.path in ("/", "/index.html"):
                corpo = painel.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            elif url.path == "/estado":
                self._json(disp.estado(int(consulta.get("desde", ["0"])[0])))
            elif url.path == "/arquivos":
                sketch = consulta.get("sketch", [disp.sketch.name])[0]
                pasta = (RAIZ / "firmware" / sketch)
                nomes = sorted(p.name for p in pasta.iterdir() if p.suffix in (".ino", ".h", ".cpp", ".c")) \
                    if pasta.is_dir() else []
                principal = f"{sketch}.ino"
                if principal in nomes:
                    nomes.remove(principal)
                    nomes.insert(0, principal)
                self._json({"sketch": sketch, "arquivos": nomes})
            elif url.path == "/arquivo":
                caminho = arquivo_seguro(consulta.get("sketch", [""])[0], consulta.get("nome", [""])[0])
                if not caminho or not caminho.is_file():
                    return self._json({"erro": "nao_encontrado"}, 404)
                self._json({"conteudo": caminho.read_text(encoding="utf-8", errors="replace")})
            elif url.path == "/cenario":
                import cenarios
                self._json(cenarios.estado())
            else:
                self._json({"erro": "nao_encontrado"}, 404)

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            try:
                dados = self._corpo()
            except json.JSONDecodeError:
                return self._json({"erro": "json_invalido"}, 400)
            if url.path == "/acao":
                self._json(disp.acao(dados))
            elif url.path == "/arquivo":
                caminho = arquivo_seguro(str(dados.get("sketch", "")), str(dados.get("nome", "")))
                if not caminho:
                    return self._json({"erro": "nome_invalido"}, 400)
                caminho.write_text(str(dados.get("conteudo", "")), encoding="utf-8")
                self._json({"ok": True})
            elif url.path == "/novo_sketch":
                nome = "".join(c for c in str(dados.get("nome", "")) if c.isalnum() or c == "_")
                if not nome:
                    return self._json({"erro": "nome_invalido"}, 400)
                pasta = RAIZ / "firmware" / nome
                pasta.mkdir(parents=True, exist_ok=True)
                principal = pasta / f"{nome}.ino"
                if not principal.exists():
                    base = RAIZ / "firmware" / str(dados.get("copiar_de", "oriki_esp32"))
                    if base.is_dir() and base.name != nome:
                        for arq in base.iterdir():
                            if arq.suffix in (".ino", ".h", ".cpp", ".c"):
                                destino = principal if arq.name == f"{base.name}.ino" else pasta / arq.name
                                destino.write_text(arq.read_text(encoding="utf-8"), encoding="utf-8")
                    else:
                        principal.write_text("void setup() {\n  Serial.begin(115200);\n}\n\nvoid loop() {\n}\n",
                                             encoding="utf-8")
                self._json({"ok": True, "sketch": nome})
            else:
                self._json({"erro": "nao_encontrado"}, 404)

    return ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sketch", nargs="?", default=str(RAIZ / "firmware" / "oriki_esp32"),
                    help="pasta do sketch (padrão: firmware/oriki_esp32)")
    ap.add_argument("--placa", choices=["auto", "esp32", "uno"], default="auto")
    ap.add_argument("--api", default="http://127.0.0.1:5000", help="endereço da API do Oriki (backend Flask)")
    ap.add_argument("--backend", default=str(Path(__file__).resolve().parent.parent / "backend"),
                    help="pasta do backend (para o botão Recomeçar os dados)")
    ap.add_argument("--usar-url-do-firmware", action="store_true",
                    help="não troca o endereço que está no firmware pelo --api")
    ap.add_argument("--porta", type=int, default=8090, help="porta do painel")
    ap.add_argument("--velocidade", type=float, default=1.0, help="acelera o tempo (2 = o dobro); 1 = tempo real")
    ap.add_argument("--dados", help="pasta da memória do dispositivo (padrão: dados/<sketch>-<placa>)")
    ap.add_argument("--contador-inicial", type=int,
                    help="numa memória nova, o primeiro ciclo usa este contador (com o seed.py: 31)")
    ap.add_argument("--sem-navegador", action="store_true")
    ap.add_argument("--cenario", choices=["criterio", "integridade", "offline"],
                    help="roda um teste sem painel e sai (código 0 se passou)")
    ap.add_argument("--quantidade", type=int, help="ciclos do cenário (padrão do teste do documento)")
    args = ap.parse_args()

    disp = Dispositivo(args)
    if args.contador_inicial and disp.memoria_vazia():
        disp.preparar_contador(args.contador_inicial)
    threading.Thread(target=disp.laco_fisica, daemon=True).start()
    if not disp.compilar_e_ligar() and args.cenario:
        return 1

    if args.cenario:
        import cenarios
        return cenarios.rodar_sem_painel(disp, args.cenario, args.quantidade)

    servidor = criar_servidor(disp, args.porta)
    endereco = f"http://localhost:{args.porta}"
    print(f"\nBancada do Oriki: {endereco}  (Ctrl+C para sair)\n"
          f"Firmware: {disp.sketch} ({disp.placa}) | API: {disp.api}\n", flush=True)
    if not args.sem_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        disp.desligando = True
        disp.desligar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
