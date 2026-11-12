"""Simula o ESP32: gera ciclos com contador sequencial, assina e envia para POST /api/ciclos (seção 13.1).

Não importa nada do app de propósito: implementa o contrato da seção 7 do zero, como o firmware,
e confere os vetores de teste antes de enviar.

Exemplos:
  python scripts/simular_esp32.py --dispositivo ORK01 --chave <chave> --quantidade 5
  python scripts/simular_esp32.py ... --pular 3            # gera lacuna de 3 contadores
  python scripts/simular_esp32.py ... --adulterar          # muda um campo depois de assinar
  python scripts/simular_esp32.py ... --repetir            # reenvia o último envio
  python scripts/simular_esp32.py ... --relogio-atrasado 600
  python scripts/simular_esp32.py ... --quantidade 0       # só heartbeat

O último contador e o último envio ficam em .simulador-<DISPOSITIVO>.json (fora do Git).
"""
import argparse
import hashlib
import hmac
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BELEM = timezone(timedelta(hours=-3))  # America/Belem não tem horário de verão
CAMPOS = ("codigo", "contador", "inicio", "fim", "temp_min", "temp_max", "segundos_acima_80", "status")


def assinar(chave: bytes, mensagem: str) -> str:
    return hmac.new(chave, mensagem.encode(), hashlib.sha256).hexdigest()


def mensagem_ciclo(ciclo: dict) -> str:
    partes = [f"{float(ciclo[c]):.2f}" if c in ("temp_min", "temp_max") else str(ciclo[c]) for c in CAMPOS]
    return "|".join(partes)


def conferir_vetores() -> None:
    """Os mesmos vetores que o firmware precisa reproduzir (seção 7.2)."""
    chave = b"chave-de-teste"
    assert assinar(chave, "ORK01|2026-10-08T07:50:00-03:00") == \
        "74a7b50b829144a0b5e44210049c7b8ba941e9b1b927f8da2f8bc9aab33a2c71"
    ciclo = {"codigo": "ORK01-000128", "contador": 128, "inicio": "2026-10-08T07:42:10-03:00",
             "fim": "2026-10-08T07:42:24-03:00", "temp_min": 81.2, "temp_max": 84.6,
             "segundos_acima_80": 12, "status": "aprovado"}
    assert assinar(chave, mensagem_ciclo(ciclo)) == \
        "d7d02435af15a3b257a765d3e90b17687d780a7620d70b3c76350b9ff8f9d24d"


def gerar_ciclo(dispositivo: str, contador: int, inicio: datetime, chave: bytes, aleatorio: random.Random) -> dict:
    reprovado = aleatorio.random() < 0.1
    segundos = aleatorio.randint(2, 9) if reprovado else aleatorio.randint(10, 25)
    ciclo = {
        "codigo": f"{dispositivo}-{contador:06d}",
        "contador": contador,
        "inicio": inicio.isoformat(timespec="seconds"),
        "fim": (inicio + timedelta(seconds=segundos + 3)).isoformat(timespec="seconds"),
        "temp_min": round(aleatorio.uniform(76, 79.5) if reprovado else aleatorio.uniform(80.1, 82), 2),
        "temp_max": round(aleatorio.uniform(79.6, 81) if reprovado else aleatorio.uniform(83, 87), 2),
        "segundos_acima_80": segundos,
        "status": "reprovado" if reprovado else "aprovado",
    }
    ciclo["assinatura"] = assinar(chave, mensagem_ciclo(ciclo))
    return ciclo


def enviar(url: str, corpo: dict) -> tuple[int, dict]:
    pedido = urllib.request.Request(f"{url.rstrip('/')}/api/ciclos", data=json.dumps(corpo).encode(),
                                    headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=15) as resposta:
            return resposta.status, json.load(resposta)
    except urllib.error.HTTPError as erro:
        return erro.code, json.loads(erro.read() or b"{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://localhost:5000")
    parser.add_argument("--dispositivo", default="ORK01")
    parser.add_argument("--chave", required=True, help="Chave mostrada pelo `flask criar-dispositivo`.")
    parser.add_argument("--quantidade", type=int, default=5, help="Ciclos a gerar (0 a 50; 0 = heartbeat).")
    parser.add_argument("--pular", type=int, default=0, help="Pula N contadores antes de gerar (lacuna).")
    parser.add_argument("--adulterar", action="store_true", help="Muda o status de um ciclo depois de assinar.")
    parser.add_argument("--repetir", action="store_true", help="Reenvia exatamente o último envio.")
    parser.add_argument("--relogio-atrasado", type=int, default=0, metavar="SEGUNDOS",
                        help="Atrasa o RTC simulado (testa relogio_divergente).")
    parser.add_argument("--contador-inicial", type=int, help="Força o próximo contador (ignora o estado salvo).")
    args = parser.parse_args()

    conferir_vetores()
    if not 0 <= args.quantidade <= 50:
        parser.error("--quantidade vai de 0 a 50")
    chave = args.chave.encode()
    estado_arquivo = Path(f".simulador-{args.dispositivo}.json")
    estado = json.loads(estado_arquivo.read_text()) if estado_arquivo.exists() else {"proximo": 1}

    rtc = datetime.now(BELEM) - timedelta(seconds=args.relogio_atrasado)
    if args.repetir:
        if "ultimo_envio" not in estado:
            parser.error("ainda não há envio para repetir")
        ciclos = estado["ultimo_envio"]
    else:
        contador = args.contador_inicial or estado["proximo"]
        contador += args.pular
        aleatorio = random.Random()
        ciclos = []
        for i in range(args.quantidade):
            inicio = rtc - timedelta(minutes=(args.quantidade - i) * 3)
            ciclos.append(gerar_ciclo(args.dispositivo, contador + i, inicio, chave, aleatorio))
        if args.adulterar and ciclos:
            alvo = ciclos[-1]
            alvo["status"], alvo["segundos_acima_80"] = "aprovado", max(alvo["segundos_acima_80"], 10)
            alvo["temp_max"] = 90.0  # muda depois de assinar: o servidor deve recusar
        if ciclos:
            estado["proximo"] = ciclos[-1]["contador"] + 1
            estado["ultimo_envio"] = ciclos

    enviado_em = rtc.replace(microsecond=0).isoformat()
    corpo = {"dispositivo": args.dispositivo, "enviado_em": enviado_em,
             "assinatura_envio": assinar(chave, f"{args.dispositivo}|{enviado_em}"), "ciclos": ciclos}
    status, resposta = enviar(args.url, corpo)
    print(f"HTTP {status}")
    print(json.dumps(resposta, ensure_ascii=False, indent=2))
    if status == 200:
        estado_arquivo.write_text(json.dumps(estado, ensure_ascii=False))
        servidor = datetime.fromisoformat(resposta["hora_servidor"].replace("Z", "+00:00"))
        if abs(servidor - rtc) > timedelta(minutes=2):
            print(f"RTC fora por {int((rtc - servidor).total_seconds())} s: o firmware ajustaria o relógio agora.")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
