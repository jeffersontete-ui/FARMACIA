# Estoque — Fase 1 (login seguro + papéis + código de barras)

App de controle de estoque de medicamentos. PWA sincronizado pelo Firebase,
roda em celular, PC e navegador. Este repositório é a **Fase 1** do sistema:
o módulo Estoque com segurança de verdade.

## O que mudou nesta versão

- **Login de verdade (Firebase Authentication).** A senha não fica mais dentro
  do código. Cada pessoa tem um login próprio; o banco só abre para quem entra.
- **Papéis.** Só o **Jefferson** é admin (vê as 3 abas e o Painel). Marconi,
  Marcelo, Eliara e Anderson veem **só o Estoque**, mas **todos movimentam**
  (entrada/saída), cada um com a própria senha.
- **Admin vê quem deu saída.** No Painel → Movim., cada saída mostra quem operou.
- **Busca por código de barras.** Pela câmera (botão 📷) ou digitando o número
  na busca. Leitor USB/Bluetooth também funciona.
- **Saldo corrigido.** Entrada e saída agora mexem no mesmo contador do estoque
  (antes a saída tirava da farmácia — o número nunca batia).
- **Grava por item.** Dois aparelhos movimentando ao mesmo tempo não se apagam.
- **Funciona offline.** Service worker: o app abre sem internet e sincroniza ao voltar.

## Como publicar (passo a passo)

### 1. Fechar o banco e criar os logins (uma vez)

1. **Console do Firebase** → seu projeto → **Authentication** → **Sign-in method**
   → ative **E-mail/senha**.
2. Suba o arquivo `setup-usuarios.html`, abra ele no navegador **uma vez** e
   clique em "Criar os 5 usuários". Confira os ✅ no log.
3. **Apague `setup-usuarios.html` do repositório** depois de rodar.
4. **Realtime Database** → aba **Regras** → cole o conteúdo de
   `firebase/database.rules.json` → **Publicar**. Isso fecha o banco:
   a partir daqui, só quem faz login lê ou grava.

### 2. Trocar o app

Suba os arquivos deste repositório (substituindo o `index.html` atual) e
adicione `sw.js`. O GitHub Pages publica sozinho.

### 3. Testar

- Entrar com cada senha atual (2407, 9876, 1991, 1234, 1010).
- Confirmar: só o Jefferson vê a aba Farmácia e o Painel.
- Dar uma entrada e uma saída — o saldo do estoque tem que bater.
- No Painel → Movim., a saída aparece com o nome de quem operou.
- Abrir `.../estoque/dados.json` no navegador **sem estar logado**: agora deve
  dar `Permission denied` (antes mostrava tudo).

## Sincronização com o Digifarma (automática)

A aba **Farmácia** do app mostra o inventário do Digifarma, atualizado
sozinho. Como funciona:

- No PC da farmácia roda o **agente** (`agente/agente_auto.py`), pelo Agendador
  de Tarefas do Windows, de tempos em tempos.
- Ele lê o estoque do Digifarma (Firebird) e **publica no Firebase**.
- O app lê e mostra — só consulta, ninguém edita esse inventário pelo app.
- **O Digifarma manda:** o que ele diz é o que o app mostra.

Instalação do agente: ver `agente/INSTALAR.txt`. Precisa do Python, das
bibliotecas `firebird-driver` e `firebase-admin`, e da chave de serviço do
Firebase (`chave-firebase.json`) — que fica **só no PC**, nunca no GitHub.

O PC precisa estar **ligado** para sincronizar (é o único jeito de ler o
Firebird do Digifarma). Com o PC desligado, o app mostra a última sincronização.

## Depois

Troque as cinco senhas (Console → Authentication → Users → Reset password).
As antigas ficaram públicas por semanas.

## Avisos

- **O `SNGPC_Sync.vbs` para de subir** com as regras novas (o SNGPC saiu deste
  módulo e vai para o módulo Farmácia, na próxima fase). Isso é esperado.
- **Nunca** suba `.csv`, `.fdb` ou o `.vbs` com senha — o `.gitignore` já bloqueia.

## Próximas fases

Farmácia (Digifarma + ANVISA + preços) e Receituário. Ver `docs/specs/`.
