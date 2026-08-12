@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Agente SNGPC - instalacao

REM ============================================================
REM  INSTALAR_AGENTE.bat  -  rodar como Administrador
REM  Instala o Python, as bibliotecas, TESTA a sincronizacao e
REM  so entao agenda as duas tarefas. Nao gera .exe: atualizar o
REM  agente e trocar o agente_auto.py e rodar este .bat de novo.
REM ============================================================

cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Este instalador precisa ser executado como ADMINISTRADOR.
  echo  Clique com o botao direito no arquivo e escolha
  echo  "Executar como administrador".
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo  AGENTE SNGPC - instalacao
echo ============================================================
echo.

REM ---------- 1. Python ----------
echo [1/5] Procurando o Python...
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )

if not defined PY (
  echo       Python nao encontrado. Baixando...
  set "INSTALADOR=%TEMP%\python-instalador.exe"
  powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\python-instalador.exe'}catch{exit 1}"
  if errorlevel 1 (
    echo.
    echo       Nao consegui baixar o Python. Instale manualmente a versao 3.12
    echo       de python.org marcando "Add python.exe to PATH" e rode este
    echo       arquivo de novo.
    pause
    exit /b 1
  )
  "%TEMP%\python-instalador.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
  set "PY=py -3"
  set "PATH=%PATH%;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"
)

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo       O Python foi instalado mas ainda nao esta no PATH desta janela.
  echo       Feche esta janela, abra outra como administrador e rode de novo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version') do echo       %%v

REM ---------- 2. Bibliotecas ----------
echo.
echo [2/5] Instalando as bibliotecas...
%PY% -m pip install --quiet --upgrade pip
%PY% -m pip install --quiet fdb firebase-admin
if errorlevel 1 (
  echo       Falhou a instalacao das bibliotecas. Verifique a internet
  echo       ou o proxy da farmacia e rode de novo.
  pause
  exit /b 1
)
echo       fdb e firebase-admin instalados.

REM ---------- 3. Chave do Firebase ----------
echo.
echo [3/5] Conferindo a chave do Firebase...
if not exist "%~dp0chave-firebase.json" (
  echo.
  echo       FALTA a chave-firebase.json nesta pasta.
  echo.
  echo       Console do Firebase ^> Configuracoes do projeto ^>
  echo       Contas de servico ^> Gerar nova chave privada.
  echo       Salve o arquivo aqui com o nome chave-firebase.json.
  echo       Esse arquivo NUNCA vai para o GitHub.
  echo.
  pause
  exit /b 1
)
echo       chave-firebase.json encontrada.

REM ---------- 4. Teste antes de agendar ----------
echo.
echo [4/5] Testando conexao e uma sincronizacao completa...
%PY% "%~dp0agente_auto.py" --teste
if errorlevel 1 (
  echo.
  echo       O teste de conexao falhou. Veja o agente.log nesta pasta.
  echo       Nada foi agendado.
  pause
  exit /b 1
)

%PY% "%~dp0agente_auto.py" --auto
if errorlevel 1 (
  echo.
  echo       A sincronizacao falhou. Veja o agente.log nesta pasta.
  echo       Se o erro for de tabela inexistente, rode:
  echo           %PY% agente_auto.py --schema
  echo       e ajuste o bloco CONSULTAS do agente_auto.py.
  echo       Nada foi agendado.
  pause
  exit /b 1
)
echo       Sincronizacao de teste concluida.

REM ---------- 5. Agendamento ----------
echo.
echo [5/5] Agendando as tarefas...
for /f "delims=" %%p in ('%PY% -c "import sys;print(sys.executable)"') do set "PYEXE=%%p"

schtasks /Delete /TN "AgenteSNGPC" /F >nul 2>&1
schtasks /Delete /TN "AgenteSNGPC_Fila" /F >nul 2>&1

schtasks /Create /TN "AgenteSNGPC" /SC HOURLY /RL HIGHEST /RU SYSTEM /F ^
  /TR "\"%PYEXE%\" \"%~dp0agente_auto.py\" --auto" >nul
if errorlevel 1 ( echo       Nao consegui criar a tarefa AgenteSNGPC. & pause & exit /b 1 )

schtasks /Create /TN "AgenteSNGPC_Fila" /SC MINUTE /MO 5 /RL HIGHEST /RU SYSTEM /F ^
  /TR "\"%PYEXE%\" \"%~dp0agente_auto.py\" --fila" >nul
if errorlevel 1 ( echo       Nao consegui criar a tarefa AgenteSNGPC_Fila. & pause & exit /b 1 )

echo       AgenteSNGPC        - de hora em hora  (sincronizacao completa)
echo       AgenteSNGPC_Fila   - a cada 5 minutos (botoes do app)

echo.
echo ============================================================
echo  PRONTO.
echo.
echo  Log:        %~dp0agente.log
echo  Config:     %~dp0agente_config.json
echo  Rodar agora: %PY% agente_auto.py --auto
echo ============================================================
echo.
pause
endlocal
