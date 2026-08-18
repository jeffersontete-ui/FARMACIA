# FARMÁCIA — SNGPC

Conferência do estoque de controlados entre o **Digifarma** e o que foi
**transmitido ao SNGPC**. Duas peças:

- o **app web** (PWA, GitHub Pages), com login por e-mail do Firebase;
- o **agente Python** (pasta `agente/`), que roda no servidor da farmácia,
  lê o Firebird do Digifarma e publica em `farmacia/inventario`.

O estoque manual do balcão fica no repositório separado **ESTOQUE**.

## O que a conferência descobriu (agosto/2026)

Vale registrar o resultado, porque a investigação levou dois dias e o
raciocínio se perde se ficar só no histórico de commits.

O app começou mostrando **4135 divergências de saldo** e um escitalopram com
200 comprimidos num lote vencido em 2024. Depois de corrigir a apuração,
sobraram ~104, e a pergunta virou: essas são de verdade?

**São — e quase todas apontam para o Digifarma, não para a ANVISA.**

O que foi medido, não suposto:

| Verificação | Comando | Resultado |
|---|---|---|
| A comparação casa lote com lote? | `--resumo` | 208 lotes casados, **191 batendo**; **0** casariam com lote comparado de forma mais frouxa |
| O inventário do SNGPC está limpo? | `--inventario` | 230 linhas, **todas** controladas, **todas** com produto no cadastro; nenhuma descartada, nenhuma órfã |
| O site da ANVISA confirma o inventário baixado? | conferência manual | sim — TORVAL CR e DUAL aparecem zerados no site, como no inventário |

Com isso, três hipóteses caíram: não é grafia de lote, não é inventário
sujo ou parcial, não é vínculo perdido no cadastro. Sobra o Digifarma.

Os padrões que restaram:

- **39 lotes com saldo negativo.** Saída lançada sem a entrada. Não é
  estoque, é lançamento errado — e é o que mais suja a conferência: na
  lamotrigina 100mg, o lote com estoque real batia 11 = 11 com a ANVISA, e
  só os três lotes negativos (−3, −3, −1) faziam o total do produto parecer
  errado.
- **Lotes antigos com estoque no Digifarma e zero na ANVISA.** Confirmados
  no site: o SNGPC tem zero mesmo, e o Digifarma é que carrega estoque
  fantasma.
- **Entradas recentes** que ainda não estavam na foto do inventário. Saem
  sozinhas no próximo download.

A ordem de trabalho sai do `--tarefas`, e é essa: corrigir o que está torto
no Digifarma primeiro, porque reaparece em toda conferência até ser
corrigido.

### Como terminou (17/08/2026)

| | 15/08 | 17/08 |
|---|---|---|
| divergências | 71 | 31 |
| lotes com saldo negativo | 39 | **0** |
| contagem de prateleira | 17 | **2** |
| zerado na ANVISA | 15 | 29, dos quais **22 são entradas de 15/08** |

Os 39 negativos foram zerados, e o `--totais` provou que ficaram certos:
nenhum deles voltou como divergência entre `PROD_SALDO` e a soma dos lotes.
Das 29 linhas "zerado na ANVISA", 22 são entradas do próprio dia 15/08 e o
inventário do site é de 15/08 — entrada nova não podia estar numa foto mais
velha; somem no próximo download.

Sobraram **9 linhas de trabalho real**, de 4135 que apareciam no começo:

- **7 lotes em 5 medicamentos** (DUAL 30MG, LAMOTRIGINA 50 TORRENT,
  ALPRAZOLAM 2MG GEN, UNINALTREX 50, PONDERA XR) onde **três fontes
  discordam de um jeito revelador**: `PROD_SALDO` = 0, inventário da ANVISA
  = 0, e só a tabela `LOTES` diz que tem estoque. Duas fontes contra uma;
- **2 lotes de escitalopram 10mg** cuja soma bate dos dois lados — 5 e 5 —
  mas com 4 unidades atribuídas ao lote errado. Não precisa contar quantas
  caixas há: precisa ler o lote impresso nelas.

Três coisas que a investigação descobriu e que valem para a próxima vez:

1. **o Digifarma guarda dois saldos** — `PRODUTOS.PROD_SALDO` e o de cada
   lote em `LOTES`. Eles batem em 735 controlados e é o sistema que os
   mantém em dia; a conferência com o SNGPC usa o segundo, a tela do balcão
   usa o primeiro;
