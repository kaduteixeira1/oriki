"""Comandos `flask` de administração (seção 11). No MVP não há tela de admin."""
import re
import secrets
from datetime import date

import click
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from . import regras
from .chaves import cifrar, gerar_chave_dispositivo, recifrar
from .extensoes import db
from .models import Dispositivo, Estabelecimento, PerfilUsuario, Usuario

RE_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
RE_IDENTIFICADOR = re.compile(r"[A-Z0-9]{3,20}")
RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SENHA_MINIMA = 10


def _data(texto: str | None, opcao: str) -> date | None:
    if texto is None:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise click.BadParameter("use o formato AAAA-MM-DD", param_hint=opcao) from None


def _texto(valor: str, opcao: str, maximo: int) -> str:
    valor = valor.strip()
    if not valor or len(valor) > maximo:
        raise click.BadParameter(f"obrigatório, até {maximo} caracteres", param_hint=opcao)
    return valor


def _estabelecimento_por_slug(slug: str) -> Estabelecimento:
    est = db.session.execute(select(Estabelecimento).where(Estabelecimento.slug_qr == slug)).scalar_one_or_none()
    if est is None:
        raise click.ClickException(f"Estabelecimento com slug '{slug}' não encontrado.")
    return est


def _dispositivo(identificador: str) -> Dispositivo:
    disp = db.session.execute(
        select(Dispositivo).where(Dispositivo.identificador == identificador.upper())).scalar_one_or_none()
    if disp is None:
        raise click.ClickException(f"Dispositivo '{identificador}' não encontrado.")
    return disp


def _usuario(email: str) -> Usuario:
    usuario = db.session.execute(
        select(Usuario).where(Usuario.email == email.strip().lower())).scalar_one_or_none()
    if usuario is None:
        raise click.ClickException(f"Usuário '{email}' não encontrado.")
    return usuario


def _mostrar_chave(identificador: str, chave: str) -> None:
    click.echo()
    click.secho(f"Chave do dispositivo {identificador} (mostrada UMA vez; grave no firmware):", bold=True)
    click.secho(chave, fg="yellow")
    click.echo("Não salve esta chave em arquivo do repositório nem envie por chat.")


