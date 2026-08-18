@echo off
chcp 65001 >nul
title Instalar o chromedriver do Anvisa.exe

REM ============================================================
REM  INSTALAR_CHROMEDRIVER.bat  -  dois cliques.
REM
REM  O Anvisa.exe e automacao de navegador. Sem o chromedriver na
REM  pasta dele, abre e fecha na hora: sem janela, sem log, e com
REM  codigo de saida 0, que parece "terminou normal". Foi assim
REM  que ele apareceu quebrado na farmacia em 18/08/2026 - o
REM  arquivo simplesmente nao estava mais la.
REM
REM  O trabalho de verdade esta no instalar_chromedriver.ps1, ao
REM  lado deste arquivo: la da para ler JSON e descompactar zip
REM  sem malabarismo. Este .bat so chama, com a politica liberada
REM  so para esta execucao - nao mexe na configuracao da maquina.
REM
REM  Nao precisa de administrador, a menos que a pasta do
REM  Digifarma esteja protegida.
REM ============================================================

cd /d "%~dp0"

set "SCRIPT=%~dp0instalar_chromedriver.ps1"
if not exist "%SCRIPT%" (
  echo.
  echo  Nao achei o instalar_chromedriver.ps1 nesta pasta.
  echo  Baixe os dois arquivos juntos:
  echo.
  echo    curl -fL -o instalar_chromedriver.ps1 https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA/main/agente/instalar_chromedriver.ps1
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "CODIGO=%ERRORLEVEL%"

echo.
if "%CODIGO%"=="0" (
  echo  Terminou bem.
) else (
  echo  Terminou com problema. A explicacao esta acima.
)
echo.
pause