2. **envio feito por outra máquina não avança o ponteiro daqui**, e o agente
   passa a descontar duas vezes a mesma venda. A assinatura são vários lotes
   batendo com a ANVISA sem precisar do movimento pendente;
3. **lote negativo não aparece na tela do Digifarma** — foi por isso que o
   app ganhou as duas únicas operações que escrevem no banco.

## Regra de ouro

**O Digifarma é a verdade.** O app só LÊ o inventário, e o agente faz
`SELECT` em tudo — com **duas exceções**, ligadas à mão no servidor e
descritas em "Escrever no Digifarma": zerar lote negativo e gravar a
contagem de um lote. Foram abertas porque esses lotes não aparecem na tela
do Digifarma e não havia como corrigi-los nem estando lá.

## O que o app mostra

| Aba | O que traz |
|---|---|
| Situação | carimbo do último sincronismo, **diagnóstico**, dados do último envio, botões que pedem ao agente |
| Saldo | divergências entre o saldo do Digifarma e o inventário SNGPC vigente, com M.S., código de barras, lote e o detalhe de cada uma — cada uma classificada pelo **tipo** (veja abaixo) |
| XML | o que saiu no banco cruzado com o que subiu no XML, por registro M.S. + lote — e, quando não há divergência, **se a conferência aconteceu** |
| Vendas | controlado vendido sem receita escriturada ou sem lote — a causa clássica de recusa — e o **acompanhamento das últimas vendas**, com número, hora, lote e quantidade, atualizado de 5 em 5 minutos |
| Aceites | marcar à mão o aceite ou a recusa de cada envio, com nome e horário |

Os dois botões da aba Situação escrevem em `farmacia/comando`. O agente
atende em até 5 minutos e marca o pedido como concluído — o app mostra o
estado da fila.

## Comandar o servidor pelo celular

A farmácia não fica no servidor o dia todo, e quase toda a investigação deste
projeto foi feita por linha de comando. Por isso os comandos foram para o app,
na aba **Servidor**: o celular escreve o pedido em `farmacia/comando`, a tarefa
de 5 em 5 minutos executa **o mesmo modo do terminal**, e a saída volta em
`farmacia/relatorios/<acao>` — o texto que apareceria no servidor, sem uma
segunda versão para manter.

| Botão | Equivale a |
|---|---|
| Tarefas | `--tarefas` |
| Folha de conferência | `--comparacao` (o HTML volta junto, dá para abrir e imprimir do celular) |
| Lotes negativos | `--negativos` |
| Resumo / Inventário SNGPC | `--resumo` / `--inventario` |
| Ver cadastro | `--produto TEXTO` |
| Sincronizar tudo | `--auto` |
| Receitas lançadas | `--receitas` |
| Atualizar o agente | baixa o `agente_auto.py` **e as regras do Firebase** do GitHub |

E dois ajustes: `transmitido_ate_venda` (o remendo do ponteiro) e a coluna de
saldo. Só essas chaves — nada que aponte para banco, arquivo ou credencial.

### Escrever no Digifarma

Por muito tempo este projeto não escrevia no Digifarma, e essa continua sendo
a regra para tudo. A exceção nasceu de um problema real: os lotes negativos
**não aparecem na tela do Digifarma**, então a farmácia não conseguia
corrigi-los nem estando no servidor — virava chamado. Duas operações, e só
elas, gravam no banco:

| Botão | O que faz |
|---|---|
| Zerar os lotes negativos | põe em 0 todo lote com saldo negativo |
| Gravar a contagem neste lote | põe o saldo de um lote no valor contado na prateleira |

As travas, todas de propósito:

- **vêm desligadas.** É preciso pôr `"permitir_ajuste_estoque": true` no
  `agente_config.json`, **no servidor** — ligar a escrita é um ato deliberado
  de quem responde pela farmácia, não um toque no celular;
- só a coluna de **saldo** do lote é escrita, nunca outra;
- se a instalação usar `LOTES` como tabela de **movimento**, o ajuste é
  recusado: ali escrever não corrige saldo, inventa lançamento;
- "zerar negativo" **não aceita valor**: o destino é sempre zero, então não há
  dedo errado possível;
- "gravar contagem" **recusa** quando o mesmo M.S. + lote tem mais de uma
  linha em `LOTES` — aí não existe "o saldo do lote", e escolher seria chute;
