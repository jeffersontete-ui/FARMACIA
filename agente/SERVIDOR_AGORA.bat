@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Servidor - tudo o que precisa ser feito agora

REM ============================================================
REM  SERVIDOR_AGORA.bat  -  a lista da vez, num arquivo so.
REM
REM  A farmacia nao fica no servidor o dia todo. Quando fica, o
REM  que atrapalha e descobrir um comando de cada vez, no meio do
REM  expediente. Este arquivo roda tudo o que da para rodar, na
REM  ordem que importa, e no fim lista o que so uma pessoa pode
REM  fazer - com o motivo de cada um.
REM
REM  Ele e reescrito quando a lista muda. Rode o
REM  ATUALIZAR_AGENTE.bat antes, ou baixe este de novo, para ter
REM  a lista do dia.
REM
REM  Cada passo pergunta antes. Pular um nao atrapalha os outros.
REM ============================================================

cd /d "%~dp0"

set "PY=python"
where python >nul 2>&1
if errorlevel 1 set "PY=py"

echo.
echo  ============================================================
echo   SERVIDOR - LISTA DE 19/08/2026
echo  ============================================================
echo.
echo   1. Atualizar o agente e as regras do Firebase
echo   2. Trocar a chave do Firebase          [a mais importante]
echo   3. Desligar a escrita no Digifarma
echo   4. Sincronizar tudo
echo   5. Abrir o Anvisa.exe para o login
echo.
echo   Cada um pergunta antes. Responda N para pular.
echo.
pause

REM ---------- 1 ----------
echo.
echo  ------------------------------------------------------------
echo   1. ATUALIZAR O AGENTE
echo   Baixa a versao nova do GitHub e publica as regras do
echo   Firebase junto. Confere o arquivo antes de trocar.
echo  ------------------------------------------------------------
set "R="
set /p R=  Fazer agora [S/N]: 
if /i not "!R!"=="S" goto PASSO2
call "%~dp0ATUALIZAR_AGENTE.bat" /auto
echo   feito.

:PASSO2
echo.
echo  ------------------------------------------------------------
echo   2. TROCAR A CHAVE DO FIREBASE
echo   A chave de administrador saiu do servidor dentro de um .rar.
echo   Ela ignora todas as regras do banco. Gerar a nova nao basta:
echo   e APAGAR a antiga que invalida a que vazou.
echo  ------------------------------------------------------------
set "R="
set /p R=  Fazer agora [S/N]: 
if /i not "!R!"=="S" goto PASSO3
call "%~dp0TROCAR_CHAVE_FIREBASE.bat"

:PASSO3
echo.
echo  ------------------------------------------------------------
echo   3. DESLIGAR A ESCRITA NO DIGIFARMA
echo   Foi ligada para zerar os lotes fantasma. Enquanto fica
echo   ligada, os botoes que escrevem estao vivos num celular que
echo   fica no balcao.
echo  ------------------------------------------------------------
set "R="
set /p R=  Desligar agora [S/N]: 
if /i not "!R!"=="S" goto PASSO4
%PY% agente_auto.py --config permitir_ajuste_estoque=false

:PASSO4
echo.
echo  ------------------------------------------------------------
echo   4. SINCRONIZAR TUDO
echo   Recalcula as divergencias com o que estiver valendo agora.
echo  ------------------------------------------------------------
set "R="
set /p R=  Sincronizar agora [S/N]: 
if /i not "!R!"=="S" goto PASSO5
%PY% agente_auto.py --auto

:PASSO5
echo.
echo  ------------------------------------------------------------
echo   5. ANVISA.EXE
echo   Ele para na tela de login e nao anda sozinho. Abrir aqui e
echo   fazer o login no site regrava o inventario do SNGPC.
echo   Rode DEPOIS de transmitir o envio, senao a foto vem velha.
echo  ------------------------------------------------------------
set "R="
set /p R=  Abrir agora [S/N]: 
if /i not "!R!"=="S" goto MANUAIS
start "" "C:\Digifarma\Aplicativos\VerificaXML\Anvisa.exe"
echo   aberto. Faca o login no site do SNGPC.

:MANUAIS
echo.
echo  ============================================================
echo   O QUE ESTE ARQUIVO NAO PODE FAZER
echo  ============================================================
echo.
echo   A. TRANSMITIR O ENVIO 17 A 18
echo      No Digifarma. E o que mais mexe nos numeros: enquanto
echo      nao sobe, as vendas dos dias 17 e 18 ficam contadas de
echo      um lado so.
echo.
echo   B. LANCAR PERDA DO DERMOBAN, lote 26111
echo      No Digifarma, nao pelo app. A ANVISA tem 2 unidades e a
echo      prateleira esta vazia. Zerar o saldo aqui nao resolve -
echo      o ajuste e interno e nao sobe ao SNGPC, entao o site
echo      continuaria com as 2. Perda e escriturada e transmitida:
echo      zera os dois lados de verdade.
echo.
echo   C. LER O LOTE IMPRESSO NAS CAIXAS DE ESCITALOPRAM 10MG
echo      Lote 2509242 tem -4 e o 2529244 tem +4. Cinco de cada
echo      lado: nao falta nem sobra nada, sao 4 caixas registradas
echo      no lote errado. Contar nao responde - o total ja esta
echo      certo. So ler a caixa responde.
echo.
echo  ============================================================
echo.
pause
