@echo off
rem Liga a bancada virtual do ESP32 (painel em http://localhost:8090).
rem Antes: deixe a API rodando (backend\iniciar.bat). Para outro sketch: iniciar_bancada.bat firmware\oriki_tinkercad
chcp 65001 > nul
cd /d "%~dp0"
title Oriki - bancada virtual (feche esta janela para parar)

set PY=
if exist "..\backend\.venv\Scripts\python.exe" set PY=..\backend\.venv\Scripts\python.exe
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" (
    echo Python nao encontrado. Instale o Python 3.10+ ou crie o .venv do backend.
    pause
    exit /b 1
)

rem Compilador C++: usa o g++/clang se houver; senao, o zig (pip install ziglang, sem instalar mais nada).
where g++ >nul 2>nul || where clang++ >nul 2>nul || (
    "%PY%" -c "import ziglang" 2>nul || (
        echo Instalando o compilador zig pelo pip ^(so na primeira vez^)...
        "%PY%" -m pip install ziglang || goto erro
    )
)

rem --contador-inicial 31: numa memoria nova, continua os 30 ciclos do seed.py (sem conflito com o banco).
"%PY%" bancada.py %* --contador-inicial 31
goto fim

:erro
echo.
echo Algo falhou acima. Leia a mensagem de erro.
:fim
pause