- toda alteração grava o antes, o depois e quem pediu em três lugares:
  `ajustes_AAAA-MM-DD.json`, o log do agente e `farmacia/ajustes`;
- uma única função (`executar`) escreve no banco, para quem auditar ler ela e
  as poucas chamadas dela, não o arquivo inteiro.

**Nenhum desses acertos pode ser transmitido ao SNGPC.** Se a ANVISA já está
com o número certo, um lançamento de entrada faria o saldo dela subir
indevidamente.

Continua fora do app, e continua sendo chamado ou acesso remoto: acertar o
ponteiro de transmissão e corrigir o lote de uma venda já transmitida.

A autoatualização tem cinto e suspensório: o arquivo baixado é conferido em
tamanho, conteúdo e **sintaxe** antes de encostar no que está rodando, e o
atual vai para `agente_auto_antes_de_AAAA-MM-DD_HHMM.py`. Se qualquer coisa
falhar, nada é trocado — agente quebrado num servidor onde ninguém está é
pior que agente desatualizado. A aba mostra o hash e o tamanho do arquivo que
está rodando lá, para não ser preciso confiar na fé.

Para isso funcionar, **as regras do Firebase precisam ser republicadas**
(`agente/regras-firebase.json`): elas validam quais ações o app pode pedir e
liberam `farmacia/relatorios`.

## O agente

```
agente/
  agente_auto.py        o agente
  mapa_xml.py           leitor do XML do SNGPC
  teste_agente.py       roda tudo com banco simulado
  INSTALAR_AGENTE.bat   instalador (rodar como administrador)
  ATUALIZAR_AGENTE.bat  atualiza o agente; /auto nao pergunta nada
  ATUALIZAR_EM_SEGUNDO_PLANO.vbs  o mesmo, sem janela nenhuma
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

#### Quando o `Anvisa.exe` não abre

Em 18/08/2026 ele simplesmente não ligava. "Não liga" é sintoma de quatro
causas diferentes, e todas deixam rastro — só que num lugar diferente cada
uma. `DIAGNOSTICO_ANVISA.bat` (dois cliques, sem administrador) olha as
quatro em ordem:

1. **já tem uma cópia travada rodando**, invisível, e a segunda não abre —
   é a mais comum, e o `.bat` oferece fechar;
2. **sobrou um `chromedriver.exe`** pendurado da execução anterior;
3. **o Chrome se atualizou e o `chromedriver` ficou para trás.** Ele é
   automação de navegador: se os dois primeiros números da versão não
   baterem, o programa abre e fecha na hora, sem dizer nada;
4. **a janela abre, mostra o erro e fecha** antes de dar tempo de ler — por
   isso o `.bat` roda o `Anvisa.exe` de dentro da própria janela e guarda a
   saída e o código de término.

Tudo vai para `agente/diagnostico_anvisa.txt`, que pode ser fotografado e
mandado sem cuidado: só versões de programa e mensagens de erro, nada de
senha nem de paciente.

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
python agente_auto.py --receitas 7    que colunas de receita estão preenchidas
python agente_auto.py --regras        publica as regras do Firebase, do GitHub
python agente_auto.py --regras        publica as regras do Firebase, do GitHub
python agente_auto.py --teste         testa Firebird e Firebase
python teste_agente.py                roda tudo com banco simulado
```

```
python agente_auto.py --config transmitido_ate_venda=46108
python agente_auto.py --atualizar
```

**Não existe .exe.** Atualizar o agente é trocar o `agente_auto.py`. Há três
jeitos, do mais fácil para o mais manual: o botão **Atualizar o agente** no
app, o `ATUALIZAR_AGENTE.bat` (que guarda backup, confere o arquivo baixado
antes de trocar e ainda pergunta a configuração), ou baixar o arquivo à mão.

O `--config` existe para ninguém precisar editar JSON com pressa: uma vírgula
fora do lugar no `agente_config.json` derruba o agente inteiro. E ele recusa
valor que não é número — `transmitido_ate_venda=46l08` digitado errado viraria
zero em silêncio, desligando o ajuste sem ninguém perceber.

**Baixando à mão, use `curl -fL`, nunca `curl -o` puro.** Sem o `-f` o curl
grava a resposta de erro DENTRO do arquivo: um 429 do GitHub vira um `.bat`
de 199 bytes com o texto do erro, que o `cmd` tenta executar. Aconteceu.

