"""F1–F5: comandos de administração (seção 11) e o app servindo o build do React (seção 14.2)."""
import re

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app import create_app
from app.models import Dispositivo, Estabelecimento, Usuario
from conftest import SENHA, enviar, logar


@pytest.fixture
def cli(app):
    return app.test_cli_runner()


def _criar_ponto(cli):
    resultado = cli.invoke(args=["criar-estabelecimento", "--nome", "Açaí do Teste", "--endereco", "Rua A, 1",
                                 "--licenca", "SESMA-123", "--validade", "2027-03-31", "--slug", "acai-do-teste"])
    assert resultado.exit_code == 0, resultado.output


def test_criar_estabelecimento_e_dispositivo_com_chave_que_funciona(cli, cliente, sessao):
    _criar_ponto(cli)
    resultado = cli.invoke(args=["criar-dispositivo", "--identificador", "ork07", "--estabelecimento", "acai-do-teste"])
    assert resultado.exit_code == 0, resultado.output
    chave = re.search(r"\b[0-9a-f]{64}\b", resultado.output).group(0)
    disp = sessao.execute(select(Dispositivo).where(Dispositivo.identificador == "ORK07")).scalar_one()
    assert chave not in disp.chave_hmac_cifrada
    assert enviar(cliente, "ORK07", chave.encode(), []).status_code == 200


def test_comandos_recusam_dados_invalidos_ou_repetidos(cli):
    _criar_ponto(cli)
    assert cli.invoke(args=["criar-estabelecimento", "--nome", "X", "--endereco", "Y", "--licenca", "SESMA-123",
                            "--validade", "2027-01-01", "--slug", "outro"]).exit_code != 0  # licença repetida
    assert cli.invoke(args=["criar-estabelecimento", "--nome", "X", "--endereco", "Y", "--licenca", "L2",
                            "--validade", "31/01/2027", "--slug", "outro"]).exit_code != 0
    assert cli.invoke(args=["criar-estabelecimento", "--nome", "X", "--endereco", "Y", "--licenca", "L3",
                            "--validade", "2027-01-01", "--slug", "Com Espaço"]).exit_code != 0
    assert cli.invoke(args=["criar-dispositivo", "--identificador", "OK", "--estabelecimento",
                            "acai-do-teste"]).exit_code != 0
    assert cli.invoke(args=["criar-usuario", "--nome", "F", "--email", "f@exemplo.com", "--perfil", "batedor"],
                      input=f"{SENHA}\n{SENHA}\n").exit_code != 0  # batedor sem estabelecimento
    assert cli.invoke(args=["criar-usuario", "--nome", "F", "--email", "f@exemplo.com", "--perfil", "fiscal",
                            "--estabelecimento", "acai-do-teste"],
                      input=f"{SENHA}\n{SENHA}\n").exit_code != 0  # fiscal não tem estabelecimento


def test_slug_repetido_nao_grava_nada(cli, sessao):
    _criar_ponto(cli)
    resultado = cli.invoke(args=["criar-estabelecimento", "--nome", "Outro", "--endereco", "Rua B, 2",
                                 "--licenca", "SESMA-999", "--validade", "2027-03-31", "--slug", "acai-do-teste"])
    assert resultado.exit_code != 0
    assert sessao.execute(select(Estabelecimento.licenca_numero)).scalars().all() == ["SESMA-123"]


def test_trocar_chave_invalida_a_antiga(cli, cliente, fabrica):
    est = fabrica.estabelecimento()
    _, chave_antiga = fabrica.dispositivo(est)
    resultado = cli.invoke(args=["trocar-chave-dispositivo", "--identificador", "ORK01", "--yes"])
    assert resultado.exit_code == 0, resultado.output
    chave_nova = re.search(r"\b[0-9a-f]{64}\b", resultado.output).group(0)
    assert enviar(cliente, "ORK01", chave_antiga, []).status_code == 401
    assert enviar(cliente, "ORK01", chave_nova.encode(), []).status_code == 200


def test_criar_usuario_pede_senha_forte_e_salva_email_minusculo(cli, cliente, sessao):
    _criar_ponto(cli)
    resultado = cli.invoke(
        args=["criar-usuario", "--nome", "Batedor", "--email", "Novo@Exemplo.com", "--perfil", "batedor",
              "--estabelecimento", "acai-do-teste"],
        input=f"curta\ncurta\n{SENHA}\n{SENHA}\n")
    assert resultado.exit_code == 0, resultado.output
    assert "pelo menos 10" in resultado.output
    usuario = sessao.execute(select(Usuario).where(Usuario.email == "novo@exemplo.com")).scalar_one()
    assert usuario.senha_hash != SENHA and usuario.termo_aceito_em is None
    assert logar(cliente, usuario).status_code == 200


