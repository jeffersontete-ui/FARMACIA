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
| Vendas | controlado vendido sem receita escriturada ou sem lote — a causa clássica de recusa — e o **acompanhamento das últimas vendas**, com número, hora, lote e quantidade, atualizado a cada minuto |
| Aceites | marcar à mão o aceite ou a recusa de cada envio, com nome e horário |

Os dois botões da aba Situação escrevem em `farmacia/comando`. O agente
atende em cerca de um minuto e marca o pedido como concluído — o app mostra o
estado da fila.

## Comandar o servidor pelo celular

A farmácia não fica no servidor o dia todo, e quase toda a investigação deste
projeto foi feita por linha de comando. Por isso os comandos foram para o app,
na aba **Servidor**: o celular escreve o pedido em `farmacia/comando`, a tarefa
a cada minuto executa **o mesmo modo do terminal**, e a saída volta em
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
| `AgenteSNGPC_Fila` | a cada minuto | `--fila`, atende os botões do app **e publica as últimas vendas** |
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

#### O que era, no fim: o driver tinha sumido

O diagnóstico fechou o caso em 18/08/2026:

| O que apareceu | O que quer dizer |
|---|---|
| `Anvisa.exe` terminou com **código 0** | não deu pau — abriu e saiu na hora, calado |
| **nenhum `anvisa.log`** | não chegou nem a começar o trabalho |
| Chrome **151.0.7922.138** | navegador instalado e atualizado |
| **nenhum chromedriver** em todo o `C:\Digifarma` | é isto |

Não era driver desatualizado: **o arquivo não estava mais lá**. A suspeita
mais provável é antivírus — `chromedriver.exe` é falso-positivo clássico.

`INSTALAR_CHROMEDRIVER.bat` resolve com dois cliques. O trabalho está no
`instalar_chromedriver.ps1` ao lado: em PowerShell dá para ler JSON e
descompactar zip sem malabarismo, e o `.bat` só chama, liberando a política
de execução **apenas para aquela execução** — não mexe na configuração da
máquina.

Ele não adivinha a versão. Lê o Chrome instalado e pergunta ao Google qual
driver corresponde, tentando as fontes em ordem — a versão exata, o último
patch daquele build, o último do marco, o canal estável — e **diz qual
respondeu**, para a próxima vez ser direta. O Google já mudou esses endereços
mais de uma vez; depender de um só é depender de sorte.

Depois de copiar, ele **espera e confere de novo**. Copiar não é instalar: se
o arquivo sumir em cinco segundos, é o antivírus, e aí a mensagem diz para
criar a exceção na pasta em vez de deixar a farmácia repetir o processo
amanhã. O driver antigo, quando existe, é guardado antes de ser trocado.

Uma ressalva de quando isto foi escrito: o proxy do ambiente bloqueia o site
do chromedriver, então as URLs não puderam ser testadas de lá. Foi justamente
por isso que o script tenta várias fontes e relata qual funcionou.

**Rodou no servidor em 18/08/2026 e deu certo na primeira**, o que já responde
o que não dava para saber:

```
Chrome 151.0.7922.138
candidata 151.0.7922.138  (mesma versao do Chrome)
Baixado: .../chrome-for-testing-public/151.0.7922.138/win64/chromedriver-win64.zip
Responde: ChromeDriver 151.0.7922.138
```

Ou seja: **existe chromedriver na versão exata do Chrome**, o endereço
`chrome-for-testing-public/<versão>/win64/chromedriver-win64.zip` está de pé, e
a primeira candidata basta. Da próxima vez que faltar driver, é esse o caminho.

Detalhe que essa primeira execução revelou: uma fonte que devolvia uma versão
**já listada** ficava calada, e a tela dava a impressão de que ela não tinha
respondido — quando estava confirmando. Agora ela diz `confirma`. Ler "duas
fontes falharam" onde na verdade concordaram custaria uma investigação inútil
justamente no dia em que alguma coisa desse errado de verdade.

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

### Acompanhamento das vendas, de minuto em minuto

A tarefa `AgenteSNGPC_Fila` roda a cada minuto para atender os
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

#### De 5 minutos para 1, e por que isso não custou nada

A lentidão que a farmácia sentia era a espera do botão: apertava no celular
e o agente podia demorar cinco minutos para responder. A fila passou a rodar
**a cada minuto**.

Rodar 5 vezes mais não custa 5 vezes mais porque a rodada passou a **só
escrever o ramo que mudou**. `mudou()` guarda uma impressão digital de cada
ramo em `ultimo_publicado.json` e compara antes de gravar; numa farmácia, a
maior parte dos minutos do dia não tem venda de controlado nenhuma, então
quase toda rodada não escreve nada. Sem isso seriam 1440 reescritas por dia
da mesma lista, e o app repintando a tela à toa.

O carimbo da hora acompanha a mesma regra: se nada mudou, ele também não
muda. "Atualizado agora" sobre dado velho é pior que carimbo antigo.

Em qualquer dúvida — arquivo ilegível, valor que não vira JSON, erro de
escrita — `mudou()` responde que **mudou**. Publicar à toa custa banda;
deixar de publicar esconde venda da farmácia, que é bem pior.

### Três datas para a mesma transmissão, e nenhuma comparável

Em 18/08/2026 a farmácia abriu o **Relatório Status de Transmissão** no site
da ANVISA e estranhou a tela: o app dizia `Movimentos de 16/08 a 17/08`, e o
site não mostrava nada desse período — o último lote aceito aparecia como
15/08 a 16/08.

A suspeita era grave e plausível: XML gerado, ponteiro avançado, ANVISA sem
receber. Se fosse isso, aquelas vendas ficariam num buraco — baixadas aqui,
inexistentes lá, e nunca mais incluídas em envio nenhum.

