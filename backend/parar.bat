@echo off
rem Desliga o PostgreSQL portatil (a API para quando a janela do iniciar.bat e fechada).
chcp 65001 > nul
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\postgres_portatil.py parar
pause
