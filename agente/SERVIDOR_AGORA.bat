@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Servidor - fazer tudo

REM ============================================================
REM  SERVIDOR_AGORA.bat  -  um arquivo, dois cliques, faz tudo.
REM
REM  Baixa sozinho o que precisa, roda a lista inteira sem
REM  perguntar nada, e no fim diz o que ficou para uma pessoa
REM  fazer - com o motivo de cada um.
REM
REM  Para o proximo, so baixar este arquivo de novo: ele traz a
REM  lista do dia junto.
REM
REM     curl -fL -o SERVIDOR_AGORA.bat https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA/main/agente/SERVIDOR_AGORA.bat
REM
REM  So para na TROCA DA CHAVE, e so quando a maquina nao tem o
REM  gcloud: ali o Google exige que uma pessoa autorize o
REM  download. Todo o resto e automatico.
REM
REM  Nao precisa de administrador.
REM ============================================================

cd /d "%~dp0"

set "CRU=https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA/main/agente"
set "PY=python"
where python >nul 2>&1
if errorlevel 1 set "PY=py"

set "LOG=%~dp0servidor_agora_%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%.log"

echo.
echo  ============================================================
echo   SERVIDOR - FAZENDO TUDO
echo  ============================================================
echo   Um passo de cada vez. O que falhar nao derruba os outros.
echo   Tudo tambem vai para:
echo   %LOG%
echo  ============================================================
echo.

echo ==== %DATE% %TIME% ==== > "%LOG%"

REM ---------- 0. trazer os ajudantes ----------
REM  Baixar antes de usar: assim este arquivo sozinho basta, e
REM  quem esta no servidor nao precisa saber que existem outros.
echo  [0/5] Baixando os arquivos de apoio...
call :BAIXAR TROCAR_CHAVE_FIREBASE.bat
call :BAIXAR DIAGNOSTICO_ANVISA.bat
call :BAIXAR instalar_chromedriver.ps1
call :BAIXAR ATUALIZAR_AGENTE.bat
echo.

REM ---------- 1. agente + regras ----------
echo  [1/5] Atualizando o agente e as regras do Firebase...
if exist "%~dp0ATUALIZAR_AGENTE.bat" (
  call "%~dp0ATUALIZAR_AGENTE.bat" /auto
  echo        pronto.
) else (
  echo        nao consegui baixar o ATUALIZAR_AGENTE.bat; pulando.
)
echo. >> "%LOG%"
echo ---- agente atualizado ---- >> "%LOG%"
echo.

REM ---------- 2. a chave ----------
REM  A mais importante: a chave de administrador saiu do servidor
REM  dentro de um .rar. Ela ignora todas as regras do banco.
echo  [2/5] Trocando a chave do Firebase...
if exist "%~dp0TROCAR_CHAVE_FIREBASE.bat" (
  call "%~dp0TROCAR_CHAVE_FIREBASE.bat"
) else (
  echo        nao consegui baixar o TROCAR_CHAVE_FIREBASE.bat; pulando.
)
echo.

REM ---------- 3. fechar a escrita ----------
echo  [3/5] Desligando a escrita no Digifarma...
%PY% agente_auto.py --config permitir_ajuste_estoque=false >> "%LOG%" 2>&1
if errorlevel 1 (
  echo        nao consegui - veja o log.
) else (
  echo        desligada.
)
echo.

REM ---------- 4. sincronizar ----------
echo  [4/5] Sincronizando tudo. Isto demora um pouco...
%PY% agente_auto.py --auto >> "%LOG%" 2>&1
if errorlevel 1 (
  echo        falhou - veja o log.
) else (
  echo        pronto.
)
echo.

REM ---------- 5. Anvisa ----------
REM  Aberto pela tarefa, nao daqui: com /IT ela roda na sessao de
REM  quem esta na tela. Aberto por este .bat herdaria a sessao de
REM  quem clicou, o que da no mesmo - mas pela tarefa funciona
REM  tambem quando o pedido vem do celular.
echo  [5/5] Abrindo o Anvisa.exe para o login...
%PY% agente_auto.py --anvisa >> "%LOG%" 2>&1
type "%LOG%" | findstr /I "anvisa" >nul 2>&1
echo        veja a tela: se o navegador abriu, faca o login no SNGPC.
echo.

echo  ============================================================
echo   O QUE SO UMA PESSOA PODE FAZER
echo  ============================================================
echo.
echo   A. LOGIN NO SITE DO SNGPC
echo      O Anvisa.exe para na tela de login - e desenho da
echo      ANVISA. Depois do login ele le o inventario sozinho, e
echo      as divergencias que sao so foto velha somem.
echo.
echo   B. TRANSMITIR A MOVIMENTACAO PENDENTE
echo      No Digifarma. Enquanto nao sobe, as vendas ficam
echo      contadas de um lado so.
echo.
echo   C. LANCAR PERDA DO DERMOBAN, lote 26111
echo      No Digifarma. A ANVISA tem 2 e a prateleira esta vazia.
echo      Zerar o saldo aqui nao resolve: o ajuste e interno e nao
echo      sobe ao SNGPC, entao o site continuaria com as 2. Perda
echo      e escriturada e transmitida - zera os dois lados.
echo.
echo   D. LER O LOTE IMPRESSO NAS CAIXAS DE ESCITALOPRAM 10MG
echo      Um lote com -4 e outro com +4, cinco de cada lado: nao
echo      falta nem sobra nada, sao caixas no lote errado. Contar
echo      nao responde. So ler a caixa responde.
echo.
echo  ============================================================
echo   Log completo em:
echo   %LOG%
echo  ============================================================
echo.
pause
goto :eof

REM ------------------------------------------------------------
:BAIXAR
REM  -f para o curl FALHAR em erro de HTTP. Sem ele, a pagina de
REM  erro do GitHub e gravada por cima do arquivo - ja aconteceu
REM  aqui, e o .bat virou 199 bytes de HTML.
curl -fsL -o "%~dp0%~1" "%CRU%/%~1" >nul 2>&1
if errorlevel 1 (
  echo        nao baixei %~1
) else (
  echo        ok %~1
)
goto :eof