**Não era.** A farmácia respondeu: a última transmissão foi feita no dia 17
cobrindo as vendas de 15 e 16, e a próxima cobre 17 a 18. Estava tudo em
ordem. O que existe são **três convenções de data para a mesma transmissão**:

| Onde | O que mostrava |
|---|---|
| Site da ANVISA | 15/08 a 16/08 |
| Cabeçalho do XML | 16/08 a 17/08 |
| `ULTIMO_ENVIO_SNGPC` | 15/08 |

O que ficou, então:

- o rótulo virou **`Movimentos do último XML`**, porque é isso que ele é — o
  período escrito no arquivo da pasta, não prova de transmissão nem de
  aceite;
- a tela diz explicitamente que as datas do XML e as do site não seguem a
  mesma contagem, e que quem responde pelo aceite é o site.

E o que **não** ficou: um alarme comparando `movimentosAte` com
`ULTIMO_ENVIO_SNGPC`, que cheguei a subir. Ele teria acendido nessa farmácia
em dia, todo dia, numa tela dizendo "os números abaixo estão errados".

Isso é pior que não avisar nada. Alarme que acende sempre ensina a ignorar
alarme, e o dia em que houvesse um buraco de verdade seria só mais um dia com
a tarja vermelha de sempre. Ficou um comentário no `agente_auto.py`, no ponto
exato onde a tentação bate, explicando por que a comparação óbvia não vale.

A regra, de novo, e agora contra mim mesmo: **o app não afirma o que não
sabe** — nem quando o palpite parece bom.

### Transmissão recusada deixa buraco, e ninguém avisa

O mesmo Relatório Status de Transmissão que desmentiu a suspeita acima
mostrou outra coisa, essa verdadeira: o lote de **12/08/2026 saiu com
`Foi aceito? NÃO`**, e o motivo estava escrito ali:

> MEDICAMENTO - ENTRADA: O medicamento de número de registro
> (1.0753.0536.001-8) não foi encontrado na base de dados da ANVISA

Duas coisas que isso ensina:

1. **A recusa é do lote inteiro, não do item.** Um registro M.S. errado num
   único medicamento derruba todos os movimentos daquela transmissão. O que
   estava no lote não chegou à ANVISA — e o inventário do site vai refletir
   essa falta até alguém reenviar o período.
2. **Corrigir o cadastro não reenvia nada.** Conserta as transmissões
   seguintes; a recusada continua recusada. Se o ponteiro do Digifarma
   avançou quando o lote foi gerado, aqueles movimentos não entram em envio
   nenhum sozinhos.

O Digifarma **não guarda esse retorno** — só o do inventário, no
`INVENTARIO_ACEITO`. Então não há como o agente descobrir uma recusa lendo o
banco: quem sabe é o site. É por isso que a aba **Aceites** existe e é
marcada à mão, e é por isso que "marcar o aceite" não é burocracia — é o
único registro de que o lote chegou.

Ao ver uma divergência antiga que não sai por nada, vale a pergunta: *o lote
que trouxe essa entrada foi aceito?*

### A divergência responde "esse remédio saiu?"

Diante de uma diferença, a primeira pergunta da farmácia é sempre a mesma —
e a tela calava sobre ela. A pessoa ia à prateleira contar um lote que podia
simplesmente ter sido vendido.

Cada divergência agora carrega as vendas daquele lote nos últimos 45 dias:
quanto saiu, em quantas vendas, quando foi a última e o número dela. Aparece
na linha, sem precisar abrir — `Vendeu 4` — e o detalhe traz a conta inteira.

A soma sai pronta do banco (`vendas_recentes_por_lote`), uma linha por lote,
com `GROUP BY`. Buscar venda a venda e somar no Python custaria caro e subiria
centenas de linhas que ninguém lê. E só os itens **com motivo** recebem o
cruzamento: quem bate não gera pergunta, e pendurar venda em 700 lotes certos
engorda o `farmacia/inventario` à toa.

Junto vai `semReceita`: quantas dessas vendas **não têm linha** em
`VENDAS_PSICOTROPICOS`. Vale lembrar o limite dessa contagem, que está
explicado acima — faltar a linha prova que a receita não foi lançada, existir
não prova nada. Por isso o app só alerta no sentido que vale.

### Chave repetida num dicionário

Escrevendo a consulta acima, dei a ela um nome que **já existia** em
`CONSULTAS`. O Python fica com a última e não reclama: a minha sumiu sem
aviso. Se tivesse vindo depois, teria substituído a consulta que apura as
baixas por lote — e o erro apareceria como saldo errado, semanas depois, sem
nenhuma ligação visível com a causa.

O `teste_agente.py` passou a ler o **código-fonte** com `ast` e recusar
chave repetida em qualquer dicionário do agente. Tem que ser no fonte: no
dicionário já construído a duplicata não existe mais, não há o que testar.

### "Tem receita" — a pergunta certa, enfim

Em 18/08/2026 a farmácia avisou que o app dizia que **todas** as receitas das
vendas do dia 17 tinham sido lançadas, e ela sabia que não tinha lançado.
Estava certa, e o erro era mais fundo que o rótulo na tela.

O agente nunca perguntou se a receita foi lançada. Perguntou se existe uma
**linha** em `VENDAS_PSICOTROPICOS` para aquele item da venda. O Digifarma
cria essa linha junto com a venda e recebe os dados da receita depois — nas
46 vendas medidas, **nenhuma** estava sem linha. O teste nunca acusava nada,
e o `0 vendas com problema` que saía em todo log era falso.

Um teste que nunca acusa nada não é um teste tranquilizador. É um teste
quebrado.

#### Como a coluna certa foi encontrada

