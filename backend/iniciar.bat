@echo off
rem Liga o ambiente de desenvolvimento do Oriki: PostgreSQL portatil + API Flask + app (build do React).
rem Uso: de dois cliques neste arquivo. Para desligar: feche a janela (ou Ctrl+C) e rode parar.bat.
chcp 65001 > nul
cd /d "%~dp0"
title Oriki - servidor (feche esta janela para parar)

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado em .venv. Veja o README.md, secao "Rodar localmente".
    pause
    exit /b 1
)

echo [1/3] Ligando o PostgreSQL...
".venv\Scripts\python.exe" scripts\postgres_portatil.py iniciar || goto erro

echo [2/3] Aplicando migracoes pendentes...
".venv\Scripts\flask.exe" db upgrade || goto erro

echo [3/3] Ligando a API em http://localhost:5000
echo        Deixe esta janela aberta. Para parar: feche a janela ou aperte Ctrl+C.
echo.
rem Serve o app React se o build existir (npm run build em ..\frontend); senao, o console de teste.
if exist "..\frontend\dist\index.html" (
    set FRONTEND_DIST=..\frontend\dist
) else (
    echo        Sem ..\frontend\dist: abrindo o console de teste. Rode "npm run build" no frontend para o app.
    set FRONTEND_DIST=dev-console
)
start "" http://localhost:5000
".venv\Scripts\flask.exe" run --port 5000
goto fim

:erro
echo.
echo Algo falhou acima. Leia a mensagem de erro.
:fim
pause
