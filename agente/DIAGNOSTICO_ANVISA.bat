@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Diagnostico do Anvisa.exe

REM ============================================================
REM  DIAGNOSTICO_ANVISA.bat  -  dois cliques, nao precisa de
REM  administrador.
REM
REM  "O Anvisa.exe nao liga" quase sempre e uma destas quatro:
REM
REM   1. ja tem uma copia dele travada rodando, invisivel, e a
REM      segunda nao abre;
REM   2. sobrou um chromedriver.exe pendurado da vez anterior;
REM   3. o Chrome se atualizou e o chromedriver que veio junto do
REM      Anvisa.exe ficou velho - ele abre e fecha na hora;
REM   4. a janela ate abre, mostra o erro, e fecha antes de dar
REM      tempo de ler.
REM
REM  Este arquivo olha as quatro, escreve tudo num relatorio e no
REM  fim abre o Anvisa.exe DE DENTRO desta janela - assim, se ele
REM  reclamar de alguma coisa, a mensagem fica na tela.
REM
REM  Nada e apagado nem instalado. So mata processo travado, e
REM  perguntando antes.
REM ============================================================

cd /d "%~dp0"

set "ANVISA=C:\Digifarma\Aplicativos\VerificaXML\Anvisa.exe"
set "PASTA=C:\Digifarma\Aplicativos\VerificaXML"
set "RELATORIO=%~dp0diagnostico_anvisa.txt"

echo Diagnostico do Anvisa.exe - %DATE% %TIME% > "%RELATORIO%"
echo. >> "%RELATORIO%"

echo.
echo  ============================================================
echo   DIAGNOSTICO DO ANVISA.EXE
echo  ============================================================
echo.

REM ---------- 1. o arquivo esta la? --------------------------
echo  [1/6] Procurando o programa...
if not exist "%ANVISA%" (
  echo        NAO ACHEI em %ANVISA%
  echo  NAO ACHEI o Anvisa.exe em %ANVISA% >> "%RELATORIO%"
  echo.
  echo        Procurando dentro de C:\Digifarma...
  echo. >> "%RELATORIO%"
  echo  Copias encontradas: >> "%RELATORIO%"
  REM  So dentro do Digifarma: varrer o disco C: inteiro leva
  REM  minutos e o programa nao mora em outro lugar.
  for /f "delims=" %%A in ('dir /s /b "C:\Digifarma\Anvisa.exe" 2^>nul') do (
    echo        achei: %%A
    echo    %%A >> "%RELATORIO%"
  )
  echo.
  echo        Se apareceu algum caminho acima, e nele que o
  echo        programa esta. Me mande o caminho.
  echo.
  goto FIM
)

for %%A in ("%ANVISA%") do (
  echo        achei: %%~fA
  echo        tamanho: %%~zA bytes   data: %%~tA
  echo  Programa: %%~fA >> "%RELATORIO%"
  echo  Tamanho: %%~zA bytes  Data: %%~tA >> "%RELATORIO%"
)
echo.

REM ---------- 2. ja tem um rodando? --------------------------
echo  [2/6] Vendo se ja tem alguma copia rodando...
echo. >> "%RELATORIO%"
echo  Processos ligados: >> "%RELATORIO%"
set "TRAVADO="
for %%P in (Anvisa.exe chromedriver.exe) do (
  tasklist /FI "IMAGENAME eq %%P" 2>nul | find /I "%%P" >nul
  if !errorlevel! EQU 0 (
    echo        JA ESTA RODANDO: %%P
    echo    %%P esta rodando >> "%RELATORIO%"
    set "TRAVADO=S"
  ) else (
    echo        parado: %%P
    echo    %%P parado >> "%RELATORIO%"
  )
)
echo.

REM  Daqui ate :SEM_TRAVA nao ha um unico bloco entre parenteses,
REM  e e de proposito. A primeira versao perguntava
REM  "...agora? (S/N):" dentro de um if - e o cmd conta os
REM  parenteses do TEXTO como se fossem do bloco. O diagnostico
REM  morria calado bem aqui, justo antes da parte que interessa.
REM  Com desvio e rotulo nao ha bloco para quebrar.
if not defined TRAVADO goto :SEM_TRAVA
echo  ------------------------------------------------------------
echo   E ISTO. Tem uma copia travada rodando invisivel, e por
echo   isso a nova nao abre. Fechar a travada resolve.
echo  ------------------------------------------------------------
echo.
set "MATAR="
set /p MATAR=Fechar as copias travadas agora [S/N]:
if /I "%MATAR%"=="S" goto :FECHAR_TRAVADAS
echo        deixei como estava.
goto :SEM_TRAVA

:FECHAR_TRAVADAS
taskkill /F /IM Anvisa.exe >nul 2>&1
taskkill /F /IM chromedriver.exe >nul 2>&1
echo        fechadas.
echo  Copias travadas fechadas pelo diagnostico. >> "%RELATORIO%"

:SEM_TRAVA
echo.