O `--receitas` (botão **Receitas lançadas**) lê as vendas do período e
mostra, uma a uma, **quais colunas estão preenchidas** — nunca o que está
escrito nelas, porque a tabela guarda paciente, comprador e médico, e o
relatório sobe para o Firebase. Zero conta como vazio, de propósito.

Ele separa as colunas em três grupos, e a resposta está no grupo do meio: as
que aparecem cheias em umas vendas e vazias em outras. Cruzando com o que a
farmácia sabia — as duas últimas vendas do dia, 19:03 e 18:09, ainda não
lançadas — o desenho apareceu limpo:

| Coluna | Preenchida | Serve? |
|---|---|---|
| `PRESCRITOR` | 44 de 46 | **sim** — vazia exatamente nas duas |
| `COMPRADOR`, `COMPRADOR_DOCUMENTO`, `RECEITUARIO_NUMERO`, `CONSELHO_NUMERO`, `PACIENTE_ID` | 44 de 46 | sim, mesmo padrão |
| `PACIENTE`, `PACIENTE_IDADE` | 42 de 46 | **não** — faltam em 2 vendas que FORAM lançadas |
| `PACIENTE_SEXO` | 44 de 46 | **não** — preenchida até nas duas não lançadas |
| `RECEITUARIO_TIPO`, `USO_MEDICAMENTO` | 25 e 1 de 46 | não — campos opcionais |

Ficou **`PRESCRITOR`** entre as seis equivalentes por um motivo prático: é
certamente coluna de texto, então `TRIM()` e comparação com `''` são
seguros. `RECEITUARIO_NUMERO` poderia ser numérica, e o mesmo teste
quebraria.

O quase-acerto vale registro: `PACIENTE` parecia servir e teria feito o app
**acusar receita boa como faltante** em duas vendas de 46. Escolher pela
plausibilidade do nome, sem olhar quem discorda, dá exatamente nisso.

#### O critério mora num lugar só

```python
SQL_RECEITA_LANCADA = (
    "(VP.VENDA_NOTA_ID IS NOT NULL AND COALESCE(TRIM(VP.PRESCRITOR), '') <> '')")
```

As consultas escrevem `{RECEITA}` e a substituição acontece no carregamento.
Repetir a condição em quatro SELECTs foi como o critério errado sobreviveu
tanto tempo: consertar um e esquecer os outros é fácil demais. O teste cobra
as quatro pelo nome — e pegou, na primeira passada, a que eu tinha esquecido.

Com o critério certo, o rótulo verde `receita ok` voltou ao app. Ele já
esteve lá, saiu por não ter base, e agora tem.

#### Uma coluna que nunca é preenchida

A mesma medição mostrou `CONFERIDO`, `CONF_DATA` e `CONF_VENDEDOR_ID`
**vazias nas 46 linhas** — a conferência de venda do Digifarma não é usada
nesta farmácia. O `vendas_problema` fazia um `LEFT JOIN VENDEDORES` por
`CONF_VENDEDOR_ID` e trazia uma coluna de vendedor sempre vazia. O join
saiu.

### Três datas para a mesma transmissão, e nenhuma comparável

Em 18/08/2026 a farmácia abriu o **Relatório Status de Transmissão** no site
da ANVISA e estranhou a tela: o app dizia `Movimentos de 16/08 a 17/08`, e o
site não mostrava nada desse período — o último lote aceito aparecia como
15/08 a 16/08.

A suspeita era grave e plausível: XML gerado, ponteiro avançado, ANVISA sem
receber. Se fosse isso, aquelas vendas ficariam num buraco — baixadas aqui,
inexistentes lá, e nunca mais incluídas em envio nenhum.

**Não era.** A farmácia respondeu: a última transmissão foi feita no dia 17
cobrindo as vendas de 15 e 16, e a próxima cobre 17 a 18. Estava tudo em
ordem. O que existe são **três convenções de data para a mesma transmissão**:

| Onde | O que mostrava |
|---|---|
| Site da ANVISA | 15/08 a 16/08 |
| Cabeçalho do XML | 16/08 a 17/08 |
| `ULTIMO_ENVIO_SNGPC` | 15/08 |

O que ficou, então:

- o rótulo virou **`Movimentos do último XML`**, porque é isso que ele é — o
  período escrito no arquivo da pasta, não prova de transmissão nem de
  aceite;
- a tela diz explicitamente que as datas do XML e as do site não seguem a
  mesma contagem, e que quem responde pelo aceite é o site.

E o que **não** ficou: um alarme comparando `movimentosAte` com
`ULTIMO_ENVIO_SNGPC`, que cheguei a subir. Ele teria acendido nessa farmácia
em dia, todo dia, numa tela dizendo "os números abaixo estão errados".

Isso é pior que não avisar nada. Alarme que acende sempre ensina a ignorar
alarme, e o dia em que houvesse um buraco de verdade seria só mais um dia com
a tarja vermelha de sempre. Ficou um comentário no `agente_auto.py`, no ponto
exato onde a tentação bate, explicando por que a comparação óbvia não vale.

A regra, de novo, e agora contra mim mesmo: **o app não afirma o que não
sabe** — nem quando o palpite parece bom.

### Transmissão recusada deixa buraco, e ninguém avisa

O mesmo Relatório Status de Transmissão que desmentiu a suspeita acima
mostrou outra coisa, essa verdadeira: o lote de **12/08/2026 saiu com
`Foi aceito? NÃO`**, e o motivo estava escrito ali:

> MEDICAMENTO - ENTRADA: O medicamento de número de registro
> (1.0753.0536.001-8) não foi encontrado na base de dados da ANVISA

Duas coisas que isso ensina:

1. **A recusa é do lote inteiro, não do item.** Um registro M.S. errado num
   único medicamento derruba todos os movimentos daquela transmissão. O que
   estava no lote não chegou à ANVISA — e o inventário do site vai refletir
   essa falta até alguém reenviar o período.
