# FARMÁCIA — SNGPC

Conferência do estoque de controlados entre o **Digifarma** e o que foi
**transmitido ao SNGPC**. Duas peças:

- o **app web** (PWA, GitHub Pages), com senha própria do farmacêutico;
- o **agente Python** (pasta `agente/`), que roda no servidor da farmácia,
  lê o Firebird do Digifarma e publica em `farmacia/inventario`.

O estoque manual do balcão fica no repositório separado **ESTOQUE**.

## Regra de ouro

**O Digifarma é a verdade.** O app só LÊ o inventário; o agente só faz
`SELECT`. Nada aqui escreve no Digifarma.

## O que o app mostra

| Aba | O que traz |
|---|---|
| Situação | carimbo do último sincronismo, dados do último envio, botões que pedem ao agente |
| Saldo | divergências entre o saldo do Digifarma e o inventário SNGPC vigente, com M.S., código de barras, lote e o detalhe de cada uma |
| XML | o que saiu no banco cruzado com o que subiu no XML, por registro M.S. + lote |
| Vendas | controlado vendido sem receita escriturada ou sem lote — a causa clássica de recusa |
| Aceites | marcar à mão o aceite ou a recusa de cada envio, com nome e horário |

Os dois botões da aba Situação escrevem em `farmacia/comando`. O agente
atende em até 5 minutos e marca o pedido como concluído — o app mostra o
estado da fila.

## O agente

```
agente/
  agente_auto.py        o agente
  mapa_xml.py           leitor do XML do SNGPC
  teste_agente.py       roda tudo com banco simulado
  INSTALAR_AGENTE.bat   instalador (rodar como administrador)
  regras-firebase.json  regras do Realtime Database
```

### Instalar no servidor

1. Copie a pasta `agente/` para o servidor da farmácia.
2. Console do Firebase > Configurações do projeto > **Contas de serviço** >
   Gerar nova chave privada. Salve como `agente/chave-firebase.json`.
   **Esse arquivo nunca vai para o GitHub** (já está no `.gitignore`).
3. Botão direito em `INSTALAR_AGENTE.bat` > **Executar como administrador**.

O instalador instala o Python e as bibliotecas, **testa uma sincronização
completa** e só então cria as tarefas. Se o teste falhar, nada é agendado.

### Tarefas criadas

| Tarefa | Quando | O que faz |
|---|---|---|
| `AgenteSNGPC` | de hora em hora | `--auto`, sincronização completa |
| `AgenteSNGPC_Fila` | a cada 5 minutos | `--fila`, atende os botões do app |
| `AnvisaSNGPC_Login` | 1x por dia, em horário de expediente | abre o `Anvisa.exe` para alguém fazer o login no site do SNGPC |

A terceira é criada pelo `AGENDAR_ANVISA.bat`, à parte, porque **não roda
sozinha** — veja abaixo.

### O que roda sozinho e o que não roda

| Etapa | Automático? |
|---|---|
| Ler vendas, entradas, perdas e transferências do Digifarma | **Sim**, sem ninguém na máquina (tarefas rodam como SYSTEM) |
| Descobrir o que está pendente de transmissão | **Sim**, pelos ponteiros da tabela `SNGPC` |
| Arquivar e conferir o XML de cada envio | **Sim** |
| Transmitir ao SNGPC | **Depende**: se `SNGPC.ENVIO_API` estiver ligado, o Digifarma envia sozinho; senão é manual |
| Baixar o inventário e o retorno do site da ANVISA | **Não.** O `Anvisa.exe` é automação de navegador e para na tela de login |

O `anvisa.log` mostra `aguardando login` em todas as execuções: alguém
precisa entrar no site do SNGPC. Depois disso o resto corre sozinho — ele
lê o inventário e regrava a tabela `INVENTARIO_SNGPC`.

Por isso o agente **mede** essa defasagem em vez de fingir que resolve: ele
lê o `anvisa.log`, calcula há quantos dias o processo não conclui e publica
em `farmacia/inventario/anvisa`. Quando passa de um dia, o app mostra o
aviso pedindo o login. É a diferença entre o inventário estar velho sem
ninguém perceber e o app cobrar.

Para o servidor voltar sozinho depois de queda de energia (o
`AGENDAR_ANVISA.bat` repete estas instruções no fim):

1. BIOS/UEFI: **Restore on AC Power Loss = Power On**;
2. `netplwiz`: desmarcar "Os usuários devem digitar um nome e uma senha",
   para a máquina chegar à área de trabalho sozinha — sem isso a tarefa do
   `Anvisa.exe` não tem tela para abrir;
3. as tarefas `AgenteSNGPC` e `AgenteSNGPC_Fila` rodam como SYSTEM e já
   independem de qualquer login.

### Rodar à mão

```
python agente_auto.py --auto          sincronização completa
python agente_auto.py --schema        confere as tabelas da base
python agente_auto.py --colunas LOTES lista as colunas de uma tabela
python agente_auto.py --teste         testa Firebird e Firebase
python teste_agente.py                roda tudo com banco simulado
```

**Não existe .exe.** Atualizar o agente é trocar o `agente_auto.py` e rodar
o `.bat` de novo.

### Consultas SQL