def _pedir_senha(email: str) -> str:
    while True:
        senha = click.prompt("Senha", hide_input=True, confirmation_prompt="Repita a senha")
        if len(senha) < SENHA_MINIMA:
            click.echo(f"A senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
        elif senha.lower() == email:
            click.echo("A senha não pode ser o e-mail.")
        else:
            return senha


def registrar_comandos(app) -> None:

    @app.cli.command("criar-estabelecimento")
    @click.option("--nome", required=True)
    @click.option("--endereco", required=True)
    @click.option("--licenca", required=True, help="Nº da licença da Sesma (confira na lista pública antes).")
    @click.option("--validade", required=True, help="Validade da licença, AAAA-MM-DD.")
    @click.option("--curso-em", default=None, help="Conclusão do curso da Casa do Açaí, AAAA-MM-DD.")
    @click.option("--slug", required=True, help="Usado na URL do QR: só [a-z0-9-].")
    def criar_estabelecimento(nome, endereco, licenca, validade, curso_em, slug):
        """Cadastra um ponto de venda."""
        slug = slug.strip().lower()
        if len(slug) > 80 or not RE_SLUG.fullmatch(slug):
            raise click.BadParameter("só letras minúsculas, números e hífens", param_hint="--slug")
        licenca = _texto(licenca, "--licenca", 40)
        repetido = db.session.execute(select(Estabelecimento.id).where(
            (Estabelecimento.slug_qr == slug) | (Estabelecimento.licenca_numero == licenca))).first()
        if repetido:
            raise click.ClickException("Já existe estabelecimento com esse slug ou nº de licença.")
        est = Estabelecimento(nome=_texto(nome, "--nome", 150), endereco=_texto(endereco, "--endereco", 255),
                              licenca_numero=licenca, licenca_validade=_data(validade, "--validade"),
                              curso_casa_acai_em=_data(curso_em, "--curso-em"), slug_qr=slug)
        db.session.add(est)
        db.session.commit()
        click.echo(f"Estabelecimento {est.id} criado: {app.config['URL_PUBLICA']}/p/{slug}")

    @app.cli.command("criar-dispositivo")
    @click.option("--identificador", required=True, help="Prefixo do código do lote, ex.: ORK02.")
    @click.option("--estabelecimento", "slug", required=True, help="Slug do estabelecimento.")
    def criar_dispositivo(identificador, slug):
        """Cria o dispositivo e mostra a chave HMAC uma única vez."""
        identificador = identificador.strip().upper()
        if not RE_IDENTIFICADOR.fullmatch(identificador):
            raise click.BadParameter("use [A-Z0-9], de 3 a 20 caracteres", param_hint="--identificador")
        if db.session.execute(select(Dispositivo.id).where(Dispositivo.identificador == identificador)).first():
            raise click.ClickException(f"O identificador {identificador} já existe.")
        est = _estabelecimento_por_slug(slug)
        chave = gerar_chave_dispositivo()
        db.session.add(Dispositivo(estabelecimento_id=est.id, identificador=identificador,
                                   chave_hmac_cifrada=cifrar(chave)))
        db.session.commit()
        click.echo(f"Dispositivo {identificador} criado para {est.nome}.")
        _mostrar_chave(identificador, chave)

    @app.cli.command("trocar-chave-dispositivo")
    @click.option("--identificador", required=True)
    @click.confirmation_option(prompt="A chave atual deixa de valer na hora. Continuar?")
    def trocar_chave_dispositivo(identificador):
        """Gera nova chave (perda ou suspeita de vazamento)."""
        disp = _dispositivo(identificador)
        chave = gerar_chave_dispositivo()
        disp.chave_hmac_cifrada = cifrar(chave)
        db.session.commit()
        _mostrar_chave(disp.identificador, chave)
        click.echo("Ciclos ainda na fila do ESP32, assinados com a chave antiga, serão recusados.")

    @app.cli.command("criar-usuario")
    @click.option("--nome", required=True)
    @click.option("--email", required=True)
    @click.option("--perfil", required=True, type=click.Choice([p.value for p in PerfilUsuario]))
    @click.option("--estabelecimento", "slug", default=None, help="Slug; obrigatório para batedor.")
    def criar_usuario(nome, email, perfil, slug):
        """Cria o usuário; a senha é pedida no terminal, sem eco."""
        email = email.strip().lower()
        if len(email) > 150 or not RE_EMAIL.fullmatch(email):
            raise click.BadParameter("e-mail inválido", param_hint="--email")
        perfil = PerfilUsuario(perfil)
        if perfil == PerfilUsuario.BATEDOR and not slug:
            raise click.BadParameter("batedor precisa de --estabelecimento", param_hint="--estabelecimento")
        if perfil != PerfilUsuario.BATEDOR and slug:
            raise click.BadParameter("só batedor tem estabelecimento", param_hint="--estabelecimento")
        if db.session.execute(select(Usuario.id).where(Usuario.email == email)).first():
            raise click.ClickException("Já existe usuário com esse e-mail.")
        est = _estabelecimento_por_slug(slug) if slug else None
        senha = _pedir_senha(email)
        usuario = Usuario(nome=_texto(nome, "--nome", 120), email=email, senha_hash=generate_password_hash(senha),
                          perfil=perfil, estabelecimento_id=est.id if est else None)
        db.session.add(usuario)
        db.session.commit()
        click.echo(f"Usuário {usuario.id} ({perfil.value}) criado.")

    @app.cli.command("trocar-senha")
    @click.option("--email", required=True)
    def trocar_senha(email):
        """Define nova senha e encerra todas as sessões abertas do usuário."""
        usuario = _usuario(email)
        if usuario.anonimizado_em:
            raise click.ClickException("Usuário anonimizado.")
        usuario.senha_hash = generate_password_hash(_pedir_senha(usuario.email))
        usuario.renovar_token_sessao()
        db.session.commit()
        click.echo("Senha trocada; sessões anteriores encerradas.")

    @app.cli.command("anonimizar-usuario")
    @click.option("--email", required=True)
    @click.confirmation_option(prompt="Nome e e-mail serão apagados e o acesso, encerrado. Continuar?")
    def anonimizar_usuario(email):
        """Atende pedido de exclusão (LGPD). Os registros sanitários do ponto permanecem."""
        usuario = _usuario(email)
        usuario.nome = "Usuário removido"
        usuario.email = f"removido-{usuario.id}@anonimizado.invalid"
        usuario.senha_hash = generate_password_hash(secrets.token_urlsafe(32))  # senha que ninguém conhece
        usuario.renovar_token_sessao()  # derruba sessões e cookies "lembrar"
        usuario.anonimizado_em = regras.agora()
        db.session.commit()
        click.echo(f"Usuário {usuario.id} anonimizado.")

    @app.cli.command("recifrar-chaves")
    def recifrar_chaves():
        """Recifra as chaves dos dispositivos com a 1ª chave de CHAVE_CIFRA (troca da chave mestra).

        Passo a passo: CHAVE_CIFRA=nova,antiga → flask recifrar-chaves → CHAVE_CIFRA=nova.
        """
        dispositivos = db.session.execute(select(Dispositivo)).scalars().all()
        for disp in dispositivos:
            disp.chave_hmac_cifrada = recifrar(disp.chave_hmac_cifrada)
        db.session.commit()
        click.echo(f"{len(dispositivos)} chave(s) recifrada(s).")
