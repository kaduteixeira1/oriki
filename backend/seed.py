"""Dados de exemplo para desenvolvimento e demonstração, sempre relativos a hoje (Belém).

Uso:
  python seed.py              cria o que faltar; se o ORK01 já tem ciclos, não duplica nada
  python seed.py --recriar    apaga os dados de exemplo e gera tudo de novo (use no dia da demo)

Recusa rodar com COOKIE_SEGURO=1 (produção): cria senhas conhecidas e usa a chave de demonstração.

O que fica no banco:
  - "Açaí da Dona Rosa (exemplo)" com o dispositivo ORK01 e a batedora rosa@exemplo.com;
  - hoje: 6 aprovados e 1 reprovado entre 06h e agora; nos 6 dias anteriores, de 0 a 9 aprovados
    por dia, com um dia sem registro; os 3 lotes mais recentes ficam a completar;
  - "Açaí do Zé (exemplo)", sem dispositivo, com o batedor ze@exemplo.com (mostra o isolamento);
  - fiscal@exemplo.com e admin@exemplo.com, e uma vistoria de 20 dias atrás.

Os ciclos passam pelo POST /api/ciclos de verdade, assinados como o ESP32 faria.
"""
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from werkzeug.security import generate_password_hash

from app import create_app, regras
from app.assinatura import assinar_ciclo, assinar_envio
from app.chaves import cifrar
from app.extensoes import db
from app.models import Ciclo, Dispositivo, Estabelecimento, Lote, PerfilUsuario, StatusLote, Usuario, Vistoria

SLUG = "acai-da-dona-rosa"
SLUG_OUTRO = "acai-do-ze"
EMAILS = ("rosa@exemplo.com", "ze@exemplo.com", "fiscal@exemplo.com", "admin@exemplo.com")
SENHA_PADRAO = "oriki-dev-2026"

# Chave de DEMONSTRAÇÃO, a mesma de firmware/oriki_tinkercad.ino: o JSON que o Tinkercad imprime
# confere contra o banco local. Só para o seed de desenvolvimento; dispositivos reais são criados
# com `flask criar-dispositivo`, que gera uma chave aleatória.
CHAVE_DEMO_ORK01 = "7f5f1804ca51c2c77b5371a984cc330aa45570a122f8319e66160fc41201666f"

HOJE_APROVADOS, HOJE_REPROVADOS = 6, 1
LOTES_A_COMPLETAR = 3
PRIMEIRA_HORA = 6        # o ponto abre às 06h
MARGEM = timedelta(minutes=2)


def iso_belem(instante: datetime) -> str:
    return instante.astimezone(ZoneInfo("America/Belem")).isoformat(timespec="seconds")


def horarios_do_dia(dia: date, quantidade: int, ate: datetime, aleatorio: random.Random) -> list[datetime]:
    """`quantidade` instantes espalhados entre 06h do dia e `ate`, em ordem."""
    inicio = regras.inicio_do_dia(dia) + timedelta(hours=PRIMEIRA_HORA)
    janela = (ate - inicio) / quantidade
    return [inicio + janela * i + janela * aleatorio.uniform(0.1, 0.8) for i in range(quantidade)]


def dia_da_demo() -> tuple[date, datetime]:
    """Hoje, com a janela até agora; antes das 06h10 ainda não há janela, então usa o dia anterior."""
    agora = regras.agora()
    hoje = regras.hoje()
    if agora - MARGEM < regras.inicio_do_dia(hoje) + timedelta(hours=PRIMEIRA_HORA, minutes=10):
        ontem = hoje - timedelta(days=1)
        return ontem, regras.inicio_do_dia(ontem) + timedelta(hours=18)
    return hoje, agora - MARGEM


def gerar_ciclos(chave: bytes) -> list[dict]:
    aleatorio = random.Random(42)
    dia_demo, fim_demo = dia_da_demo()

    agenda: list[tuple[datetime, bool]] = []  # (início, reprovado)
    for dias_atras in range(6, 0, -1):
        dia = dia_demo - timedelta(days=dias_atras)
        quantidade = 0 if dias_atras == 2 else aleatorio.randint(1, 9)  # um dia sem registro
        fim = regras.inicio_do_dia(dia) + timedelta(hours=18)
        agenda += [(h, False) for h in horarios_do_dia(dia, quantidade, fim, aleatorio)] if quantidade else []
    hoje = horarios_do_dia(dia_demo, HOJE_APROVADOS + HOJE_REPROVADOS, fim_demo, aleatorio)
    # O reprovado é o penúltimo: aparece entre os lotes a completar, ao lado de aprovados.
    agenda += [(h, i == len(hoje) - 2) for i, h in enumerate(hoje)]

    ciclos = []
    for contador, (inicio, reprovado) in enumerate(agenda, start=1):  # sequencial, sem lacuna
        segundos = aleatorio.randint(3, 8) if reprovado else aleatorio.randint(10, 25)
        ciclo = {
            "codigo": f"ORK01-{contador:06d}", "contador": contador,
            "inicio": iso_belem(inicio), "fim": iso_belem(inicio + timedelta(seconds=segundos + 2)),
            "temp_min": round(aleatorio.uniform(76, 79) if reprovado else aleatorio.uniform(80.2, 82), 2),
            "temp_max": round(aleatorio.uniform(80.5, 82) if reprovado else aleatorio.uniform(83, 87), 2),
            "segundos_acima_80": segundos, "status": "reprovado" if reprovado else "aprovado",
        }
        ciclo["assinatura"] = assinar_ciclo(ciclo, chave)
        ciclos.append(ciclo)
    return ciclos