2. **Corrigir o cadastro não reenvia nada.** Conserta as transmissões
   seguintes; a recusada continua recusada. Se o ponteiro do Digifarma
   avançou quando o lote foi gerado, aqueles movimentos não entram em envio
   nenhum sozinhos.

O Digifarma **não guarda esse retorno** — só o do inventário, no
`INVENTARIO_ACEITO`. Então não há como o agente descobrir uma recusa lendo o
banco: quem sabe é o site. É por isso que a aba **Aceites** existe e é
marcada à mão, e é por isso que "marcar o aceite" não é burocracia — é o
único registro de que o lote chegou.

Ao ver uma divergência antiga que não sai por nada, vale a pergunta: *o lote
que trouxe essa entrada foi aceito?*

### A divergência responde "esse remédio saiu?"

Diante de uma diferença, a primeira pergunta da farmácia é sempre a mesma —
e a tela calava sobre ela. A pessoa ia à prateleira contar um lote que podia
simplesmente ter sido vendido.

Cada divergência agora carrega as vendas daquele lote nos últimos 45 dias:
quanto saiu, em quantas vendas, quando foi a última e o número dela. Aparece
na linha, sem precisar abrir — `Vendeu 4` — e o detalhe traz a conta inteira.

A soma sai pronta do banco (`vendas_recentes_por_lote`), uma linha por lote,
com `GROUP BY`. Buscar venda a venda e somar no Python custaria caro e subiria
centenas de linhas que ninguém lê. E só os itens **com motivo** recebem o
cruzamento: quem bate não gera pergunta, e pendurar venda em 700 lotes certos
engorda o `farmacia/inventario` à toa.

Junto vai `semReceita`: quantas dessas vendas **não têm linha** em
`VENDAS_PSICOTROPICOS`. Vale lembrar o limite dessa contagem, que está
explicado acima — faltar a linha prova que a receita não foi lançada, existir
não prova nada. Por isso o app só alerta no sentido que vale.

### Chave repetida num dicionário

Escrevendo a consulta acima, dei a ela um nome que **já existia** em
`CONSULTAS`. O Python fica com a última e não reclama: a minha sumiu sem
aviso. Se tivesse vindo depois, teria substituído a consulta que apura as
baixas por lote — e o erro apareceria como saldo errado, semanas depois, sem
nenhuma ligação visível com a causa.

O `teste_agente.py` passou a ler o **código-fonte** com `ast` e recusar
chave repetida em qualquer dicionário do agente. Tem que ser no fonte: no
dicionário já construído a duplicata não existe mais, não há o que testar.

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

Por isso a tarefa de cada minuto publica um `diagnostico` em
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

### O app carimba a própria versão

Três vezes na mesma semana a pergunta foi: *"o celular já pegou a versão
nova?"*. E a única forma de responder era procurar na tela uma frase que eu
tinha mudado no texto — arqueologia, não engenharia.

O service worker é **cache-first** de propósito: o app abre offline e continua
funcionando no balcão sem sinal. O preço é que o aparelho serve a casca antiga
até trocá-la, e quem olha a tela não tem como saber qual está na mão.

Agora o cabeçalho mostra `Conferindo: jefferson · v25`. Uma olhada responde.

A versão vive em `app.js` (`VERSAO_APP`) e em `sw.js` (`VERSAO`), e o
`teste-fumaca.js` cobra que sejam a mesma. Sem isso o carimbo mentiria
justamente sobre o que existe para responder: diria "v25" servindo a casca da
v24. Verifiquei que o teste falha quando as duas divergem.

Para forçar a troca no celular, quando ela não vier sozinha: abrir o endereço
com `?v=` e um número novo no fim. A consulta não casa com nada no cache, então
o navegador busca da rede.

### A lista de prateleira diz o que procurar

A farmácia leu o `--tarefas`, escolheu um item e teve que perguntar qual era
o código. A seção "CONFERIR NA PRATELEIRA" mandava conferir sem dizer **o
que** procurar: só descrição e lote, sem código nem registro M.S. — que é
justamente o que se digita no Digifarma e no site da ANVISA.

Cada linha ganhou uma segunda com `cód.` e `M.S.`.

E ganhou uma coisa que a lista escondia. Quando dois lotes do **mesmo
medicamento** aparecem com diferenças que se anulam, não falta nem sobra
nada:

```
ESCITALOPRAM 10MG   lote 2509242   Digifarma 0   SNGPC 4   dif -4
ESCITALOPRAM 10MG   lote 2529244   Digifarma 5   SNGPC 1   dif +4
```

Cinco de um lado, cinco do outro. São **4 caixas registradas no lote
errado** — e a conferência certa é *ler o lote impresso na caixa*, não
contar quantidade. Contar não resolve: o total já está certo.

A lista agora diz isso na cara: `TROCA DE LOTE com 2529244: a soma bate,
confira o lote impresso`. Sem o aviso, o relatório manda fazer a conferência
que não responde nada — e a pessoa volta da prateleira com o mesmo número e
nenhuma conclusão.

### Zerar não é o conserto quando a ANVISA ainda tem

Em 18/08/2026 a farmácia conferiu a prateleira, achou vazia, e zerou três
lotes de DUAL. Certo: a ANVISA também estava zerada, e os dois lados ficaram
em 0.

O item seguinte da lista parecia igual e não era:

```
DERMOBAN   lote "26 111"   Digifarma 2   SNGPC 0      (com espaço)
DERMOBAN   lote "26111"    Digifarma 0   SNGPC 2      (sem espaço)
```

**Mesmo lote, escrito de dois jeitos.** A ANVISA tem as 2 unidades, só que
sob a outra grafia. Zerar o lado de cá não resolveria nada: o ajuste é
**interno** — não vira movimento e não sobe ao SNGPC — então o site
continuaria acreditando que a farmácia guarda 2 unidades de um controlado
que ela não tem. A divergência mudaria de sinal, não desapareceria.