REM ---------- 3. o que o log dele diz? -----------------------
echo  [3/6] Lendo o log do proprio Anvisa.exe...
echo. >> "%RELATORIO%"
echo  Ultimas linhas do anvisa.log: >> "%RELATORIO%"
set "ACHOULOG="
for %%L in ("%PASTA%\anvisa.log" "%PASTA%\log\anvisa.log" "%PASTA%\Anvisa.log") do (
  if exist %%L (
    set "ACHOULOG=S"
    echo        achei %%~L
    powershell -NoProfile -Command "Get-Content -LiteralPath '%%~L' -Tail 25 -ErrorAction SilentlyContinue" >> "%RELATORIO%" 2>nul
    powershell -NoProfile -Command "Get-Content -LiteralPath '%%~L' -Tail 8 -ErrorAction SilentlyContinue"
  )
)
if not defined ACHOULOG (
  echo        nao achei anvisa.log - o programa pode nem estar
  echo        chegando a escrever, o que ja e uma pista.
  echo    nenhum anvisa.log encontrado >> "%RELATORIO%"
)
echo.

REM ---------- 4. Chrome x chromedriver ------------------------
REM  A causa mais comum de "abre e fecha na hora": o Chrome se
REM  atualiza sozinho e o chromedriver que veio com o Anvisa.exe
REM  fica para tras. Os dois numeros grandes tem que bater.
echo  [4/6] Comparando as versoes do Chrome e do chromedriver...
echo. >> "%RELATORIO%"
echo  Versoes: >> "%RELATORIO%"

for %%C in ("C:\Program Files\Google\Chrome\Application\chrome.exe" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") do (
  if exist %%C (
    for /f "delims=" %%V in ('powershell -NoProfile -Command "(Get-Item -LiteralPath '%%~C').VersionInfo.ProductVersion" 2^>nul') do (
      echo        Chrome ........ %%V
      echo    Chrome: %%V >> "%RELATORIO%"
    )
  )
)

if exist "%PASTA%\chromedriver.exe" (
  for /f "delims=" %%V in ('"%PASTA%\chromedriver.exe" --version 2^>nul') do (
    echo        chromedriver .. %%V
    echo    chromedriver: %%V >> "%RELATORIO%"
  )
) else (
  echo        nao achei chromedriver.exe na pasta do Anvisa
  echo    chromedriver.exe nao esta em %PASTA% >> "%RELATORIO%"
)
echo.
echo        Se os dois primeiros numeros nao baterem - por
echo        exemplo Chrome 139 e chromedriver 127 - e essa a causa.
echo.

REM ---------- 5. tem internet e o site responde? --------------
echo  [5/6] Testando o site do SNGPC...
echo. >> "%RELATORIO%"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'https://sngpc.anvisa.gov.br' -UseBasicParsing -TimeoutSec 20; Write-Output ('  site respondeu: ' + $r.StatusCode) } catch { Write-Output ('  site NAO respondeu: ' + $_.Exception.Message) }" > "%TEMP%\_sngpc.txt" 2>&1
type "%TEMP%\_sngpc.txt"
type "%TEMP%\_sngpc.txt" >> "%RELATORIO%"
del "%TEMP%\_sngpc.txt" >nul 2>&1
echo.

REM ---------- 6. abrir com a janela aberta --------------------
echo  [6/6] Abrindo o Anvisa.exe AQUI DENTRO.
echo.
echo        Se ele reclamar de alguma coisa, a mensagem vai
echo        ficar nesta tela em vez de sumir. Faca o login no
echo        site quando a janela do navegador abrir.
echo.
pause

echo. >> "%RELATORIO%"
echo  Saida do Anvisa.exe: >> "%RELATORIO%"

REM  Sem cano para o PowerShell aqui de proposito: num cano quem
REM  responde por %ERRORLEVEL% e o ultimo comando, e o que se quer
REM  saber e como o Anvisa.exe terminou. Redireciona, guarda o
REM  codigo na hora, e so depois mostra.
pushd "%PASTA%"
"%ANVISA%" > "%TEMP%\_anvisa_saida.txt" 2>&1
set "CODIGO=%ERRORLEVEL%"
popd

type "%TEMP%\_anvisa_saida.txt"
type "%TEMP%\_anvisa_saida.txt" >> "%RELATORIO%"
del "%TEMP%\_anvisa_saida.txt" >nul 2>&1

echo.
echo  ------------------------------------------------------------
echo   O Anvisa.exe terminou com codigo %CODIGO%
echo  ------------------------------------------------------------
echo  Codigo de saida: %CODIGO% >> "%RELATORIO%"
echo.
echo   0  = terminou normal
echo   -1 ou numero grande = fechou com erro (a mensagem esta acima)
echo.

:FIM
echo.
echo  ============================================================
echo   Relatorio salvo em:
echo   %RELATORIO%
echo.
echo   Abra esse arquivo, tire uma foto ou copie o texto e me
echo   mande. Ele nao tem senha nem dado de paciente - so as
echo   versoes dos programas e as mensagens de erro.
echo  ============================================================
echo.
pause
