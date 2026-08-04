# Spec — Casca do sistema + Módulo Estoque

**Data:** 17/07/2026
**Status:** aguardando revisão
**Sub-projeto:** 1 de 4

---

## 1. Objetivo

Entregar a casca do sistema (login, menu, sincronização, offline) e o primeiro
módulo funcionando de ponta a ponta: **Estoque**.

Não é o sistema inteiro. Os módulos Farmácia, Receituário, Administração e
Dashboard têm specs próprias, depois desta.

---

## 2. Decisões já tomadas

| Decisão | Escolha | Por quê |
| --- | --- | --- |
| Plataforma | PWA único (Windows, Linux, Android, iOS, Web) | Já existe e funciona; é a única opção que roda no celular sem virar app nativo |
| Banco | Firebase Realtime Database | Já em uso; o agente fala REST com ele em duas linhas |
| Organização | Opção A — um app, abas isoladas | Preserva os Prompts 4 e 5 (Administração e Dashboard) |
| Estoque | 100% digitado à mão | Definição do dono do projeto |
| Fonte do dado | Estoque **não** conhece Digifarma nem ANVISA | Definição do dono do projeto |
| Aba SNGPC | **Sai** do Estoque, vai para o Farmácia | É alimentada pelo Digifarma/ANVISA, logo não é Estoque |
| Transferências (Prompt 3) | **Cortado** | Só faz sentido com duas lojas ou dois depósitos (YAGNI) |
| Agente local | **Não usado** neste módulo | Nada é importado aqui |

### O que "isolado" significa, exatamente

Os três módulos não leem os dados uns dos outros. Nenhum código do Estoque
importa código do Farmácia ou do Receituário. As duas únicas coisas
compartilhadas são:

1. **O login** — um usuário, válido para os três (Prompt 4).
2. **O Dashboard** — lê os três **somente para exibir número em tela** (Prompt 5).
   Leitura, nunca escrita.

Teste prático: apagar a pasta de um módulo não pode quebrar os outros dois.

---

## 3. Arquitetura

```
        CELULAR / PC / TABLET                  PC DA FARMÁCIA
     ┌──────────────────────────┐         ┌──────────────────────┐
     │   PWA (o app)            │         │   Agente local       │
     │   ┌──────────────────┐   │         │   (Windows)          │
     │   │ Dashboard        │   │         │                      │
     │   │ Receituário      │   │         │  Firebird Digifarma  │
     │   │ Farmácia         │   │         │  XML da ANVISA       │
     │   │ Estoque   ◄──────┼───┼─┐       │  Playwright          │
     │   │ Administração    │   │ │       └──────────┬───────────┘
     │   └──────────────────┘   │ │                  │
     │   Service worker (fila)  │ │                  │ só escreve em
     └────────────┬─────────────┘ │                  │ /farmacia
                  │               │                  │
                  ▼               │                  ▼
     ┌────────────────────────────┴──────────────────────────────┐
     │                 FIREBASE (Auth + Realtime DB)             │
     │   /estoque      /farmacia      /receituario     /admin    │
     │   (este spec)   (spec 2)       (spec 3)         (spec 4)  │
     └───────────────────────────────────────────────────────────┘
```

O agente **não aparece neste sub-projeto**. Está no desenho só para deixar claro
que ele escreve em `/farmacia` e nunca em `/estoque`.

### Estrutura do repositório

O Prompt 8 pedia `backend/`, `frontend/`, `mobile/`, `api/`, `database/`,
`docker-compose.yml`. Estou propondo diferente, e explico:

- **`backend/`, `api/`, `database/`, `docker-compose.yml` não existem** — o
  Firebase é o backend, a API e o banco. Criar essas pastas vazias é mentira no
  repositório.
- **`mobile/` não existe** — o PWA *é* o mobile. Uma pasta `mobile/` sugere um
  app nativo que não vamos construir.

Estrutura real:

