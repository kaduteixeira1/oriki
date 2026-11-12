"""Testes do documento do projeto rodados na bancada, como um operador faria no tanque.

  criterio     OR-26 · "Critério do ciclo": 30 ciclos (15 corretos; 15 com água esfriando ou tempo curto),
               meta 30 de 30 classificados certo.
  integridade  OR-25 · "Integridade": um ciclo alterado na memória e outro apagado antes do envio,
               meta 100% recusados ou sinalizados.
  offline      OR-24 · "Sincronização offline": N ciclos sem Wi-Fi (50 no ESP32; 19 no Uno, o tamanho da
               EEPROM), depois a rede volta; meta N de N no servidor, sem duplicados.

Pelo painel (aba Testes) ou sem painel:
  python bancada.py --cenario criterio --velocidade 5
  python bancada.py firmware/oriki_tinkercad --cenario integridade --velocidade 4

Os cenários usam só o botão, o cesto, o aquecedor, o Wi-Fi e o Monitor serial: valem para qualquer firmware
que siga o fluxo do oriki_tinkercad.ino (toque = novo lote, toque = cesto na água, toque = cesto fora) e
imprima "REGISTRO <codigo> ... APROVADO|REPROVADO". A conferência no servidor usa o login do fiscal do seed.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RE_REGISTRO = re.compile(r"REGISTRO (\S+) .*?(\d+) s >= 80 C.*?(APROVADO|REPROVADO)")
FISCAL = ("fiscal@exemplo.com", "oriki-dev-2026")

_estado = {"nome": None, "rodando": False, "log": [], "resultado": None, "relatorio": None}
_trava = threading.Lock()


class FalhaCenario(Exception):
    pass


def estado() -> dict:
    with _trava:
        return json.loads(json.dumps(_estado))


def _log(texto: str):
    print(f"[cenário] {texto}", flush=True)
    with _trava:
        _estado["log"].append(texto)
        _estado["log"] = _estado["log"][-400:]


# ---------------------------------------------------------------------
# Operador virtual
# ---------------------------------------------------------------------
class Operador:
    def __init__(self, disp):
        self.disp = disp
        self.linhas: list[str] = []
        self.cv = threading.Condition()
        disp.ouvintes.append(self._ouvir)

    def fechar(self):
        if self._ouvir in self.disp.ouvintes:
            self.disp.ouvintes.remove(self._ouvir)

    def _ouvir(self, linha: str):
        with self.cv:
            self.linhas.append(linha)
            self.cv.notify_all()

    def esperar(self, segundos_sim: float):
        time.sleep(segundos_sim / self.disp.velocidade)

    def aguardar(self, padrao: str, timeout_sim: float, desde: int | None = None) -> re.Match | None:
        regex = re.compile(padrao)
        limite = time.monotonic() + timeout_sim / self.disp.velocidade
        inicio = len(self.linhas) if desde is None else desde
        with self.cv:
            while True:
                for i in range(inicio, len(self.linhas)):
                    m = regex.search(self.linhas[i])
                    if m:
                        return m
                inicio = len(self.linhas)
                restante = limite - time.monotonic()
                if restante <= 0:
                    return None
                self.cv.wait(restante)

    def marca(self) -> int:
        with self.cv:
            return len(self.linhas)

    def ciclo(self, agua: float, queda: float, imersao_s: float, aquecedor_na_imersao: bool = True) -> dict:
        """Um lote completo: novo lote, cesto na água, espera e cesto fora. Devolve o REGISTRO do firmware."""
        t = self.disp.tanque
        with self.disp.trava:
            t.manual = None
            t.retirar()
            t.aquecedor = True
            t.setpoint = agua
            t.temperatura = agua
        self.esperar(1.0)
        m0 = self.marca()
        self.disp.tocar()
        if not self.aguardar(r"Agua pronta|Novo lote", 5, m0):
            raise FalhaCenario("o firmware não respondeu ao toque de novo lote")
        if not self.aguardar(r"Agua pronta", 15, m0):
            raise FalhaCenario(f"a água a {agua:.1f} °C não ficou pronta")
        m1 = self.marca()
        self.disp.tocar()
        inicio = self.aguardar(r"Imersao iniciada: (\S+)", 5, m1)
        if not inicio:
            raise FalhaCenario("a imersão não começou depois do segundo toque")
        with self.disp.trava:
            t.queda = queda
            t.mergulhar()
            t.aquecedor = aquecedor_na_imersao
        registro = self.aguardar(r"REGISTRO ", imersao_s, m1)
        if not registro:
            self.disp.tocar()
            registro = self.aguardar(r"REGISTRO ", 5, m1)
        with self.disp.trava:
            t.retirar()
            t.aquecedor = True
        if not registro:
            raise FalhaCenario("o firmware não fechou o ciclo")
        linha = registro.string
        m = RE_REGISTRO.search(linha)
        if not m:
            raise FalhaCenario(f"não entendi a linha do registro: {linha}")
        self.aguardar(r"Pronto para o proximo lote", 8, m1)
        return {"codigo": m.group(1), "segundos": int(m.group(2)), "status": m.group(3).lower(), "linha": linha}


# ---------------------------------------------------------------------
# Conferência no servidor (login do fiscal)
# ---------------------------------------------------------------------
class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def chamar(self, metodo: str, caminho: str, corpo=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        pedido = urllib.request.Request(self.base + caminho, data=dados, method=metodo)
        if dados is not None:
            pedido.add_header("Content-Type", "application/json")
        with self.abridor.open(pedido, timeout=10) as resp:
            return json.loads(resp.read() or b"null")

    def entrar_como_fiscal(self):
        self.chamar("POST", "/api/login", {"email": FISCAL[0], "senha": FISCAL[1]})

    def detalhe_do_dispositivo(self, identificador: str) -> dict:
        for est in self.chamar("GET", "/api/fiscal/estabelecimentos"):
            det = self.chamar("GET", f"/api/fiscal/estabelecimentos/{est['id']}")
            if any(d["identificador"] == identificador for d in det["dispositivos"]):
                return det
        raise FalhaCenario(f"nenhum ponto tem o dispositivo {identificador}")


def _respostas_desde(disp, instante: float) -> list[dict]:
    with disp.trava:
        return [h for h in disp.http if h["t"] >= instante and h["status"] == 200]


def _forcar_envio(disp, op: Operador, instante: float, timeout_sim: float = 30) -> list[dict]:
    """Pede o envio no Monitor serial e espera a resposta da API chegar."""
    disp.serial_digitar("enviar")
    limite = time.monotonic() + timeout_sim / disp.velocidade + 5
    while time.monotonic() < limite:
        respostas = _respostas_desde(disp, instante)
        if respostas:
            time.sleep(1.0)
            return _respostas_desde(disp, instante)
        time.sleep(0.2)
    raise FalhaCenario("a API não respondeu ao envio (o backend está rodando? confira o --api)")


# ---------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------
def cenario_criterio(disp, quantidade: int | None = None) -> dict:
    casos = []
    for i in range(15):
        casos.append(("correto", 84 + (i % 5), 2.0, 11.5 + (i % 4) * 0.8, True, "aprovado"))
    for i in range(5):
        casos.append(("tempo curto", 86, 2.0, 4.0 + i, True, "reprovado"))
    for i in range(5):
        casos.append(("água cai abaixo de 80 °C ao mergulhar", 82, 4.0 + i * 0.5, 15, True, "reprovado"))
    for i in range(5):
        casos.append(("água esfria durante a imersão", 82.5, 1.5, 20, False, "reprovado"))
    # intercala corretos e incorretos
    ordem = [c for par in zip(casos[:15], casos[15:]) for c in par]
    if quantidade:
        ordem = ordem[:quantidade]
    op = Operador(disp)
    linhas, certos = [], 0
    try:
        for n, (tipo, agua, queda, imersao, aquecedor, esperado) in enumerate(ordem, 1):
            r = op.ciclo(agua, queda, imersao, aquecedor)
            ok = r["status"] == esperado
            certos += ok
            linhas.append({"n": n, "caso": tipo, "agua": agua, "imersao_s": imersao, "esperado": esperado,
                           "obtido": r["status"], "segundos": r["segundos"], "codigo": r["codigo"], "ok": ok})
            _log(f"{n:>2}/{len(ordem)} {tipo}: esperado {esperado}, firmware {r['status']} ({r['segundos']} s) "
                 f"{'✔' if ok else '✘'}")
    finally:
        op.fechar()
    passou = certos == len(ordem)
    return {"titulo": "Critério do ciclo (OR-26)", "meta": f"{len(ordem)} de {len(ordem)} classificados certo",
            "obtido": f"{certos} de {len(ordem)}", "passou": passou, "casos": linhas}


def cenario_integridade(disp, _quantidade=None) -> dict:
    op = Operador(disp)
    api = Api(disp.api)
    try:
        disp.acao({"acao": "wifi", "ligado": False})
        _log("Wi-Fi desligado: os ciclos ficam na fila local.")
        a = op.ciclo(86, 2, 12)
        b = op.ciclo(86, 2, 12)
        c = op.ciclo(86, 2, 5)
        _log(f"Ciclos na fila: {a['codigo']} ({a['status']}), {b['codigo']} ({b['status']}), {c['codigo']} ({c['status']})")
        num = lambda codigo: int(codigo.rsplit("-", 1)[1])  # noqa: E731

        m = op.marca()
        disp.serial_digitar(f"adulterar {num(c['codigo'])}")
        op.aguardar(r"alterado", 5, m)
        _log(f"Alterado na memória sem nova assinatura: {c['codigo']} (reprovado → aprovado)")

        if disp.placa == "esp32":
            arquivo = disp.dados / "littlefs" / "pendentes" / f"{num(b['codigo']):06d}.json"
            arquivo.unlink()
            _log(f"Apagado da memória (arquivo do LittleFS): {b['codigo']}")
        else:
            disp.serial_digitar(f"ok {b['codigo']}")
            _log(f"Tirado da fila sem enviar ('ok' falso na EEPROM): {b['codigo']}")
        d = op.ciclo(86, 2, 12)
        _log(f"Mais um ciclo depois do apagado: {d['codigo']}")

        instante = time.time()
        disp.acao({"acao": "wifi", "ligado": True})
        _log("Wi-Fi ligado: enviando.")
        op.esperar(2)
        respostas = _forcar_envio(disp, op, instante)
        recebidos = {codigo for r in respostas for codigo in (r["recebidos"] or [])}
        recusados = {x["codigo"]: x["motivo"] for r in respostas for x in (r["recusados"] or [])}
        adulterado_recusado = recusados.get(c["codigo"]) == "assinatura_invalida"
        _log(f"Servidor: recebidos {sorted(recebidos)} | recusados {recusados}")

        api.entrar_como_fiscal()
        det = api.detalhe_do_dispositivo(a["codigo"].split("-")[0])
        lacunas = det.get("lacunas", [])
        n = num(b["codigo"])
        apagado_sinalizado = any(f"contadores {n} a {n} " in l or f"contadores {n} a" in l for l in lacunas)
        _log(f"Painel do fiscal, lacunas: {lacunas}")
    finally:
        op.fechar()
        disp.acao({"acao": "wifi", "ligado": True})
    casos = [
        {"caso": f"{c['codigo']} alterado na memória", "esperado": "recusado (assinatura_invalida)",
         "obtido": recusados.get(c["codigo"], "aceito!"), "ok": adulterado_recusado},
        {"caso": f"{b['codigo']} apagado antes do envio", "esperado": "lacuna de contador no painel do fiscal",
         "obtido": "; ".join(lacunas) or "sem lacuna", "ok": apagado_sinalizado},
        {"caso": "ciclos íntegros", "esperado": f"{a['codigo']} e {d['codigo']} recebidos",
         "obtido": ", ".join(sorted(recebidos)) or "nenhum", "ok": {a["codigo"], d["codigo"]} <= recebidos},
    ]
    certos = sum(1 for x in casos[:2] if x["ok"])
    return {"titulo": "Integridade (OR-25)", "meta": "100% das alterações recusadas ou sinalizadas",
            "obtido": f"{certos * 50}% ({certos} de 2)", "passou": all(x["ok"] for x in casos), "casos": casos}


def cenario_offline(disp, quantidade: int | None = None) -> dict:
    n = quantidade or (19 if disp.placa == "uno" else 50)
    if disp.placa == "uno" and n > 19:
        _log("A EEPROM do Uno guarda 19 ciclos: usando 19.")
        n = 19
    op = Operador(disp)
    api = Api(disp.api)
    codigos = []
    try:
        disp.acao({"acao": "wifi", "ligado": False})
        _log(f"Wi-Fi desligado. Gravando {n} ciclos na fila local…")
        for i in range(n):
            r = op.ciclo(86, 2, 11)
            codigos.append(r["codigo"])
            if (i + 1) % 10 == 0 or i + 1 == n:
                _log(f"{i + 1}/{n} ciclos na fila (último {r['codigo']})")
        instante = time.time()
        disp.acao({"acao": "wifi", "ligado": True})
        _log("Wi-Fi ligado de novo.")
        op.esperar(2)
        recebidos: set[str] = set()
        for tentativa in range(4):
            respostas = _forcar_envio(disp, op, instante)
            recebidos |= {codigo for r in respostas for codigo in (r["recebidos"] or [])}
            if set(codigos) <= recebidos:
                break
            instante = time.time()
            op.esperar(3)
        confirmados = set(codigos) & recebidos
        recusados = {x["codigo"]: x["motivo"] for r in respostas for x in (r["recusados"] or [])}
        _log(f"Servidor confirmou {len(confirmados)} de {n}." + (f" Recusados: {recusados}" if recusados else ""))
        api.entrar_como_fiscal()
        det = api.detalhe_do_dispositivo(codigos[0].split("-")[0])
        no_banco = [l["codigo"] for l in det["lotes"] if l["codigo"] in set(codigos)]
    finally:
        op.fechar()
        disp.acao({"acao": "wifi", "ligado": True})
    sem_duplicados = len(no_banco) == len(set(no_banco))
    todos = len(confirmados) == n
    casos = [{"caso": "ciclos gravados offline", "esperado": n, "obtido": len(codigos), "ok": len(codigos) == n},
             {"caso": "confirmados em \"recebidos\" depois da rede voltar", "esperado": n, "obtido": len(confirmados),
              "ok": todos},
             {"caso": "linhas duplicadas no banco", "esperado": 0, "obtido": len(no_banco) - len(set(no_banco)),
              "ok": sem_duplicados}]
    if recusados:
        casos.append({"caso": "recusados", "esperado": "nenhum", "obtido": recusados, "ok": False})
    return {"titulo": "Sincronização offline (OR-24)", "meta": f"{n} de {n} no servidor, sem duplicados",
            "obtido": f"{len(confirmados)} de {n} confirmados, {'sem' if sem_duplicados else 'COM'} duplicados",
            "passou": todos and sem_duplicados, "casos": casos,
            "observacao": "O documento pede 48 h sem Wi-Fi; aqui o tempo offline é o de gravar os ciclos. "
                          "O que se testa é a fila local e a idempotência do envio. Se dois sketches simulados "
                          "usarem o mesmo identificador (ORK01), os contadores repetidos voltam como conflito."}


CENARIOS = {"criterio": cenario_criterio, "integridade": cenario_integridade, "offline": cenario_offline}


def _relatorio_md(disp, r: dict) -> str:
    linhas = [f"# {r['titulo']}", "",
              f"- Data: {datetime.now():%d/%m/%Y %H:%M}",
              f"- Firmware: `{disp.sketch.name}` ({disp.placa}), bancada a {disp.velocidade}x",
              f"- Meta: {r['meta']}", f"- Obtido: **{r['obtido']}** — {'PASSOU' if r['passou'] else 'NÃO PASSOU'}", ""]
    if r.get("observacao"):
        linhas += [f"> {r['observacao']}", ""]
    casos = r.get("casos") or []
    if casos:
        chaves = [k for k in casos[0].keys() if k != "linha"]
        linhas.append("| " + " | ".join(chaves) + " |")
        linhas.append("|" + "---|" * len(chaves))
        for c in casos:
            linhas.append("| " + " | ".join("✔" if c[k] is True else "✘" if c[k] is False else str(c[k]) for k in chaves) + " |")
    return "\n".join(linhas) + "\n"


def _executar(disp, nome: str, quantidade: int | None) -> dict:
    with _trava:
        _estado.update(nome=nome, rodando=True, log=[], resultado=None, relatorio=None)
    _log(f"Começando: {nome} ({disp.sketch.name}, {disp.placa}, {disp.velocidade}x)")
    try:
        if not disp.aguardar_pronto():
            raise FalhaCenario("o dispositivo não está ligado")
        resultado = CENARIOS[nome](disp, quantidade)
    except (FalhaCenario, OSError) as erro:
        resultado = {"titulo": nome, "passou": False, "obtido": f"erro: {erro}", "meta": "", "casos": []}
        _log(f"Parou: {erro}")
    pasta = RAIZ / "relatorios"
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"{nome}-{disp.sketch.name}-{datetime.now():%Y%m%d-%H%M%S}.md"
    arquivo.write_text(_relatorio_md(disp, resultado), encoding="utf-8")
    _log(f"{'PASSOU' if resultado['passou'] else 'NÃO PASSOU'}: {resultado['obtido']} | relatório em {arquivo}")
    with _trava:
        _estado.update(rodando=False, resultado=resultado, relatorio=str(arquivo))
    return resultado


# ---------------------------------------------------------------------
# Lote completo pelo painel: o que o batedor faz no tanque, num clique
# ---------------------------------------------------------------------
_lote = {"rodando": False}


def lote_completo(disp, resultado: str) -> dict:
    """Novo lote, água pronta, cesto na água e toque para fechar: aprovado fecha aos 12 s, reprovado aos 5 s.

    Tirar o cesto não fecha o ciclo (o sensor não sabe onde está o cesto): quem fecha é o toque no botão,
    como no tanque de verdade. O firmware envia para a API uns 10 s depois de fechar.
    """
    with _trava:
        if _lote["rodando"] or _estado["rodando"]:
            return {"erro": "ocupado"}
        _lote["rodando"] = True
    imersao = 12 if resultado != "reprovado" else 5

    def rodar():
        op = Operador(disp)
        try:
            disp.evento("lote", f"Lote {'aprovado' if imersao >= 10 else 'reprovado'}: novo lote, cesto na água "
                                f"e toque no botão aos {imersao} s")
            r = op.ciclo(agua=86.0, queda=3.0, imersao_s=imersao)
            disp.evento("lote", f"{r['codigo']} {r['status']} ({r['segundos']} s). O dispositivo envia em ~10 s.")
        except FalhaCenario as erro:
            disp.evento("lote", f"Lote não concluído: {erro}")
        finally:
            op.fechar()
            with _trava:
                _lote["rodando"] = False

    threading.Thread(target=rodar, daemon=True).start()
    return {"ok": True}


def iniciar(disp, nome: str, dados: dict) -> dict:
    if nome not in CENARIOS:
        return {"erro": "cenario_desconhecido"}
    with _trava:
        if _estado["rodando"]:
            return {"erro": "ja_rodando"}
    quantidade = dados.get("quantidade")
    threading.Thread(target=_executar, args=(disp, nome, int(quantidade) if quantidade else None), daemon=True).start()
    return {"ok": True}


def rodar_sem_painel(disp, nome: str, quantidade: int | None) -> int:
    resultado = _executar(disp, nome, quantidade)
    disp.desligando = True
    disp.desligar()
    return 0 if resultado["passou"] else 1
