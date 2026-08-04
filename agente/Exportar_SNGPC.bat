@echo off
REM ============================================================
REM  Exporta o inventario de controlados (SNGPC) do Digifarma
REM  Basta dar dois cliques neste arquivo.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === Exportador de inventario SNGPC (Digifarma) ===
echo.

REM Verifica se o Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado.
  echo Instale em https://python.org e marque "Add Python to PATH".
  pause
  exit /b 1
)

REM Instala o driver do Firebird se faltar
python -c "import firebird.driver" >nul 2>&1
if errorlevel 1 (
  echo Instalando o driver do Firebird...
  python -m pip install firebird-driver
)

REM Roda o agente
python agente_sngpc.py

echo.
echo Pronto. O arquivo inventario_sngpc.json foi gerado nesta pasta.
echo Agora importe ele no app: Painel ADM ^> Config ^> Importar inventario.
echo.
pause