```
/
├── app/                    o PWA
│   ├── index.html
│   ├── manifest.json
│   ├── sw.js               service worker
│   ├── core/               login, sync, fila offline, layout (compartilhado)
│   └── modulos/
│       ├── estoque/        este spec
│       ├── farmacia/       spec 2
│       ├── receituario/    spec 3
│       ├── admin/          spec 4
│       └── dashboard/      spec 4
├── agente/                 o que roda no PC da farmácia (spec 2)
├── firebase/
│   └── database.rules.json as regras de segurança
├── docs/
│   ├── specs/
│   └── plans/
├── tests/
├── .github/
│   ├── workflows/          CI
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── README.md
├── CHANGELOG.md
└── LICENSE
```

Regra de isolamento: `modulos/estoque/` pode importar de `core/`. Não pode
importar de `modulos/farmacia/` nem de `modulos/receituario/`. O CI vai barrar
isso.

---

## 4. Segurança — o que está errado hoje

Isto é a Tarefa 1. Nada de novo entra antes.

### 4.1 As senhas estão no código-fonte

```js
let SENHAS={Jefferson:"2407",Marconi:"9876",Marcelo:"1991",Eliara:"1234",Anderson:"1010"};
```

Qualquer pessoa que abra o código-fonte da página lê as cinco senhas. E o login
é só um `if` em JavaScript — quem sabe a URL do banco escreve nele sem senha
nenhuma, porque as regras estão liberadas.

**Correção:** Firebase Authentication. O usuário digita só a senha, como hoje;
por baixo, cada pessoa vira uma conta de verdade (e-mail interno + senha), e as
regras do banco passam a exigir login. A senha sai do código.

### 4.2 As regras do banco

```json
{
  "rules": {
    "estoque": {
      ".read":  "auth != null",
      "meds":   { ".write": "auth != null && root.child('admin/usuarios').child(auth.uid).child('estoque_escrita').val() === true" },
      "movs":   { ".write": "auth != null" },
      "logs":   { ".write": "auth != null", ".read": "root.child('admin/usuarios').child(auth.uid).child('adm').val() === true" }
    },
    "farmacia":    { ".read": "auth != null", ".write": false },
    "receituario": { ".read": "auth != null", ".write": "auth != null" },
    "admin":       { ".read": "auth != null", ".write": "root.child('admin/usuarios').child(auth.uid).child('adm').val() === true" }
  }
}
```

Eliara e Anderson são `somenteVer` hoje — isso passa a ser regra no servidor, não
só botão escondido na tela.

As regras acima leem `/admin/usuarios`, que é do spec 4. Para não travar um no
outro, **este spec cria só o nó mínimo** — `/admin/usuarios/{uid} = {nome, adm,
estoque_escrita}` — preenchido à mão no console do Firebase para as cinco pessoas
que já usam. A tela de cadastro de usuários fica no spec 4.

### 4.3 O `masterkey` do agente

O `SNGPC_Sync.vbs` tem `PASS = "masterkey"` em texto puro. Ele escreve em
`/farmacia`, então entra na spec 2 — mas fica registrado aqui: **enquanto ele
existir assim, o banco tem uma porta aberta**, e isso afeta o Estoque também.

---

## 5. Modelo de dados

### Hoje

```js
{id:"a01", n:"ALPRAZOLAM 0,25MG", q:1, v:"12/27"}
```

Um medicamento, uma quantidade, uma validade. Não dá para ter dois lotes do
mesmo remédio com validades diferentes — que é o caso normal.

### Proposto

```
/estoque
  /meds/{medId}
      nome          "ALPRAZOLAM 0,25MG"
      codigo        "A01"
      barras        "7891234567890"
      lab           "EMS"
      local         "Armário 2 / Prateleira B"
      minimo        2
      ativo         true
  /lotes/{loteId}
      medId         "a01"
      lote          "L2207"
      validade      "2027-12-31"
      qtd           14
  /movs/{movId}
      medId, loteId
      tipo          "entrada" | "saida" | "ajuste" | "inventario"
      qtd           -2
      resp          uid do usuário
      quando        timestamp do servidor
      obs           "conferência mensal"
  /logs/{logId}
```

