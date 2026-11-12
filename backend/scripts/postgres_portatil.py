"""PostgreSQL 16 portátil para desenvolvimento, sem instalar nada no sistema (útil no Windows).

Requer: pip install pgserver   (não faz parte do requirements: quem já tem PostgreSQL não precisa)

  python scripts/postgres_portatil.py iniciar   # sobe na porta 5433 e cria oriki/oriki_test
  python scripts/postgres_portatil.py parar

URLs para o .env:
  DATABASE_URL=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki
  DATABASE_URL_TESTE=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki_test

Só escuta em 127.0.0.1 e usa autenticação "trust": nunca use isto fora da sua máquina.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

PORTA = "5433"


def caminhos() -> tuple[Path, Path]:
    try:
        import pgserver
    except ImportError:
        sys.exit("Instale antes: pip install pgserver")
    instalacao = Path(pgserver.__file__).parent / "pginstall"
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return instalacao, base / "oriki-pgdata"


def garantir_fusos(instalacao: Path) -> None:
    """O build do pgserver vem sem a base de fusos; copia a do pacote tzdata (mesmo formato TZif)."""
    destino = instalacao / "share" / "postgresql" / "timezone"
    if (destino / "America" / "Belem").exists():
        return
    import tzdata
    shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", destino, dirs_exist_ok=True)


def executar(*comando, **kwargs):
    return subprocess.run(comando, check=True, **kwargs)


def iniciar() -> None:
    instalacao, dados = caminhos()
    garantir_fusos(instalacao)
    binarios = instalacao / "bin"
    primeira_vez = not (dados / "PG_VERSION").exists()
    if primeira_vez:
        dados.mkdir(parents=True, exist_ok=True)
        executar(str(binarios / "initdb"), "-D", str(dados), "-U", "postgres", "-E", "UTF8",
                 "--auth=trust", "--no-locale")
    rodando = subprocess.run([str(binarios / "pg_ctl"), "-D", str(dados), "status"],
                             capture_output=True).returncode == 0
    if rodando:
        print("O PostgreSQL portátil já está rodando.")
        return
    executar(str(binarios / "pg_ctl"), "-D", str(dados), "-o", f"-p {PORTA} -h 127.0.0.1",
             "-l", str(dados / "server.log"), "-w", "start")
    if primeira_vez:
        psql = [str(binarios / "psql"), "-h", "127.0.0.1", "-p", PORTA, "-U", "postgres", "-v", "ON_ERROR_STOP=1"]
        executar(*psql, "-c", "CREATE ROLE oriki LOGIN PASSWORD 'oriki' CREATEDB",
                 "-c", "CREATE DATABASE oriki OWNER oriki", "-c", "CREATE DATABASE oriki_test OWNER oriki")
    print(f"PostgreSQL no ar em 127.0.0.1:{PORTA} (dados em {dados}).")


def parar() -> None:
    instalacao, dados = caminhos()
    executar(str(instalacao / "bin" / "pg_ctl"), "-D", str(dados), "stop", "-m", "fast")


if __name__ == "__main__":
    acoes = {"iniciar": iniciar, "parar": parar}
    if len(sys.argv) != 2 or sys.argv[1] not in acoes:
        sys.exit(__doc__)
    acoes[sys.argv[1]]()
