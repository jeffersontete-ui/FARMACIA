' ============================================================
'  ATUALIZAR_EM_SEGUNDO_PLANO.vbs
'  Roda o ATUALIZAR_AGENTE.bat SEM JANELA NENHUMA.
'
'  Dois cliques e pronto: nada aparece na tela, nada pergunta,
'  nada fica esperando. O que aconteceu vai para o arquivo
'  atualizacao_AAAA-MM-DD.log, nesta mesma pasta.
'
'  Sem parametros ele NAO mexe na configuracao: so atualiza o
'  agente e sincroniza. Para configurar junto, edite a linha
'  ARGUMENTOS abaixo, por exemplo:
'
'     ARGUMENTOS = "/auto 46108 S"
'
'     46108 = numero da ultima venda transmitida
'     S     = libera o app a escrever no Digifarma
'             (N desliga; sem a letra, fica como esta)
' ============================================================

ARGUMENTOS = "/auto"

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = pasta
' o 0 e o que esconde a janela; o False nao espera terminar
shell.Run """" & pasta & "\ATUALIZAR_AGENTE.bat"" " & ARGUMENTOS, 0, False
