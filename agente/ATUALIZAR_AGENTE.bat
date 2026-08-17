@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Agente SNGPC - atualizacao

REM ============================================================
REM  ATUALIZAR_AGENTE.bat
REM  Baixa a versao mais nova do agente, guarda a atual em backup,
REM  CONFERE se o arquivo baixado esta inteiro antes de trocar, e
REM  roda uma sincronizacao.
REM
REM  Dois cliques ............ pergunta a configuracao e espera
REM  ATUALIZAR_AGENTE.bat /auto ............... nao pergunta nada
REM  ATUALIZAR_AGENTE.bat /auto 46108 S ....... ja configura tudo
REM      2o parametro: numero da ultima venda transmitida
REM      3o parametro: S libera o app a escrever no Digifarma
REM  Parametro que nao vier NAO e alterado - de proposito: nada
REM  de mudar configuracao em silencio por causa de um default.
REM
REM  No modo /auto nao ha janela esperando: tudo vai para o
REM  atualizacao_AAAA-MM-DD.log, nesta mesma pasta.
REM
REM  Se o arquivo baixado tiver qualquer problema, nada e trocado.
REM  Agente quebrado num servidor onde ninguem esta e pior que
REM  agente desatualizado.
REM
REM  Nao precisa de administrador: nao mexe em tarefa nem em
REM  instalacao, so no agente_auto.py.
REM ============================================================

cd /d "%~dp0"

set "AUTO="
if /i "%~1"=="/auto" set "AUTO=1"
set "PONTEIRO=%~2"
set "AJUSTE=%~3"

if defined AUTO (
  set "LOG=%~dp0atualizacao_%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%.log"
  echo. >> "!LOG!"
  echo ==== %DATE% %TIME% ==================================== >> "!LOG!"
  call :principal >> "!LOG!" 2>&1
  exit /b %errorlevel%
)

call :principal
echo.
pause
exit /b %errorlevel%


REM ============================================================
:principal
REM ============================================================
echo ============================================================
echo  AGENTE SNGPC - atualizacao
echo ============================================================
echo.

REM ---------- 1. Python ----------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo  Python nao encontrado nesta maquina.
  echo  Rode o INSTALAR_AGENTE.bat como administrador primeiro.
  exit /b 1
)

REM ---------- 2. Backup ----------
echo [1/5] Guardando a versao atual...
set "CARIMBO=%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%"
set "CARIMBO=%CARIMBO: =0%"
if exist agente_auto.py (
  copy /y agente_auto.py "agente_auto_antes_de_%CARIMBO%.py" >nul
  echo       backup: agente_auto_antes_de_%CARIMBO%.py
) else (
  echo       nao havia agente_auto.py nesta pasta ^(primeira instalacao^)
)

REM ---------- 3. Baixar ----------
echo [2/5] Baixando a versao mais nova do GitHub...
set "URL=https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA/main/agente/agente_auto.py"
curl -fsSL -o agente_auto_novo.py "%URL%"
if errorlevel 1 (
  echo       curl falhou, tentando pelo PowerShell...
  powershell -NoProfile -Command "try{Invoke-WebRequest -Uri '%URL%' -OutFile 'agente_auto_novo.py'}catch{exit 1}"
)
if not exist agente_auto_novo.py (
  echo.
  echo  Nao consegui baixar. Verifique a internet e tente de novo.
  echo  Nada foi alterado.
  exit /b 1
)

REM ---------- 4. Conferir antes de trocar ----------
echo [3/5] Conferindo o arquivo baixado...
%PY% -c "import sys;t=open('agente_auto_novo.py',encoding='utf-8').read();sys.exit(0 if len(t)>20000 and 'def principal(' in t and 'CONSULTAS' in t and compile(t,'a','exec') is not None else 1)"
if errorlevel 1 (
  echo.
  echo  O arquivo baixado esta incompleto ou com erro. NADA foi trocado:
  echo  o agente que estava rodando continua no lugar.
  del agente_auto_novo.py >nul 2>&1
  exit /b 1
)
move /y agente_auto_novo.py agente_auto.py >nul
echo       arquivo conferido e instalado

REM ---------- 5. Configuracao ----------
echo.
echo [4/5] Configuracao

if defined AUTO goto :configurar

echo.
echo  O envio ao SNGPC foi feito por outro computador? Entao o ponteiro
echo  daqui ficou para tras e o agente conta as mesmas vendas duas vezes.
echo  Informe o numero da ULTIMA VENDA que foi transmitida.
echo  Enter pula esta configuracao e deixa como esta.
echo.
set /p "PONTEIRO=  Transmitido ate a venda numero: "
echo.
echo  Liberar o app a ZERAR LOTE NEGATIVO e GRAVAR CONTAGEM no Digifarma?
echo  Sao as unicas operacoes que escrevem no Digifarma, e cada uma fica
echo  registrada com o antes, o depois e quem pediu.
echo  Enter pula e deixa como esta.
echo.
set /p "AJUSTE=  Liberar? (S/N): "

:configurar
if not "!PONTEIRO!"=="" (
  %PY% agente_auto.py --config transmitido_ate_venda=!PONTEIRO!
) else (
  echo       ponteiro: nao mexi, ficou como estava
)
if /i "!AJUSTE!"=="S" (
  %PY% agente_auto.py --config permitir_ajuste_estoque=true
) else if /i "!AJUSTE!"=="N" (
  %PY% agente_auto.py --config permitir_ajuste_estoque=false
) else (
  echo       escrita no Digifarma: nao mexi, ficou como estava
)

REM ---------- 6. Rodar ----------
echo.
echo [5/5] Sincronizando...
echo.
%PY% agente_auto.py --auto
if errorlevel 1 (
  echo.
  echo  A sincronizacao falhou. O arquivo NOVO ja esta instalado; para
  echo  voltar ao anterior, renomeie o backup desta pasta para
  echo  agente_auto.py.
  exit /b 1
)

echo.
echo ============================================================
echo  PRONTO.
echo.
echo  Confira nas linhas acima:
echo    - "Config transmitido_ate_venda" com o numero certo
echo    - "Pendentes de transmissao" caiu
echo    - o aviso de "lote(s) ja batem com a ANVISA" sumiu
echo.
echo  Falta so republicar as regras do Firebase, no console, com o
echo  conteudo de regras-firebase.json. Depois disso o resto do
echo  trabalho e pelo celular, na aba Servidor.
echo ============================================================
exit /b 0
