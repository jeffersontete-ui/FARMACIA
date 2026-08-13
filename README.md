# FARMÁCIA — SNGPC

Conferência do estoque de controlados entre o **Digifarma** e o que foi
**transmitido ao SNGPC**. Duas peças:

- o **app web** (PWA, GitHub Pages), com login por e-mail do Firebase;
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
| Saldo | divergências entre o saldo do Digifarma e o inventário SNGPC vigente, com M.S., código de barras, lote e o detalhe de cada uma — cada uma classificada pelo **tipo** (veja abaixo) |
| XML | o que saiu no banco cruzado com o que subiu no XML, por registro M.S. + lote — e, quando não há divergência, **se a conferência aconteceu** |
| Vendas | controlado vendido sem receita escriturada ou sem lote — a causa clássica de recusa — e o **acompanhamento das últimas vendas**, com número, hora, lote e quantidade, atualizado de 5 em 5 minutos |
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
| `AgenteSNGPC_Fila` | a cada 5 minutos | `--fila`, atende os botões do app **e publica as últimas vendas** |
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
python agente_auto.py --envio         inventário vigente no último envio
python agente_auto.py 31/07/2026      inventário daquela data
python agente_auto.py --schema        confere as tabelas da base
python agente_auto.py --colunas LOTES lista as colunas de uma tabela
python agente_auto.py --saldo TEXTO   mostra como o saldo de um lote foi apurado
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
python agente_auto.py --saldo ESCITALOPRAM abre a conta do saldo, lote por lote
```

### Como o saldo por lote é apurado

`LOTES` é tabela de **movimento**, não de saldo: cada entrada de nota gera
uma linha e `ENTRADA_SAIDA` diz se aquela linha soma ou subtrai. Duas
consequências, e as duas já morderam:

1. somar a coluna sem olhar o `ENTRADA_SAIDA` faz devolução ao fornecedor
   **somar** ao estoque;
2. a **venda** de controlado não passa por `LOTES` — ela fica em
   `ITEM_VENDAS_LOTES`. Sem descontar isso, o lote nunca baixa e o app
   publica o total comprado na vida do lote como se fosse estoque (era daí
   que saíam 200 comprimidos num lote vencido em 2024).

Por isso o agente separa dois casos:

| Modo | Quando | Conta |
|---|---|---|
| `saldo` | `LOTES` tem coluna de saldo — no Digifarma é **`LOTE_QUANTIDADE`** | soma a coluna, só das linhas de entrada |
| `movimento` | só há coluna de quantidade (`QUANTIDADE_COMPRA`…) | entradas − saídas − vendas (`ITEM_VENDAS_LOTES`) − perdas (`PERDAS_PSICOTROPICOS`) |

**No Digifarma o modo certo é `saldo`, com `LOTE_QUANTIDADE`.** Não tente
reconstruir o estoque a partir das compras: o Digifarma dá baixa por
caminhos que não aparecem em venda nem em perda — o vencido que sai do
estoque é o caso comum. O lote 3G4313 do escitalopram tem 63 comprados, 3
vendidos e `LOTE_QUANTIDADE = 0`; a reconstrução dava 60.

`QUANTIDADE_COMPRA` é o que entrou em cada nota, e `ESTOQUE_CONTADO` /
`ESTOQUE_MOVIMENTADO` / `LOTE_COMISSAO` não são saldo — o casamento é por
nome exato justamente para não pegar nenhuma delas.

O modo escolhido vai para `farmacia/inventario/inventario/modoSaldo` e o app
mostra na aba Situação, em **Como o saldo é apurado**. No modo `movimento`
cada item leva também `entradas` e `baixas`, que aparecem no detalhe da
divergência — é o que permite bater o número com a tela do Digifarma.

Se a instalação usar outro nome, ou se o agente escolher a coluna errada,
rode `--saldo` para ver a conta e fixe no `agente_config.json`:

```json
{ "coluna_saldo": "QUANTIDADE", "modo_saldo": "saldo" }
```

### O que entra: só controlado, dos dois lados

**Controlado é `PRODUTOS.PSICOTROPICO='S'` ou `PRODUTOS.ANTIMICROBIANO='S'`**,
e esse é o único critério — nas vendas, nas entradas, nas perdas, no estoque
e **também no inventário do SNGPC** que o `Anvisa.exe` grava em
`INVENTARIO_SNGPC`.

Esse último faltava. A tabela era lida inteira, então um item não marcado
como controlado que estivesse lá virava divergência "só na ANVISA" —
comparando lados que não se comparam. Agora ela é filtrada por `PRODUTO_ID`
contra o cadastro, e quantas linhas ficaram de fora é publicado em
`inventario.foraDoCriterio`.

Uma exceção deliberada: linha do inventário que **não casa com nenhum
produto do cadastro** continua entrando. Pode ser medicamento que o SNGPC
tem e a farmácia não — divergência de verdade, que precisa aparecer. Só sai
o que está no cadastro e está marcado como não controlado.

### A conta: o inventário é uma foto do último envio

O inventário do SNGPC mostra o estoque **como estava no último envio**. O
saldo do Digifarma é de **agora**. Entre um e outro a farmácia vendeu e
recebeu. Comparar as duas fotos direto acusa como divergência tudo que se
moveu no intervalo — inclusive a entrada de ontem, que ainda nem podia
estar no inventário.

```
SNGPC (último envio) + entradas − vendas − perdas − transferências
= saldo do Digifarma hoje
```

O que entra nessa conta são os **pendentes de transmissão**, que o agente já
levanta pelos ponteiros da tabela `SNGPC`. Cada item publica
`movimentoDesdeEnvio` e `esperadoSngpc`, e a `diferenca` é contra o
esperado, não contra a foto. O app mostra a conta inteira, nesta ordem:
saldo no último envio → movimento desde então → esperado hoje → Digifarma →
diferença.

Divergência de verdade é o que **sobra** depois disso.

### A regra da comparação

**Registro M.S. + número do lote → quantidade.** Dois lotes só são o mesmo
lote se o M.S. e o número do lote baterem; aí as quantidades são comparadas.

O M.S. é normalizado para só dígitos dos dois lados (`1.0525.0018.018-9` e
`1052500180189` são o mesmo registro) e o lote é comparado em maiúsculas.
Nada além disso: nem zero à esquerda ignorado, nem pontuação removida —
o `--resumo` mediu quantas divergências sumiriam com um casamento mais
frouxo e deu **zero**, então afrouxar só criaria risco de juntar lotes
diferentes.

**O nome do medicamento não entra na chave**, de propósito. Os dois lados
escrevem diferente — `ESCITALOPRAM 10MG` no Digifarma contra
`ESCITALOPRAM OXALATO 10 MG NOVA QUIMICA` —, e casar por nome perderia
lotes que hoje casam. Na base da Drogaria Humanae a questão nem se coloca:
`INVENTARIO_SNGPC` só tem `REGISTRO_MS`, `NUM_LOTE` e `SALDO_LOTE`, sem
coluna de descrição. O nome existe para quem lê a linha.

Corolário: **produto sem M.S. no cadastro não pode ser conferido — e nem
existe para o SNGPC.** O SNGPC recusa medicamento sem registro M.S., então
esse produto nunca foi transmitido: nem a entrada, nem a venda. Não é
divergência de estoque, é controlado se movimentando sem escrituração, e
nenhuma conferência de prateleira resolve.

Por isso eles ficam **fora da contagem de divergências**, num bloco próprio
no topo da aba Saldo e numa seção própria do `--tarefas`. O conserto é
cadastrar o registro no Digifarma; feito isso, o produto passa a ser
transmitido e a ser conferível.

### Lote, não produto

A conferência é **por M.S. + lote**, porque é assim que o SNGPC guarda o
inventário. A tela do Digifarma mostra o **produto**, somando os lotes. Os
dois números são diferentes e os dois estão certos.

A pregabalina 150mg (código 66132) da Drogaria Humanae tem três lotes —
72200415 com 6, 72200416 com 1 e 72200417 com 2. A tela do Digifarma mostra
9; o app mostra 6 no lote que diverge, porque os outros dois batem com a
ANVISA e nem entram na lista. Quem confere lê 6 num lado e 9 no outro e
conclui que o app está errado.

Por isso cada item leva também `saldoDigifarmaMs` e `saldoSngpcMs` — os
totais somando os lotes daquele registro M.S. — e o app os mostra como
"todos os lotes deste M.S.". Eles só aparecem quando o medicamento tem
mais de um lote, que é exatamente quando o número do lote não bate com a
tela.

### Acompanhamento das vendas, de 5 em 5 minutos

A tarefa `AgenteSNGPC_Fila` já rodava a cada 5 minutos para atender os
botões do app. Ela passa a publicar também as vendas de controlado dos
últimos 7 dias em `farmacia/inventario/vendasRecentes` — **uma linha por
lote vendido**, com número da venda, hora, produto, lote e quantidade. A
mesma venda aparece duas vezes quando sai de dois lotes, que é como o SNGPC
precisa e como se confere no balcão.

Junto sobe `vendasSemReceita`: as vendas de controlado **que ainda não foram
transmitidas** e estão sem receita escriturada — cortadas pelo ponteiro, não
por data. É a causa clássica de recusa, e o conserto antes do envio é bem
mais barato que depois. O app mostra essas em bloco próprio, no topo da aba
Vendas.

Escrever num filho de `farmacia/inventario` é de propósito: a regra do banco
já libera esse caminho para o agente, então não é preciso republicar regras.
E a sincronização completa, que é cara, continua de hora em hora.

### Zero que não quer dizer "tudo certo"

Foi o erro que originou este trabalho: 4135 "sobras" que não eram sobra, e
um saldo do SNGPC zerado que era coluna não reconhecida. A recíproca vale —
um **zero** também engana. "0 divergências de XML" tanto pode ser
conferência limpa quanto conferência que não aconteceu: sem `SNGPC.XML` na
pasta, sem período no cabeçalho, ou sem venda nenhuma no período.

Por isso `conferenciaXmlResumo` publica `conferiu`, o arquivo, o período e
quantas saídas havia de cada lado; e `vendasProblemaDesde` publica a data de
corte da aba Vendas, porque aquela consulta corta por data e o zero não vale
para a história inteira. O app usa os dois para dizer qual zero é qual, em
vez de "tudo que saiu no período está no XML".

### Os tipos de divergência de saldo

"Sobra no Digifarma" não diz o que fazer. Cada divergência se resolve num
lugar diferente, então o agente classifica cada item em `motivo` e o app
mostra isso na tarja:

| `motivo` | O que é | Por onde começar |
|---|---|---|
| `sem_ms` | o produto não tem registro M.S.; o SNGPC recusa, logo nunca foi transmitido | cadastrar o M.S. no Digifarma — fora da contagem de divergências |
| `anvisa_zerada_produto` | a ANVISA não tem saldo em lote nenhum desse registro M.S. | conferir o estoque físico e o saldo do Digifarma |
| `anvisa_zerada_lote` | a ANVISA tem outros lotes do medicamento, mas não esse | conferir o número do lote e a entrada dele |
| `quantidade` | os dois lados têm o lote, com contagens diferentes | conferência de prateleira |
| `so_na_anvisa` | a ANVISA tem saldo e o Digifarma não | saída lançada só de um lado |
| `negativo` | o próprio Digifarma está com saldo negativo | corrigir no Digifarma: saída sem entrada |

O nome do `motivo` diz o que se **observa**, não a causa. Zero na ANVISA
tanto pode ser entrada que não subiu quanto saldo errado no Digifarma — os
dois casos apareceram no mesmo dia na Drogaria Humanae, no TORVAL CR e no
DUAL. As etiquetas anteriores (`nao_transmitido`, `lote_ausente`)
afirmavam a causa e mandavam mexer na escrituração quando o problema era o
estoque.

`farmacia/inventario/resumoSaldo` traz a contagem por tipo, que o app
mostra no topo da aba Saldo.

Para medir de onde vem a divergência antes de mandar alguém conferir
prateleira:

```
python agente_auto.py --resumo
```

E para virar trabalho, na ordem em que se resolve:

```
python agente_auto.py --tarefas
```

Três listas, e a ordem não é gosto: **(1)** saldo negativo no Digifarma vem
primeiro porque é dado torto que reaparece em toda conferência até alguém
corrigir; **(2)** o que o SNGPC não tem é escrituração, e a lista já separa
o que **já está na fila do próximo envio** (resolve sozinho) do que não
está; **(3)** contar prateleira por último, que é o mais caro e costuma ser
o menor grupo. Grava um `tarefas_saldo_AAAA-MM-DD.txt` na pasta do agente,
para imprimir. Como tudo aqui, só lê.

O `--resumo` separa quantos lotes casaram e batem, quantos divergem no valor,
quantos só existem de um lado — e quantos **casariam se o número do lote
fosse comparado sem zero à esquerda e sem pontuação**. Esse último número
é o que diz se a divergência é de grafia (conserto no código) ou de
estoque (conserto na farmácia). Na Drogaria Humanae ele deu 0: a
comparação exata está certa.

Do lado da ANVISA, as colunas de `INVENTARIO_SNGPC` são casadas **por nome
exato primeiro** e só depois por pedaço do nome. Procurar só o pedaço `LOTE`
devolvia `LOTE_VENCIMENTO` quando ela vinha antes de `NUM_LOTE` na tabela: a
chave da comparação virava uma data, nada casava com o Digifarma e todo item
aparecia como sobra com o saldo do SNGPC zerado. As colunas efetivamente
usadas vão para `farmacia/inventario/inventario/camposAnvisa`.

Quando `INVENTARIO_SNGPC` está vazia — o `Anvisa.exe` nunca completou o
login — não existe lado ANVISA para comparar, e o app agora avisa isso no
topo da aba Saldo em vez de mostrar milhares de "sobras" que não são
divergência nenhuma.

## Firebase

```
farmacia/inventario   escrito só pelo agente; lido pelo app
                      { atualizadoEm,
                        vendasRecentes[], vendasRecentesEm  (a cada 5 min),
                        inventario{data,origem,itens,colunaSaldo,modoSaldo,camposAnvisa},
                        itens[], envio{}, xml_envio{},
                        pendentes{vendas,entradas,perdas,transferencias},
                        resumoPendentes{}, conferencia_xml[],
                        vendas_problema[], anvisa{}, enviosConhecidos[] }
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

## Quem entra

Só o login por e-mail do Firebase (Authentication > Usuários). Não há
segunda senha: quem consegue ler o inventário é quem tem o UID em
`farmacia/autorizados`, e isso é decidido pelas regras do banco, não
pelo app. Para liberar mais alguém, crie o usuário em Authentication e
acrescente o UID dele em `farmacia/autorizados`.

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
