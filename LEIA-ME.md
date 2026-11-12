# Oriki — software completo (backend, front e simulador do ESP32)

```
oriki/
├── backend/     API Flask + PostgreSQL (repositório oriki-back)
├── frontend/    PWA em React (repositório oriki-front)
└── simulador/   bancada virtual: roda o .ino do firmware no PC e envia para a API
```

## Subir tudo no Windows (primeira vez)

1. **Backend** (pasta `backend`), como no README dele:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   pip install pgserver
   copy .env.example .env
   ```
   No `.env`, preencha `SECRET_KEY` e `CHAVE_CIFRA` (os comandos estão no próprio arquivo) e troque as duas URLs
   do banco pelas do PostgreSQL portátil:
   ```
   DATABASE_URL=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki
   DATABASE_URL_TESTE=postgresql+psycopg://oriki:oriki@127.0.0.1:5433/oriki_test
   ```
   Depois:
   ```bat
   python scripts\postgres_portatil.py iniciar
   flask db upgrade
   python seed.py --recriar
   ```
2. **Front** (pasta `frontend`): `npm install` e `npm run build`.
3. **No dia a dia**: dois cliques em `backend\iniciar.bat` (API + app em http://localhost:5000) e em
   `simulador\iniciar_bancada.bat` (painel do dispositivo em http://localhost:8090).

Logins do seed (senha `oriki-dev-2026`): `rosa@exemplo.com` (batedora), `fiscal@exemplo.com`, `admin@exemplo.com`.
Página do consumidor: http://localhost:5000/p/acai-da-dona-rosa

## Demonstração em 1 minuto

No topo do painel da bancada, o quadro **Celular (app do Oriki)** abre o app (entre como Rosa), a página do
consumidor pelo QR e o QR do Zé, cada um numa aba nova. Deixe a aba do app ao lado do painel. O botão
**Recomeçar os dados** roda o `seed.py --recriar` e zera a memória do dispositivo, para começar a
apresentação do zero.

1. Na bancada, clique no **BOTÃO** (novo lote), espere o verde piscar, clique em **Mergulhar o cesto** e no
   **BOTÃO** de novo. Aos 10 s o buzzer apita: clique no **BOTÃO** para fechar o ciclo.
   Atalho: **Fazer um lote aprovado** (ou **reprovado**) no painel faz esse passo a passo inteiro num clique.
2. Em 10 s o firmware envia: o lote aparece em "Lotes a completar" no app da batedora (a tela inicial se
   atualiza sozinha a cada 10 s, sem recarregar) e na página do QR.
3. Desligue o roteador Wi-Fi, faça mais ciclos e ligue de novo: a fila sobe sozinha.
4. Com o Wi-Fi desligado, faça um ciclo e digite `adulterar N` no Monitor serial (N = número do ciclo, ex.: 33). Ligue o Wi-Fi: o servidor recusa esse ciclo e o fiscal vê o alerta "Envio recusado".

Para desenvolver o front com recarga automática: `npm run dev` em `frontend` (http://localhost:5173, o `/api`
vai para o Flask).
