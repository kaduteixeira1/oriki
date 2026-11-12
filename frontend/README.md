# Oriki — frontend

PWA do batedor em React 19 + Vite 6 + React Router 6, conforme o protótipo do Figma.

A API fica em outro repositório: [oriki-back](https://github.com/kaduteixeira1/oriki-back). Clone os dois lado a
lado, com as pastas `backend` e `frontend`, e siga o README do backend para subir a API e o banco:

```bash
git clone https://github.com/kaduteixeira1/oriki-back.git backend
git clone https://github.com/kaduteixeira1/oriki-front.git frontend
```

Com a API rodando (`flask run` em `backend/`):

```bash
npm install
npm run dev      # http://localhost:5173 (o /api vai para o Flask em 127.0.0.1:5000)
npm run build    # gera dist/, que o Flask serve em produção (FRONTEND_DIST)
npm run lint
```

Telas:

| Rota | Tela |
|---|---|
| `/login` | Entrar (batedor, fiscal ou admin) |
| `/batedor` | Home: ponto e licença, hoje, último ciclo, lotes a completar e "Meu ponto" |
| `/batedor/lotes/:codigo` | Completar lote (funciona sem internet, OR-19) |
| `/batedor/historico` | Histórico por período e situação (OR-27) |
| `/batedor/relatorio` | Relatório em PDF para a vistoria (OR-28) |
| `/batedor/qr` | QR do ponto para imprimir (OR-22) |
| `/p/:slug` | Página do consumidor, aberta pelo QR (`?origem=qr` conta o acesso, OR-21/OR-23) |
| `/fiscal` | Painel do fiscal: alertas de todos os pontos, com filtro por tipo, e lista de pontos com busca (OR-29) |
| `/fiscal/pontos/:id` | Detalhe do ponto: dispositivos, ciclos × rasas por dia, lacunas, envios recusados (OR-31), acessos do QR, lotes e vistorias (com o registro de uma nova) |

**Celular ou web**: o botão "Web"/"Celular" na barra (e no login) troca o layout. O de celular é a coluna de
420 px do protótipo; o web usa a largura da tela, com colunas e o menu na barra. A escolha fica guardada no
aparelho; sem escolha, telas com 1024 px ou mais abrem no web. Lote reprovado aparece com a borda vermelha em
todas as telas (OR-30).

Estrutura:

- `src/api.js` — chamadas à API; erros viram `ErroApi` com `status`, `erro` e `detalhes`.
- `src/layout.jsx` — alternância celular/web (`LayoutProvider`, `useLayout`, `BotaoLayout`).
- `src/alertas.js` — tipos de alerta do painel do fiscal, do mais grave para o menos.
- `src/fila.js` — fila offline (OR-19): sem internet, o lote salvo fica no IndexedDB e sobe sozinho depois.
- `src/paginas/` — uma tela por arquivo; `SoBatedor` protege as rotas do batedor e mostra o termo de uso;
  `SoFiscal` protege as do fiscal (fiscal e admin).
- `src/componentes.jsx` — barra do app, chips de status e botão Sair.
- `src/formato.js` — datas no fuso de Belém, temperaturas e o motivo do lote reprovado (OR-30).
- `src/estilo.css` — tokens do protótipo (cores, raios, tipografia).
- `public/sw.js` e `public/manifest.webmanifest` — app instalável que abre sem internet (OR-20).

O Service Worker só é registrado no build (`npm run build`): para testar o modo offline, sirva o `dist/` pelo
Flask (`FRONTEND_DIST`, em http://localhost:5000) ou com `npm run preview`. Ao mudar o que o `sw.js` guarda,
troque a constante `VERSAO` dentro dele.

A fonte Inter vem do pacote `@fontsource/inter`, dentro do build: a CSP do backend (`font-src 'self'`)
bloquearia o Google Fonts, e assim a fonte também funciona offline.


## Demonstração dentro do Claude

`npm run build:demo` gera `dist-demo/`: o app de verdade num celular, ao lado do tanque com o ESP32 simulado,
com o servidor imitado no navegador (`demo/servidor.js`, mesmas rotas e regras da API) e o firmware de
`branqueamento.ino` portado para JavaScript (`demo/dispositivo.js`). Serve para mostrar e testar o fluxo sem
instalar nada; não substitui o backend nem os testes. `npm run dev:demo` abre em http://localhost:5174.

## Convenção de commits

[Conventional Commits](https://www.conventionalcommits.org/pt-br/) em português, com o cartão do Trello no
fim do título quando houver: `tipo(escopo): descrição curta [OR-XX]`, com `feat`, `fix`, `test`, `docs`,
`refactor` ou `chore` e escopo `frontend`. Exemplo: `feat(frontend): histórico de lotes por período [OR-27]`.

Ficam fora do Git (veja o `.gitignore`): `.env`, qualquer `.md` que não seja README (roteiros e instruções
de tarefa), PDFs, prints e protótipos, `node_modules/` e `dist/`.
