# Oriki — backend

API Flask + PostgreSQL do Oriki, fases F0–F5 do plano técnico do projeto.

Faz parte do repositório [oriki](https://github.com/kaduteixeira1/oriki): o app fica em `../frontend` (o Flask
serve o build dele, `../frontend/dist`; outro caminho vai em `FRONTEND_DIST` no `.env`) e o firmware com a
bancada virtual que o roda no PC fica em `../simulador`. Para subir tudo de uma vez, siga o
[README principal](../README.md). O contrato com o firmware está em `app/assinatura.py` e `app/contrato.py`,
e `tests/dados/` guarda saídas reais do Monitor serial.

## Rodar localmente

Requisitos: Python 3.12+ e PostgreSQL 16.

```bash
python -m venv .venv
.venv\Scripts\activate                 # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env                 # Linux/macOS: cp; depois preencha SECRET_KEY e CHAVE_CIFRA
flask db upgrade
python seed.py --recriar               # dados de exemplo relativos a hoje (senha: oriki-dev-2026)
flask run                              # http://localhost:5000
```

Sem PostgreSQL instalado (Windows), dá para usar um portátil só para desenvolvimento:

```bash
pip install pgserver
python scripts/postgres_portatil.py iniciar     # porta 5433; cria os bancos oriki e oriki_test
```

### App completo no mesmo endereço

Com o build do front (`npm run build` em `../frontend`), o Flask serve o app e a API juntos em
http://localhost:5000 (o padrão do `.env`, `FRONTEND_DIST=../frontend/dist`). O `iniciar.bat` faz isso sozinho
quando o build existe.

### Console de teste no navegador

```bash
set FRONTEND_DIST=dev-console          # PowerShell: $env:FRONTEND_DIST="dev-console"
flask run                              # abra http://localhost:5000
```

Uma página simples (`dev-console/`) com login, simulador do ESP32 assinando no navegador, telas do batedor,
do fiscal e da página pública, e o JSON de cada resposta. Só para desenvolvimento: serve para testar o fiscal
e a página pública sem passar pelo app.

## Testes

```bash
pytest
```

Usam o banco de `DATABASE_URL_TESTE`, que **precisa terminar em `_test`** (o schema é apagado e recriado
pela própria migração a cada execução). Cada teste roda numa transação desfeita no final.

## Simular o ESP32

```bash
python scripts/simular_esp32.py --chave <chave> --quantidade 5
python scripts/simular_esp32.py --chave <chave> --pular 3            # lacuna de contador
python scripts/simular_esp32.py --chave <chave> --adulterar          # deve voltar assinatura_invalida
python scripts/simular_esp32.py --chave <chave> --repetir            # reenvio: não duplica
python scripts/simular_esp32.py --chave <chave> --relogio-atrasado 600
```

A chave sai do `seed.py` (ORK01 usa a chave de demonstração do firmware) ou do `flask criar-dispositivo`. O simulador confere os vetores da seção 7.2 antes de enviar.

## Conferir a saída do firmware

Copie o Monitor serial do Tinkercad (ou do ESP32) para um arquivo e confira as assinaturas:

```bash
python scripts/conferir_envio.py saida.txt --do-banco ORK01           # chave do banco do .env
python scripts/conferir_envio.py saida.txt --chave <64 hex>
python scripts/conferir_envio.py saida.txt --chave <64 hex> --enviar http://127.0.0.1:5000
```

Arquivos `saida_do_tinkercad*.txt` ficam fora do Git (`.gitignore`).

## Comandos de administração

| Comando | O que faz |
|---|---|
| `flask criar-estabelecimento --nome … --endereco … --licenca … --validade AAAA-MM-DD [--curso-em …] --slug …` | Cadastra o ponto |
| `flask criar-dispositivo --identificador ORK02 --estabelecimento <slug>` | Cria o dispositivo e mostra a chave **uma vez** |
| `flask trocar-chave-dispositivo --identificador ORK02` | Nova chave (perda ou vazamento) |
| `flask criar-usuario --nome … --email … --perfil batedor\|fiscal\|admin [--estabelecimento <slug>]` | Senha pedida sem eco (mín. 10 caracteres) |
| `flask trocar-senha --email …` | Nova senha; derruba as sessões abertas |
| `flask anonimizar-usuario --email …` | Pedido de exclusão (LGPD) |
| `flask recifrar-chaves` | Troca da `CHAVE_CIFRA` sem perder dispositivos (veja abaixo) |