def apagar_exemplo() -> None:
    """Remove só o que o seed cria. Os ciclos são imutáveis (gatilho), então o gatilho é desligado
    dentro desta transação; se algo falhar, o rollback desfaz o ALTER TABLE também."""
    ests = {"slugs": [SLUG, SLUG_OUTRO]}
    db.session.execute(text("ALTER TABLE ciclos DISABLE TRIGGER ciclos_sem_alteracao"))
    db.session.execute(text("""
        DELETE FROM ciclos WHERE lote_id IN (
            SELECT l.id FROM lotes l JOIN dispositivos d ON d.id = l.dispositivo_id
            JOIN estabelecimentos e ON e.id = d.estabelecimento_id WHERE e.slug_qr = ANY(:slugs))"""), ests)
    db.session.execute(text("ALTER TABLE ciclos ENABLE TRIGGER ciclos_sem_alteracao"))
    db.session.execute(text("""
        DELETE FROM lotes WHERE dispositivo_id IN (
            SELECT d.id FROM dispositivos d JOIN estabelecimentos e ON e.id = d.estabelecimento_id
            WHERE e.slug_qr = ANY(:slugs))"""), ests)
    filtro_est = "estabelecimento_id IN (SELECT id FROM estabelecimentos WHERE slug_qr = ANY(:slugs))"
    # Envios recusados (OR-31) prendem o dispositivo: saem antes dele (ex.: depois do teste de adulteração).
    db.session.execute(text(f"DELETE FROM recusas_envio WHERE dispositivo_id IN (SELECT id FROM dispositivos WHERE {filtro_est})"), ests)
    db.session.execute(text(f"DELETE FROM dispositivos WHERE {filtro_est}"), ests)
    db.session.execute(text(f"DELETE FROM acessos_qr WHERE {filtro_est}"), ests)
    db.session.execute(text(f"""DELETE FROM vistorias WHERE {filtro_est}
        OR fiscal_id IN (SELECT id FROM usuarios WHERE email = ANY(:emails))"""), {**ests, "emails": list(EMAILS)})
    db.session.execute(text(f"DELETE FROM usuarios WHERE email = ANY(:emails) OR {filtro_est}"),
                       {**ests, "emails": list(EMAILS)})
    db.session.execute(text("DELETE FROM estabelecimentos WHERE slug_qr = ANY(:slugs)"), ests)
    db.session.commit()


def _estabelecimento(slug: str, **dados) -> Estabelecimento:
    est = db.session.execute(select(Estabelecimento).where(Estabelecimento.slug_qr == slug)).scalar_one_or_none()
    if est is None:
        est = Estabelecimento(slug_qr=slug, **dados)
        db.session.add(est)
        db.session.flush()
    return est


def _usuario(email: str, hash_senha: str, **dados) -> Usuario:
    usuario = db.session.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    if usuario is None:
        usuario = Usuario(email=email, senha_hash=hash_senha, **dados)
        db.session.add(usuario)
        db.session.flush()
    return usuario


def garantir_cadastros(senha: str) -> Dispositivo:
    rosa_est = _estabelecimento(SLUG, nome="Açaí da Dona Rosa (exemplo)", endereco="Rua Exemplo, 100 · Guamá, Belém",
                                licenca_numero="SESMA-0001-EXEMPLO", licenca_validade=date(2027, 3, 31),
                                curso_casa_acai_em=date(2025, 5, 12))
    ze_est = _estabelecimento(SLUG_OUTRO, nome="Açaí do Zé (exemplo)", endereco="Travessa Exemplo, 20 · Jurunas, Belém",
                              licenca_numero="SESMA-0002-EXEMPLO", licenca_validade=date(2026, 11, 10),
                              curso_casa_acai_em=None)
    disp = db.session.execute(select(Dispositivo).where(Dispositivo.identificador == "ORK01")).scalar_one_or_none()
    if disp is None:
        disp = Dispositivo(estabelecimento_id=rosa_est.id, identificador="ORK01",
                           chave_hmac_cifrada=cifrar(CHAVE_DEMO_ORK01))
        db.session.add(disp)

    hash_senha = generate_password_hash(senha)
    aceite = regras.agora()
    _usuario("rosa@exemplo.com", hash_senha, nome="Rosa (exemplo)", perfil=PerfilUsuario.BATEDOR,
             estabelecimento_id=rosa_est.id, termo_aceito_em=aceite)
    _usuario("ze@exemplo.com", hash_senha, nome="Zé (exemplo)", perfil=PerfilUsuario.BATEDOR,
             estabelecimento_id=ze_est.id, termo_aceito_em=aceite)
    fiscal = _usuario("fiscal@exemplo.com", hash_senha, nome="Fiscal (exemplo)", perfil=PerfilUsuario.FISCAL)
    _usuario("admin@exemplo.com", hash_senha, nome="Admin (exemplo)", perfil=PerfilUsuario.ADMIN)
    if not db.session.execute(select(Vistoria.id).where(Vistoria.estabelecimento_id == rosa_est.id)).first():
        db.session.add(Vistoria(estabelecimento_id=rosa_est.id, fiscal_id=fiscal.id,
                                data=regras.hoje() - timedelta(days=20), resultado="regular",
                                observacoes="Tanque e haste em ordem."))
    db.session.commit()
    return disp