Quando a prateleira está vazia e a ANVISA tem saldo, o conserto é **perda
escriturada** no Digifarma, que é transmitida.

O agente passou a recusar essa zeragem, com a mensagem dizendo o porquê. A
conferência normaliza o lote da mesma forma frouxa que a comparação
(maiúsculas, sem espaços), senão ela erraria exatamente no caso que existe
para pegar. E quando o M.S. tem saldo na ANVISA em **outro** lote, a
zeragem passa mas fica registrada no log — pode ser grafia diferente, pode
ser lote irmão legítimo, e só quem está na farmácia sabe.

Falhar ao ler o inventário **não** trava a correção: este aviso é rede a
mais, não a única.

### O login do site: a resposta que fechou a pergunta

A medição do `--login-sngpc` respondeu: **e-mail, senha e CPF do responsável
estão todos preenchidos** na tabela `SNGPC`. Então o `Anvisa.exe` tem as
credenciais e mesmo assim para.

O `CPF_RESPONSAVEL_SNGPC` ao lado do e-mail e da senha aponta para o login
pelo **gov.br**, que é como o SNGPC autentica. E o gov.br costuma exigir
segundo fator — código no aplicativo ou SMS. Se for isso, **nenhum programa
faz esse login sozinho**: nem o `Anvisa.exe`, nem nada que se escreva aqui.
É desenho do governo, não limitação do Digifarma.

Uma observação separa as duas hipóteses, e não precisa do servidor: **quando
a janela abre, os campos já vêm preenchidos?** Preenchidos e parando num
código, o passo humano é obrigatório e a busca acaba. Em branco, o programa
não usa o que a própria tabela dele guarda — e aí é chamado no Digifarma,
com a evidência na mão.

Enquanto isso, o objetivo mudou: não é automatizar o login, é **tornar o
passo humano barato**. Quem está no balcão aperta um botão no celular de
quem cuida do SNGPC, a janela abre na tela do servidor, e alguém entra.

`--log-anvisa` (botão **Log do Anvisa.exe**) completa isso: mostra o fim do
`anvisa.log` e a data em que ele foi escrito pela última vez. Era o
`DIAGNOSTICO_ANVISA.bat` que lia esse arquivo, no servidor — sem acesso à
máquina, "onde ele parou?" ficaria sem resposta, e é justamente a pergunta
que separa problema do programa, do login, e de simplesmente não ter rodado.
Quando o log termina em *aguardando login*, ele diz isso em português, para
poupar a leitura.

### Quando o servidor deixa de ser alcançável

Em 19/08/2026 a farmácia perdeu o acesso à máquina. Daí em diante, tudo pelo
app.

Isso obrigou a revisar uma decisão que estava certa e passou a estar errada:
**ligar a escrita no Digifarma só no servidor**. A intenção era boa — ato
deliberado, presencial, longe do celular de balcão. Mas trava que ninguém
consegue desarmar não protege, impede: as duas operações que corrigem
estoque ficariam mortas para sempre.

O que a torna aceitável de longe é o **prazo**. A liberação agora vence
sozinha em uma hora. O pior caso deixa de ser "ficou aberto por dias" — que
foi o que realmente aconteceu aqui — e passa a ser "ficou aberto até a hora
do almoço". Esquecer de desligar deixou de ser uma categoria de erro.

Quatro cuidados no prazo, todos com teste:

- configuração antiga, ligada no servidor **sem** prazo, continua valendo:
  esta mudança não podia desligar quem já estava trabalhando;
- prazo ilegível cai no caso "sem prazo", nem liberado para sempre nem
  fechado — quem gravou aquilo foi o próprio agente;
- desligar **apaga** o prazo, senão ele reapareceria na leitura seguinte;
- vencido, o recado diz **quando** venceu e como liberar de novo.

Junto foi o `arrumar_tarefa_anvisa`: recriar a tarefa do `Anvisa.exe` no nome
de quem usa a máquina só existia no `AGENDAR_ANVISA.bat`, rodado no servidor.
Sem isso o programa ficaria travado para sempre — a tarefa pertence ao
administrador que a criou, e com `/IT` o Windows só abre janela na sessão do
dono. O agente roda como SYSTEM, então tem permissão para recriá-la; o nome
vem de quem está conectado, que é justamente quem precisa ver a janela.

**O que continua exigindo alguém na máquina**, e não vai mudar: a troca da
chave do Firebase (o arquivo precisa chegar ao disco), o login no site do
SNGPC, e as telas do Digifarma — transmitir e lançar perda.

### Mexer no servidor: um arquivo, não uma lista de comandos

A farmácia não fica no servidor o dia todo. Quando fica, o que atrapalha é
descobrir um comando de cada vez, no meio do expediente, com o balcão
esperando.

`SERVIDOR_AGORA.bat` é a lista da vez num arquivo só — e **um arquivo só**
mesmo: ele baixa sozinho os outros `.bat` de que precisa. Quem está no
servidor não tem que saber que existem.

Roda a lista inteira **sem perguntar nada**. A versão anterior pedia S/N a
cada passo, e a farmácia pediu que fizesse tudo automaticamente: quem está
lá quer terminar, não decidir. Passo que falha não derruba os seguintes, e
tudo vai para um log com data.

Ele **só para uma vez**, na troca da chave, e só quando a máquina não tem o
`gcloud` — ali o Google exige que uma pessoa autorize o download. Não é
teimosia do script.

No fim lista **o que só uma pessoa pode fazer**, com o motivo de cada um,
porque essa parte não some por ser ignorada.

A lista do dia vem junto com o arquivo: para o próximo, basta baixá-lo de
novo.

#### A troca da chave sem `gcloud` ficou quase automática