O bloco `CONSULTAS`, no topo do `agente_auto.py`, é o único ponto que
conhece o esquema do Digifarma. Os nomes saíram dos `.sql` do próprio
VerificaXML (pasta `sqls\`), então são os reais:

| Assunto | Tabelas |
|---|---|
| Vendas | `CAB_VENDAS`, `ITEM_VENDAS`, `ITEM_VENDAS_LOTES`, `VENDAS_PSICOTROPICOS`, `VENDEDORES` |
| Entradas e transferências | `CAB_NOTAS`, `ITEM_NOTAS`, `LOTES`, `FORNECEDORES` |
| Perdas | `PERDAS_PSICOTROPICOS` |
| Cadastro | `PRODUTOS` (`PSICOTROPICO`/`ANTIMICROBIANO` = `'S'`) |
| Controle do envio | `SNGPC`, `CONFIG` |
| Inventário da ANVISA | `INVENTARIO_SNGPC` (regravada pelo `Anvisa.exe`) |

Regras que os SQLs do VerificaXML deixam explícitas e o agente segue:

- controlado é `PSICOTROPICO='S'` **ou** `ANTIMICROBIANO='S'`;
- venda só conta se `VENDA_RECEBIDO + SUBSIDIO + SUBSIDIO_ASSEFAZ > 0` e o
  item não estiver cancelado;
- entrada ignora CFOP `1411` e `1202`;
- transferência é saída com CFOP `5150/5151/5152/5155/5409/6409`;
- pendência sai por `VENDA_NOTA_ID > ponteiro` e `CAB_NOTA_ID > ponteiro`,
  **não por data**; perdas e transferências, cujos ponteiros ficam em 0,
  cortam por data a partir do último envio.

Duas coisas o agente descobre sozinho em tempo de execução, porque variam
entre instalações: o nome da coluna de saldo em `LOTES` e as colunas de
`INVENTARIO_SNGPC`. Se algo não bater:

```
python agente_auto.py --schema             confere as tabelas e mostra o que achou
python agente_auto.py --colunas LOTES      lista as colunas de uma tabela
```

## Firebase

```
farmacia/inventario   escrito só pelo agente; lido pelo app
                      { atualizadoEm, inventario{data,origem,colunaSaldo},
                        itens[], envio{}, xml_envio{},
                        pendentes{vendas,entradas,perdas,transferencias},
                        resumoPendentes{}, conferencia_xml[],
                        vendas_problema[], anvisa{}, enviosConhecidos[] }
farmacia/config       hash SHA-256 da senha do app (a senha não fica no código)
farmacia/aceites      { "2026-08-10": { status, por, em } }
farmacia/operadores   nomes da equipe (compartilhado com o ESTOQUE)
farmacia/comando      pedido dos botões do app; o agente atende e marca
farmacia/autorizados  UIDs que podem LER o inventário
farmacia/agentes      UIDs que podem ESCREVER (só o agente)
```

### Publicar as regras — faça isto primeiro

O banco fica aberto a quem souber o endereço enquanto as regras não
subirem. Ordem certa:

1. **Cadastre os UIDs antes.** Console do Firebase > Authentication >
   Usuários: copie o UID de cada pessoa. No Realtime Database, crie
   `farmacia/autorizados/{uid}: true` para cada uma e
   `farmacia/agentes/agente-sngpc: true` para o agente.
   O Console tem acesso de administrador e ignora as regras, então isso
   funciona antes da publicação — e evita ficar trancado do lado de fora.
2. Cole `agente/regras-firebase.json` em Realtime Database > **Regras** e publique.
3. Teste na hora: abra o app logado (tem que ler) e rode
   `python agente_auto.py --auto` (tem que escrever).

O `uid_agente` do `agente_config.json` precisa bater com a chave criada em
`farmacia/agentes`. O agente autentica com esse UID via
`databaseAuthVariableOverride`, então as regras valem para ele também — a
chave de serviço não vira passe livre.

## Senha do app

Definida na primeira abertura, ou trocada em **Config**. Só o hash SHA-256
vai para `farmacia/config`. A senha em si não fica no código, no
repositório nem no aparelho.

## Decisões que valem lembrar

- **O aceite da ANVISA não existe em arquivo local.** A pasta
  `retorno_sngpc` está vazia e o Digifarma guarda o último envio
  *enviado*, não o *aceito*. Confira no site e marque na aba Aceites.
- **O XML é sobrescrito a cada transmissão.** `SNGPC.XML`,
  `MOVIMENTACAO.XML` e `sngpc.zip` são o mesmo conteúdo. Por isso o agente
  arquiva uma cópia em `VerificaXML\enviados\sngpc_AAAA-MM-DD.xml` antes de
  qualquer leitura.
- **Vendas já transmitidas e aceitas não aparecem como pendência.**
- **Sem `prompt()` e `confirm()` nativos** — o PWA bloqueia. Modais próprios.
- **`localStorage` só guarda o nome do operador** daquele aparelho.
- **Nunca subir** `chave-firebase.json` nem os XMLs do SNGPC (dados de paciente).

## Testes

```
node teste-fumaca.js .        app: sintaxe, ids, manifest, service worker
python agente/teste_agente.py agente: XML, cruzamento, saldos, arquivamento
```