**A quantidade mora no lote, nunca no medicamento.** O total do medicamento é a
soma dos lotes — calculado na tela, nunca gravado. Número gravado em dois lugares
é número que vai divergir.

### Migração

Os 34 itens do `DEFAULTS` viram 34 medicamentos + 34 lotes (validade `v:"12/27"`
→ `2027-12-31`, último dia do mês). Lote fica `"—"` até alguém conferir. Script
roda uma vez, com backup antes.

---

## 6. O módulo Estoque

### Telas

1. **Lista** — medicamentos com total (soma dos lotes), busca no topo, filtros
   rápidos (todos / baixo / vencendo / vencido).
2. **Medicamento** — cadastro + lotes + histórico daquele item.
3. **Movimento** — entrada, saída, ajuste. Escolhe o lote; ajuste exige motivo.
4. **Inventário** — lista para contagem; digita o contado, o app mostra a
   diferença e gera os ajustes de uma vez.
5. **Histórico** — todos os movimentos, filtro por período, pessoa e tipo.

### Busca

Nome, lote, código e código de barras. No celular, **lendo o código com a
câmera** (`BarcodeDetector`, com fallback digitado no iOS antigo).

### Alertas

| Alerta | Regra |
| --- | --- |
| Estoque baixo | soma dos lotes ≤ `minimo` |
| Vencendo | validade dentro de N dias (N configurável, padrão 90) |
| Vencido | validade < hoje |

Vencido **não** some da lista: fica marcado em vermelho, porque ele existe
fisicamente no armário e tem que ser baixado, não escondido.

### Permissões

| Papel | Pode |
| --- | --- |
| Administrador | tudo |
| Operador | movimento e inventário; não mexe no cadastro |
| Somente ver | só olha |

---

## 7. Sincronização e offline

### O problema de hoje

```js
set(REF,{meds,movs,users,logs})
```

Reescreve o banco inteiro a cada ação. Dois lançamentos ao mesmo tempo: o último
apaga o primeiro, sem erro em tela.

### Correção

- Movimento → `push()` (cada um com chave própria; nunca colidem).
- Quantidade do lote → `transaction()` (soma incremental, não substituição).
- Cadastro → `update()` só nos campos mudados.
- Nunca mais `set()` na raiz do módulo.

### Offline

- **Service worker** cacheia a casca do app: abre sem internet (hoje abre em
  branco).
- **Fila local** (IndexedDB): movimento feito offline entra na fila, a tela
  mostra "pendente", e sobe sozinho quando a conexão volta.
- **Cadastro offline é só leitura** — criar medicamento exige estar online.
  Evita dois cadastros do mesmo remédio criados em dois celulares desconectados.
- O indicador `✅ Ao vivo / ❌ Offline` que já existe ganha um terceiro estado:
  `⏳ N pendentes`.

---

## 8. LGPD

O Estoque não guarda dado de paciente — guarda medicamento e nome de
funcionário. O risco pesado (CPF dos 525 clientes) está no Receituário, spec 3.
Mas as regras de segurança da seção 4 são pré-requisito para aquele módulo
existir, e por isso elas nascem aqui.

---

## 9. Fora de escopo

Transferências entre lojas · qualquer leitura do Digifarma · a aba SNGPC (vai
para o spec 2) · Dashboard e Administração completos (spec 4) · app nativo ·
leitor de código de barras USB.

---

## 10. Critérios de aceite

1. As senhas não existem no código-fonte; o banco recusa escrita sem login.
2. Dois celulares lançando o mesmo medicamento ao mesmo tempo: os dois
   movimentos aparecem no histórico.
3. Avião ligado, lança uma saída, avião desligado: o movimento sobe sozinho.
4. Um medicamento com dois lotes de validades diferentes aparece com o total
   certo e alerta só do lote que está vencendo.
5. Ler o código de barras com a câmera abre o medicamento certo.
6. Apagar a pasta `modulos/receituario/` não quebra o Estoque.
7. Os 34 itens de hoje aparecem depois da migração, com o mesmo saldo.