```
curl -fL -o ATUALIZAR_AGENTE.bat https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA/main/agente/ATUALIZAR_AGENTE.bat
```

O `ATUALIZAR_AGENTE.bat` tem três jeitos de rodar:

```
ATUALIZAR_AGENTE.bat              pergunta a configuracao e espera
ATUALIZAR_AGENTE.bat /auto        nao pergunta nada, grava log
ATUALIZAR_AGENTE.bat /auto 46108 S   ja configura tudo
```

**Parâmetro que não vier não é alterado** — de propósito. Um `.bat` que muda
configuração em silêncio por causa de um valor padrão é exatamente como se
liga a escrita no Digifarma sem ninguém ter decidido isso.

O `ATUALIZAR_EM_SEGUNDO_PLANO.vbs` roda o mesmo `.bat` **sem janela nenhuma**;
o que aconteceu fica no `atualizacao_AAAA-MM-DD.log`, na pasta do agente.

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

### Quando o envio é feito por outra máquina

O ponteiro é o que o Digifarma **daquela instalação** grava ao fechar um
envio. Transmitindo por outro computador, a ANVISA recebe e o ponteiro daqui
não avança — o agente continua achando que aquelas vendas estão na fila e
desconta do saldo o que a ANVISA **já** descontou. A mesma venda entra duas
vezes na conta e a divergência incha (na farmácia: 71 viraram 87, sem nada
ter mudado no estoque).

A assinatura disso é o lote que **já bate com a ANVISA sem precisar do
movimento pendente**. O agente conta esses lotes e avisa no log e no app,
com o alerta que mais importa: **transmitir por esta máquina escrituraria as
mesmas vendas em dobro** na ANVISA.

O conserto é acertar o ponteiro no Digifarma, e isso o agente não faz — ele
nunca escreve no Digifarma. Enquanto o suporte não acerta, o
`agente_config.json` aceita:

```json
"transmitido_ate_venda": 46067
```

o número da última venda realmente transmitida. Vale **só para cima**, para
nunca esconder venda que o próprio Digifarma ainda considera pendente, e sai
dito no log a cada execução — ponteiro remendado à mão precisa aparecer.
Volte para `0` quando o ponteiro do Digifarma for acertado.

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

### "Tem receita" é uma pergunta que ainda não sabemos fazer

Em 18/08/2026 a farmácia avisou que o app dizia que **todas** as receitas
das vendas do dia 17 tinham sido lançadas, e ela sabia que não tinha
lançado. Estava certa, e o erro é mais fundo que o rótulo na tela.

O agente nunca perguntou se a receita foi lançada. Ele perguntou se existe
uma linha em `VENDAS_PSICOTROPICOS` para aquele item da venda:

```sql
LEFT JOIN VENDAS_PSICOTROPICOS VP ON (VP.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                 AND (VP.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
```

O Digifarma aparentemente cria essa linha junto com a venda e só recebe os
dados da receita depois. Então **faltar a linha prova que a receita não foi
lançada; existir não prova nada**. O critério só funciona num sentido.

Esse mesmo `VP.VENDA_NOTA_ID IS NULL` está em `vendas_problema` e em
`vendas_sem_receita_pendentes` — o que explica o `0 vendas com problema` que
saía em todo log e que ninguém questionou. Um teste que nunca acusa nada não
é um teste tranquilizador, é um teste quebrado.

O que foi feito por enquanto:

- o rótulo verde `receita ok` **saiu do app**. Ficou só o alerta vermelho
  `SEM RECEITA`, que é o lado confiável, e a tela avisa que a ausência da
  marca não garante nada;
- entrou o `--receitas [dias]` (botão **Receitas lançadas**), que mostra,
  venda por venda, **quais colunas de `VENDAS_PSICOTROPICOS` estão
  preenchidas** — e agrupa as colunas em "sempre", "nunca" e "às vezes". A
  coluna candidata é uma das "às vezes", e a farmácia sabe quais vendas ela
  lançou: cruzar as duas coisas dá o critério certo.

O relatório **não imprime valor nenhum**, só `tem`/`não tem`. A tabela
guarda paciente, comprador e médico, e o relatório sobe para o Firebase —
mesma lição do `EMAIL`/`SENHA` que vazaram no diagnóstico do `SNGPC`. Zero
conta como não preenchido: `CONF_VENDEDOR_ID = 0` é campo em branco, e é
justamente essa diferença que se procura.

