@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Trocar a chave do Firebase

REM ============================================================
REM  TROCAR_CHAVE_FIREBASE.bat
REM
REM  Gera uma chave nova, testa, e so entao APAGA A VELHA no
REM  Google. Apagar a velha e o que invalida uma chave vazada -
REM  gerar uma nova sozinho nao desativa nada.
REM
REM  Quem troca e a SUA conta Google, nao a chave do agente. A
REM  chave nao pode trocar a si mesma: para isso precisaria de
REM  permissao para criar e apagar chaves, e ai uma chave vazada
REM  poderia gerar novas para sempre. O gcloud autentica voce uma
REM  vez e a rotacao passa a ser um comando.
REM
REM  Se qualquer coisa falhar, a chave antiga volta e a nova e
REM  apagada do Google. O agente nunca fica sem chave boa.
REM ============================================================

cd /d "%~dp0"

set "CHAVE=%~dp0chave-firebase.json"
set "CARIMBO=%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%"
set "CARIMBO=%CARIMBO: =0%"
set "BACKUP=%~dp0chave-firebase_antes_de_%CARIMBO%.json"
set "NOVA=%~dp0chave-firebase_nova.json"

echo.
echo  ============================================================
echo   TROCAR A CHAVE DO FIREBASE
echo  ============================================================
echo.

if not exist "%CHAVE%" (
  echo  Nao achei %CHAVE%
  echo  Sem a chave atual nao da para saber qual conta trocar.
  goto FIM
)

REM ---------- 1. de quem e a chave de hoje ----------
echo  [1/6] Lendo a chave atual...
for /f "delims=" %%A in ('powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%CHAVE%' ^| ConvertFrom-Json).client_email" 2^>nul') do set "CONTA=%%A"
for /f "delims=" %%A in ('powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%CHAVE%' ^| ConvertFrom-Json).private_key_id" 2^>nul') do set "IDVELHA=%%A"
for /f "delims=" %%A in ('powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%CHAVE%' ^| ConvertFrom-Json).project_id" 2^>nul') do set "PROJETO=%%A"

if "!CONTA!"=="" (
  echo  A chave atual nao parece um JSON de conta de servico.
  goto FIM
)
echo        conta ..... !CONTA!
echo        projeto ... !PROJETO!
echo        chave hoje  !IDVELHA!
echo.

REM ---------- 2. tem gcloud? ----------
echo  [2/6] Procurando o gcloud...
where gcloud >nul 2>&1
if errorlevel 1 goto SEM_GCLOUD
echo        achei.
echo.

REM ---------- 3. voce esta autenticado? ----------
echo  [3/6] Conferindo o login do Google...
set "LOGADO="
for /f "delims=" %%A in ('gcloud auth list --filter=status:ACTIVE --format="value(account)" 2^>nul') do set "LOGADO=%%A"
if "!LOGADO!"=="" (
  echo        ninguem logado. Abrindo o navegador...
  gcloud auth login
  for /f "delims=" %%A in ('gcloud auth list --filter=status:ACTIVE --format="value(account)" 2^>nul') do set "LOGADO=%%A"
)
if "!LOGADO!"=="" (
  echo        nao consegui autenticar. Nada foi trocado.
  goto FIM
)
echo        logado como !LOGADO!
echo.

REM ---------- 4. gerar a nova ----------
echo  [4/6] Gerando a chave nova...
if exist "%NOVA%" del "%NOVA%" >nul 2>&1
gcloud iam service-accounts keys create "%NOVA%" --iam-account=!CONTA! --project=!PROJETO!
if errorlevel 1 goto FALHOU_CRIAR
if not exist "%NOVA%" goto FALHOU_CRIAR

set "OKJSON="
for /f "delims=" %%A in ('powershell -NoProfile -Command "$j = Get-Content -Raw -LiteralPath '%NOVA%' ^| ConvertFrom-Json; if ($j.private_key -and $j.client_email) { 'sim' }" 2^>nul') do set "OKJSON=%%A"
if not "!OKJSON!"=="sim" (
  echo        o arquivo gerado nao parece uma chave. Nada foi trocado.
  del "%NOVA%" >nul 2>&1
  goto FIM
)
for /f "delims=" %%A in ('powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%NOVA%' ^| ConvertFrom-Json).private_key_id" 2^>nul') do set "IDNOVA=%%A"
echo        chave nova  !IDNOVA!
echo.

REM ---------- 5. trocar e testar ----------
echo  [5/6] Trocando e testando...
copy /Y "%CHAVE%" "%BACKUP%" >nul
move /Y "%NOVA%" "%CHAVE%" >nul

set "PY=python"
where python >nul 2>&1
if errorlevel 1 set "PY=py"

%PY% agente_auto.py --teste
if errorlevel 1 goto TESTE_FALHOU
echo        a chave nova funciona.
echo.

REM ---------- 6. apagar a velha ----------
REM  So aqui. E este passo que invalida a chave que vazou; ate
REM  ele, as duas valem.
echo  [6/6] Apagando a chave antiga no Google...
gcloud iam service-accounts keys delete !IDVELHA! --iam-account=!CONTA! --project=!PROJETO! --quiet
if errorlevel 1 (
  echo        NAO consegui apagar a antiga. A nova ja esta valendo,
  echo        mas a velha continua aceita ate ser removida a mao em:
  echo        https://console.cloud.google.com/iam-admin/serviceaccounts
  goto FIM
)
echo        apagada. A chave que vazou nao vale mais.
echo.
echo  ------------------------------------------------------------
echo   PRONTO. Backup da anterior em:
echo   %BACKUP%
echo   Guarde fora do servidor ou apague: e uma chave valida ate
echo   o momento em que foi revogada, e nao serve mais para nada.
echo  ------------------------------------------------------------
goto FIM

:TESTE_FALHOU
echo.
echo        O TESTE FALHOU com a chave nova. Voltando a anterior.
move /Y "%BACKUP%" "%CHAVE%" >nul
gcloud iam service-accounts keys delete !IDNOVA! --iam-account=!CONTA! --project=!PROJETO! --quiet >nul 2>&1
echo        a chave antiga voltou e a nova foi apagada do Google.
echo        Nada mudou. Me mande o erro acima.
goto FIM

:FALHOU_CRIAR
echo        Nao consegui gerar a chave. Motivo comum: a sua conta
echo        precisa do papel "Administrador de conta de servico"
echo        no projeto. Nada foi trocado.
goto FIM

:SEM_GCLOUD
echo        nao achei o gcloud nesta maquina.
echo.
echo        Para a troca virar um comando so, instale uma vez:
echo        https://cloud.google.com/sdk/docs/install
echo.
echo        Sem ele, a troca e a mao no console:
echo         1. gerar nova chave privada e salvar como
echo            chave-firebase.json nesta pasta;
echo         2. APAGAR a chave antiga na mesma tela - e isso que
echo            invalida a que vazou;
echo         3. rodar: python agente_auto.py --teste
echo.
echo        Abrindo a pagina...
start "" "https://console.firebase.google.com/project/%PROJETO%/settings/serviceaccounts/adminsdk"
goto FIM

:FIM
echo.
pause