def test_anonimizar_apaga_dados_pessoais_e_derruba_a_sessao(cli, cliente, fabrica, sessao):
    est = fabrica.estabelecimento()
    usuario = fabrica.usuario(est=est, email="rosa@exemplo.com")
    logar(cliente, usuario)
    resultado = cli.invoke(args=["anonimizar-usuario", "--email", "rosa@exemplo.com", "--yes"])
    assert resultado.exit_code == 0, resultado.output
    assert cliente.get("/api/me").status_code == 401
    assert cliente.post("/api/login", json={"email": "rosa@exemplo.com", "senha": SENHA}).status_code == 401
    sessao.expire_all()
    anonimo = sessao.get(Usuario, usuario.id)
    assert anonimo.nome == "Usuário removido" and "rosa" not in anonimo.email
    assert anonimo.estabelecimento_id == est.id  # registros sanitários do ponto permanecem


def test_trocar_senha_derruba_sessoes(cli, cliente, fabrica):
    usuario = fabrica.usuario(est=fabrica.estabelecimento(), email="rosa@exemplo.com")
    logar(cliente, usuario)
    nova = "outra-senha-forte-456"
    resultado = cli.invoke(args=["trocar-senha", "--email", "rosa@exemplo.com"], input=f"{nova}\n{nova}\n")
    assert resultado.exit_code == 0, resultado.output
    assert cliente.get("/api/me").status_code == 401
    assert logar(cliente, usuario, senha=nova).status_code == 200


def test_recifrar_chaves_permite_trocar_a_chave_mestra(app, cli, cliente, fabrica, sessao):
    est = fabrica.estabelecimento()
    _, chave = fabrica.dispositivo(est)
    antiga = app.config["CHAVE_CIFRA"]
    nova = Fernet.generate_key().decode()
    try:
        app.config["CHAVE_CIFRA"] = f"{nova},{antiga}"
        app.extensions.pop("oriki_fernet", None)
        assert cli.invoke(args=["recifrar-chaves"]).exit_code == 0
        app.config["CHAVE_CIFRA"] = nova  # a antiga já pode ser descartada
        app.extensions.pop("oriki_fernet", None)
        assert enviar(cliente, "ORK01", chave, []).status_code == 200
    finally:
        app.config["CHAVE_CIFRA"] = antiga
        app.extensions.pop("oriki_fernet", None)


# ---------- configuração e build do React ----------

def test_app_nao_sobe_sem_segredos(app):
    with pytest.raises(RuntimeError, match="CHAVE_CIFRA"):
        create_app({**app.config, "CHAVE_CIFRA": None})
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({**app.config, "SECRET_KEY": "curta"})


def test_flask_serve_o_build_do_react(app, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "app-123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("self.x=1", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (tmp_path.parent / "segredo.txt").write_text("não pode vazar", encoding="utf-8")
    spa = create_app({**app.config, "FRONTEND_DIST": str(tmp_path)}).test_client()

    for rota in ("/", "/batedor", "/p/acai-da-dona-rosa"):
        resposta = spa.get(rota)
        assert resposta.status_code == 200 and b"root" in resposta.data
        assert resposta.headers["Cache-Control"] == "no-cache"
        assert "frame-ancestors 'none'" in resposta.headers["Content-Security-Policy"]
    assert "max-age=31536000" in spa.get("/assets/app-123.js").headers["Cache-Control"]
    assert "max-age=31536000" not in spa.get("/sw.js").headers.get("Cache-Control", "")
    # PWA (OR-20): o navegador só instala com o manifest no tipo certo.
    assert spa.get("/manifest.webmanifest").mimetype == "application/manifest+json"
    assert spa.get("/api/nao-existe").get_json() == {"erro": "nao_encontrado"}
    assert b"vazar" not in spa.get("/../segredo.txt").data
    assert b"vazar" not in spa.get("/%2e%2e/segredo.txt").data


def test_estabelecimento_criado_pelo_comando_aparece_no_publico(cli, cliente, sessao):
    _criar_ponto(cli)
    assert sessao.execute(select(Estabelecimento.slug_qr)).scalar_one() == "acai-do-teste"
    assert cliente.get("/api/publico/acai-do-teste").status_code == 200