Enquanto a coluna certa não é conhecida, as consultas continuam com o
critério frouxo. Preferi tirar a afirmação errada da tela agora e corrigir a
consulta quando houver evidência, em vez de trocar um palpite por outro.

### A tarja como identidade

A referência visual é a **tarja preta da caixa de controlado**, e ela
aparece em tudo: no ícone do app, na borda do topo, na faixa de cada
divergência, no botão principal. Os ícones do app são gerados a partir de
SVG (`agente/` não entra nisso — é arte, não código de servidor), com duas
variantes: `any`, que usa a arte inteira, e `maskable`, que desenha a mesma
caixa menor porque o Android recorta o ícone em círculo e comeria os cantos.

A aba Saldo agrupa as divergências por tipo, na ordem em que se resolvem —
dado torto no Digifarma primeiro, porque reaparece em toda conferência;
depois o que sumiu do estoque e o SNGPC ainda acusa; por último o que a
ANVISA só não recebeu ainda. Dentro do grupo, a maior diferença vem antes.
A faixa de cada linha mostra a comparação (`Digifarma 6 · SNGPC 0`) em vez
de repetir o nome do grupo logo acima dela.

O app segue o modo claro ou escuro do aparelho.

### Diagnóstico à distância

Quase todo diagnóstico deste projeto exigiu alguém sentado no servidor
rodando `--saldo`, `--resumo`, `--inventario`. Quem cuida da farmácia nem
sempre está lá, e o mais comum é justamente querer entender um número
olhando o celular.

Por isso a tarefa de 5 minutos publica um `diagnostico` em
`farmacia/inventario`, que o app mostra na aba Situação:

- quanto está **esperando transmissão**, por tipo, e os ponteiros de venda e
  entrada — é o que diz se a conta do movimento desde o envio tem com o que
  trabalhar;
- como a `INVENTARIO_SNGPC` foi lida: quantas linhas, quantas entram na
  comparação, quantas ficam fora do critério e quantas não têm produto no
  cadastro.

Não substitui os comandos, que trazem a lista item a item — mas responde
"por que ainda há divergência" sem precisar ir até a máquina.

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

Para levar ao balcão em papel:

```
python agente_auto.py --comparacao
python agente_auto.py --comparacao ESCITALOPRAM
```

Gera `comparacao_AAAA-MM-DD.html` na pasta do agente. Abra e imprima com
Ctrl+P — o estilo é feito para A4, com o cabeçalho repetindo a cada página,
linha que não parte no meio, coluna em branco para anotar a contagem física
e espaço de assinatura.

**Duas listas, não uma:** psicotrópicos/entorpecentes primeiro,
antimicrobianos depois, **cada uma começando em página nova**, com o seu
próprio total e a sua própria assinatura. São duas escriturações diferentes
— a receita de psicotrópico fica retida, a de antimicrobiano não — e assim
as duas conferências podem sair ao mesmo tempo, em mãos diferentes. Dentro
de cada lista os medicamentos vêm em **ordem alfabética**, que é como se
procura na prateleira, e abaixo de cada um os seus lotes.

A classe sai do cadastro do Digifarma (`PSICOTROPICO` / `ANTIMICROBIANO`),
o mesmo critério que decide o que é importado. Cadastro marcado como os
dois entra em psicotrópico, a lista mais rígida. Se algum medicamento
estiver sem marcação nenhuma, sai numa terceira lista no fim, dizendo que é
acerto de cadastro — melhor do que ser posto na lista errada em silêncio.

### O que a contagem da lamotrigina decidiu

Primeiro medicamento contado, e serve de régua para os outros 21 iguais.
Lamotrigina 100 mg, três lotes negativos somando −7 e o lote BLGH24024 com 11:

| | BLGH24024 | lotes velhos | total |
|---|---|---|---|
| prateleira | 11 | 0 | 11 |
| ANVISA | 11 | 0 | 11 |
| Digifarma | 11 | −7 | 4 |

A prateleira bate com a ANVISA lote a lote: **o único errado é o Digifarma**.
Conserto: zerar os três negativos e **não encostar no lote cheio**.

E o cuidado que não é óbvio: **esse acerto não pode ser transmitido**. Zerar
um lote negativo lança 7 unidades a mais no Digifarma; se isso entrar no
próximo XML, a ANVISA passa de 11 para 18 e o erro migra para o lado mais
caro de consertar. A ANVISA já está certa — é correção interna de estoque,
não movimento novo.

