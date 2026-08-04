@echo off
REM Sincroniza o Digifarma com o app (publica direto no Firebase).
chcp 65001 >nul
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado. Instale em https://python.org (marque Add to PATH).
  pause & exit /b 1
)

python -c "import firebird.driver, firebase_admin" >nul 2>&1
if errorlevel 1 (
  echo Instalando bibliotecas...
  python -m pip install firebird-driver firebase-admin
)

python agente_auto.py
if errorlevel 1 ( echo. & echo Houve um erro. Veja agente_erro.log & pause )