O único passo que **precisa** de gente é o download — o Google exige que
alguém autorize. O resto o `.bat` faz: abre a página certa, espera, procura
o arquivo baixado em Downloads, na Área de Trabalho e na pasta do agente,
confere que é mesmo uma chave **daquela conta de serviço**, recusa se for
outro `.json` qualquer, recusa se for a mesma chave que já está em uso,
guarda a atual, troca, testa, apaga o arquivo baixado — e no fim cobra em
voz alta o passo que mais importa e que se esquece: **apagar a chave antiga
no console**, dizendo o ID dela.

Se o teste falhar, devolve a anterior. O agente nunca fica sem chave boa.

Quem faz isso costuma estar por acesso remoto, às vezes guiando outra pessoa
por telefone. Cada passo manual a menos é um erro a menos.

### Trocar a chave do Firebase

A chave de administrador saiu do servidor dentro de um `.rar`, duas vezes.
Ela ignora todas as regras do banco.

`TROCAR_CHAVE_FIREBASE.bat` gera a nova, **testa**, e só então apaga a velha
no Google. Se o teste falhar, a antiga volta e a nova é apagada — o agente
nunca fica sem chave boa.

Três decisões que valem explicar:

**Quem troca é a conta Google da pessoa, não a chave do agente.** A chave não
pode trocar a si mesma: para isso precisaria de permissão para criar e apagar
chaves, e aí uma chave vazada poderia gerar novas para sempre. O `gcloud`
autentica a pessoa uma vez e a rotação passa a ser um comando.

**Apagar a velha é o passo que importa.** Gerar uma chave nova não desativa
nada: as duas valem até a antiga ser removida. Um script de rotação que só
gera dá a sensação de segurança sem a segurança.

**Sem `gcloud`, ele não finge.** Diz o que falta, abre a página do console e
lista os três passos manuais — incluindo o de apagar a antiga, que é o que
se esquece.

O backup da chave anterior fica na pasta com carimbo de data. É uma chave
válida até o momento da revogação: guardar fora do servidor ou apagar.

### O que dá e o que não dá para fazer de longe

A pergunta veio direta — *"teria como fazer sem acessar o servidor?"* — e a
resposta honesta é item por item.

**Já era remoto:** atualizar o agente e as regras, sincronizar, todos os
relatórios, os ajustes de leitura, e as duas operações que escrevem no
Digifarma.

**Passou a ser:** *desligar* a escrita. De mão única — o app fecha a porta,
nunca abre. Ligar continua sendo ato local, porque é a direção perigosa.

A assimetria resolve um problema que aconteceu: a escrita foi liberada num
dia em que havia alguém no servidor, e no dia seguinte não havia mais. Ficou
ligada, com os botões que gravam vivos num celular que fica no balcão. **Uma
trava que não dá para desarmar de longe acaba ficando armada.**

**Não dá, e não vai dar:**

*A troca da chave do Firebase.* O arquivo novo precisa chegar ao disco do
servidor, e todo caminho remoto para isso é pior que o problema: ou o agente
busca a chave de algum lugar — e esse lugar vira o novo vazamento —, ou a
chave ganha permissão de criar chaves, e aí uma chave vazada se renova
sozinha para sempre. Continua sendo `TROCAR_CHAVE_FIREBASE.bat`, no servidor.

*O login do `Anvisa.exe`.* Ele é automação de navegador e para na tela de
login do site do SNGPC — por desenho da ANVISA, não do Digifarma. Precisa de
alguém na máquina.

*Transmitir o envio e lançar perda.* São telas do Digifarma. O projeto lê o
banco dele; operar o sistema é outra coisa.

### Modo pronto sem botão: o erro que eu cometi duas vezes

Primeiro foi "Colunas da tabela". Depois "Apuração do saldo". Nos dois casos
eu mandei a farmácia usar um botão que não existia: o modo estava pronto no
agente, entrava em `RELATORIOS`, tinha nome em `ROTULO_PEDIDO` — e não havia
como pedir pela tela. A pessoa procura, não acha, e volta perguntando.

É invariante, e invariante se cobra em teste. O `teste_agente.py` passou a
ler o `index.html` e o `app.js` e exigir que **toda ação de `RELATORIOS`
tenha um `data-pedir` ou uma chamada a `pedirRelatorio`**. E o contrário
também: nenhum botão pode pedir ação que o agente não atende — esse erra
mais calado ainda, porque o pedido sobe ao Firebase e morre lá.

Verifiquei que o teste falha quando o botão é removido.

O que o botão faz, agora que existe: `--saldo TEXTO` abre a conta lote a
lote — as linhas cruas do Digifarma, a soma de cada coluna candidata, o que
foi baixado em venda e perda, e o que a ANVISA tem do mesmo lote. É o
relatório que responde quando os dois lados falam de lotes com números
diferentes.

### Duas datas para a mesma transmissão, de novo — agora resolvida

Já tinha aparecido, e voltou noutro lugar. A farmácia abriu o **Relatório
Status de Transmissão** ao lado da aba Aceites e não conseguiu casar linha
com linha:

| | |
|---|---|
| o site dizia | `Data Inicial 17/08 · Data Final 18/08` |
| o app dizia | `Envio de 19/08/2026` |

**É a mesma transmissão.** O XML foi gerado e arquivado no dia 19, cobrindo o
movimento dos dias 17 e 18. As duas datas estão certas e nomeiam coisas
diferentes.

O app listava os XMLs de `enviados/` e tirava o título do **nome do
arquivo** — que carrega a data em que o agente arquivou. Esse número não
aparece em lugar nenhum do site, então não havia por onde casar.

Agora o agente lê o cabeçalho de cada XML arquivado e publica o período em
`periodosDeEnvio`. O título da linha passa a ser **`Movimentos de 17/08 a
18/08`**, igual ao site, e a data do arquivo desce para a segunda linha, onde
serve de referência sem confundir.

