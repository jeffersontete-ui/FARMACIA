@echo off
chcp 65001 >nul
title Agendar sincronizacao com o site da ANVISA

REM ============================================================
REM  AGENDAR_ANVISA.bat  -  rodar como Administrador
REM
REM  O Anvisa.exe e automacao de navegador: ele abre o site do
REM  SNGPC e PARA no login (o log mostra "aguardando login" em
REM  todas as execucoes). Nao da para rodar sem ninguem na
REM  maquina - por isso esta tarefa e "somente com usuario
REM  conectado", em horario de expediente.
REM
REM  O que ela faz: abre o navegador na hora marcada, alguem no
REM  balcao faz o login, e o resto (ler o inventario e gravar na
REM  tabela INVENTARIO_SNGPC) corre sozinho.
REM ============================================================

cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo  Execute como administrador.
  pause & exit /b 1
)

set "ANVISA=C:\Digifarma\Aplicativos\VerificaXML\Anvisa.exe"
if not exist "%ANVISA%" (
  echo  Nao achei %ANVISA%
  echo  Ajuste o caminho no topo deste arquivo.
  pause & exit /b 1
)

set /p HORA=Horario para abrir a tela de login (HH:MM, ex 08:30):
if "%HORA%"=="" set "HORA=08:30"

schtasks /Delete /TN "AnvisaSNGPC_Login" /F >nul 2>&1
schtasks /Create /TN "AnvisaSNGPC_Login" /SC DAILY /ST %HORA% /IT /F ^
  /TR "\"%ANVISA%\"" >nul
if errorlevel 1 (
  echo  Nao consegui criar a tarefa.
  pause & exit /b 1
)

echo.
echo  Tarefa AnvisaSNGPC_Login criada para %HORA%, todo dia.
echo  /IT = so roda com usuario conectado (precisa do login no site).
echo.
echo  Para o servidor voltar sozinho depois de queda de energia:
echo    1. BIOS/UEFI: ligue "Restore on AC Power Loss" = Power On;
echo    2. Windows: netplwiz, desmarque "Os usuarios devem digitar
echo       um nome...", para a maquina entrar na area de trabalho
echo       sozinha e a tarefa poder abrir a tela;
echo    3. as tarefas AgenteSNGPC e AgenteSNGPC_Fila rodam como
echo       SYSTEM e nao dependem de ninguem estar logado.
echo.
pause
