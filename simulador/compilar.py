"""Compila um sketch do Arduino/ESP32 (.ino) para rodar no PC, ligado à bancada virtual.

Faz o mesmo que a IDE do Arduino antes de compilar:
  1. junta as abas (.ino) da pasta: a principal primeiro, as outras em ordem alfabética;
  2. gera os protótipos das funções (no Arduino dá para chamar uma função escrita mais abaixo);
  3. compila junto com o núcleo de mentira (pasta nucleo/) e os .cpp da pasta do sketch.

Uso:
  python compilar.py firmware/oriki_esp32                  # placa ESP32 (padrão)
  python compilar.py firmware/oriki_tinkercad --placa uno  # Arduino Uno do Tinkercad
  python compilar.py meu_sketch.ino --saida build/meu

Compilador: usa o que achar primeiro entre a variável CXX, g++, clang++, c++ e o zig
(`pip install ziglang`, que funciona no Windows sem instalar mais nada).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NUCLEO = RAIZ / "nucleo"
BIBLIOTECAS = RAIZ / "bibliotecas"  # bibliotecas header-only de verdade (ex.: ArduinoJson) podem ir aqui
EXE = ".exe" if os.name == "nt" else ""

PALAVRAS_NAO_FUNCAO = {"if", "for", "while", "switch", "catch", "return", "else", "do", "sizeof"}
INICIO_NAO_FUNCAO = ("struct", "class", "enum", "union", "namespace", "typedef", "extern", "template")


class ErroCompilacao(Exception):
    pass


# ---------------------------------------------------------------------
# Protótipos
# ---------------------------------------------------------------------
def _limpar(texto: str) -> str:
    """Troca comentários, strings, chars e linhas de pré-processador por espaços (mantém as posições)."""
    saida = list(texto)
    i, n = 0, len(texto)
    inicio_linha = True
    while i < n:
        c = texto[i]
        if inicio_linha and c in " \t":
            i += 1
            continue
        if inicio_linha and c == "#":
            # diretiva: até o fim da linha (com continuação por \)
            while i < n and texto[i] != "\n":
                if texto[i] == "\\" and i + 1 < n and texto[i + 1] == "\n":
                    saida[i] = " "
                    i += 2
                    continue
                saida[i] = " "
                i += 1
            continue
        inicio_linha = False
        if c == "/" and i + 1 < n and texto[i + 1] == "/":
            while i < n and texto[i] != "\n":
                saida[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "*":
            fim = texto.find("*/", i + 2)
            fim = n if fim < 0 else fim + 2
            for k in range(i, fim):
                if texto[k] != "\n":
                    saida[k] = " "
            i = fim
            continue
        if c in "\"'":
            k = i + 1
            while k < n and texto[k] != c and texto[k] != "\n":
                k += 2 if texto[k] == "\\" else 1
            for j in range(i, min(k + 1, n)):
                if texto[j] != "\n":
                    saida[j] = " "
            i = k + 1
            continue
        if c == "\n":
            inicio_linha = True
        i += 1
    return "".join(saida)


RE_ASSINATURA = re.compile(
    r"^(?P<retorno>[A-Za-z_][\w\s\*&:<>,]*?[\s\*&])(?P<nome>[A-Za-z_]\w*)\s*\((?P<params>[^;{}()]*(?:\([^()]*\)[^;{}()]*)*)\)\s*(?P<const>const)?\s*$",
    re.S,
)


def _sem_padroes(params: str) -> str:
    """Tira os valores padrão ("int x = 3") dos parâmetros, que não podem se repetir no protótipo."""
    partes, nivel, atual = [], 0, ""
    for c in params:
        if c in "(<[{":
            nivel += 1
        elif c in ")>]}":
            nivel -= 1
        if c == "," and nivel == 0:
            partes.append(atual)
            atual = ""
        else:
            atual += c
    partes.append(atual)
    limpos = []
    for p in partes:
        nivel, corte = 0, None
        for i, c in enumerate(p):
            if c in "(<[{":
                nivel += 1
            elif c in ")>]}":
                nivel -= 1
            elif c == "=" and nivel == 0:
                corte = i
                break
        limpos.append(p[:corte] if corte is not None else p)
    return ",".join(limpos)


def prototipos(codigo: str) -> tuple[list[str], int]:
    """Lista de protótipos e a posição (no código) onde inseri-los: antes da primeira função."""
    limpo = _limpar(codigo)
    encontrados: list[str] = []
    primeira = -1
    nivel = 0
    inicio_cabecalho = 0
    for i, c in enumerate(limpo):
        if nivel == 0 and c in ";}":
            inicio_cabecalho = i + 1
        if c == "{":
            if nivel == 0:
                cabecalho = limpo[inicio_cabecalho:i]
                texto = " ".join(cabecalho.split())
                m = RE_ASSINATURA.match(texto)
                if (m and "=" not in texto.split("(")[0] and m.group("nome") not in PALAVRAS_NAO_FUNCAO
                        and not texto.startswith(INICIO_NAO_FUNCAO) and m.group("retorno").strip()):
                    retorno = m.group("retorno").strip()
                    if retorno not in ("else", "return", "new", "delete"):
                        params = " ".join(_sem_padroes(m.group("params")).split())
                        proto = f"{retorno} {m.group('nome')}({params}){' const' if m.group('const') else ''};"
                        if proto not in encontrados:
                            encontrados.append(proto)
                        if primeira < 0:
                            # começo da linha do cabeçalho
                            k = inicio_cabecalho
                            while k < i and limpo[k] in " \t\r\n":
                                k += 1
                            primeira = codigo.rfind("\n", 0, k) + 1
            nivel += 1
        elif c == "}":
            nivel = max(0, nivel - 1)
            if nivel == 0:
                inicio_cabecalho = i + 1
    return encontrados, primeira


# ---------------------------------------------------------------------
# Montagem do .cpp e compilação
# ---------------------------------------------------------------------
def abas_do_sketch(caminho: Path) -> tuple[Path, list[Path]]:
    if caminho.is_file():
        return caminho.parent, [caminho]
    if not caminho.is_dir():
        raise ErroCompilacao(f"Não achei o sketch: {caminho}")
    abas = sorted(caminho.glob("*.ino"), key=lambda p: p.name.lower())
    if not abas:
        raise ErroCompilacao(f"A pasta {caminho} não tem nenhum .ino")
    principal = caminho / f"{caminho.name}.ino"
    if principal in abas:
        abas.remove(principal)
        abas.insert(0, principal)
    return caminho, abas


def montar_cpp(abas: list[Path]) -> str:
    partes = []
    for aba in abas:
        texto = aba.read_text(encoding="utf-8", errors="replace")
        partes.append((aba, texto))
    # Os protótipos entram antes da primeira função da primeira aba que tiver função.
    saida = ['#include "Arduino.h"\n']
    inseridos = False
    todos = []
    for _, texto in partes:
        todos.extend(p for p in prototipos(texto)[0] if p not in todos)
    for aba, texto in partes:
        caminho = aba.resolve().as_posix()
        _, primeira = prototipos(texto)
        if not inseridos and primeira >= 0:
            antes, depois = texto[:primeira], texto[primeira:]
            linha_depois = antes.count("\n") + 1
            saida.append(f'#line 1 "{caminho}"\n{antes}')
            saida.append("// --- protótipos gerados pelo simulador (como a IDE do Arduino faz) ---\n")
            saida.extend(p + "\n" for p in todos)
            saida.append(f'#line {linha_depois} "{caminho}"\n{depois}\n')
            inseridos = True
        else:
            saida.append(f'#line 1 "{caminho}"\n{texto}\n')
    return "".join(saida)


def achar_compilador() -> list[str]:
    if os.environ.get("CXX"):
        return os.environ["CXX"].split()
    for nome in ("g++", "clang++", "c++"):
        if shutil.which(nome):
            return [nome]
    if importlib.util.find_spec("ziglang") is not None:
        return [sys.executable, "-m", "ziglang", "c++"]
    raise ErroCompilacao(
        "Não achei um compilador C++. O jeito mais fácil (funciona no Windows):\n"
        "    pip install ziglang\n"
        "Ou instale o g++ (Linux: sudo apt install g++ | macOS: xcode-select --install | "
        "Windows: MSYS2/MinGW).")


def compilar(sketch: Path, placa: str = "esp32", saida: Path | None = None, otimizar: bool = True) -> Path:
    pasta, abas = abas_do_sketch(sketch)
    nome = pasta.name if sketch.is_dir() else sketch.stem
    build = RAIZ / "build" / f"{nome}-{placa}"
    build.mkdir(parents=True, exist_ok=True)
    fonte = build / "sketch.cpp"
    fonte.write_text(montar_cpp(abas), encoding="utf-8")
    binario = Path(saida) if saida else build / f"firmware{EXE}"

    extras = [str(p) for p in sorted(pasta.glob("*.cpp"))] + [str(p) for p in sorted(pasta.glob("*.c"))]
    inclui = ["-I", str(NUCLEO), "-I", str(pasta)]
    if BIBLIOTECAS.is_dir():
        inclui += ["-I", str(BIBLIOTECAS)]
        for sub in sorted(BIBLIOTECAS.iterdir()):
            if sub.is_dir():
                inclui += ["-I", str(sub), "-I", str(sub / "src")]
    compilador = achar_compilador()
    # -fpermissive (só no g++) aceita deslizes que o compilador do Arduino também aceita.
    permissivo = ["-fpermissive"] if Path(compilador[0]).name.startswith("g++") else []
    comando = compilador + [
        "-std=gnu++17", "-O1" if otimizar else "-O0", "-g0", "-w", *permissivo,
        f"-DORIKI_PLACA_{placa.upper()}", *inclui,
        str(fonte), str(NUCLEO / "nucleo.cpp"), str(NUCLEO / "bibliotecas.cpp"), *extras,
        "-o", str(binario),
    ]
    if os.name != "nt":
        comando.insert(-2, "-pthread")
    proc = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        mensagens = (proc.stderr or proc.stdout).strip()
        raise ErroCompilacao(f"O firmware não compilou ({len(mensagens.splitlines())} linhas de erro):\n{mensagens}")
    return binario


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sketch", type=Path, help="pasta do sketch (com o .ino de mesmo nome) ou um arquivo .ino")
    ap.add_argument("--placa", choices=["esp32", "uno"], default="esp32")
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--mostrar-cpp", action="store_true", help="imprime o .cpp montado (para depurar)")
    args = ap.parse_args()
    try:
        if args.mostrar_cpp:
            _, abas = abas_do_sketch(args.sketch)
            print(montar_cpp(abas))
            return 0
        binario = compilar(args.sketch, args.placa, args.saida)
    except ErroCompilacao as erro:
        print(erro, file=sys.stderr)
        return 1
    print(f"OK: {binario}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