A chave do aceite continua sendo a data do arquivo: é o que já está gravado
em `farmacia/aceites`, e trocá-la órfãaria os aceites que a farmácia já
marcou. O que mudou é só o rótulo — e o rótulo é o que a pessoa lê.

Só os 20 arquivos mais recentes são abertos a cada sincronização. Ler 60
XMLs de hora em hora custaria caro para responder sobre aceite que foi
marcado há meses.

E fica dito na tela o que o episódio ensinou duas vezes: **XML arquivado não
é prova de transmissão.** Só o site responde isso.

### Abrir o Anvisa.exe pelo app, e o que isso não resolve

A farmácia pediu para abrir o `Anvisa.exe` de dentro do app. Dá — com um
limite que precisa estar escrito: **abrir, sim; logar, não.** O programa para
na tela de login do site do SNGPC, e isso é desenho da ANVISA. O que o botão
resolve é o "não tem ninguém que saiba abrir o programa", que é um problema
real quando quem está na loja não é quem cuida do servidor.

E há uma armadilha do Windows no caminho. O agente roda como **SYSTEM**, numa
tarefa agendada. Programa aberto por SYSTEM nasce na **sessão 0**, isolada do
desktop desde o Windows Vista: a janela existe e ninguém vê. Para um programa
que *para esperando alguém*, isso significaria processo pendurado para
sempre — que é exatamente como o `Anvisa.exe` já apareceu quebrado aqui.

Por isso quem abre não é o agente: é a tarefa `AnvisaSNGPC_Login`, criada
pelo `AGENDAR_ANVISA.bat` com `/IT`. Ela roda como o usuário conectado, na
sessão dele. O agente só dispara com `schtasks /Run`.

Se não houver ninguém conectado no servidor, ela não roda — e **isso é a
resposta certa, não um erro**. O app diz isso, em vez de fingir que abriu.

Duas coisas que o botão faz antes de responder:

- **confere se já está aberto.** Cópia pendurada é a causa nº 1 de "o
  Anvisa.exe não abre", e abrir outra em cima só piora;
- **espera o processo aparecer** antes de dar a resposta. Sem isso o recado
  seria sempre "mandei abrir", que não informa nada a quem está longe.

### O servidor sem ninguém conectado explica o inventário velho

Na primeira vez que a farmácia apertou "Abrir o Anvisa.exe", o app respondeu
que o programa não apareceu na lista de processos e que *"o mais provável é
não haver ninguém conectado"*.

Provável não serve. É um recado lido a quilômetros do servidor, e as duas
hipóteses levam a consertos opostos — mexer no login automático do Windows,
ou investigar o programa. O agente passou a **perguntar**, com `quser` e,
onde ele não existe, `query session`.

A resposta muda o que se faz, e por isso são três recados diferentes:

| O que o Windows diz | O que o app responde |
|---|---|
| ninguém conectado | é falta de sessão — e o conserto é o `netplwiz` |
| alguém conectado | então não é sessão: rode o `DIAGNOSTICO_ANVISA.bat` |
| não deu para perguntar | diz que não sabe, em vez de chutar |

A tarefa diária `AnvisaSNGPC_Login` é criada com `/IT`: **só roda com usuário
na sessão**. Com o servidor na tela de bloqueio ela não roda — silenciosamente,
todo dia. Era a explicação mais provável para o inventário viver velho.

**Não era essa.** A farmácia respondeu que o servidor entra sozinho, sem pedir
senha: existe sessão. E é aí que a resposta fica interessante, porque sobra a
causa que ninguém procura.

#### Tarefa com `/IT` só abre janela para o dono dela

O `AGENDAR_ANVISA.bat` é rodado **como administrador** — está escrito no
próprio arquivo, porque criar tarefa exige. Então a tarefa nasce pertencendo
ao administrador. Mas quem entra sozinho na máquina, pelo login automático, é
a conta do balcão.

Com `/IT`, o Windows abre a janela **na sessão do dono da tarefa**. Se o dono
não está na tela, ele obedece o comando, não abre nada, e **não reporta erro
nenhum** — `schtasks /Run` devolve sucesso. Do lado de fora é indistinguível
de "funcionou".

Por isso o agente passou a comparar os dois nomes: o dono da tarefa
(`schtasks /Query /V`) e quem está na sessão (`quser`). Quando diferem, ele
diz isso e diz o conserto — recriar a tarefa logado como a conta que
realmente usa a máquina.

Comparar nomes de usuário do Windows tem duas pegadinhas, e as duas fariam o
agente acusar troca onde não há: o domínio (`DROGARIA\\jefferson` e
`jefferson` são a mesma pessoa) e a caixa. E os rótulos do `schtasks` mudam
com o idioma — `Run As User` vira `Executar como usuário`. Os casos estão no
teste.

Ler a sessão parece trivial e não é. O parser tem que ignorar a linha de
`services`, não confundir sessão **desconectada** com conectada, e entender
o Windows em português — `Ativo` no lugar de `Active`. Os quatro casos estão
no `teste_agente.py`, com a saída real do `quser`.

### A lista de ações conhecidas vem do código

O teste que cobra "todo botão tem ação e toda ação tem botão" começou com uma
lista fixa das ações válidas. Ao acrescentar o `anvisa`, ele acusou — certo —
e a correção óbvia seria escrever `'anvisa'` na lista.

Seria trocar um problema por outro mais silencioso: lista fixa apodrece, e
a partir daí o teste mente no sentido contrário, deixando passar botão órfão
porque alguém esqueceu de atualizá-la. Agora as ações são lidas do corpo do
`atender_pedido`. Confirmei removendo o `anvisa` do agente: o teste acusa o
botão órfão.