Trocar a `CHAVE_CIFRA`: defina `CHAVE_CIFRA=nova,antiga`, rode `flask recifrar-chaves` e depois deixe só `CHAVE_CIFRA=nova`.

## Deploy

`Procfile` pronto (gunicorn com **1 worker** enquanto o limitador usar `memory://`; migração no `release`).
No provedor: `COOKIE_SEGURO=1`, `PROXIES_CONFIAVEIS=1`, `SECRET_KEY`, `CHAVE_CIFRA`, `URL_PUBLICA` e
`FRONTEND_DIST` (o Flask serve o build do React no mesmo domínio). Checklist completo na seção 14 do plano.

## Onde a implementação vai além do plano

Escolhas feitas para segurança e robustez. Todas têm teste.

- **Ciclos imutáveis no banco**: um gatilho recusa `UPDATE`/`DELETE` em `ciclos`, além de a API não ter rota para isso.
- **CHECKs no banco** espelham as regras da API (status coerente com os campos, faixa de temperatura, `aprovado` ≥ 10 s, formato do slug, do identificador e da assinatura).
- **`usuarios.token_sessao`**: anonimizar ou trocar a senha invalida na hora todas as sessões e os cookies "lembrar" já emitidos. **`usuarios.anonimizado_em`** marca a conta como inativa.
- **Termo de uso exigido no servidor**: o batedor recebe `403 termo_pendente` nas rotas de batedor até chamar `POST /api/batedor/termo`.
- **CSRF**: além do SameSite=Lax, as rotas que alteram dados exigem `Content-Type: application/json` (senão **415**) e recusam `Origin` de outro domínio (**403**). O PWA precisa enviar `Content-Type: application/json` também no `logout` e no `termo` (pode mandar `{}` no corpo).
- **Login**: 5/min por IP (como no plano) e 20/hora por e-mail. O tempo de resposta é o mesmo para e-mail inexistente e senha errada.
- **Cabeçalhos**: `Cache-Control: no-store` em toda a API (a página pública mantém `public, max-age=60`), CSP, `nosniff`, `X-Frame-Options` e HSTS em produção.
- **Ingestão em bloco**: 1 consulta para os códigos já gravados, 1 `INSERT … ON CONFLICT DO NOTHING` para os lotes e 1 `INSERT` para os ciclos. Isso também cobre dois envios simultâneos do mesmo ciclo.
- **`CHAVE_CIFRA` com rotação** (MultiFernet) e o comando `recifrar-chaves`.
- **Log de segurança** com proteção contra injeção de linhas. Com `LOG_SEGURANCA_ARQUIVO`, grava um arquivo por dia e guarda 90.
- **Recusas de envio no banco (OR-31)**: cada ciclo recusado no `POST /api/ciclos` (depois de a assinatura do
  envio conferir) vai para a tabela `recusas_envio` (migração 0002). Vira o alerta `envios_recusados` (últimos 7
  dias) e a lista `recusas` no detalhe do ponto. O detalhe também traz `acessos_qr` (total e por dia, OR-23).
- **Extras nas respostas**: `total_a_completar` no resumo (a lista vem limitada a 100), e o detalhe do fiscal traz `lacunas` e `por_dia` com aprovados, reprovados e lotes completos.

## Convenção de commits

[Conventional Commits](https://www.conventionalcommits.org/pt-br/) em português, com o cartão do Trello no
fim do título quando houver: `tipo(escopo): descrição curta [OR-XX]`.

- **tipo**: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.
- **escopo**: `backend`, `seed`; omita quando o commit é do repositório todo.
- Exemplo: `feat(backend): conferidor do envio do firmware e teste de contrato [OR-12]`.

Ficam fora do Git (veja o `.gitignore`): `.env`, certificados e chaves, qualquer `.md` que não seja README
(roteiros e instruções de tarefa), PDFs, o firmware e saídas locais.