def enviar_ciclos(app, ciclos: list[dict]) -> bool:
    """Pelo endpoint real, em blocos de 50, como o ESP32."""
    cliente = app.test_client()
    chave = CHAVE_DEMO_ORK01.encode()
    for i in range(0, len(ciclos), 50):
        with app.app_context():
            enviado_em = iso_belem(regras.agora())
        resposta = cliente.post("/api/ciclos", json={
            "dispositivo": "ORK01", "enviado_em": enviado_em,
            "assinatura_envio": assinar_envio("ORK01", enviado_em, chave), "ciclos": ciclos[i:i + 50]})
        corpo = resposta.get_json()
        if resposta.status_code != 200 or corpo["recusados"]:
            print("Falha ao enviar ciclos:", resposta.status_code, corpo)
            return False
    return True


def completar_antigos() -> None:
    """Todos completos, menos os LOTES_A_COMPLETAR mais recentes."""
    lotes = db.session.execute(
        select(Lote).join(Ciclo, Ciclo.lote_id == Lote.id).join(Dispositivo, Lote.dispositivo_id == Dispositivo.id)
        .where(Dispositivo.identificador == "ORK01").order_by(Ciclo.inicio)).scalars().all()
    for lote in lotes[:-LOTES_A_COMPLETAR]:
        lote.origem_fruto = "Ilha do Combu"
        lote.quantidade_rasas = 3
        lote.catacao = lote.sanitizacao = lote.resfriamento = True
        lote.status = StatusLote.COMPLETO
    db.session.commit()


def imprimir_acessos(app, senha: str, proximo_contador: int) -> None:
    print(f"Logins (senha '{senha}'):")
    print("  rosa@exemplo.com   batedora do Açaí da Dona Rosa (ORK01)")
    print("  ze@exemplo.com     batedor do Açaí do Zé (sem dispositivo)")
    print("  fiscal@exemplo.com / admin@exemplo.com")
    print(f"Página pública: {app.config['URL_PUBLICA']}/p/{SLUG}")
    print("Chave do ORK01: a de demonstração (a mesma do firmware/oriki_tinkercad.ino). Simulador:")
    print(f"  python scripts/simular_esp32.py --dispositivo ORK01 --chave {CHAVE_DEMO_ORK01} "
          f"--contador-inicial {proximo_contador}")
    print("Bancada virtual (roda o .ino do firmware, pasta simulador/ ao lado do backend):")
    print(f"  python bancada.py --contador-inicial {proximo_contador}")


def main() -> int:
    app = create_app()
    if app.config["COOKIE_SEGURO"] and "--forcar" not in sys.argv:
        print("COOKIE_SEGURO=1 indica produção; o seed cria senhas conhecidas. Abortado.")
        return 1
    senha = os.environ.get("SEED_SENHA", SENHA_PADRAO)

    with app.app_context():
        if "--recriar" in sys.argv:
            apagar_exemplo()
            print("Dados de exemplo apagados.")
        disp = garantir_cadastros(senha)
        ultimo = db.session.scalar(
            select(Ciclo.contador).join(Lote, Ciclo.lote_id == Lote.id)
            .where(Lote.dispositivo_id == disp.id).order_by(Ciclo.contador.desc()).limit(1))
        if ultimo is not None:
            print(f"O ORK01 já tem ciclos (último contador: {ultimo}); nada duplicado. "
                  "Para gerar de novo, relativo a hoje: python seed.py --recriar")
            imprimir_acessos(app, senha, ultimo + 1)
            return 0
        ciclos = gerar_ciclos(CHAVE_DEMO_ORK01.encode())

    if not enviar_ciclos(app, ciclos):
        return 1
    with app.app_context():
        completar_antigos()
        dia_demo, _ = dia_da_demo()

    print(f"Seed aplicado: {len(ciclos)} ciclos (contadores 1 a {len(ciclos)}, sem lacuna).")
    print(f"Dia da demonstração: {dia_demo.strftime('%d/%m/%Y')} — {HOJE_APROVADOS} aprovados, "
          f"{HOJE_REPROVADOS} reprovado, {LOTES_A_COMPLETAR} lotes a completar.")
    imprimir_acessos(app, senha, len(ciclos) + 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