A folha de conferência passou a imprimir essa regra, com os dois desfechos
possíveis, para quem conta decidir sem precisar perguntar.

A tela de divergências do app segue a mesma divisão e a mesma ordem
alfabética, para o papel e o celular não contarem histórias diferentes.

**As vendas do dia saem na folha**, e por um motivo prático: o inventário do
SNGPC é a **foto do último envio** e a prateleira é de **agora**. O que foi
vendido hoje já saiu da prateleira e ainda está na foto — quem conta encontra
a caixa faltando e marca divergência de uma venda que está certa. Por isso a
tabela tem cinco números, e não três:

```
SNGPC (foto do envio) + Movim. = Esperado        Dif. = Digifarma − Esperado
```

A coluna **Movim.** é o que se moveu depois do envio e ainda não subiu, lote a
lote. No fim de cada lista vem o detalhe desse movimento — **número da venda,
data e hora, medicamento, lote e quantidade** —, na ordem em que aconteceu,
para dar baixa no papel na hora da contagem. Entradas e perdas pendentes
entram na mesma lista, com o tipo em cada linha. A diferença **nunca** é
contra a foto do envio; é contra o esperado.

**Lote com saldo negativo fica de fora dessa folha**, junto com o que não
tem registro M.S. Nenhum dos dois é divergência de estoque, e nenhuma
contagem os resolve — são acerto no cadastro do Digifarma. Quantos ficaram
de fora sai no cabeçalho da folha: sumir em silêncio seria esconder
trabalho, não poupar.

Para a primeira lista — os lotes com saldo negativo — há um comando que abre
cada um:

```
python agente_auto.py --negativos
python agente_auto.py --negativos LAMOTRIGINA
```

Ele mostra o que entrou (nota e data), o que foi vendido (venda e data) e
**quais outros lotes do mesmo medicamento têm saldo**. Essa última linha é a
que aponta a causa, e são duas, com consertos diferentes:

- **lote negativo com irmão cheio** — assinatura de venda lançada no lote
  errado: o produto saiu do lote novo e o sistema debitou o antigo. O
  conserto é corrigir o lote na venda;
- **lote negativo sem irmão nenhum** — entrada que nunca foi lançada. O
  conserto é lançar a nota.

O rodapé conta quantos caíram em cada caso.

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

### Depois da primeira vez, o agente publica as regras sozinho

Toda função nova do app quase sempre pede uma ação nova liberada em
`comando/acao`. Enquanto o JSON não era copiado à mão para o console, o
botão novo era **recusado sem dizer por quê** — e o passo manual sempre
acontecia num momento ruim, com a farmácia no balcão.

O servidor já tem a chave de administrador. Então **`--atualizar` (o botão
"Atualizar o agente") passou a publicar as regras junto**: baixa
`regras-firebase.json` do mesmo repositório, confere, compara com o que está
publicado e só grava se mudou.

```
python agente_auto.py --regras     publica as regras à mão, sem atualizar o agente
```

As regras ficam noutra porta que não a dos dados: `PUT` em
`/.settings/rules.json`, com um token OAuth tirado da mesma chave de serviço
nos escopos `firebase.database` e `userinfo.email`. Se o Firebase responder
401 ou 403, falta à conta de serviço o papel **Firebase Realtime Database
Admin** no Google Cloud > IAM.

Publicar regra é mexer na tranca do banco, então o arquivo baixado passa por
`conferir_regras()` antes:

- precisa ter `rules`, e a raiz precisa estar fechada (`.read` e `.write`
  em `false`);
- precisa ter os nós deste projeto (`inventario`, `comando`, `relatorios`,
  `autorizados`, `agentes`) — arquivo de outro projeto não entra;
- **nenhum `.read`/`.write` pode ser `true`** em lugar nenhum da árvore,
  nem como texto. Regra frouxa não quebra nada na hora: abre o banco
  calada, e é o erro que passa numa revisão apressada.

Se a conferência recusar, as regras que estão valendo continuam valendo e a
atualização do agente segue normalmente — o recado vai para o log e para a
tela do app.

Isto não é confiança nova: o agente já baixava e executava o **próprio
código** da mesma URL, o que é estritamente mais poderoso do que trocar as
regras. O que muda é que agora as duas coisas andam juntas, e a farmácia
parou de ser o passo manual entre elas.

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
