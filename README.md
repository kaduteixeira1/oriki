# Oriki

**Registro verificável do branqueamento do açaí em Belém.** Um dispositivo no tanque registra cada
branqueamento (água a 80 °C por 10 segundos, como exige o Decreto Estadual nº 326/2012). A plataforma web guarda
o histórico por lote, e um QR Code na vitrine mostra ao consumidor a licença, a capacitação e os últimos ciclos
do ponto.

> "80 °C, 10 segundos, comprovado."

Projeto Integrado do curso de Ciência da Computação do CESUPA (2026), feito por Carlos Eduardo Teixeira,
Maria Clara Arruda e Rafael Chada.

## Sumário

- [O problema](#o-problema)
- [Como funciona](#como-funciona)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Tecnologias](#tecnologias)
- [Rodar no Windows](#rodar-no-windows)
- [Demonstração em 5 minutos](#demonstração-em-5-minutos)
- [Funcionalidades](#funcionalidades)
- [Segurança e LGPD](#segurança-e-lgpd)
- [Testes](#testes)
- [Entregas](#entregas)
- [Documentação de cada parte](#documentação-de-cada-parte)

## O problema

A norma existe e a fiscalização funciona, mas entre uma vistoria e outra não há registro de que o branqueamento
foi feito em cada lote. O branqueamento é o que elimina o parasita da doença de Chagas, e no Pará a transmissão
oral, pelo alimento, responde pela grande maioria dos casos agudos. A licença sanitária é anual, e o consumidor só
vê um papel na parede.

O Oriki não substitui a fiscalização nem emite selo. Ele é a camada de **prova de processo**: o sensor registra
temperatura e tempo da água em cada lote, o registro é assinado para não poder ser forjado, e a fonte oficial
continua sendo a licença da Sesma.

## Como funciona

```mermaid
flowchart LR
    subgraph Ponto["Ponto de venda"]
        ESP["ESP32 + DS18B20<br/>fila local assinada"]
        CEL["Celular da batedora<br/>PWA com fila offline"]
    end
    QR["QR na vitrine"] --> CONS["Celular do consumidor"]
    FISC["Fiscal (navegador)"]
    ESP -- "POST /api/ciclos<br/>HMAC-SHA256" --> API
    CEL -- "completa o lote" --> API
    CONS -- "página pública, sem login" --> API
    FISC -- "alertas e vistorias" --> API
    API["Flask"] --> DB[("PostgreSQL")]
```

1. A batedora aperta o botão **novo lote** no dispositivo. Ele confere se a água chegou a 80 °C, conta os
   10 segundos com o cesto na água e apita.
2. O ciclo (início, fim, temperaturas, segundos acima de 80 °C, aprovado ou reprovado) é gravado na memória do
   dispositivo com um **contador sequencial** e uma **assinatura HMAC**, mesmo sem internet.
3. Quando há Wi-Fi, o dispositivo envia a fila. A API confere a assinatura, ignora reenvios e recusa o que foi
   alterado.
4. O ciclo vira um lote "a completar" no app. A batedora informa a origem do fruto, a quantidade e as etapas
   manuais (catação, sanitização e resfriamento), mesmo offline.
5. O consumidor escaneia o QR e vê os registros dos últimos 7 dias. O fiscal vê alertas e o histórico entre
   uma vistoria e outra.

## Estrutura do repositório

```
oriki/
├── backend/      API Flask + PostgreSQL, testes e comandos de cadastro
├── frontend/     PWA em React (batedora, consumidor e fiscal) e a demonstração para o navegador
└── simulador/    bancada virtual: roda o firmware .ino do ESP32 no PC, ligado a um tanque simulado
```

Nesta fase o ESP32 é **simulado**: a bancada compila e roda no computador o mesmo `.ino` que iria para a placa,
e envia os ciclos assinados para a API de verdade.

## Tecnologias

| Parte | Tecnologias |
| --- | --- |
| Backend | Python 3.12, Flask 3.1, SQLAlchemy + Alembic, PostgreSQL 16, Flask-Login, Flask-Limiter, cryptography (Fernet), fpdf2, qrcode |
| Frontend | React 19, Vite 6, React Router, PWA (Service Worker + IndexedDB) |
| Firmware | ESP32 (Arduino), DS18B20, RTC DS3231, LittleFS, HMAC-SHA256 |
| Simulador | Python (biblioteca padrão) + compilador C++ (zig), painel em HTML |
| Testes | pytest (181 testes), ESLint, cenários automáticos na bancada |

## Rodar no Windows

Requisitos: **Python 3.12+** e **Node.js 20+**. Não precisa instalar o PostgreSQL: o projeto traz um portátil
para desenvolvimento.

### Primeira vez

**1. Backend** (pasta `backend`):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pip install pgserver
copy .env.example .env
```

No `.env`, preencha `SECRET_KEY` e `CHAVE_CIFRA` (os comandos para gerar estão no próprio arquivo) e troque as
duas URLs do banco pelas do PostgreSQL portátil:

```
DATABASE_URL=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki
DATABASE_URL_TESTE=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki_test
```

Depois, ainda em `backend`:

```bat
python scripts\postgres_portatil.py iniciar
flask db upgrade
python seed.py --recriar
```

**2. Frontend** (pasta `frontend`):

```bat
npm install
npm run build
```

### No dia a dia

| O que | Como | Endereço |
| --- | --- | --- |
| Banco, API e app | dois cliques em `backend\iniciar.bat` | http://localhost:5000 |
| Bancada do ESP32 | dois cliques em `simulador\iniciar_bancada.bat` | http://localhost:8090 |

Contas de exemplo (senha `oriki-dev-2026`):

| Conta | Perfil | Situação no exemplo |
| --- | --- | --- |
| `rosa@exemplo.com` | Batedora | Açaí da Dona Rosa: licença em dia, dispositivo ORK01, 30 ciclos na semana |
| `ze@exemplo.com` | Batedor | Açaí do Zé: licença vencida, sem dispositivo |
| `fiscal@exemplo.com` | Fiscal | Vê todos os pontos |
| `admin@exemplo.com` | Admin | Mesmo acesso do fiscal |

Páginas do consumidor: http://localhost:5000/p/acai-da-dona-rosa e http://localhost:5000/p/acai-do-ze

Para desenvolver o front com recarga automática: `npm run dev` em `frontend` (http://localhost:5173; o `/api`
vai para o Flask).

## Demonstração em 5 minutos

Com o `iniciar.bat` e o `iniciar_bancada.bat` abertos:

1. No painel da bancada, quadro **Celular (app do Oriki)**, clique em **Recomeçar os dados**. Isso roda o
   `seed.py --recriar` e zera a memória do dispositivo.
2. Clique em **Abrir o app**, entre como `rosa@exemplo.com` e deixe essa aba ao lado do painel.
3. No tanque, clique em **Fazer um lote aprovado**. Em uns 20 segundos o lote aparece sozinho na tela inicial
   do app, em "Lotes a completar". **Fazer um lote reprovado** mostra o caso de água que esfriou antes dos 10 s.
4. No app, complete o lote com a origem do fruto e a quantidade em rasas.
5. Clique em **Escanear o QR da Dona Rosa** para ver a página do consumidor.
6. Na bancada, desligue o **roteador Wi-Fi**, faça um lote e digite `adulterar N` no Monitor serial (N é o
   número do ciclo, ex.: `adulterar 32`). Ligue o Wi-Fi: o servidor recusa esse ciclo.
7. No app, saia e entre como `fiscal@exemplo.com`. O painel mostra o alerta "Envio recusado", e o detalhe do
   ponto mostra a recusa, os escaneamentos do QR e o registro de vistorias.

Para fazer o lote passo a passo: **BOTÃO** (novo lote) → esperar o LED verde piscar → **Mergulhar o cesto** →
**BOTÃO** (começa a contar) → apito dos 10 s → **BOTÃO** de novo para fechar o ciclo.

## Funcionalidades

| Perfil | O que faz |
| --- | --- |
| **Batedora** | Login e termo de uso; tela inicial com o dia (aprovados e reprovados), último ciclo e lotes a completar, atualizada sozinha a cada 10 s; formulário do lote com origem, quantidade e checklist, que funciona sem internet; histórico por período; relatório em PDF para a vistoria; QR do ponto para imprimir |
| **Consumidor** | Página pública pelo QR, sem login: licença, curso da Casa do Açaí, última vistoria e os ciclos dos últimos 7 dias |
| **Fiscal** | Painel de alertas (licença vencida ou vencendo, ponto sem registro, ciclos reprovados, dispositivo sem contato, relógio fora de hora, contador com lacuna, envio recusado); detalhe do ponto com integridade dos registros, ciclos × rasas por dia e escaneamentos do QR; registro de vistoria |
| **Dispositivo** | Ciclo de 80 °C por 10 s com LEDs e buzzer; fila local; assinatura HMAC de cada ciclo; envio a cada 5 min, 10 s depois de cada ciclo e assim que o Wi-Fi volta; ajuste do relógio pela hora do servidor |

## Segurança e LGPD

| Ameaça | Controle |
| --- | --- |
| Ciclo forjado | Cada dispositivo tem uma chave própria; cada ciclo leva assinatura HMAC-SHA256, e a API recusa a inválida |
| Registro editado na memória | A assinatura cobre todos os campos; mudar "reprovado" para "aprovado" invalida o ciclo |
| Registro apagado | Contador sequencial dentro da assinatura; número faltando vira alerta de lacuna para o fiscal |
| Reenvio de ciclo antigo | Código único por ciclo: reenvio idêntico é ignorado, e o mesmo código com outra assinatura é recusado |
| Relógio adulterado | A API compara a hora do dispositivo com a do servidor e marca o ciclo |
| Vazamento do banco | Chaves dos dispositivos cifradas com Fernet; a chave de cifra fica só no ambiente |
| Acesso indevido | Senhas com hash, limite de tentativas de login, perfis separados e cada batedor vendo só o próprio ponto |

A página pública mostra só dados do estabelecimento, nunca nome, e-mail ou telefone de pessoas. O consumidor
não faz login e não é rastreado: o sistema guarda só o total de escaneamentos por dia.

**Limite declarado:** o sensor prova a temperatura e o tempo da água, não que o fruto estava no cesto. Por isso
o Oriki mostra registros, não emite selo, e a vistoria continua sendo a fonte oficial.

## Testes

O `pytest` roda os 181 testes do backend num banco separado (`oriki_test`), sem mexer nos dados de exemplo.

```bat
cd backend
pytest

cd ..\frontend
npm run lint

cd ..\simulador
python bancada.py --cenario criterio --velocidade 5 --contador-inicial 31
python bancada.py --cenario integridade --velocidade 5 --contador-inicial 31
python bancada.py --cenario offline --velocidade 6 --contador-inicial 31
```

Os três cenários da bancada são os testes do documento do projeto, cada um com sua meta:

| Teste | Meta |
| --- | --- |
| Critério do ciclo | 30 de 30 ciclos classificados certo |
| Integridade | 100% das alterações recusadas ou sinalizadas |
| Sincronização offline | 50 de 50 ciclos no servidor, sem duplicados |

Cada cenário grava um relatório em `simulador/relatorios/`. Rode o `seed.py --recriar` e apague a pasta
`simulador/dados` entre um cenário e outro, para os contadores não colidirem.

## Entregas

| Data | Entrega | Situação |
| --- | --- | --- |
| 08/10 | Arquitetura: circuito, protótipo das telas, modelo de dados e esqueleto do backend | Feita |
| 15/10 | MVP da API e estrutura do front | Feita |
| 22/10 | Algoritmo de branqueamento e assinatura HMAC | Feita |
| 29/10 | Envio do dispositivo para a API e artigo parcial | Feita |
| 05/11 | PWA offline-first | Feita |
| 12/11 | Página do consumidor via QR, QR do ponto e contagem de acessos | Feita |
| 19/11 | Testes integrados (sincronização offline, integridade e critério do ciclo) | Próxima |
| 26/11 | Histórico, relatório em PDF e painel do fiscal | Já implementada |
| 03/12 | Tratamento de exceções (lote reprovado, erros de envio, dispositivo sem contato) | Já implementada |
| 10/12 | Revisão de textos, acessibilidade e termo de uso (LGPD) | Em andamento |
| 17/12 | Deploy, piloto em um ponto e apresentação final | A fazer |

## Documentação de cada parte

- [backend/README.md](backend/README.md): API, banco, comandos de cadastro, variáveis de ambiente e testes.
- [frontend/README.md](frontend/README.md): telas, modo offline, convenções e a demonstração para o navegador.
- [simulador/README.md](simulador/README.md): bancada virtual, firmware, comandos do Monitor serial e cenários.