### O que a verificação de 19/08 encontrou

Uma varredura do projeto inteiro depois da semana de mudanças. Três achados,
todos meus e todos silenciosos:

**Dois parsers para a mesma saída.** `sessao_interativa()` e
`usuario_conectado()` liam o `quser` com lógicas parecidas — uma tratava o
`>` da própria sessão, a outra não — e cada uma chamava o Windows por conta
própria. Duas lógicas parecidas divergem; agora há um `ler_sessoes()` só, e
as duas o usam.

**A cobertura das regras do Firebase valia só para metade.** O teste
conferia as ações de `RELATORIOS` contra `regras-firebase.json`, mas ações
como `anvisa`, `zerar_negativos` e `ajustar_lote` são despachadas fora dele.
Ação nova esquecida na regra é **o erro mais silencioso desta dupla**: o
botão aparece, o clique funciona, e o Firebase recusa a escrita sem que nada
no servidor fique sabendo. Agora o teste lê as ações do `index.html` e do
`app.js` — todas — e faz o mesmo com as chaves de configuração. Confirmei
removendo `anvisa` da regra: acusa.

**O refactor apagou uma função junto.** Ao unificar os parsers, o
`so_usuario()` foi no meio do trecho substituído. O teste que compara dono
da tarefa com quem está na tela quebrou na hora — que é exatamente o que
teste serve para fazer.

Também entrou o que faltava: `abrir_anvisa()` passou a ser testado de ponta
a ponta, nos seis cenários. É o caminho que a farmácia usa de longe, e cada
resposta dele manda mexer num lugar diferente do servidor — dar o recado
errado ali custa uma viagem.

O que foi varrido e está limpo: código morto (nenhum), os oito `.bat` e
`.vbs` contra a armadilha do parêntese, os arquivos que o `SERVIDOR_AGORA`
baixa, as flags do agente, e a versão do `app.js` contra a do `sw.js`.

### "21 movimentos" não responde nada

A aba Situação dizia quantos movimentos aguardavam transmissão e parava aí.
A farmácia perguntou o óbvio: **quais?** Saber o número não ajuda a decidir
nada — a pergunta real é se o próximo envio cobre o período certo, e qual
venda está faltando quando a ANVISA acusa saldo diferente.

`--pendentes` (botão **O que falta transmitir**) lista por tipo e por dia:
número da venda, hora, produto, lote e quantidade, com o total de cada dia —
que é o número que se compara com a tela do Digifarma. E mostra os ponteiros
em cima, porque é por eles que a conta é feita, não por data.

Quando não há nada pendente ele diz mais do que "nada": se a ANVISA ainda
mostra saldo diferente e o Digifarma não tem o que transmitir, o problema
não é falta de envio — é envio que não foi aceito, e isso se confere no
Relatório Status de Transmissão.

### O ritmo: a venda do dia sobe no dia seguinte

Regra do negócio que a farmácia contou e que o app não sabia. **O número de
"aguardando transmissão" quase nunca é zero, e não deveria ser** — as vendas
de hoje ficam ali até amanhã, por funcionamento normal.

Sem isso, todo fim de tarde a tela mostra pendência crescente e parece
problema. E, pior, o problema de verdade fica escondido no meio: movimento de
**antes de ontem** ainda parado não é ritmo, é envio que não aconteceu — e é
exatamente isso que explica divergência de saldo contra a ANVISA.

O `--pendentes` marca cada dia: `sobe amanhã`, `sobe hoje`, ou **`ATRASADO`**.
E abre com a contagem do que passou do prazo, que é o único número que pede
ação. A nota da aba Situação passou a dizer o mesmo, para o contador ali
parar de assustar.

### O login do SNGPC: a pergunta antes da automação

A farmácia sugeriu que o programa fizesse o login no site sozinho. A
resposta útil não era automatizar o site por fora — era descobrir se o
**próprio Digifarma já sabe entrar e só não está usando**.

A tabela `SNGPC` tem colunas de e-mail e senha. Se estiverem vazias, é a
explicação mais simples para o `Anvisa.exe` parar esperando alguém digitar,
e o conserto é preenchê-las na configuração do Digifarma — não escrever
credencial pela porta dos fundos.

`--login-sngpc` (botão **Login do SNGPC**) responde isso e **nunca imprime o
valor**: diz preenchido ou vazio, que é o que decide o próximo passo. É a
mesma lição do dia em que o diagnóstico publicou `EMAIL` e `SENHA` no
Firebase sem ninguém notar.

Se estiver tudo preenchido e o programa ainda parar, aí a conclusão é outra:
ou o site exige algo que não se automatiza — um código de imagem, por
exemplo —, ou o `Anvisa.exe` não usa o que a própria tabela dele guarda. A
segunda é pergunta para o suporte do Digifarma, com evidência na mão.

## Testes

**Os dois, sempre.** São suítes separadas porque são linguagens separadas, e
rodar só uma é como conferir metade da farmácia:

```
python agente/teste_agente.py   agente: XML, cruzamento, saldos, arquivamento
node teste-fumaca.js .          app: sintaxe, ids, manifest, service worker
```

Isso não é conselho de manual. Em 18/08/2026 uma varredura do projeto inteiro
achou o `teste-fumaca.js` **falhando** — e falhando havia tempo, porque só a
suíte do agente vinha sendo rodada. O caso era o inverso do que parece: o
**teste** estava velho, não o código. Ele ainda cobrava a regra antiga de
"pendência de cadastro" (pelo motivo do item), e o código já usava a regra
nova (pelo M.S. em falta) — mudada por causa da amoxicilina da Cimed, que
passou meses sem escrituração justamente por causa disso.

Um teste que ninguém roda não protege nada; e um teste velho que ninguém roda
mente sobre o código quando alguém finalmente o executa.
