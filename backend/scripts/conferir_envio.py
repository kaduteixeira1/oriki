"""Confere o JSON que o firmware imprime no Monitor serial contra o contrato do backend (seções 7.2 e 7.4).

É o "teste nos dois lados" da seção 16: prova que o servidor aceita as assinaturas que o Arduino gera.

Uso:
  python scripts/conferir_envio.py saida_do_tinkercad.txt --chave <64 hex>
  python scripts/conferir_envio.py saida_do_tinkercad.txt --do-banco ORK01     # chave cifrada do banco (.env)
  python scripts/conferir_envio.py - --chave <64 hex> < saida.txt               # lê da entrada padrão
  python scripts/conferir_envio.py saida.txt --chave <...> --enviar http://127.0.0.1:5000

Cada linha que começa com {"dispositivo" é um envio; o resto do Monitor serial é ignorado.
Código de saída 0 só se todas as assinaturas e todos os ciclos conferirem.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/, para importar o app

from app.assinatura import confere_envio  # noqa: E402
from app.contrato import validar_ciclo  # noqa: E402

PREFIXO = '{"dispositivo"'


def ler_envios(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip().startswith(PREFIXO)]


def conferir(linha: str, chave: bytes) -> tuple[bool, list[tuple[str, str, str]]]:
    """(assinatura_envio confere?, [(codigo, status, "ok" | motivo)]), com a mesma ordem de regras do servidor."""
    envio = json.loads(linha)
    dispositivo = envio.get("dispositivo")
    envelope_ok = (isinstance(dispositivo, str) and isinstance(envio.get("enviado_em"), str)
                   and confere_envio(dispositivo, envio["enviado_em"], envio.get("assinatura_envio"), chave))
    resultados = []
    for ciclo in envio.get("ciclos") or []:
        motivo = validar_ciclo(dispositivo, ciclo, chave)
        codigo = ciclo.get("codigo") if isinstance(ciclo, dict) else None
        status = ciclo.get("status") if isinstance(ciclo, dict) else None
        resultados.append((str(codigo), str(status), motivo or "ok"))
    return envelope_ok, resultados


def chave_do_banco(identificador: str) -> bytes:
    from sqlalchemy import select

    from app import create_app
    from app.chaves import decifrar
    from app.extensoes import db
    from app.models import Dispositivo

    with create_app().app_context():
        disp = db.session.execute(
            select(Dispositivo).where(Dispositivo.identificador == identificador.upper())).scalar_one_or_none()
        if disp is None:
            sys.exit(f"Dispositivo {identificador} não existe no banco do .env.")
        return decifrar(disp.chave_hmac_cifrada)


def enviar(url: str, linha: str) -> None:
    pedido = urllib.request.Request(f"{url.rstrip('/')}/api/ciclos", data=linha.encode(), method="POST",
                                    headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=15) as resposta:
            status, corpo = resposta.status, resposta.read().decode()
    except urllib.error.HTTPError as erro:
        status, corpo = erro.code, erro.read().decode()
    except urllib.error.URLError as erro:
        print(f"  envio: sem conexão com {url} ({erro.reason}). O flask run está ligado?")
        return
    if status == 501:
        print("  envio: a API respondeu 501; o POST /api/ciclos (OR-15) ainda não está implementado nesse servidor.")
        return
    print(f"  envio: HTTP {status} {corpo}")


def imprimir(numero: int, envelope_ok: bool, resultados: list[tuple[str, str, str]]) -> None:
    print(f"Envio {numero}: assinatura_envio {'ok' if envelope_ok else 'NÃO confere'}")
    largura = max([len("codigo")] + [len(c) for c, _, _ in resultados])
    print(f"  {'codigo'.ljust(largura)} | {'status'.ljust(9)} | resultado")
    print(f"  {'-' * largura}-+-{'-' * 9}-+-{'-' * 19}")
    for codigo, status, resultado in resultados:
        print(f"  {codigo.ljust(largura)} | {status.ljust(9)} | {resultado}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", help="Saída do Monitor serial (ou - para a entrada padrão).")
    origem = parser.add_mutually_exclusive_group(required=True)
    origem.add_argument("--chave", help="Chave do dispositivo (64 caracteres hex, usada como texto).")
    origem.add_argument("--do-banco", metavar="IDENTIFICADOR", help="Lê a chave cifrada do banco do .env.")
    parser.add_argument("--enviar", metavar="URL", help="Também faz POST {URL}/api/ciclos com cada linha, como veio.")
    args = parser.parse_args(argv)

    texto = sys.stdin.read() if args.arquivo == "-" else Path(args.arquivo).read_text(encoding="utf-8")
    linhas = ler_envios(texto)
    if not linhas:
        print(f"Nenhuma linha começando com {PREFIXO} foi encontrada.")
        return 1
    chave = args.chave.encode() if args.chave else chave_do_banco(args.do_banco)

    tudo_ok = True
    for numero, linha in enumerate(linhas, start=1):
        try:
            envelope_ok, resultados = conferir(linha, chave)
        except json.JSONDecodeError as erro:
            print(f"Envio {numero}: JSON inválido ({erro}). A linha foi cortada ao copiar?")
            tudo_ok = False
            continue
        imprimir(numero, envelope_ok, resultados)
        tudo_ok &= envelope_ok and all(resultado == "ok" for _, _, resultado in resultados)
        if args.enviar:
            enviar(args.enviar, linha)

    print("Tudo confere." if tudo_ok else "Há recusas: o servidor não aceitaria tudo.")
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")  # console do Windows sem UTF-8
    sys.exit(main())
