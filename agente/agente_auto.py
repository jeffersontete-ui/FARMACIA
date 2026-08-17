# -*- coding: utf-8 -*-
"""
agente_auto.py — roda no SERVIDOR da farmácia.

Lê o Digifarma (Firebird, C:\\Digifarma\\Dados\\Digifarma6.fdb), cruza com o
XML da última transmissão ao SNGPC e publica o resultado em
farmacia/inventario no Firebase. O app só LÊ; o Digifarma é a verdade e
NUNCA é escrito por aqui — todas as consultas são SELECT.

Modos:
    python agente_auto.py --auto            sincronização completa (de hora em hora)
    python agente_auto.py --fila            atende os botões do app (de 5 em 5 min)
    python agente_auto.py --envio           usa o inventário vigente no último envio
    python agente_auto.py 31/07/2026        usa o inventário daquela data
    python agente_auto.py --schema          confere se as tabelas/campos existem
    python agente_auto.py --saldo TEXTO     mostra como o saldo de um lote foi apurado
    python agente_auto.py --linhas LOTE     despeja todas as colunas de LOTES de um lote
    python agente_auto.py --resumo          separa divergência real de lote escrito diferente
    python agente_auto.py --inventario      mostra o que entra e o que sai do inventário SNGPC
    python agente_auto.py --tarefas         três listas de trabalho, na ordem de resolver
    python agente_auto.py --negativos       abre cada lote negativo e aponta a causa provável
    python agente_auto.py --comparacao      folha de conferência em HTML, para imprimir
    python agente_auto.py --teste           testa conexão com Firebird e Firebase

Não gera .exe. Atualizar o agente = trocar este arquivo.
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import traceback

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_CONFIG = os.path.join(PASTA, 'agente_config.json')
ARQUIVO_LOG = os.path.join(PASTA, 'agente.log')

CONFIG_PADRAO = {
    "banco": r"C:\Digifarma\Dados\Digifarma6.fdb",
    "usuario": "SYSDBA",
    "senha": "masterkey",
    "charset": "WIN1252",
    "pasta_xml": r"C:\Digifarma\Aplicativos\VerificaXML",
    "chave_firebase": os.path.join(PASTA, "chave-firebase.json"),
    "url_banco": "https://estoque-remedios-7b785-default-rtdb.firebaseio.com",
    "uid_agente": "agente-sngpc",
    # Saldo por lote. Em branco, o agente descobre sozinho (veja
    # detectar_coluna_saldo). Se a instalação tiver uma coluna com nome
    # diferente, ou se o agente escolher a errada, fixe aqui:
    #   "coluna_saldo": "QUANTIDADE"
    #   "modo_saldo":   "saldo"      a coluna JÁ é o saldo do lote
    #                   "movimento"  a coluna é a quantidade de cada movimento,
    #                                e o saldo é apurado descontando as baixas
    #                   "auto"       decide pelo nome da coluna
    "coluna_saldo": "",
    "modo_saldo": "auto",
    # ESCRITA no Digifarma, pedida pelo app. Vem desligada: ligar é um ato
    # deliberado, feito no servidor, por quem responde pela farmácia. Sem
    # isto o agente é somente leitura, como sempre foi.
    "permitir_ajuste_estoque": False,
    # Envio feito por OUTRA máquina: a ANVISA recebeu, mas o ponteiro deste
    # Digifarma não avançou e ele continua oferecendo as mesmas vendas como
    # pendentes — o agente desconta duas vezes e infla a divergência.
    # Ponha aqui o número da ÚLTIMA VENDA transmitida e o agente passa a
    # tratar tudo até ela como enviado. Só vale para cima: nunca esconde
    # venda que o próprio Digifarma ainda considera pendente.
    # Volte para 0 quando o ponteiro do Digifarma for acertado.
    "transmitido_ate_venda": 0
}


# ============================================================
# CONSULTAS AO DIGIFARMA
# ============================================================
# Os nomes abaixo saíram dos .sql do próprio VerificaXML
# (pasta sqls\), então são os reais — não são chute:
#   CAB_VENDAS, ITEM_VENDAS, ITEM_VENDAS_LOTES, VENDAS_PSICOTROPICOS,
#   CAB_NOTAS, ITEM_NOTAS, LOTES, PERDAS_PSICOTROPICOS,
#   PRODUTOS, FORNECEDORES, VENDEDORES, SNGPC, CONFIG.
#
# Controlado = PRODUTOS.PSICOTROPICO='S' OU PRODUTOS.ANTIMICROBIANO='S'.
# Venda válida = (VENDA_RECEBIDO + SUBSIDIO + SUBSIDIO_ASSEFAZ) > 0
# e item não cancelado. Entradas ignoram CFOP 1411 e 1202.
# Transferência = saída com CFOP 5150/5151/5152/5155/5409/6409.
#
# INVENTARIO_SNGPC é a tabela que o Anvisa.exe apaga e regrava com o
# inventário lido do site da ANVISA. É o lado "ANVISA" da comparação.
CONSULTAS = {

    # ponteiros do último envio + CNPJ da farmácia + flag de envio por API
    "ponteiros": """
        SELECT S.*, C.CNPJ
          FROM SNGPC S
         CROSS JOIN (SELECT FIRST 1 CNPJ FROM CONFIG) C
    """,

    # --- pendentes de transmissão, pelos PONTEIROS (não por data) ---
    "saidas_pendentes": """
        SELECT C.VENDA_NOTA_ID,
               CAST(C.VENDA_DATA_HORA AS DATE) AS DATA,
               C.VENDA_DATA_HORA AS DATA_HORA,
               P.PRODUTO, P.REGISTRO_MS, P.COD_BARRAS,
               IVL.NUM_LOTE, IVL.QUANTIDADE
          FROM CAB_VENDAS C
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = C.VENDA_NOTA_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          JOIN ITEM_VENDAS_LOTES IVL ON (IVL.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                    AND (IVL.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
                                    AND (IVL.PRODUTO_ID = I.PRODUTO_ID)
         WHERE C.VENDA_NOTA_ID > ?
           AND (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
         ORDER BY C.VENDA_NOTA_ID
    """,

    "entradas_pendentes": """
        SELECT C.CAB_NOTA_ID, C.NOTA_FISCAL, C.DATA_RECEBIMENTO,
               P.PRODUTO, P.REGISTRO_MS, P.COD_BARRAS,
               L.NUM_LOTE, L.QUANTIDADE_COMPRA AS QUANTIDADE
          FROM CAB_NOTAS C
          JOIN ITEM_NOTAS I ON (I.CAB_NOTA_ID = C.CAB_NOTA_ID)
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          LEFT JOIN LOTES L ON ((L.PRODUTO_ID = I.PRODUTO_ID)
                            AND (L.ENTRADA_SAIDA = 'E')
                            AND (L.CAB_NOTA_ID = C.CAB_NOTA_ID)
                            AND ((L.ITEM_NOTA_ID = I.ITEM_NOTA_ID) OR (L.ITEM_NOTA_ID IS NULL)))
         WHERE C.CAB_NOTA_ID > ?
           AND C.ENTRADA_SAIDA = 'E'
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
           AND C.CFOP NOT IN ('1411', '1202')
         ORDER BY C.CAB_NOTA_ID
    """,

    # o ponteiro de perda fica sempre em 0, então aqui o corte é por DATA
    # o LEFT JOIN e o "OR P.PRODUTO_ID IS NULL" são de propósito: perda cujo
    # produto sumiu do cadastro continua sendo perda de controlado, e some
    # da tela se a gente exigir a marcação
    "perdas_pendentes": """
        SELECT PP.PERDA_ID, PP.DATA, PP.LOTE AS NUM_LOTE, PP.QUANTIDADE,
               P.PRODUTO, P.REGISTRO_MS
          FROM PERDAS_PSICOTROPICOS PP
          LEFT JOIN PRODUTOS P ON (P.PRODUTO_ID = PP.PRODUTO_ID)
         WHERE PP.DATA >= ? AND PP.PERDA_ID > ?
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S')
                OR (P.PRODUTO_ID IS NULL))
         ORDER BY PP.PERDA_ID
    """,

    # transferências também ficam com ponteiro em 0
    "transferencias_pendentes": """
        SELECT C.CAB_NOTA_ID, C.DATA_EMISSAO, P.PRODUTO,
               IL.REGISTRO_MS, IL.NUM_LOTE, IL.QUANTIDADE
          FROM CAB_NOTAS C
          LEFT JOIN ITEM_NOTAS I ON (I.CAB_NOTA_ID = C.CAB_NOTA_ID)
          LEFT JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          LEFT JOIN ITEM_VENDAS_LOTES IL ON (IL.CAB_NOTA_ID = I.CAB_NOTA_ID)
                                        AND (IL.ITEM_NOTA_ID = I.ITEM_NOTA_ID)
         WHERE C.CAB_NOTA_ID > ?
           AND C.DATA_EMISSAO >= ?
           AND C.ENTRADA_SAIDA = 'S'
           AND (C.CANCELAMENTO <> 'S')
           AND C.CFOP IN ('5150', '5151', '5152', '5155', '5409', '6409')
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
         ORDER BY C.CAB_NOTA_ID
    """,

    # --- saídas do período do XML, para o cruzamento ---
    "saidas_periodo": """
        SELECT C.VENDA_NOTA_ID AS VENDA,
               CAST(C.VENDA_DATA_HORA AS DATE) AS DATA,
               P.PRODUTO, P.REGISTRO_MS,
               IVL.NUM_LOTE, IVL.QUANTIDADE
          FROM CAB_VENDAS C
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = C.VENDA_NOTA_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          JOIN ITEM_VENDAS_LOTES IVL ON (IVL.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                    AND (IVL.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
                                    AND (IVL.PRODUTO_ID = I.PRODUTO_ID)
         WHERE CAST(C.VENDA_DATA_HORA AS DATE) BETWEEN ? AND ?
           AND (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
    """,

    # --- últimas vendas de controlado, para o acompanhamento ao vivo ---
    # Uma linha por LOTE vendido: a mesma venda pode sair de dois lotes, e
    # é o lote que interessa para o SNGPC.
    "vendas_recentes": """
        SELECT FIRST 300
               C.VENDA_NOTA_ID AS VENDA,
               C.VENDA_DATA_HORA AS QUANDO,
               P.PRODUTO, P.REGISTRO_MS,
               IVL.NUM_LOTE, IVL.QUANTIDADE
          FROM CAB_VENDAS C
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = C.VENDA_NOTA_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          JOIN ITEM_VENDAS_LOTES IVL ON (IVL.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                    AND (IVL.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
                                    AND (IVL.PRODUTO_ID = I.PRODUTO_ID)
         WHERE CAST(C.VENDA_DATA_HORA AS DATE) >= ?
           AND (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
         ORDER BY C.VENDA_NOTA_ID DESC
    """,

    # --- venda AINDA NÃO TRANSMITIDA que vai travar o próximo envio ---
    # Corta pelo ponteiro, não por data: o que interessa é o que ainda vai
    # subir. Venda de controlado sem receita escriturada é a causa clássica
    # de recusa, e depois de transmitida o conserto é bem mais caro.
    "vendas_sem_receita_pendentes": """
        SELECT C.VENDA_NOTA_ID AS VENDA,
               C.VENDA_DATA_HORA AS QUANDO,
               P.PRODUTO, P.REGISTRO_MS,
               IVL.NUM_LOTE, I.ITEMVEND_QUANT AS QUANTIDADE
          FROM CAB_VENDAS C
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = C.VENDA_NOTA_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          LEFT JOIN VENDAS_PSICOTROPICOS VP ON (VP.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                           AND (VP.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
          LEFT JOIN ITEM_VENDAS_LOTES IVL ON (IVL.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                         AND (IVL.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
                                         AND (IVL.PRODUTO_ID = I.PRODUTO_ID)
         WHERE C.VENDA_NOTA_ID > ?
           AND (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
           AND VP.VENDA_NOTA_ID IS NULL
         ORDER BY C.VENDA_NOTA_ID
    """,

    # --- venda de controlado sem receita escriturada ou sem lote ---
    "vendas_problema": """
        SELECT C.VENDA_NOTA_ID AS VENDA,
               CAST(C.VENDA_DATA_HORA AS DATE) AS DATA,
               P.PRODUTO, P.REGISTRO_MS,
               I.ITEMVEND_QUANT AS QUANTIDADE,
               IVL.NUM_LOTE,
               VP.VENDA_NOTA_ID AS RECEITA,
               V.VENDEDOR
          FROM CAB_VENDAS C
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = C.VENDA_NOTA_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
          LEFT JOIN VENDAS_PSICOTROPICOS VP ON (VP.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                           AND (VP.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
          LEFT JOIN ITEM_VENDAS_LOTES IVL ON (IVL.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
                                         AND (IVL.ITEM_VENDA_ID = I.ITEM_VENDA_ID)
                                         AND (IVL.PRODUTO_ID = I.PRODUTO_ID)
          LEFT JOIN VENDEDORES V ON (V.VENDEDOR_ID = VP.CONF_VENDEDOR_ID)
         WHERE CAST(C.VENDA_DATA_HORA AS DATE) >= ?
           AND (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
           AND (VP.VENDA_NOTA_ID IS NULL
                OR IVL.NUM_LOTE IS NULL OR IVL.NUM_LOTE = ''
                OR P.REGISTRO_MS IS NULL OR P.REGISTRO_MS = '')
         ORDER BY C.VENDA_NOTA_ID
    """,

    # --- inventário lido do site da ANVISA pelo Anvisa.exe ---
    # Lido inteiro de propósito: os nomes das colunas variam entre versões e
    # são descobertos em tempo de execução. O filtro de controlado é aplicado
    # depois, em Python, por PRODUTO_ID — veja ler_inventario_anvisa().
    "inventario_sngpc": "SELECT * FROM INVENTARIO_SNGPC",

    # --- PRODUTOS.PROD_SALDO x soma dos lotes (--totais) ---
    # O Digifarma guarda DOIS saldos: o total do produto, em
    # PRODUTOS.PROD_SALDO, e o de cada lote, em LOTES. A tela do balcao le o
    # primeiro; a comparacao com o SNGPC usa o segundo. Quando os dois
    # discordam, um dos lados esta mentindo — e e preciso saber qual antes
    # de escrever em qualquer um deles.
    "totais_produto": """
        SELECT P.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, P.PROD_SALDO,
               (SELECT SUM(L.{COLUNA}) FROM LOTES L
                 WHERE L.PRODUTO_ID = P.PRODUTO_ID) AS SOMA_LOTES
          FROM PRODUTOS P
         WHERE ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
           AND ((P.PROD_ATIVO = 'S') OR (P.PROD_ATIVO IS NULL))
    """,

    # --- cadastro de um produto, pelo nome (--produto) ---
    # O CAST é o mesmo cuidado das outras: sem ele o fdb reclama que o
    # parâmetro é maior que a coluna e a busca morre antes de rodar.
    "produtos_por_nome": """
        SELECT P.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, P.COD_BARRAS,
               P.PSICOTROPICO, P.ANTIMICROBIANO
          FROM PRODUTOS P
         WHERE UPPER(CAST(P.PRODUTO AS VARCHAR(500))) LIKE ?
         ORDER BY P.PRODUTO
    """,

    # quem é controlado, para filtrar o inventário do SNGPC pelo mesmo
    # critério das vendas: PSICOTROPICO='S' OU ANTIMICROBIANO='S'
    "produtos_controlados": """
        SELECT PRODUTO_ID, PRODUTO, REGISTRO_MS, PSICOTROPICO, ANTIMICROBIANO
          FROM PRODUTOS
    """,

    # --- saldo por lote no Digifarma ---
    # A coluna e a EXPRESSÃO são montadas em tempo de execução; veja
    # detectar_coluna_saldo() e montar_expressao_saldo(). {EXPRESSAO} e
    # {FILTROS} são trocados antes de executar.
    #
    # LOTES é tabela de MOVIMENTO: cada entrada de nota gera uma linha, e
    # ENTRADA_SAIDA diz se aquela linha soma ou subtrai (a consulta
    # entradas_pendentes, acima, já filtra por 'E'). Somar a coluna crua,
    # sem sinal, devolvia o total comprado na vida do lote em vez do saldo —
    # era daí que saíam 200 comprimidos num lote vencido em 2024.
    "saldo_digifarma": """
        SELECT P.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, P.COD_BARRAS,
               L.NUM_LOTE, L.LOTE_VENCIMENTO,
               SUM({EXPRESSAO}) AS SALDO
          FROM LOTES L
          JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID)
         WHERE ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
               {FILTROS}
         GROUP BY P.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, P.COD_BARRAS,
                  L.NUM_LOTE, L.LOTE_VENCIMENTO
    """,

    # --- baixas por lote, para o modo "movimento" ---
    # A venda de controlado NÃO passa por LOTES: ela fica em
    # ITEM_VENDAS_LOTES. Sem descontar isto, o lote nunca baixa.
    "vendas_por_lote": """
        SELECT P.REGISTRO_MS, IVL.NUM_LOTE, SUM(IVL.QUANTIDADE) AS QUANTIDADE
          FROM ITEM_VENDAS_LOTES IVL
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = IVL.VENDA_NOTA_ID)
                            AND (I.ITEM_VENDA_ID = IVL.ITEM_VENDA_ID)
                            AND (I.PRODUTO_ID = IVL.PRODUTO_ID)
                            AND ((I.CANCELADO = 'N') OR (I.CANCELADO IS NULL))
          JOIN CAB_VENDAS C ON (C.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
          JOIN PRODUTOS P ON (P.PRODUTO_ID = I.PRODUTO_ID)
         WHERE (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) > 0
           AND ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
         GROUP BY P.REGISTRO_MS, IVL.NUM_LOTE
    """,

    "perdas_por_lote": """
        SELECT P.REGISTRO_MS, PP.LOTE AS NUM_LOTE, SUM(PP.QUANTIDADE) AS QUANTIDADE
          FROM PERDAS_PSICOTROPICOS PP
          JOIN PRODUTOS P ON (P.PRODUTO_ID = PP.PRODUTO_ID)
         WHERE ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
         GROUP BY P.REGISTRO_MS, PP.LOTE
    """,

    # --- quando cada lote entrou, e por qual nota ---
    # Comparar a nota com ULT_ENTRADA_CAB_NOTA_ID diz se aquela entrada já
    # foi transmitida. Um lote que o SNGPC não tem mas cuja nota já passou
    # pelo ponteiro não é pendência de escrituração: ou o envio daquele
    # período foi recusado, ou o inventário da ANVISA não veio inteiro.
    "entradas_por_lote": """
        SELECT P.REGISTRO_MS, L.NUM_LOTE,
               MAX(C.CAB_NOTA_ID) AS CAB_NOTA_ID,
               MAX(C.DATA_RECEBIMENTO) AS DATA
          FROM LOTES L
          JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID)
          JOIN CAB_NOTAS C ON (C.CAB_NOTA_ID = L.CAB_NOTA_ID)
         WHERE ((P.PSICOTROPICO = 'S') OR (P.ANTIMICROBIANO = 'S'))
           AND C.ENTRADA_SAIDA = 'E'
         GROUP BY P.REGISTRO_MS, L.NUM_LOTE
    """,

    # --- diagnóstico: TUDO que existe sobre um lote (--linhas) ---
    # SELECT * sem join: aqui o que interessa são as colunas de LOTES como
    # elas são, inclusive as que o agente ainda não conhece.
    "linhas_do_lote": """
        SELECT * FROM LOTES L
         WHERE UPPER(CAST(L.NUM_LOTE AS VARCHAR(500))) = ?
    """,

    "vendas_do_lote": """
        SELECT C.VENDA_NOTA_ID,
               CAST(C.VENDA_DATA_HORA AS DATE) AS DATA,
               IVL.QUANTIDADE, I.CANCELADO,
               (C.VENDA_RECEBIDO + C.SUBSIDIO + COALESCE(C.SUBSIDIO_ASSEFAZ, 0)) AS RECEBIDO
          FROM ITEM_VENDAS_LOTES IVL
          JOIN ITEM_VENDAS I ON (I.VENDA_NOTA_ID = IVL.VENDA_NOTA_ID)
                            AND (I.ITEM_VENDA_ID = IVL.ITEM_VENDA_ID)
                            AND (I.PRODUTO_ID = IVL.PRODUTO_ID)
          JOIN CAB_VENDAS C ON (C.VENDA_NOTA_ID = I.VENDA_NOTA_ID)
         WHERE UPPER(CAST(IVL.NUM_LOTE AS VARCHAR(500))) = ?
         ORDER BY C.VENDA_NOTA_ID
    """,

    # --- entradas de um lote, com a nota e a data (--negativos) ---
    # LEFT JOIN em CAB_NOTAS: lote cuja nota sumiu do banco continua sendo
    # entrada, e é justamente o caso que interessa investigar.
    "entradas_do_lote": """
        SELECT P.REGISTRO_MS, C.CAB_NOTA_ID, C.NOTA_FISCAL, C.DATA_RECEBIMENTO,
               {COLUNAS}
          FROM LOTES L
          JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID)
          LEFT JOIN CAB_NOTAS C ON (C.CAB_NOTA_ID = L.CAB_NOTA_ID)
         WHERE UPPER(CAST(L.NUM_LOTE AS VARCHAR(500))) = ?
    """,

    # --- diagnóstico: linhas cruas de LOTES de um produto (--saldo) ---
    # {COLUNAS} é montado com as colunas que existem na LOTES desta
    # instalação; um SELECT * traria junto as de PRODUTOS, e uma coluna de
    # mesmo nome nas duas tabelas estragaria a conta.
    # O CAST não é enfeite: o fdb dimensiona o parâmetro do LIKE pelo
    # tamanho declarado da coluna, e REGISTRO_MS é VARCHAR(13) — procurar
    # "ESCITALOPRAM" (14 com os %) estourava antes de chegar ao banco.
    "lotes_detalhe": """
        SELECT P.PRODUTO, P.REGISTRO_MS, {COLUNAS}
          FROM LOTES L
          JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID)
         WHERE UPPER(CAST(P.PRODUTO AS VARCHAR(500))) LIKE ?
            OR CAST(P.REGISTRO_MS AS VARCHAR(500)) LIKE ?
            OR UPPER(CAST(L.NUM_LOTE AS VARCHAR(500))) LIKE ?
    """,
}

# candidatas a coluna de saldo por lote, em ordem de preferência.
# COLUNAS_SALDO já é o saldo remanescente do lote: soma direto.
# COLUNAS_MOVIMENTO é a quantidade de CADA movimento: o saldo só sai
# depois de descontar vendas, perdas e saídas.
#
# LOTE_QUANTIDADE encabeça a lista porque é o nome real no Digifarma6.fdb,
# confirmado com --colunas LOTES na Drogaria Humanae. Ela é o saldo que o
# Digifarma mostra na tela, já com as baixas que não passam por venda nem
# por perda — o vencido que sai do estoque, por exemplo. Reconstruir isso
# a partir das compras dá números inventados: o lote 3G4313 tem 63
# comprados, 3 vendidos e LOTE_QUANTIDADE = 0.
COLUNAS_SALDO = ('LOTE_QUANTIDADE', 'QUANTIDADE_LOTE', 'SALDO', 'SALDO_LOTE',
                 'SALDO_ATUAL', 'ESTOQUE', 'ESTOQUE_ATUAL', 'QUANTIDADE_ATUAL',
                 'QTD_ATUAL', 'QUANTIDADE_ESTOQUE', 'QUANTIDADE_ATU', 'QTD_SALDO')
COLUNAS_MOVIMENTO = ('QUANTIDADE', 'QUANTIDADE_COMPRA', 'QTDE', 'QTD',
                     'QUANTIDADE_ENTRADA')

TABELAS_ESPERADAS = [
    'SNGPC', 'CONFIG', 'PRODUTOS', 'CAB_VENDAS', 'ITEM_VENDAS',
    'ITEM_VENDAS_LOTES', 'VENDAS_PSICOTROPICOS', 'CAB_NOTAS',
    'ITEM_NOTAS', 'LOTES', 'PERDAS_PSICOTROPICOS', 'VENDEDORES',
    'FORNECEDORES', 'INVENTARIO_SNGPC',
]


# ============================================================
# INFRAESTRUTURA
# ============================================================
def registrar(texto):
    carimbo = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    linha = '[%s] %s' % (carimbo, texto)
    print(linha)
    try:
        with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except Exception:
        pass


def carregar_config():
    config = dict(CONFIG_PADRAO)
    if os.path.exists(ARQUIVO_CONFIG):
        with open(ARQUIVO_CONFIG, encoding='utf-8') as f:
            config.update(json.load(f))
    else:
        with open(ARQUIVO_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        registrar('Criei %s com os valores padrão. Confira antes de agendar.' % ARQUIVO_CONFIG)
    return config


def ponteiro_de_venda(ponteiros, config, avisar=True):
    """O ponteiro da última venda transmitida, com o remendo do config.

    Envio feito por OUTRA máquina não avança o ponteiro daqui: o Digifarma
    continua oferecendo as mesmas vendas como pendentes, o agente desconta
    de novo o que a ANVISA já descontou, e a divergência incha. O config
    transmitido_ate_venda cobre esse buraco enquanto o ponteiro não é
    acertado — só para CIMA, para nunca esconder venda que o Digifarma
    ainda considera pendente, e sempre dito no log: ponteiro remendado à
    mão é coisa que precisa aparecer."""
    do_banco = int(numero(ponteiros.get('ULT_SAIDA_VENDA_NOTA_ID')))
    forcado = int(numero((config or {}).get('transmitido_ate_venda')))
    if forcado > do_banco:
        if avisar:
            registrar('Config transmitido_ate_venda=%d: tratando como enviado tudo '
                      'até a venda %d (o Digifarma ainda diz %d). Volte para 0 '
                      'quando o ponteiro do Digifarma for acertado.'
                      % (forcado, forcado, do_banco))
        return forcado, True
    return do_banco, False


def conectar_firebird(config):
    try:
        import fdb
    except ImportError:
        raise SystemExit('Falta a biblioteca fdb. Rode: pip install fdb')
    return fdb.connect(
        dsn=config['banco'],
        user=config['usuario'],
        password=config['senha'],
        charset=config['charset'],
    )


def conectar_firebase(config):
    try:
        import firebase_admin
        from firebase_admin import credentials, db
    except ImportError:
        raise SystemExit('Falta a biblioteca firebase-admin. Rode: pip install firebase-admin')

    if not os.path.exists(config['chave_firebase']):
        raise SystemExit(
            'Não achei %s.\n'
            'Console do Firebase > Configurações do projeto > Contas de serviço >\n'
            'Gerar nova chave privada. Salve o arquivo com esse nome nesta pasta.\n'
            'Ele NUNCA vai para o GitHub.' % config['chave_firebase'])

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(config['chave_firebase']),
            {
                'databaseURL': config['url_banco'],
                # o agente escreve como este UID; ele precisa estar
                # em farmacia/agentes para as regras deixarem passar
                'databaseAuthVariableOverride': {'uid': config['uid_agente']},
            })
    return db


def consultar(conexao, sql, parametros=()):
    cursor = conexao.cursor()
    try:
        cursor.execute(sql, parametros)
        colunas = [d[0].strip().upper() for d in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
    finally:
        # sem isto o cursor da consulta que falhou fica pendurado na
        # transação, e o erro de verdade morre escondido atrás de um
        # "attempt to reclose a closed cursor" na hora de fechar
        try:
            cursor.close()
        except Exception:
            pass


def executar(conexao, sql, parametros=()):
    """A ÚNICA função deste arquivo que escreve no Digifarma.

    Está sozinha de propósito: quem for auditar o que este agente altera no
    banco da farmácia lê esta função e as poucas chamadas dela, não o
    arquivo inteiro. Devolve quantas linhas foram afetadas."""
    cursor = conexao.cursor()
    try:
        cursor.execute(sql, parametros)
        afetadas = cursor.rowcount
        conexao.commit()
        return afetadas
    except Exception:
        conexao.rollback()
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def fechar(conexao):
    """Fechar conexão não pode estourar por cima do erro que interessa."""
    try:
        conexao.close()
    except Exception as e:
        registrar('Aviso ao fechar a conexão com o Firebird: %s' % e)


def texto(valor):
    if valor is None:
        return ''
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.strftime('%Y-%m-%d')
    return str(valor).strip()


def texto_hora(valor):
    """Como texto(), mas guarda a HORA. O texto() corta tudo em AAAA-MM-DD,
    e a hora da venda é justamente o que se quer ver no acompanhamento."""
    if valor is None:
        return ''
    if isinstance(valor, datetime.datetime):
        return valor.isoformat(timespec='seconds')
    if isinstance(valor, datetime.date):
        return valor.isoformat()
    return str(valor).strip()


def numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# XML
# ============================================================
def arquivar_xml(config):
    """Copia o XML da última transmissão para enviados\\sngpc_AAAA-MM-DD.xml.

    O Digifarma sobrescreve SNGPC.XML a cada envio, então sem essa cópia
    o histórico se perde. Devolve o caminho do arquivo arquivado."""
    pasta = config['pasta_xml']
    if not os.path.isdir(pasta):
        registrar('Pasta do XML não encontrada: %s' % pasta)
        return None

    candidatos = ['SNGPC.XML', 'MOVIMENTACAO.XML', 'sngpc.zip']
    origem = None
    for nome in candidatos:
        caminho = os.path.join(pasta, nome)
        if os.path.exists(caminho):
            origem = caminho
            break
    if not origem:
        registrar('Nenhum XML de envio em %s' % pasta)
        return None

    data = datetime.datetime.fromtimestamp(os.path.getmtime(origem)).strftime('%Y-%m-%d')
    destino_pasta = os.path.join(pasta, 'enviados')
    os.makedirs(destino_pasta, exist_ok=True)
    destino = os.path.join(destino_pasta, 'sngpc_%s.xml' % data)

    if origem.lower().endswith('.zip'):
        import zipfile
        with zipfile.ZipFile(origem) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith('.xml')]
            if not nomes:
                return None
            with z.open(nomes[0]) as f, open(destino, 'wb') as saida:
                shutil.copyfileobj(f, saida)
    elif not os.path.exists(destino) or os.path.getmtime(origem) > os.path.getmtime(destino):
        shutil.copy2(origem, destino)

    return destino


# ============================================================
# COLETA
# ============================================================
def colunas_da_tabela(conexao, tabela):
    linhas = consultar(conexao, """
        SELECT TRIM(RF.RDB$FIELD_NAME) AS CAMPO
          FROM RDB$RELATION_FIELDS RF
         WHERE RF.RDB$RELATION_NAME = ?
         ORDER BY RF.RDB$FIELD_POSITION
    """, (tabela.upper(),))
    return [str(l['CAMPO']).strip().upper() for l in linhas]


def detectar_coluna_saldo(conexao, config=None):
    """Descobre como se chama o saldo por lote na tabela LOTES e, o que é
    tão importante quanto, o que aquela coluna significa.

    Devolve {'coluna', 'modo', 'campos'}. 'modo' é:
      'saldo'      a coluna já é o que resta do lote — soma direto;
      'movimento'  a coluna é a quantidade de cada movimento — o saldo é
                   apurado descontando vendas, perdas e saídas.

    O agente antigo só procurava o nome e somava. Quando a base não tinha
    coluna de saldo, ele caía em QUANTIDADE/QUANTIDADE_COMPRA e publicava o
    total comprado como se fosse estoque."""
    config = config or {}
    campos = colunas_da_tabela(conexao, 'LOTES')

    escolhida = str(config.get('coluna_saldo') or '').strip().upper()
    if escolhida:
        if escolhida not in campos:
            raise RuntimeError(
                'coluna_saldo do agente_config.json é "%s", que não existe em '
                'LOTES. Campos existentes: %s.' % (escolhida, ', '.join(campos)))
    else:
        escolhida = next((c for c in COLUNAS_SALDO if c in campos), None) \
            or next((c for c in COLUNAS_MOVIMENTO if c in campos), None)

    if not escolhida:
        raise RuntimeError(
            'Não achei a coluna de saldo em LOTES. Campos existentes: %s.\n'
            'Acrescente o nome certo em COLUNAS_SALDO, no topo do agente_auto.py,\n'
            'ou fixe "coluna_saldo" no agente_config.json.' % ', '.join(campos))

    modo = str(config.get('modo_saldo') or 'auto').strip().lower()
    if modo not in ('saldo', 'movimento'):
        modo = 'saldo' if escolhida in COLUNAS_SALDO else 'movimento'

    return {'coluna': escolhida, 'modo': modo, 'campos': campos}


def montar_expressao_saldo(info):
    """A expressão que vai dentro do SUM(). LOTES guarda movimento: sem o
    sinal de ENTRADA_SAIDA, uma devolução ao fornecedor SOMA ao estoque."""
    coluna = 'COALESCE(L.%s, 0)' % info['coluna']
    if 'ENTRADA_SAIDA' not in info['campos']:
        return coluna
    if info['modo'] == 'saldo':
        # o que resta do lote mora na linha da entrada; linha de saída não é saldo
        return "CASE WHEN L.ENTRADA_SAIDA = 'S' THEN 0 ELSE %s END" % coluna
    return "CASE WHEN L.ENTRADA_SAIDA = 'S' THEN -%s ELSE %s END" % (coluna, coluna)


def montar_filtros_lotes(info):
    filtros = []
    if 'CANCELADO' in info['campos']:
        filtros.append("AND ((L.CANCELADO = 'N') OR (L.CANCELADO IS NULL))")
    return '\n               '.join(filtros)


def baixas_por_lote(conexao):
    """Saídas que NÃO passam por LOTES: venda de controlado
    (ITEM_VENDAS_LOTES) e perda (PERDAS_PSICOTROPICOS)."""
    baixas = {}
    for nome in ('vendas_por_lote', 'perdas_por_lote'):
        try:
            linhas = consultar(conexao, CONSULTAS[nome])
        except Exception as e:
            registrar('Não consegui somar %s: %s' % (nome, e))
            continue
        for linha in linhas:
            chave = (so_digitos(linha.get('REGISTRO_MS')),
                     texto(linha.get('NUM_LOTE')).upper())
            baixas[chave] = baixas.get(chave, 0.0) + numero(linha.get('QUANTIDADE'))
    return baixas


def total_por_lote(conexao, info):
    """Soma qualquer coluna de LOTES pela chave da comparação. Serve para
    pôr a compra ao lado do saldo sem repetir o SQL."""
    sql = (CONSULTAS['saldo_digifarma']
           .replace('{EXPRESSAO}', montar_expressao_saldo(info))
           .replace('{FILTROS}', montar_filtros_lotes(info)))
    total = {}
    for linha in consultar(conexao, sql):
        chave = (so_digitos(linha.get('REGISTRO_MS')),
                 texto(linha.get('NUM_LOTE')).upper())
        total[chave] = total.get(chave, 0.0) + numero(linha.get('SALDO'))
    return total


def saldo_por_lote(conexao, config):
    """Saldo do Digifarma por M.S. + lote — a chave da comparação com a ANVISA.

    O SQL agrupa por PRODUTO_ID e LOTE_VENCIMENTO também, mas a comparação
    com a ANVISA é só por M.S. + lote. Dois cadastros com o mesmo registro,
    ou o mesmo lote gravado com validades diferentes, viravam DUAS linhas com
    a mesma chave: a primeira levava todo o saldo do SNGPC e a segunda ficava
    com zero, inventando divergência dos dois lados. Somamos pela chave da
    comparação antes de comparar."""
    info = detectar_coluna_saldo(conexao, config)
    sql = (CONSULTAS['saldo_digifarma']
           .replace('{EXPRESSAO}', montar_expressao_saldo(info))
           .replace('{FILTROS}', montar_filtros_lotes(info)))

    por_chave = {}
    for linha in consultar(conexao, sql):
        chave = (so_digitos(linha.get('REGISTRO_MS')),
                 texto(linha.get('NUM_LOTE')).upper())
        registro = por_chave.get(chave)
        if registro is None:
            registro = por_chave[chave] = {
                'codigo': texto(linha.get('PRODUTO_ID')),
                'descricao': texto(linha.get('PRODUTO')),
                'ms': chave[0],
                'ean': texto(linha.get('COD_BARRAS')),
                'lote': chave[1],
                'validade': texto(linha.get('LOTE_VENCIMENTO')),
                'saldoDigifarma': 0.0,
            }
            if registro['descricao'] and chave[0] not in DESCRICOES_POR_MS:
                DESCRICOES_POR_MS[chave[0]] = registro['descricao']
        registro['saldoDigifarma'] += numero(linha.get('SALDO'))

    if info['modo'] == 'movimento':
        baixas = baixas_por_lote(conexao)
        for chave, registro in por_chave.items():
            baixado = baixas.get(chave, 0.0)
            registro['entradas'] = round(registro['saldoDigifarma'], 3)
            registro['baixas'] = round(baixado, 3)
            registro['saldoDigifarma'] -= baixado

    for registro in por_chave.values():
        registro['saldoDigifarma'] = round(registro['saldoDigifarma'], 3)

    return por_chave, info


# colunas de INVENTARIO_SNGPC, que mudam de nome entre versões.
# 'exatos' vale mais que 'pedacos': procurar só o pedaço 'LOTE' devolvia
# LOTE_VENCIMENTO quando ela vinha antes de NUM_LOTE na tabela — a chave
# virava uma data, nada casava com o Digifarma e TODO item aparecia como
# sobra, com o saldo do SNGPC zerado.
CAMPOS_INVENTARIO = {
    'ms': {
        'exatos': ('REGISTRO_MS', 'REGISTROMS', 'NUM_REGISTRO_MS', 'REGISTRO_ANVISA',
                   'NUM_REGISTRO', 'REGISTRO', 'MS'),
        'pedacos': ('REGISTRO_MS', 'REGISTRO'),
        'proibidas': ('DATA', 'NOME', 'DESCRICAO'),
    },
    'lote': {
        'exatos': ('NUM_LOTE', 'NUMERO_LOTE', 'LOTE', 'LOTE_MEDICAMENTO',
                   'NUM_LOTE_MEDICAMENTO'),
        'pedacos': ('NUM_LOTE', 'LOTE'),
        'proibidas': ('VENC', 'VALID', 'DATA', 'QUANT', 'SALDO'),
    },
    'quantidade': {
        # SALDO_LOTE é o nome na base da Drogaria Humanae. Não dá para
        # barrar 'LOTE' aqui: a coluna do saldo carrega o nome do lote.
        'exatos': ('SALDO_LOTE', 'QUANTIDADE', 'QUANTIDADE_ESTOQUE',
                   'QUANTIDADE_INVENTARIO', 'QUANTIDADE_ATUAL', 'QUANTIDADE_LOTE',
                   'SALDO', 'SALDO_ATUAL', 'ESTOQUE', 'QTD_LOTE', 'QTDE', 'QTD'),
        'pedacos': ('SALDO', 'QUANT', 'ESTOQUE'),
        'proibidas': ('DATA', 'VENC', 'VALID'),
    },
    'descricao': {
        # '_ID' fora: sem isso o pedaço 'PRODUTO' casava com PRODUTO_ID e a
        # descrição do item virava um número
        'exatos': ('MEDICAMENTO', 'DESCRICAO', 'PRODUTO', 'NOME_MEDICAMENTO',
                   'DESCRICAO_MEDICAMENTO', 'NOME'),
        'pedacos': ('MEDICAMENTO', 'PRODUTO', 'DESCRICAO', 'NOME'),
        'proibidas': ('REGISTRO', 'CODIGO', 'LOTE', 'DATA', '_ID'),
    },
    'data': {
        'exatos': ('DATA_ATUALIZACAO', 'DATA_INVENTARIO', 'DATA_SALDO',
                   'ATUALIZADO_EM', 'DATA'),
        'pedacos': ('ATUALIZ', 'DATA'),
        'proibidas': ('VALID', 'VENC', 'FABRIC'),
    },
}


def escolher_campo(campos, regras):
    """Casa o nome da coluna por igualdade primeiro e só depois por pedaço do
    nome — e, no pedaço, o nome mais curto ganha. Sem isso quem decidia era a
    ORDEM das colunas na tabela, que ninguém controla."""
    mapa = {}
    for campo in campos:
        mapa.setdefault(str(campo).strip().upper(), campo)

    for nome in regras['exatos']:
        if nome in mapa:
            return mapa[nome]
    for pedaco in regras.get('pedacos', ()):
        for nome in sorted(mapa, key=lambda n: (len(n), n)):
            if pedaco in nome and not any(p in nome for p in regras.get('proibidas', ())):
                return mapa[nome]
    return None


def classes_dos_produtos(conexao):
    """Quem é controlado, pelo mesmo critério das vendas.

    Devolve (controlados, conhecidos). O segundo conjunto existe para separar
    "produto marcado como não controlado" de "produto que não está no
    cadastro" — descartar os dois é diferente, e só o primeiro é seguro."""
    controlados, conhecidos = set(), set()
    for linha in consultar(conexao, CONSULTAS['produtos_controlados']):
        produto = texto(linha.get('PRODUTO_ID'))
        if not produto:
            continue
        conhecidos.add(produto)
        if (texto(linha.get('PSICOTROPICO')).upper() == 'S'
                or texto(linha.get('ANTIMICROBIANO')).upper() == 'S'):
            controlados.add(produto)
    return controlados, conhecidos


CLASSES = ('psicotropico', 'antimicrobiano')
NOME_CLASSE = {
    'psicotropico': 'Psicotrópicos e entorpecentes',
    'antimicrobiano': 'Antimicrobianos',
    '': 'Sem marcação de classe no cadastro',
}


def classes_por_medicamento(conexao):
    """De que lista é cada medicamento: psicotrópico ou antimicrobiano.

    São duas escriturações diferentes na farmácia — a receita de psicotrópico
    fica retida e a de antimicrobiano não —, e quem confere prateleira confere
    uma lista de cada vez. Por isso a folha sai separada.

    Cadastro marcado como os dois entra em psicotrópico: é a lista mais
    rígida, e conferir por lá não deixa nada de fora.

    Devolve (por_produto, por_ms). O segundo é o desempate para o lote que
    só existe no inventário da ANVISA, que chega sem PRODUTO_ID."""
    por_produto, por_ms = {}, {}
    for linha in consultar(conexao, CONSULTAS['produtos_controlados']):
        psico = texto(linha.get('PSICOTROPICO')).upper() == 'S'
        anti = texto(linha.get('ANTIMICROBIANO')).upper() == 'S'
        if not psico and not anti:
            continue
        classe = 'psicotropico' if psico else 'antimicrobiano'
        produto = texto(linha.get('PRODUTO_ID'))
        if produto:
            por_produto[produto] = classe
        ms = so_digitos(linha.get('REGISTRO_MS'))
        # dois cadastros com o mesmo registro e marcações diferentes: fica o
        # psicotrópico, para não sumir da lista que exige receita retida
        if ms and (classe == 'psicotropico' or ms not in por_ms):
            por_ms[ms] = classe
    return por_produto, por_ms


def ler_inventario_anvisa(conexao):
    """Lê INVENTARIO_SNGPC — a tabela que o Anvisa.exe regrava com o
    inventário do site da ANVISA.

    Só entram os medicamentos marcados como PSICOTROPICO ou ANTIMICROBIANO,
    o mesmo critério das vendas e do estoque. Sem isso, item não controlado
    que estivesse na tabela virava divergência "só na ANVISA" — comparando
    lados que não se comparam.

    Devolve (saldo, data, colunas usadas, descartados)."""
    try:
        linhas = consultar(conexao, CONSULTAS['inventario_sngpc'])
    except Exception as e:
        registrar('Não consegui ler INVENTARIO_SNGPC: %s' % e)
        return {}, None, {}, 0
    if not linhas:
        registrar('INVENTARIO_SNGPC está vazia — sem o lado ANVISA, todo lote do '
                  'Digifarma vira "sobra". Rode o Anvisa.exe e faça o login no site.')
        return {}, None, {}, 0

    campos = list(linhas[0])

    # filtro de controlado, por PRODUTO_ID. Linha que não casa com o cadastro
    # fica: pode ser produto que o SNGPC tem e a farmácia não, que é
    # divergência de verdade e precisa aparecer.
    campo_produto = next((c for c in campos if c.strip().upper() == 'PRODUTO_ID'), None)
    descartados = 0
    if campo_produto:
        try:
            controlados, conhecidos = classes_dos_produtos(conexao)
        except Exception as e:
            registrar('Não consegui ler as marcações de controlado: %s' % e)
            controlados, conhecidos = set(), set()
        if conhecidos:
            mantidas = []
            for linha in linhas:
                produto = texto(linha.get(campo_produto))
                if produto in conhecidos and produto not in controlados:
                    descartados += 1
                    continue
                mantidas.append(linha)
            linhas = mantidas
            if descartados:
                registrar('INVENTARIO_SNGPC: %d linha(s) de produto não marcado como '
                          'psicotrópico nem antimicrobiano ficaram de fora.' % descartados)
    else:
        registrar('INVENTARIO_SNGPC não tem PRODUTO_ID: não dá para filtrar por '
                  'controlado, o inventário entra inteiro.')
    usados = {chave: escolher_campo(campos, regras)
              for chave, regras in CAMPOS_INVENTARIO.items()}
    campo_ms, campo_lote = usados['ms'], usados['lote']
    campo_qtd, campo_desc, campo_data = usados['quantidade'], usados['descricao'], usados['data']

    if not (campo_ms and campo_qtd):
        registrar('INVENTARIO_SNGPC tem colunas inesperadas: %s' % ', '.join(campos))
        return {}, None, {'colunas': campos}, descartados

    saldo = {}
    atualizado = None
    for linha in linhas:
        chave = (so_digitos(texto(linha.get(campo_ms))),
                 texto(linha.get(campo_lote)).upper() if campo_lote else '')
        saldo[chave] = saldo.get(chave, 0.0) + numero(linha.get(campo_qtd))
        if campo_desc and chave not in DESCRICOES:
            DESCRICOES[chave] = texto(linha.get(campo_desc))
        if campo_data and linha.get(campo_data):
            valor = texto(linha.get(campo_data))
            atualizado = max(atualizado, valor) if atualizado else valor
    return saldo, atualizado, usados, descartados


DESCRICOES = {}        # (ms, lote) -> descrição, vinda do inventário da ANVISA
DESCRICOES_POR_MS = {}  # ms -> descrição, vinda do cadastro do Digifarma


def so_digitos(valor):
    return ''.join(c for c in str(valor or '') if c.isdigit())


def normalizar_texto(valor):
    """Para busca no terminal: sem acento e em maiúsculas, como o app faz."""
    import unicodedata
    sem_acento = unicodedata.normalize('NFD', str(valor or ''))
    return ''.join(c for c in sem_acento if unicodedata.category(c) != 'Mn').upper()


def formatar_ms(valor):
    """1052500180189 -> 1.0525.0018.018-9, que é como o registro aparece no
    site da ANVISA e na bula. A comparação interna é só de dígitos; isto é
    para quem vai conferir com o site aberto do lado."""
    d = so_digitos(valor)
    if len(d) != 13:
        return d or '(sem M.S.)'
    return '%s.%s.%s.%s-%s' % (d[0], d[1:5], d[5:9], d[9:12], d[12])


DIAS_VENDAS_RECENTES = 7


def vendas_recentes(conexao, dias=DIAS_VENDAS_RECENTES):
    """As últimas vendas de controlado, uma linha por lote vendido.

    É o que o balcão precisa ver sem abrir o Digifarma: número da venda,
    hora, produto, lote e quantidade. Sai pela mesma tarefa de 5 minutos que
    já atende os botões do app."""
    corte = (datetime.date.today() - datetime.timedelta(days=dias)).isoformat()
    linhas = consultar(conexao, CONSULTAS['vendas_recentes'], (corte,))
    return [{
        'venda': l.get('VENDA'),
        'quando': texto_hora(l.get('QUANDO')),
        'descricao': texto(l.get('PRODUTO')),
        'ms': so_digitos(l.get('REGISTRO_MS')),
        'lote': texto(l.get('NUM_LOTE')),
        'quantidade': numero(l.get('QUANTIDADE')),
    } for l in linhas]


def vendas_sem_receita_pendentes(conexao, config=None):
    """Vendas de controlado que ainda vão subir e estão sem receita
    escriturada. É a lista para corrigir ANTES do próximo envio — depois de
    transmitido, o conserto é bem mais caro."""
    linhas = consultar(conexao, CONSULTAS['ponteiros'])
    ptr_venda = ponteiro_de_venda(linhas[0] if linhas else {}, config, avisar=False)[0]
    return [{
        'venda': l.get('VENDA'),
        'quando': texto_hora(l.get('QUANDO')),
        'descricao': texto(l.get('PRODUTO')),
        'ms': so_digitos(l.get('REGISTRO_MS')),
        'lote': texto(l.get('NUM_LOTE')),
        'quantidade': numero(l.get('QUANTIDADE')),
    } for l in consultar(conexao, CONSULTAS['vendas_sem_receita_pendentes'], (ptr_venda,))]


def classificar_divergencia(registro, saldo_anvisa, ms_no_inventario):
    """Divergência de saldo não é uma coisa só, e cada tipo se resolve num
    lugar diferente. Sem isso o app mistura 'falta transmitir a entrada'
    com 'a contagem não fecha' na mesma etiqueta de sobra.

    O nome diz o que se OBSERVA, não a causa. Um lote ausente do inventário
    da ANVISA quer dizer saldo zero lá, e zero tanto pode ser entrada que
    não subiu quanto saldo errado no Digifarma — a farmácia confirmou os
    dois casos no mesmo dia. Afirmar a causa na etiqueta manda gente
    mexer na escrituração quando o problema era o estoque."""
    if registro['saldoDigifarma'] < 0:
        # o Digifarma é a verdade, mas aqui a verdade dele está torta:
        # saída lançada sem a entrada correspondente
        return 'negativo'
    if not registro['ms']:
        # a chave da comparação é M.S. + lote. Sem M.S. o item não pode
        # casar com a ANVISA nem por acaso: qualquer diferença que apareça
        # é do cadastro, não do estoque, e mandar conferir prateleira por
        # causa dela é trabalho jogado fora.
        return 'sem_ms'
    if not saldo_anvisa:
        return ('anvisa_zerada_produto' if registro['ms'] not in ms_no_inventario
                else 'anvisa_zerada_lote')
    return 'quantidade'


def montar_inventario(conexao, config, data_inventario=None, usar_envio=False):
    import mapa_xml

    resultado = {'atualizadoEm': datetime.datetime.now().isoformat(timespec='seconds')}
    DESCRICOES.clear()
    DESCRICOES_POR_MS.clear()

    # ------------------------------------------------------------
    # 1. ponteiros do último envio
    # ------------------------------------------------------------
    linhas = consultar(conexao, CONSULTAS['ponteiros'])
    ponteiros = linhas[0] if linhas else {}
    ptr_venda, ponteiro_forcado = ponteiro_de_venda(ponteiros, config)
    ptr_entrada = int(numero(ponteiros.get('ULT_ENTRADA_CAB_NOTA_ID')))
    ptr_perda = int(numero(ponteiros.get('ULT_SAIDA_PERDA_ID')))
    ptr_transf = int(numero(ponteiros.get('ULT_SAIDA_TRANSFERENCIA_ID')))
    ultimo_envio = texto(ponteiros.get('ULTIMO_ENVIO_SNGPC'))[:10] or None

    # ------------------------------------------------------------
    # 2. XML da última transmissão
    # ------------------------------------------------------------
    caminho_xml = arquivar_xml(config)
    dados_xml = None
    if caminho_xml:
        try:
            dados_xml = mapa_xml.ler(caminho_xml)
        except Exception as e:
            registrar('Não consegui ler o XML (%s): %s' % (caminho_xml, e))

    cabecalho = (dados_xml or {}).get('cabecalho', {})
    # o período vem do cabeçalho do XML — é exato, não precisa deduzir
    periodo_de = cabecalho.get('dataInicio') or anterior(ultimo_envio)
    periodo_ate = cabecalho.get('dataFim') or ultimo_envio
    data_envio = ultimo_envio or periodo_ate

    resultado['envio'] = {
        'data': data_envio,
        'movimentosDe': periodo_de,
        'movimentosAte': periodo_ate,
        'ULT_SAIDA_VENDA_NOTA_ID': ptr_venda,
        'ULT_ENTRADA_CAB_NOTA_ID': ptr_entrada,
        'arquivoXml': os.path.basename(caminho_xml) if caminho_xml else None,
        'envioPorApi': texto(ponteiros.get('ENVIO_API')).upper() in ('S', 'T', '1', 'TRUE'),
        'ponteiroForcado': ponteiro_forcado,
    }

    if dados_xml:
        resultado['xml_envio'] = {
            'arquivo': dados_xml['arquivo'],
            'total': dados_xml['total'],
            'datas': dados_xml['datas'],
            'porTipo': {t: round(sum(i['quantidade'] for i in b.values()), 3)
                        for t, b in dados_xml['movimentos'].items()},
        }

    # ------------------------------------------------------------
    # 3. pendentes de transmissão — pelos PONTEIROS
    # ------------------------------------------------------------
    corte_data = periodo_ate or (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    pendentes = {}
    try:
        pendentes['vendas'] = consultar(conexao, CONSULTAS['saidas_pendentes'], (ptr_venda,))
        pendentes['entradas'] = consultar(conexao, CONSULTAS['entradas_pendentes'], (ptr_entrada,))
        # ponteiro de perda e de transferência ficam em 0: corta por data
        pendentes['perdas'] = consultar(conexao, CONSULTAS['perdas_pendentes'], (corte_data, ptr_perda))
        pendentes['transferencias'] = consultar(
            conexao, CONSULTAS['transferencias_pendentes'], (ptr_transf, corte_data))
    except Exception as e:
        registrar('Falha ao levantar pendentes: %s' % e)

    resultado['pendentes'] = {
        tipo: [{
            'id': l.get('VENDA_NOTA_ID') or l.get('CAB_NOTA_ID') or l.get('PERDA_ID'),
            'data': texto(l.get('DATA') or l.get('DATA_RECEBIMENTO') or l.get('DATA_EMISSAO')),
            # a hora só existe na venda, e é ela que deixa a folha de
            # conferência conversar com o cupom: mesma venda, mesma hora
            'hora': texto_hora(l.get('DATA_HORA'))[11:16],
            'descricao': texto(l.get('PRODUTO')),
            'ms': texto(l.get('REGISTRO_MS')),
            'lote': texto(l.get('NUM_LOTE')),
            'quantidade': numero(l.get('QUANTIDADE')),
        } for l in linhas_tipo]
        for tipo, linhas_tipo in pendentes.items()
    }
    resultado['resumoPendentes'] = {t: len(v) for t, v in resultado['pendentes'].items()}

    # ------------------------------------------------------------
    # 3b. movimento desde o último envio, por M.S. + lote
    # ------------------------------------------------------------
    # O inventário do SNGPC é a foto do ÚLTIMO ENVIO; o saldo do Digifarma é
    # de agora. Entre um e outro a farmácia vendeu e recebeu. Comparar as
    # duas fotos direto acusa como divergência tudo que se moveu no
    # intervalo — inclusive a entrada de ontem, que ainda nem podia estar
    # no inventário. A conta certa é:
    #
    #     SNGPC (último envio) + entradas − vendas − perdas − transferências
    #     = saldo do Digifarma hoje
    movimento_pendente = {}
    for tipo, itens_tipo in resultado['pendentes'].items():
        sinal = 1 if tipo == 'entradas' else -1
        for pendente in itens_tipo:
            chave = (so_digitos(pendente['ms']), texto(pendente['lote']).upper())
            if not chave[1]:
                continue  # sem lote não há como somar na conta do lote
            movimento_pendente[chave] = (movimento_pendente.get(chave, 0.0)
                                         + sinal * numero(pendente['quantidade']))

    # ------------------------------------------------------------
    # 4. saldo do Digifarma × inventário da ANVISA
    # ------------------------------------------------------------
    saldo_anvisa, inventario_em, campos_anvisa, fora_do_criterio = ler_inventario_anvisa(conexao)
    # data do inventário: prioridade é a data pedida na linha de comando;
    # senão, se veio de "--envio"/botão "Atualizar envio", a data do último
    # envio ao SNGPC; senão, o carimbo que o próprio Anvisa.exe deixou.
    data_do_inventario = (
        data_inventario
        or (ultimo_envio if usar_envio else None)
        or (inventario_em or '')[:10]
        or None
    )
    resultado['inventario'] = {
        'data': data_do_inventario,
        'origem': 'INVENTARIO_SNGPC (site da ANVISA, via Anvisa.exe)',
        'itens': len(saldo_anvisa),
        'camposAnvisa': {k: texto(v) for k, v in (campos_anvisa or {}).items() if v},
        # quantas linhas do inventário do SNGPC ficaram de fora por não
        # estarem marcadas como psicotrópico nem antimicrobiano
        'foraDoCriterio': fora_do_criterio,
    }

    # antes de consumir saldo_anvisa: saber se o M.S. aparece em ALGUM lote
    # do inventário é o que separa "não transmiti a entrada" de "o lote
    # sumiu do inventário"
    ms_no_inventario = {chave[0] for chave in saldo_anvisa}
    # totais por medicamento, somando os lotes. A tela do Digifarma mostra o
    # PRODUTO; o app compara LOTE a lote. Sem os dois números lado a lado,
    # quem confere lê 6 no app, 9 no Digifarma e conclui que o app erra —
    # quando os outros 3 estão em lotes que batem e por isso nem aparecem.
    total_ms_anvisa = {}
    for (ms_lote, _), quantidade in saldo_anvisa.items():
        total_ms_anvisa[ms_lote] = total_ms_anvisa.get(ms_lote, 0.0) + quantidade
    # o dicionário é consumido na comparação (pop); guardar a cópia é o que
    # permite listar depois TODOS os lotes de um medicamento
    anvisa_por_lote = dict(saldo_anvisa)

    itens = []
    try:
        por_chave, info_saldo = saldo_por_lote(conexao, config)
        resultado['inventario']['colunaSaldo'] = info_saldo['coluna']
        resultado['inventario']['modoSaldo'] = info_saldo['modo']

        total_ms_digifarma = {}
        for (ms_lote, _), registro in por_chave.items():
            total_ms_digifarma[ms_lote] = (total_ms_digifarma.get(ms_lote, 0.0)
                                           + registro['saldoDigifarma'])

        # todos os lotes de cada medicamento, dos dois lados. A lista só
        # mostra o lote que diverge; sem os irmãos, não dá para entender por
        # que o total do Digifarma é maior nem conferir contra a tela.
        lotes_por_ms = {}
        for (ms_lote, num_lote), registro in por_chave.items():
            lotes_por_ms.setdefault(ms_lote, {})[num_lote] = {
                'lote': num_lote,
                'digifarma': registro['saldoDigifarma'],
                'sngpc': 0.0,
            }
        for (ms_lote, num_lote), quantidade in anvisa_por_lote.items():
            irmao = lotes_por_ms.setdefault(ms_lote, {}).setdefault(
                num_lote, {'lote': num_lote, 'digifarma': 0.0, 'sngpc': 0.0})
            irmao['sngpc'] = round(quantidade, 3)

        ja_na_anvisa = 0
        for chave, registro in por_chave.items():
            anvisa = saldo_anvisa.pop(chave, 0.0)
            pendente = round(movimento_pendente.pop(chave, 0.0), 3)
            # Lote que JÁ bate com a ANVISA sem precisar do movimento
            # pendente: sinal de que o site já recebeu essa venda, mas o
            # ponteiro deste Digifarma não avançou — envio feito por outra
            # máquina, por exemplo. Aí a conta desconta a mesma venda duas
            # vezes (a ANVISA já descontou, e o agente desconta de novo) e
            # inventa divergência. Contamos para poder avisar em vez de
            # publicar número inflado sem explicação.
            if pendente and not round(registro['saldoDigifarma'] - anvisa, 3):
                ja_na_anvisa += 1
            # lote zerado dos dois lados não é divergência nem notícia:
            # publicar tudo só engorda o farmacia/inventario
            if not registro['saldoDigifarma'] and not anvisa and not pendente:
                continue
            esperado = round(anvisa + pendente, 3)
            registro['saldoSngpc'] = round(anvisa, 3)
            if pendente:
                # o que ainda não subiu: é o que explica a diferença entre a
                # foto do envio e o saldo de agora
                registro['movimentoDesdeEnvio'] = pendente
                registro['esperadoSngpc'] = esperado
            registro['diferenca'] = round(registro['saldoDigifarma'] - esperado, 3)
            if registro['diferenca']:
                registro['motivo'] = classificar_divergencia(
                    registro, anvisa, ms_no_inventario)
            # só quando o medicamento tem mais de um lote: aí o número do
            # lote não bate com a tela do Digifarma e o total explica
            digi_ms = round(total_ms_digifarma.get(chave[0], 0.0), 3)
            anvisa_ms = round(total_ms_anvisa.get(chave[0], 0.0), 3)
            irmaos = lotes_por_ms.get(chave[0], {})
            if digi_ms != registro['saldoDigifarma'] or anvisa_ms != registro['saldoSngpc']:
                registro['saldoDigifarmaMs'] = digi_ms
                registro['saldoSngpcMs'] = anvisa_ms
            if registro.get('motivo') and len(irmaos) > 1:
                registro['lotesDoMs'] = sorted(irmaos.values(), key=lambda x: x['lote'])
            itens.append(registro)
        resultado['inventario']['jaNaAnvisa'] = ja_na_anvisa
    except Exception as e:
        registrar('Falha ao levantar o saldo por lote: %s' % e)

    # o que a ANVISA tem e o Digifarma não
    for (ms, lote), quantidade in saldo_anvisa.items():
        pendente = round(movimento_pendente.pop((ms, lote), 0.0), 3)
        esperado = round(quantidade + pendente, 3)
        if not esperado:
            continue  # o movimento pendente já zerou o lote: nada a conferir
        item = {
            'codigo': '',
            'descricao': (DESCRICOES.get((ms, lote))
                          or DESCRICOES_POR_MS.get(ms)
                          or '(só no inventário da ANVISA)'),
            'ms': ms, 'ean': '', 'lote': lote, 'validade': '',
            'saldoDigifarma': 0.0, 'saldoSngpc': round(quantidade, 3),
            'diferenca': round(-esperado, 3),
            'motivo': 'so_na_anvisa',
        }
        if pendente:
            item['movimentoDesdeEnvio'] = pendente
            item['esperadoSngpc'] = esperado
        itens.append(item)
    # de que lista é cada item — psicotrópico ou antimicrobiano. Vai junto
    # com o item para o app e para a folha de conferência não precisarem
    # voltar ao banco só para separar as duas listas.
    try:
        classe_produto, classe_ms = classes_por_medicamento(conexao)
        for i in itens:
            i['classe'] = (classe_produto.get(i.get('codigo'))
                           or classe_ms.get(i['ms']) or '')
        # o movimento pendente também: cada lista leva as suas vendas
        for linhas_tipo in resultado['pendentes'].values():
            for p in linhas_tipo:
                p['classe'] = classe_ms.get(so_digitos(p['ms']), '')
    except Exception as e:
        registrar('Falha ao classificar psicotrópico/antimicrobiano: %s' % e)

    resultado['itens'] = itens
    resultado['resumoSaldo'] = {}
    for i in itens:
        if i.get('motivo'):
            resultado['resumoSaldo'][i['motivo']] = resultado['resumoSaldo'].get(i['motivo'], 0) + 1

    # ------------------------------------------------------------
    # 5. conferência do XML contra as vendas do período
    # ------------------------------------------------------------
    # "0 divergências" tanto pode ser conferência limpa quanto conferência
    # que não aconteceu — sem XML, sem período, ou sem venda nenhuma no
    # período. O app precisa saber a diferença; o mesmo zero enganoso do
    # saldo, que fazia 4135 sobras parecerem divergência.
    resumo_xml = {
        'temXml': bool(dados_xml),
        'arquivo': (dados_xml or {}).get('arquivo'),
        'periodoDe': periodo_de,
        'periodoAte': periodo_ate,
    }
    if dados_xml and periodo_de and periodo_ate:
        saidas = consultar(conexao, CONSULTAS['saidas_periodo'], (periodo_de, periodo_ate))
        do_banco = [{
            'ms': texto(l.get('REGISTRO_MS')),
            'lote': texto(l.get('NUM_LOTE')),
            'descricao': texto(l.get('PRODUTO')),
            'quantidade': numero(l.get('QUANTIDADE')),
            'venda': l.get('VENDA'),
        } for l in saidas]
        # só as VENDAS do XML entram aqui; entradas são outro balde
        vendas_xml = dados_xml['movimentos'].get('venda', {})
        divergencias = mapa_xml.comparar(vendas_xml, do_banco)
        periodo = '%s a %s' % (br(periodo_de), br(periodo_ate))
        for d in divergencias:
            d['periodo'] = periodo
            d['arquivo'] = dados_xml['arquivo']
        resultado['conferencia_xml'] = divergencias
        resumo_xml.update({
            'conferiu': True,
            'vendasNoBanco': len(do_banco),
            'totalNoBanco': round(sum(l['quantidade'] for l in do_banco), 3),
            'itensNoXml': len(vendas_xml),
            'totalNoXml': round(sum(i['quantidade'] for i in vendas_xml.values()), 3),
            'divergencias': len(divergencias),
        })
    else:
        resumo_xml['conferiu'] = False
        resumo_xml['porque'] = ('o agente não achou o XML da transmissão em %s'
                                % config.get('pasta_xml') if not dados_xml
                                else 'o XML não trouxe o período da transmissão')
    resultado['conferenciaXmlResumo'] = resumo_xml

    # ------------------------------------------------------------
    # 6. vendas com problema
    # ------------------------------------------------------------
    problemas = []
    try:
        for linha in consultar(conexao, CONSULTAS['vendas_problema'], (corte_data,)):
            if not linha.get('RECEITA'):
                motivo = 'sem_receita'
            elif not texto(linha.get('NUM_LOTE')):
                motivo = 'sem_lote'
            else:
                motivo = 'sem_ms'
            problemas.append({
                'venda': linha.get('VENDA'),
                'data': texto(linha.get('DATA')),
                'descricao': texto(linha.get('PRODUTO')),
                'ms': texto(linha.get('REGISTRO_MS')),
                'lote': texto(linha.get('NUM_LOTE')),
                'quantidade': numero(linha.get('QUANTIDADE')),
                'operador': texto(linha.get('VENDEDOR')),
                'motivo': motivo,
            })
    except Exception as e:
        registrar('Falha ao levantar vendas com problema: %s' % e)
    resultado['vendas_problema'] = problemas
    # a consulta corta por data: sem dizer desde quando, "nenhuma venda com
    # problema" parece valer para sempre
    resultado['vendasProblemaDesde'] = corte_data

    # acompanhamento das vendas; a tarefa de 5 minutos regrava só este ramo
    try:
        resultado['vendasRecentes'] = vendas_recentes(conexao)
        resultado['vendasRecentesEm'] = datetime.datetime.now().isoformat(timespec='seconds')
    except Exception as e:
        registrar('Falha ao levantar as vendas recentes: %s' % e)
    try:
        resultado['vendasSemReceita'] = vendas_sem_receita_pendentes(conexao, config)
    except Exception as e:
        registrar('Falha ao levantar as vendas sem receita: %s' % e)
    try:
        resultado['diagnostico'] = snapshot_diagnostico(conexao)
    except Exception as e:
        registrar('Falha ao montar o diagnóstico: %s' % e)

    # ------------------------------------------------------------
    # 7. saúde da sincronização com o site da ANVISA
    # ------------------------------------------------------------
    resultado['anvisa'] = estado_do_anvisa(config, inventario_em)
    # qual arquivo está rodando no servidor — sem isso, atualizar de longe é
    # pedir e torcer
    resultado['agente'] = versao_do_agente()

    # datas já arquivadas, para a aba Aceites
    pasta_enviados = os.path.join(config['pasta_xml'], 'enviados')
    if os.path.isdir(pasta_enviados):
        resultado['enviosConhecidos'] = sorted(
            n[6:16] for n in os.listdir(pasta_enviados)
            if n.lower().startswith('sngpc_') and n.lower().endswith('.xml'))[-60:]

    return resultado


def estado_do_anvisa(config, inventario_em):
    """O Anvisa.exe é automação de navegador e PARA no login do site.
    Aqui a gente só mede há quanto tempo ele não completa, para o app
    poder avisar quem precisa ir lá logar."""
    log = os.path.join(config['pasta_xml'], 'Anvisa', 'anvisa.log')
    ultima_conclusao = None
    ultima_tentativa = None
    if os.path.exists(log):
        try:
            with open(log, encoding='latin-1', errors='replace') as f:
                for linha in f:
                    if 'Aplicação iniciada' in linha:
                        ultima_tentativa = linha[:19]
                    if 'Processo de sincronização finalizado' in linha:
                        ultima_conclusao = linha[:19]
        except Exception as e:
            registrar('Não consegui ler o anvisa.log: %s' % e)

    dias = None
    if ultima_conclusao:
        try:
            d = datetime.datetime.strptime(ultima_conclusao[:10], '%d/%m/%Y').date()
            dias = (datetime.date.today() - d).days
        except ValueError:
            pass

    return {
        'ultimaTentativa': ultima_tentativa,
        'ultimaConclusao': ultima_conclusao,
        'diasSemSincronizar': dias,
        'inventarioEm': inventario_em,
        'precisaLogin': dias is None or dias > 1,
    }


def anterior(data_iso):
    if not data_iso:
        return None
    try:
        d = datetime.date.fromisoformat(str(data_iso)[:10])
    except ValueError:
        return None
    return (d - datetime.timedelta(days=1)).isoformat()


def br(data_iso):
    if not data_iso:
        return '—'
    p = str(data_iso)[:10].split('-')
    return '%s/%s/%s' % (p[2], p[1], p[0]) if len(p) == 3 else str(data_iso)


# ============================================================
# PUBLICAÇÃO
# ============================================================
def erro_de_permissao(e):
    """O Firebase devolve 401 'Permission denied' quando as REGRAS recusam a
    escrita — não é chave de serviço inválida nem internet fora."""
    return 'permission denied' in str(e).lower()


def recado_de_permissao(config):
    uid = config.get('uid_agente') or CONFIG_PADRAO['uid_agente']
    return (
        'O Firebase recusou a escrita em farmacia/inventario.\n'
        'Pelas regras, só escreve quem está cadastrado em farmacia/agentes:\n'
        '\n'
        '    farmacia/agentes/%s   precisa existir e valer true\n'
        '\n'
        'Console do Firebase > Realtime Database > aba Dados. O valor tem de ser\n'
        'o booleano true, sem aspas — "true" como texto não passa na regra.\n'
        'Confira também se o "uid_agente" do agente_config.json é exatamente\n'
        'esse nome. A chave de serviço não é passe livre: o agente entra com\n'
        'esse UID e as regras valem para ele igual valem para o app.' % uid)


def publicar(db, dados):
    db.reference('farmacia/inventario').set(dados)
    inventario = dados.get('inventario', {})
    registrar('Publicado: %d itens, %d divergências de XML, %d vendas com problema.' % (
        len(dados.get('itens', [])),
        len(dados.get('conferencia_xml', [])),
        len(dados.get('vendas_problema', [])),
    ))
    registrar('Saldo apurado por LOTES.%s (modo %s); inventário da ANVISA com %d lote(s).' % (
        inventario.get('colunaSaldo', '?'),
        inventario.get('modoSaldo', '?'),
        inventario.get('itens', 0),
    ))
    # Sem isto não dá para saber se a conta do movimento desde o envio teve
    # com o que trabalhar: pendentes zerados e divergência de pé significam
    # que o que foi transmitido não voltou no inventário.
    envio = dados.get('envio', {})
    resumo = dados.get('resumoPendentes', {})
    registrar('Pendentes de transmissão: %s. Ponteiros: venda %s, entrada %s.' % (
        ', '.join('%d %s' % (n, t) for t, n in sorted(resumo.items())) or 'nenhum',
        envio.get('ULT_SAIDA_VENDA_NOTA_ID', '?'),
        envio.get('ULT_ENTRADA_CAB_NOTA_ID', '?'),
    ))
    divergem = sum(1 for i in dados.get('itens', []) if i.get('motivo'))
    registrar('Divergências: %d de %d lote(s) publicados. Por tipo: %s.' % (
        divergem, len(dados.get('itens', [])),
        ', '.join('%d %s' % (n, t) for t, n in sorted(
            dados.get('resumoSaldo', {}).items())) or 'nenhuma',
    ))
    # o motivo é um só por item, e 'negativo' ganha de 'sem_ms': contar por
    # aqui é o único jeito de o controlado sem registro aparecer quando o
    # lote dele também está negativo — que foi como um deles passou meses
    # se movimentando fora do SNGPC
    # o ponteiro deste Digifarma não avançou, mas a ANVISA já recebeu: a
    # mesma venda é descontada duas vezes e a lista incha sem motivo. Pior
    # que o número errado é o risco do próximo envio daqui reenviar tudo.
    ja = dados.get('inventario', {}).get('jaNaAnvisa') or 0
    pendentes_vendas = (dados.get('resumoPendentes') or {}).get('vendas') or 0
    if ja and pendentes_vendas:
        registrar('ATENÇÃO: %d lote(s) já batem com a ANVISA SEM contar o movimento '
                  'pendente. O site já recebeu essas vendas e o ponteiro deste '
                  'Digifarma não avançou (envio feito por outra máquina?). As '
                  'divergências acima estão infladas, e transmitir por AQUI '
                  'escrituraria as %d venda(s) em dobro.' % (ja, pendentes_vendas))
        ids = sorted(int(numero(v['id'])) for v in
                     (dados.get('pendentes') or {}).get('vendas', []) if v.get('id'))
        if ids and not dados.get('envio', {}).get('ponteiroForcado'):
            registrar('As vendas na fila vão de %d a %d. Confirme com quem transmitiu '
                      'até qual delas foi, ponha esse número em '
                      'transmitido_ate_venda no agente_config.json, e os números '
                      'voltam ao certo enquanto o suporte não acerta o ponteiro.'
                      % (ids[0], ids[-1]))
    sem_ms = sum(1 for i in dados.get('itens', []) if not i.get('ms'))
    if sem_ms:
        registrar('%d lote(s) de controlado SEM registro M.S.: não são '
                  'escriturados, nem a entrada nem a venda. Use --produto '
                  'para achar o cadastro.' % sem_ms)


# ============================================================
# MODOS
# ============================================================
def modo_auto(config, data_inventario=None, usar_envio=False):
    db = conectar_firebase(config)
    conexao = conectar_firebird(config)
    try:
        dados = montar_inventario(conexao, config, data_inventario, usar_envio)
        publicar(db, dados)
    except Exception as e:
        if erro_de_permissao(e):
            registrar(recado_de_permissao(config))
        raise
    finally:
        fechar(conexao)


def publicar_vendas_recentes(config, db):
    """Regrava só o ramo das vendas, sem refazer a sincronização inteira.

    Escreve em farmacia/inventario/vendasRecentes: como a regra do banco
    libera farmacia/inventario para o agente, os filhos vêm junto e não é
    preciso mexer nas regras publicadas."""
    conexao = conectar_firebird(config)
    try:
        linhas = vendas_recentes(conexao)
        try:
            sem_receita = vendas_sem_receita_pendentes(conexao, config)
        except Exception as e:
            registrar('Não consegui levantar as vendas sem receita: %s' % e)
            sem_receita = None
        try:
            diagnostico = snapshot_diagnostico(conexao)
        except Exception as e:
            registrar('Não consegui montar o diagnóstico: %s' % e)
            diagnostico = None
    finally:
        fechar(conexao)
    agora_iso = datetime.datetime.now().isoformat(timespec='seconds')
    db.reference('farmacia/inventario/vendasRecentes').set(linhas)
    db.reference('farmacia/inventario/vendasRecentesEm').set(agora_iso)
    if sem_receita is not None:
        db.reference('farmacia/inventario/vendasSemReceita').set(sem_receita)
    # o diagnóstico sobe junto: é o que permite ver de fora do servidor por
    # que ainda há divergência, sem precisar estar na máquina
    if diagnostico is not None:
        db.reference('farmacia/inventario/diagnostico').set(diagnostico)
    registrar('Vendas recentes publicadas: %d linha(s); %s sem receita para o próximo envio.'
              % (len(linhas), len(sem_receita) if sem_receita is not None else '?'))
    return linhas


URL_AGENTE = ('https://raw.githubusercontent.com/jeffersontete-ui/FARMACIA'
              '/main/agente/agente_auto.py')

# Só estas chaves podem ser mudadas pelo app. Nada que aponte para arquivo,
# banco ou credencial entra aqui: o que se ajusta de longe é a leitura, não
# a instalação.
CONFIG_REMOTO = {
    'transmitido_ate_venda': 'inteiro',
    'coluna_saldo': 'texto',
    'modo_saldo': 'modo',
}


def versao_do_agente():
    """Tamanho e impressão digital do próprio arquivo. É o que diz, de fora,
    se o servidor está rodando a versão que a gente acha que está."""
    try:
        with open(os.path.abspath(__file__), 'rb') as f:
            dados = f.read()
        import hashlib
        return {'bytes': len(dados),
                'hash': hashlib.sha1(dados).hexdigest()[:12],
                'em': datetime.datetime.fromtimestamp(
                    os.path.getmtime(os.path.abspath(__file__))).isoformat(timespec='seconds')}
    except Exception:
        return {}


def atualizar_agente(config):
    """Baixa o agente do GitHub e se substitui.

    É o que tira a farmácia da obrigação de ir ao servidor a cada correção.
    Por isso mesmo, com cinto e suspensório: o arquivo baixado é conferido
    (tamanho, conteúdo e SINTAXE) antes de encostar no que está rodando, e o
    atual é guardado em backup. Se qualquer coisa falhar, nada é trocado —
    um agente quebrado num servidor onde ninguém está é pior do que um
    agente desatualizado."""
    import urllib.request
    url = config.get('url_atualizacao') or URL_AGENTE
    with urllib.request.urlopen(url, timeout=60) as resposta:
        novo = resposta.read().decode('utf-8')

    if len(novo) < 20000 or 'def principal(' not in novo or 'CONSULTAS' not in novo:
        raise RuntimeError('o arquivo baixado não parece o agente (%d bytes)' % len(novo))
    compile(novo, 'agente_auto.py', 'exec')  # erro de sintaxe morre aqui, não no servidor

    atual = os.path.abspath(__file__)
    antes = versao_do_agente()
    backup = os.path.join(PASTA, 'agente_auto_antes_de_%s.py'
                          % datetime.datetime.now().strftime('%Y-%m-%d_%H%M'))
    shutil.copy2(atual, backup)
    with open(atual, 'w', encoding='utf-8') as f:
        f.write(novo)

    depois = versao_do_agente()
    if depois.get('hash') == antes.get('hash'):
        return 'O agente já estava na versão mais nova (%s).' % antes.get('hash')
    return ('Agente atualizado: %s -> %s (%d bytes). Backup em %s. A próxima '
            'execução já roda a versão nova.'
            % (antes.get('hash'), depois.get('hash'), depois.get('bytes'),
               os.path.basename(backup)))


def linhas_do_lote_para_ajuste(conexao, info, ms, lote):
    """As linhas de LOTES daquele M.S. + lote, com o saldo de cada uma.

    A comparação agrupa por M.S. + lote, mas em LOTES isso pode ser mais de
    uma linha. Ajustar sem olhar isso escreveria num pedaço do saldo e
    deixaria o resto — por isso a lista vem inteira, e quem decide o que
    fazer com mais de uma é a função que chama."""
    sql = ("SELECT L.LOTE_ID, L.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, L.NUM_LOTE, "
           "L.%s AS SALDO FROM LOTES L JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID) "
           "WHERE UPPER(CAST(L.NUM_LOTE AS VARCHAR(500))) = ?" % info['coluna'])
    return [l for l in consultar(conexao, sql, (texto(lote).upper(),))
            if not ms or so_digitos(l.get('REGISTRO_MS')) == so_digitos(ms)]


def conferir_permissao_de_ajuste(config, info):
    """As duas travas que valem para qualquer escrita no Digifarma."""
    if not config.get('permitir_ajuste_estoque'):
        raise RuntimeError(
            'ajuste de estoque desligado. Para ligar, ponha '
            '"permitir_ajuste_estoque": true no agente_config.json, no servidor. '
            'É de propósito que isso não se liga pelo app.')
    if info['modo'] != 'saldo':
        # nesta instalação a coluna é de MOVIMENTO: cada linha é um
        # lançamento, e o saldo é a soma. Escrever nela não corrige saldo,
        # inventa um lançamento com valor arbitrário.
        raise RuntimeError(
            'nesta instalação a coluna %s é de movimento, não de saldo. '
            'Ajustar por aqui inventaria lançamento — corrija no Digifarma.'
            % info['coluna'])


def registrar_ajuste(db, dados):
    """Guarda o antes e o depois: no arquivo, no log e no Firebase.

    Escrita em banco de sistema fiscalizado sem rastro é o que transforma um
    acerto em problema seis meses depois, quando ninguém lembra o que mudou."""
    dados['em'] = datetime.datetime.now().isoformat(timespec='seconds')
    caminho = os.path.join(PASTA, 'ajustes_%s.json' % datetime.date.today().isoformat())
    try:
        anteriores = []
        if os.path.exists(caminho):
            with open(caminho, encoding='utf-8') as f:
                anteriores = json.load(f)
        anteriores.append(dados)
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(anteriores, f, indent=2, ensure_ascii=False)
    except Exception as e:
        registrar('Não consegui gravar o histórico do ajuste: %s' % e)
    registrar('AJUSTE NO DIGIFARMA: %s' % json.dumps(dados, ensure_ascii=False))
    try:
        db.reference('farmacia/ajustes').push(dados)
    except Exception as e:
        registrar('Não consegui publicar o ajuste: %s' % e)


def zerar_negativos(config, db, pedido):
    """Põe em ZERO os lotes com saldo negativo.

    É a única escrita com valor que não se escolhe: saldo negativo nunca é
    estoque, é lançamento errado, e o destino certo é sempre zero. Por isso
    ela é segura de fazer em lote — e por isso não aceita um valor vindo do
    celular, que é onde um dedo errado viraria estoque inventado."""
    alvo = texto(pedido.get('texto'))
    conexao = conectar_firebird(config)
    try:
        info = detectar_coluna_saldo(conexao, config)
        conferir_permissao_de_ajuste(config, info)

        sql = ("SELECT L.LOTE_ID, L.PRODUTO_ID, P.PRODUTO, P.REGISTRO_MS, "
               "L.NUM_LOTE, L.%s AS SALDO FROM LOTES L "
               "JOIN PRODUTOS P ON (P.PRODUTO_ID = L.PRODUTO_ID) "
               "WHERE L.%s < 0" % (info['coluna'], info['coluna']))
        negativos = consultar(conexao, sql)
        if alvo:
            chave = normalizar_texto(alvo)
            negativos = [l for l in negativos
                         if chave in normalizar_texto(l.get('PRODUTO'))
                         or chave in texto(l.get('NUM_LOTE')).upper()]
        if not negativos:
            return 'Nenhum lote negativo para zerar%s.' % (' em "%s"' % alvo if alvo else '')

        feitos, total = [], 0.0
        for linha in negativos:
            lote_id = linha.get('LOTE_ID')
            saldo = numero(linha.get('SALDO'))
            afetadas = executar(
                conexao,
                'UPDATE LOTES SET %s = 0 WHERE LOTE_ID = ? AND %s < 0'
                % (info['coluna'], info['coluna']),
                (lote_id,))
            if afetadas:
                total += saldo
                feitos.append({'loteId': lote_id, 'produtoId': linha.get('PRODUTO_ID'),
                               'produto': texto(linha.get('PRODUTO')),
                               'ms': so_digitos(linha.get('REGISTRO_MS')),
                               'lote': texto(linha.get('NUM_LOTE')),
                               'de': saldo, 'para': 0})
        registrar_ajuste(db, {
            'tipo': 'zerar_negativos', 'coluna': info['coluna'],
            'por': texto(pedido.get('pedidoPor')), 'filtro': alvo,
            'lotes': feitos, 'unidades': round(total, 3),
        })
        return ('%d lote(s) negativo(s) zerado(s), somando %g unidade(s). '
                'ATENÇÃO: este acerto NÃO pode ser transmitido ao SNGPC.'
                % (len(feitos), abs(round(total, 3))))
    finally:
        fechar(conexao)


def ajustar_lote(config, db, pedido):
    """Põe o saldo de UM lote no valor contado na prateleira.

    Recusa quando o mesmo M.S. + lote tem mais de uma linha em LOTES: aí não
    existe "o saldo do lote", e escolher em qual linha escrever seria chute
    do agente sobre o estoque da farmácia."""
    ms = so_digitos(pedido.get('ms'))
    lote = texto(pedido.get('lote'))
    contado = numero(pedido.get('quantidade'))
    if not lote:
        raise RuntimeError('diga qual lote')
    if contado < 0:
        raise RuntimeError('quantidade contada não pode ser negativa')

    conexao = conectar_firebird(config)
    try:
        info = detectar_coluna_saldo(conexao, config)
        conferir_permissao_de_ajuste(config, info)
        linhas = linhas_do_lote_para_ajuste(conexao, info, ms, lote)
        if not linhas:
            raise RuntimeError('lote %s não encontrado em LOTES' % lote)
        if len(linhas) > 1:
            raise RuntimeError(
                'o lote %s tem %d linhas em LOTES (saldos %s). Não dá para '
                'saber em qual escrever — este caso é no Digifarma.'
                % (lote, len(linhas),
                   ', '.join('%g' % numero(l.get('SALDO')) for l in linhas)))

        linha = linhas[0]
        antes = numero(linha.get('SALDO'))
        if antes == contado:
            return 'O lote %s já está com %g. Nada a fazer.' % (lote, contado)
        executar(conexao,
                 'UPDATE LOTES SET %s = ? WHERE LOTE_ID = ?' % info['coluna'],
                 (contado, linha.get('LOTE_ID')))
        registrar_ajuste(db, {
            'tipo': 'ajustar_lote', 'coluna': info['coluna'],
            'por': texto(pedido.get('pedidoPor')),
            'motivo': texto(pedido.get('motivo')) or 'contagem de prateleira',
            'lotes': [{'loteId': linha.get('LOTE_ID'),
                       'produtoId': linha.get('PRODUTO_ID'),
                       'produto': texto(linha.get('PRODUTO')),
                       'ms': so_digitos(linha.get('REGISTRO_MS')),
                       'lote': texto(linha.get('NUM_LOTE')),
                       'de': antes, 'para': contado}],
        })
        return ('%s lote %s: %g -> %g. Confira o total do produto na tela do '
                'Digifarma antes de fazer os outros.'
                % (texto(linha.get('PRODUTO'))[:40], lote, antes, contado))
    finally:
        fechar(conexao)


def aplicar_config(config, pedido):
    """Muda uma chave do agente_config.json a pedido do app.

    Só as chaves de CONFIG_REMOTO, e nenhuma delas escreve no Digifarma —
    mudam como o agente LÊ. O valor antigo volta na resposta: mexer na
    configuração de longe só é aceitável se ficar registrado o que era."""
    chave = texto(pedido.get('chave'))
    if chave not in CONFIG_REMOTO:
        raise RuntimeError('chave "%s" não pode ser mudada pelo app' % chave)

    bruto = pedido.get('valor')
    tipo = CONFIG_REMOTO[chave]
    if tipo == 'inteiro':
        # numero() devolve 0 para texto que não é número, e aqui isso seria
        # péssimo: "46l08" digitado errado viraria 0 em silêncio, desligando
        # o ajuste sem ninguém perceber. Melhor recusar.
        try:
            valor = int(str(bruto).strip())
        except (TypeError, ValueError):
            raise RuntimeError('%s só aceita número inteiro, e veio "%s"'
                               % (chave, bruto))
        if valor < 0:
            raise RuntimeError('%s não aceita número negativo' % chave)
    elif tipo == 'modo':
        valor = texto(bruto).lower()
        if valor not in ('auto', 'saldo', 'movimento'):
            raise RuntimeError('modo_saldo aceita auto, saldo ou movimento')
    else:
        valor = texto(bruto).upper()

    atual = {}
    if os.path.exists(ARQUIVO_CONFIG):
        with open(ARQUIVO_CONFIG, encoding='utf-8') as f:
            atual = json.load(f)
    antigo = atual.get(chave, CONFIG_PADRAO.get(chave))
    atual[chave] = valor
    with open(ARQUIVO_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(atual, f, indent=2, ensure_ascii=False)
    config[chave] = valor
    return '%s: %s -> %s' % (chave, antigo, valor)


def modo_config(par):
    """--config chave=valor, para não precisar editar JSON à mão.

    Uma vírgula fora do lugar no agente_config.json derruba o agente inteiro,
    e quem está no servidor às pressas não é a pessoa certa para editar JSON.
    Aceita as chaves do app mais permitir_ajuste_estoque — essa só por aqui,
    porque ligar a escrita no Digifarma tem que ser um ato local."""
    if '=' not in texto(par):
        print('Use assim: --config transmitido_ate_venda=46108')
        print('Chaves: %s, permitir_ajuste_estoque'
              % ', '.join(sorted(CONFIG_REMOTO)))
        return False

    chave, _, bruto = texto(par).partition('=')
    chave, bruto = chave.strip(), bruto.strip()
    config = carregar_config()

    if chave == 'permitir_ajuste_estoque':
        valor = bruto.lower() in ('true', 'sim', 's', '1', 'on')
        antigo = config.get(chave, False)
        config[chave] = valor
        with open(ARQUIVO_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print('permitir_ajuste_estoque: %s -> %s' % (antigo, valor))
        if valor:
            print('A escrita no Digifarma está LIGADA: o app pode zerar lote')
            print('negativo e gravar contagem. Toda alteração fica registrada.')
        return True

    try:
        print(aplicar_config(config, {'chave': chave, 'valor': bruto}))
    except Exception as e:
        print('Não deu: %s' % e)
        return False
    return True


def texto_do_modo(funcao, *argumentos):
    """Roda um dos modos de linha de comando e devolve o que ele imprimiria.

    Os modos foram escritos para o terminal; em vez de duplicá-los numa
    versão "para o app", captura-se a saída. Assim o que aparece no celular
    é exatamente o que apareceria no servidor — sem duas verdades."""
    import contextlib
    import io
    balde = io.StringIO()
    with contextlib.redirect_stdout(balde):
        funcao(*argumentos)
    return balde.getvalue()


RELATORIOS = {
    'tarefas': lambda config, alvo: texto_do_modo(modo_tarefas, config),
    'negativos': lambda config, alvo: texto_do_modo(modo_negativos, config, alvo),
    'comparacao': lambda config, alvo: texto_do_modo(modo_comparacao, config, alvo),
    'resumo': lambda config, alvo: texto_do_modo(modo_resumo, config),
    'inventario': lambda config, alvo: texto_do_modo(modo_inventario, config),
    'produto': lambda config, alvo: texto_do_modo(modo_produto, config, alvo),
    'saldo': lambda config, alvo: texto_do_modo(modo_conferir_saldo, config, alvo),
    'colunas': lambda config, alvo: texto_do_modo(modo_colunas, config, alvo or 'LOTES'),
    'totais': lambda config, alvo: texto_do_modo(modo_totais, config, alvo),
}

LIMITE_TEXTO = 120000    # o relatório inteiro cabe; o corte é rede de segurança
LIMITE_HTML = 600000


def publicar_relatorio(db, acao, texto_saida, extras=None):
    """Grava o relatório em farmacia/relatorios/<acao>, para o app mostrar."""
    corpo = {
        'texto': texto_saida[:LIMITE_TEXTO],
        'cortado': len(texto_saida) > LIMITE_TEXTO,
        'em': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    corpo.update(extras or {})
    db.reference('farmacia/relatorios/%s' % acao).set(corpo)


def atender_pedido(config, db, pedido):
    """Um pedido do app. Devolve o recado que vai para a tela."""
    acao = texto(pedido.get('acao'))
    alvo = texto(pedido.get('texto'))

    if acao in ('sincronizar_vendas', 'atualizar_envio'):
        modo_auto(config, usar_envio=(acao == 'atualizar_envio'))
        return 'Sincronização concluída.'

    if acao == 'atualizar_agente':
        return atualizar_agente(config)

    if acao == 'zerar_negativos':
        return zerar_negativos(config, db, pedido)

    if acao == 'ajustar_lote':
        return ajustar_lote(config, db, pedido)

    if acao == 'config':
        recado = aplicar_config(config, pedido)
        # a mudança só aparece nos números depois de recalcular
        modo_auto(config)
        return recado

    if acao in RELATORIOS:
        saida = RELATORIOS[acao](config, alvo)
        extras = {'filtro': alvo} if alvo else {}
        if acao == 'comparacao':
            caminho = os.path.join(
                PASTA, 'comparacao_%s.html' % datetime.date.today().isoformat())
            try:
                with open(caminho, encoding='utf-8') as f:
                    html = f.read()
                if len(html) <= LIMITE_HTML:
                    extras['html'] = html
                else:
                    extras['htmlGrande'] = len(html)
            except Exception as e:
                registrar('Não consegui ler a folha para publicar: %s' % e)
        publicar_relatorio(db, acao, saida, extras)
        return 'Relatório "%s" pronto.' % acao

    raise RuntimeError('não sei atender "%s"' % acao)


def modo_fila(config):
    """Atende os botões do app E atualiza as vendas. Roda de 5 em 5 minutos."""
    db = conectar_firebase(config)

    # antes da fila: as vendas sobem toda vez, mesmo sem ninguém pedir nada.
    # É isto que faz o acompanhamento ser de 5 em 5 minutos sem obrigar a
    # sincronização completa, que é cara e roda de hora em hora.
    try:
        publicar_vendas_recentes(config, db)
    except Exception as e:
        if erro_de_permissao(e):
            registrar(recado_de_permissao(config))
        registrar('Não consegui publicar as vendas recentes: %s' % e)

    ref = db.reference('farmacia/comando')
    pedido = ref.get()
    if not pedido or pedido.get('estado') != 'pendente':
        registrar('Fila vazia.')
        return

    acao = pedido.get('acao')
    registrar('Atendendo "%s" pedido por %s.' % (acao, pedido.get('pedidoPor')))
    try:
        recado = atender_pedido(config, db, pedido)
        registrar(recado)
        ref.update({
            'estado': 'concluido',
            'mensagem': recado[:300],
            'concluidoEm': datetime.datetime.now().isoformat(timespec='seconds'),
        })
    except Exception as e:
        registrar('Falhou: %s' % e)
        ref.update({
            'estado': 'erro',
            'mensagem': str(e)[:300],
            'concluidoEm': datetime.datetime.now().isoformat(timespec='seconds'),
        })
        raise


def modo_schema(config):
    """Confere se as tabelas que as consultas usam existem na base."""
    conexao = conectar_firebird(config)
    try:
        existentes = {linha['RDB$RELATION_NAME'].strip().upper() for linha in consultar(
            conexao,
            "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0")}
        faltando = [t for t in TABELAS_ESPERADAS if t not in existentes]
        for tabela in TABELAS_ESPERADAS:
            print(('  OK   ' if tabela in existentes else '  FALTA') + '  ' + tabela)

        if 'LOTES' in existentes:
            try:
                info = detectar_coluna_saldo(conexao, config)
                print('\n  coluna de saldo em LOTES: %s (modo %s)'
                      % (info['coluna'], info['modo']))
                print('  expressão somada: SUM(%s)' % montar_expressao_saldo(info))
                if info['modo'] == 'movimento':
                    print('  -> a coluna é quantidade de movimento, não saldo:')
                    print('     o saldo desconta vendas (ITEM_VENDAS_LOTES) e perdas.')
                    print('     Confira um lote com: python agente_auto.py --saldo NOME')
            except Exception as e:
                print('\n  %s' % e)

        if 'INVENTARIO_SNGPC' in existentes:
            campos = colunas_da_tabela(conexao, 'INVENTARIO_SNGPC')
            print('  colunas de INVENTARIO_SNGPC: %s' % ', '.join(campos))
            print('  colunas escolhidas: %s' % ', '.join(
                '%s=%s' % (k, escolher_campo(campos, r) or '(nenhuma)')
                for k, r in CAMPOS_INVENTARIO.items()))
        else:
            print('\n  INVENTARIO_SNGPC não existe ainda — ela só aparece depois')
            print('  que o Anvisa.exe rodar uma vez e trazer o inventário do site.')

        if faltando:
            print('\nTabelas parecidas na base, para ajustar o bloco CONSULTAS:')
            for t in faltando:
                raiz = t.split('_')[0][:5]
                parecidas = sorted(x for x in existentes if raiz in x)[:8]
                print('  %s -> %s' % (t, ', '.join(parecidas) or 'nenhuma'))
        else:
            print('\nTodas as tabelas esperadas existem.')
        return not faltando
    finally:
        fechar(conexao)


def modo_colunas(config, tabela):
    """Lista as colunas de uma tabela — para conferir um nome sem abrir o IBExpert."""
    conexao = conectar_firebird(config)
    try:
        campos = colunas_da_tabela(conexao, tabela)
        if not campos:
            print('Tabela %s não encontrada.' % tabela.upper())
            return False
        print('%s:' % tabela.upper())
        for c in campos:
            print('  ' + c)
        return True
    finally:
        fechar(conexao)


def modo_conferir_saldo(config, filtro):
    """Mostra, para os lotes que casam com o texto, COMO o saldo foi apurado:
    as linhas cruas de LOTES, a soma de cada coluna candidata, as baixas e o
    que a ANVISA tem. É com isto que se confere o número contra a tela do
    Digifarma antes de confiar no app."""
    conexao = conectar_firebird(config)
    try:
        info = detectar_coluna_saldo(conexao, config)
        print('coluna de saldo: %s (modo %s)' % (info['coluna'], info['modo']))
        print('expressão somada: SUM(%s)\n' % montar_expressao_saldo(info))

        candidatas = [c for c in (COLUNAS_SALDO + COLUNAS_MOVIMENTO) if c in info['campos']]
        colunas = ['NUM_LOTE'] + candidatas
        if 'ENTRADA_SAIDA' in info['campos']:
            colunas.append('ENTRADA_SAIDA')
        sql = CONSULTAS['lotes_detalhe'].replace(
            '{COLUNAS}', ', '.join('L.%s' % c for c in colunas))

        alvo = '%' + str(filtro or '').strip().upper() + '%'
        linhas = consultar(conexao, sql, (alvo, alvo, alvo))
        if not linhas:
            print('Nenhum lote casa com "%s".' % filtro)
            return False

        baixas = baixas_por_lote(conexao)
        por_lote = {}
        for linha in linhas[:4000]:
            chave = (so_digitos(linha.get('REGISTRO_MS')), texto(linha.get('NUM_LOTE')).upper())
            grupo = por_lote.setdefault(chave, {
                'produto': texto(linha.get('PRODUTO')), 'linhas': 0,
                'entradas': 0.0, 'saidas': 0.0,
                'colunas': dict.fromkeys(candidatas, 0.0),
            })
            grupo['linhas'] += 1
            saida = texto(linha.get('ENTRADA_SAIDA')).upper() == 'S'
            for c in candidatas:
                grupo['colunas'][c] += numero(linha.get(c))
            quantidade = numero(linha.get(info['coluna']))
            grupo['saidas' if saida else 'entradas'] += quantidade

        saldo_anvisa, inventario_em, campos_anvisa, fora_do_criterio = ler_inventario_anvisa(conexao)
        print('inventário da ANVISA: %d lote(s), colunas %s, carimbo %s' % (
            len(saldo_anvisa),
            ', '.join('%s=%s' % (k, v) for k, v in sorted((campos_anvisa or {}).items()) if v)
            or '(nenhuma reconhecida)',
            inventario_em or '(sem data)'))
        if fora_do_criterio:
            print('  (%d linha(s) fora do critério psicotrópico/antimicrobiano)'
                  % fora_do_criterio)
        print('')

        ordenados = sorted(por_lote.items(), key=lambda x: -abs(x[1]['entradas']))
        if len(ordenados) > 40:
            print('%d lotes casam com "%s"; mostrando os 40 maiores.\n'
                  % (len(ordenados), filtro))
        for chave, g in ordenados[:40]:
            print('%s  |  M.S. %s  |  lote %s' % (g['produto'], chave[0] or '—', chave[1] or '—'))
            print('  linhas em LOTES: %d   entradas %g   saídas %g'
                  % (g['linhas'], g['entradas'], g['saidas']))
            print('  somas por coluna: %s'
                  % ', '.join('%s=%g' % (c, v) for c, v in g['colunas'].items()))
            baixado = baixas.get(chave, 0.0)
            # a conta aqui tem que ser a MESMA de montar_expressao_saldo:
            # no modo 'saldo' a linha de saída não é saldo e fica de fora
            saldo = g['entradas']
            if info['modo'] == 'movimento':
                print('  baixas fora de LOTES (vendas + perdas): %g' % baixado)
                saldo -= g['saidas'] + baixado
            print('  SALDO PUBLICADO: %g     ANVISA: %g'
                  % (round(saldo, 3), round(saldo_anvisa.get(chave, 0.0), 3)))
            # a tela do Digifarma mostra o produto, não o lote
            irmaos = [c for c in por_lote if c[0] == chave[0]]
            if len(irmaos) > 1:
                print('  este M.S. tem %d lotes; a tela do Digifarma soma todos\n'
                      % len(irmaos))
            else:
                print('')
        print('Se o SALDO PUBLICADO não bater com a tela do Digifarma, fixe a coluna')
        print('certa em agente_config.json ("coluna_saldo" e "modo_saldo").')
        return True
    finally:
        fechar(conexao)


def chave_frouxa(chave):
    """A chave da comparação sem os enfeites do número de lote: só letra e
    número, sem zero à esquerda. '00036467' e '36467' viram a mesma coisa.
    Serve para MEDIR quantas divergências são só jeito de escrever o lote —
    não é usada na comparação de verdade, que continua exata."""
    ms, lote = chave
    return (ms, ''.join(c for c in lote if c.isalnum()).lstrip('0'))


FOLHA_ESTILO = """
  @page { size: A4 portrait; margin: 14mm 12mm; }
  * { box-sizing: border-box; }
  body { font: 11px/1.4 Arial, Helvetica, sans-serif; color: #000; margin: 0; }
  h1 { font-size: 16px; margin: 0 0 2px; }
  .sub { font-size: 10.5px; color: #444; margin: 0 0 10px; }
  .aviso { border: 1px solid #000; padding: 6px 8px; margin: 0 0 10px; font-size: 10.5px; }
  table { width: 100%; border-collapse: collapse; }
  thead { display: table-header-group; }   /* repete o cabeçalho a cada página */
  tr { page-break-inside: avoid; }
  th, td { border-bottom: 1px solid #BBB; padding: 4px 5px; text-align: left;
           vertical-align: top; }
  th { border-bottom: 1.5px solid #000; font-size: 9.5px; text-transform: uppercase;
       letter-spacing: .04em; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .contar { width: 62px; border-bottom: 1px solid #BBB; }
  .med td { background: #EEE; border-top: 1.5px solid #000; padding-top: 6px; }
  .med .ms { font-weight: normal; font-size: 9.5px; color: #444; }
  .lote .rec { padding-left: 16px; }
  .lote.bate td { color: #555; }        /* já bate: fica, mas não chama */
  .secao h2 { font-size: 13px; margin: 0 0 6px; border-bottom: 2px solid #000;
              padding-bottom: 3px; }
  .secao h3 { font-size: 11.5px; margin: 20px 0 2px; page-break-after: avoid; }
  .movimento { margin-top: 4px; }
  .movimento td { font-size: 10.5px; }
  .movimento .semlote td { font-weight: 700; }
  .secao h2 .conta { float: right; font-weight: normal; font-size: 10px;
                     color: #444; padding-top: 3px; }
  /* cada lista começa em página nova: dá para conferir as duas ao mesmo
     tempo, em duas mãos diferentes */
  .quebra { page-break-before: always; }
  .rodape { margin-top: 18px; font-size: 10px; color: #444;
            page-break-inside: avoid; }
  .vazio { border: 1px solid #000; padding: 10px; }
  .assinatura { margin-top: 22px; border-top: 1px solid #000; width: 62%;
                padding-top: 4px; font-size: 10px; page-break-inside: avoid; }
  @media print { .naoimprime { display: none; } }
"""


def escapar_html(valor):
    return (texto(valor).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


NOME_MOVIMENTO = {'vendas': 'Venda', 'entradas': 'Entrada',
                  'perdas': 'Perda', 'transferencias': 'Transferência'}


def bloco_movimento(movimentos):
    """O que se moveu depois do último envio: venda, entrada, perda.

    Sem esta lista a folha parece errada. O inventário do SNGPC é a FOTO do
    último envio e a prateleira é de agora: o que foi vendido hoje já saiu da
    prateleira e ainda está na foto. Quem conta encontra a caixa faltando e
    marca divergência de uma venda que está certa. Aqui estão, com número da
    venda, hora, lote e quantidade, para dar baixa no papel na hora."""
    if not movimentos:
        return ('<p class="sub">Nenhuma venda, entrada ou perda desta lista '
                'desde o último envio — a foto do SNGPC ainda vale como está.</p>')
    linhas = []
    sem_lote = 0
    for m in movimentos:
        # sem lote não entra na conta de lote nenhum: aparece na lista, mas
        # marcado, senão a soma da coluna Movim. não fecha com este anexo —
        # e o lançamento sem lote é problema por si só, o SNGPC exige o lote
        if not texto(m.get('lote')):
            sem_lote += 1
        linhas.append(
            '<tr%s><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td class="num">%s</td></tr>' % (
                ' class="semlote"' if not texto(m.get('lote')) else '',
                br(m['data']) if m.get('data') else '—',
                (' %s' % escapar_html(m['hora'])) if m.get('hora') else '',
                escapar_html(NOME_MOVIMENTO.get(m['tipo'], m['tipo'])),
                escapar_html(m.get('id')) or '—',
                escapar_html(m.get('descricao'))[:42] or '—',
                escapar_html(m.get('lote')) or '(sem lote) *',
                '%+g' % m['assinado']))
    return """<h3>Movimento desde o último envio &mdash; %d lançamento(s)</h3>
<p class="sub">Já saiu (ou entrou) na prateleira e ainda <strong>não</strong> está
no inventário do SNGPC. A coluna Movim. da tabela acima é a soma disto, lote a lote.</p>
<table class="movimento">
<thead><tr>
  <th>Data e hora</th><th>Tipo</th><th>Nº</th><th>Medicamento</th><th>Lote</th>
  <th class="num">Qtd.</th>
</tr></thead>
<tbody>
%s
</tbody></table>%s""" % (len(movimentos), '\n'.join(linhas),
                         ('\n<p class="sub">* %d lançamento(s) sem lote: não entram '
                          'na coluna Movim. porque não há em qual lote somar, e o '
                          'SNGPC exige o lote. Corrija no Digifarma antes do envio.</p>'
                          % sem_lote) if sem_lote else '')


def bloco_sem_prateleira(medicamentos):
    """Medicamento cujo ÚNICO lote está negativo.

    Não tem uma linha para conferir: o saldo que o Digifarma conhece não
    existe. Mas a caixa pode estar na prateleira, vinda de uma entrada que
    nunca foi lançada — e é o lote impresso NA CAIXA que diz qual nota
    procurar. Por isso aqui os campos vão em branco: quem conta escreve o
    lote e a quantidade que achou, ou risca se não achou nada."""
    if not medicamentos:
        return ''
    linhas = []
    for m in medicamentos:
        linhas.append(
            '<tr><td><strong>%s</strong><br><span class="ms">M.S. %s · '
            'Digifarma diz %+g no lote %s</span></td>'
            '<td class="contar"></td><td class="contar"></td>'
            '<td class="contar"></td></tr>' % (
                escapar_html(m['descricao'])[:62], escapar_html(formatar_ms(m['ms'])),
                m['negativo'], escapar_html(', '.join(m['lotes'])[:40]) or '—'))
    return """<h3>Sem lote para conferir &mdash; %d medicamento(s)</h3>
<p class="sub">O único saldo que o Digifarma tem destes é negativo, então não há
linha para conferir. Procure na prateleira: se houver caixa, <strong>copie o lote
da caixa</strong> — é ele que diz qual nota de entrada nunca foi lançada. Se não
houver nada, risque.</p>
<table>
<thead><tr>
  <th>Medicamento</th><th>Lote na caixa</th><th>Validade</th><th>Quantidade</th>
</tr></thead>
<tbody>
%s
</tbody></table>""" % (len(medicamentos), '\n'.join(linhas))


def bloco_conferencia(titulo, medicamentos, quebra=False, nota='', movimentos=None,
                      sem_prateleira=None):
    """Uma lista da folha: o título da classe e a tabela dos medicamentos
    dela, em ordem alfabética, cada um com os seus lotes embaixo, e no fim o
    movimento do dia que ainda não subiu ao SNGPC."""
    linhas = []
    lotes = 0
    for m in medicamentos:
        lotes += len(m['lotes'])
        linhas.append(
            '<tr class="med"><td><strong>%s</strong><br><span class="ms">M.S. %s</span>%s</td>'
            '<td></td><td class="num">%g</td><td class="num">%g</td>'
            '<td class="num">%s</td><td class="num">%g</td>'
            '<td class="num">%s</td><td class="contar"></td></tr>' % (
                escapar_html(m['descricao'])[:62], escapar_html(formatar_ms(m['ms'])),
                ('<span class="ms"> · %d lote(s) negativo(s) fora desta folha, '
                 'somando %+g: conte este medicamento para decidir o acerto</span>'
                 % (m['omitidos'], m['negativo'])) if m['omitidos'] else '',
                m['digifarma'], m['sngpc'],
                ('%+g' % m['movimento']) if m['movimento'] else '—',
                m['esperado'],
                # total do medicamento batendo com lotes divergentes é o
                # caso mais informativo da folha: o estoque existe, o que
                # está errado é em qual lote ele foi lançado
                ('%+g' % round(m['digifarma'] - m['esperado'], 3))
                if round(m['digifarma'] - m['esperado'], 3) else 'total bate'))
        for l in m['lotes']:
            bate = ' bate' if not numero(l.get('diferenca')) else ''
            movido = numero(l.get('movimentoDesdeEnvio'))
            linhas.append(
                '<tr class="lote%s"><td class="rec">lote %s</td><td>%s</td>'
                '<td class="num">%g</td><td class="num">%g</td><td class="num">%s</td>'
                '<td class="num">%g</td><td class="num">%s</td>'
                '<td class="contar"></td></tr>' % (
                    bate, escapar_html(l['lote']) or '—',
                    br(l['validade']) if l['validade'] else '—',
                    numero(l['saldoDigifarma']), numero(l['saldoSngpc']),
                    ('%+g' % movido) if movido else '—',
                    numero(l.get('esperadoSngpc', l['saldoSngpc'])),
                    ('%+g' % numero(l['diferenca'])) if numero(l['diferenca']) else '—'))

    return """<section class="secao%s">
<h2>%s <span class="conta">%d medicamento(s), %d lote(s)</span></h2>
%s<table>
<thead><tr>
  <th>Medicamento &middot; lote</th><th>Validade</th>
  <th class="num">Digifarma</th><th class="num">SNGPC<br>(envio)</th>
  <th class="num">Movim.</th><th class="num">Esperado</th>
  <th class="num">Dif.</th><th>Contado</th>
</tr></thead>
<tbody>
%s
</tbody></table>
%s
%s
<p class="assinatura">Conferido por __________________________________ em ____/____/______</p>
</section>""" % (
        ' quebra' if quebra else '', escapar_html(titulo),
        len(medicamentos), lotes,
        ('<p class="sub">%s</p>' % escapar_html(nota)) if nota else '',
        '\n'.join(linhas),
        bloco_sem_prateleira(sem_prateleira or []),
        bloco_movimento(movimentos or []))


def modo_comparacao(config, filtro=''):
    """Gera a comparação Digifarma × SNGPC em HTML, para imprimir.

    Fica de fora o lote com saldo NEGATIVO: negativo é lançamento errado, não
    estoque, e quem for conferir prateleira com o papel na mão perde tempo
    com linha que não existe. Quantos ficaram de fora sai no cabeçalho —
    sumir em silêncio seria esconder trabalho, não poupar."""
    conexao = conectar_firebird(config)
    try:
        dados = montar_inventario(conexao, config)
    finally:
        fechar(conexao)

    todos = dados.get('itens', [])
    negativos = [i for i in todos if i.get('motivo') == 'negativo']
    sem_ms = [i for i in todos if i.get('motivo') == 'sem_ms']

    # Agrupado por MEDICAMENTO, não por lote solto: quem confere vai à
    # prateleira, acha o remédio e conta as caixas. Para a conta fechar
    # precisa ver TODOS os lotes dele, inclusive os que batem — foi
    # exatamente isso que faltou na pregabalina, com 6 no app e 9 na tela.
    por_ms = {}
    for i in todos:
        if i.get('motivo') == 'sem_ms':
            continue
        por_ms.setdefault((i['ms'], i['descricao']), []).append(i)

    medicamentos, sem_prateleira = [], []
    for (ms, descricao), lotes in por_ms.items():
        # lote negativo não está na prateleira: é lançamento errado, e mandar
        # alguém procurar por ele é desperdiçar a conferência
        visiveis = [l for l in lotes if numero(l['saldoDigifarma']) >= 0]
        se_conta = [l for l in visiveis
                    if l.get('motivo') and l['motivo'] not in ('negativo', 'sem_ms')]
        # Medicamento com lote NEGATIVO entra mesmo que os lotes visíveis
        # batam. O negativo diz que o lançamento está errado, e só a
        # contagem decide de que lado: se a prateleira tem o que o irmão
        # mostra, falta lançar; se tem menos, a baixa foi no lote errado e a
        # ANVISA está sobrando. Sem contar, não dá para escolher o conserto —
        # foi o que aconteceu com a lamotrigina, fora da folha com −7 abertos.
        negativos_do_ms = len(lotes) - len(visiveis)
        if filtro:
            alvo = normalizar_texto(filtro)
            if alvo not in normalizar_texto(descricao) and not any(alvo in l['lote'] for l in lotes):
                continue
        classe_do_ms = ''
        for l in lotes:
            if l.get('classe'):
                classe_do_ms = l['classe']
                break
        # medicamento cujo ÚNICO lote é negativo não tem linha para conferir,
        # mas a caixa pode estar na prateleira: vai para um bloco à parte,
        # com os campos em branco, para quem contar copiar o lote da caixa
        if not visiveis:
            sem_prateleira.append({
                'ms': ms, 'descricao': descricao, 'classe': classe_do_ms,
                'lotes': sorted(l['lote'] for l in lotes),
                'negativo': round(sum(numero(l['saldoDigifarma']) for l in lotes), 3),
            })
            continue
        if not se_conta and not negativos_do_ms:
            continue
        medicamentos.append({
            'ms': ms, 'descricao': descricao, 'classe': classe_do_ms,
            'lotes': sorted(visiveis, key=lambda l: l['lote']),
            'omitidos': negativos_do_ms,
            # quanto os lotes negativos somam: é o tamanho do acerto que a
            # contagem vai decidir, e sem ele a folha manda contar sem dizer
            # o que está em jogo
            'negativo': round(sum(numero(l['saldoDigifarma']) for l in lotes
                                  if numero(l['saldoDigifarma']) < 0), 3),
            'digifarma': round(sum(numero(l['saldoDigifarma']) for l in visiveis), 3),
            'sngpc': round(sum(numero(l['saldoSngpc']) for l in visiveis), 3),
            # o que se moveu depois do envio, e o que o SNGPC teria hoje se
            # já tivesse recebido esse movimento. É contra o ESPERADO que a
            # contagem da prateleira fecha — a foto do envio já está velha.
            'movimento': round(sum(numero(l.get('movimentoDesdeEnvio'))
                                   for l in visiveis), 3),
            'esperado': round(sum(numero(l.get('esperadoSngpc', l['saldoSngpc']))
                                  for l in visiveis), 3),
        })
    # ordem alfabética pelo nome, sem acento e sem caixa — é assim que o
    # medicamento é procurado na prateleira
    medicamentos.sort(key=lambda m: normalizar_texto(m['descricao']))
    sem_prateleira.sort(key=lambda m: normalizar_texto(m['descricao']))

    inventario = dados.get('inventario', {})
    envio = dados.get('envio', {})

    # Psicotrópico e antimicrobiano são duas escriturações e duas
    # conferências: saem em listas separadas, cada uma começando em página
    # nova, para poderem ser conferidas por pessoas diferentes ao mesmo tempo.
    # cada lista repete de onde saiu: a segunda folha vai para outra mão, e
    # papel sem data não serve de conferência
    origem = 'Inventário do SNGPC de %s · gerado em %s' % (
        br(inventario.get('data')) if inventario.get('data') else '(sem data)',
        datetime.datetime.now().strftime('%d/%m/%Y %H:%M'))

    # o movimento que ainda não subiu, em ordem de acontecido — é o que
    # explica a prateleira não bater com a foto do último envio
    movimentos = []
    for tipo, linhas_tipo in (dados.get('pendentes') or {}).items():
        sinal = 1 if tipo == 'entradas' else -1
        for p in linhas_tipo:
            movimentos.append(dict(p, tipo=tipo,
                                   assinado=round(sinal * numero(p['quantidade']), 3)))
    movimentos.sort(key=lambda p: (texto(p.get('data')), texto(p.get('hora')),
                                   normalizar_texto(p.get('descricao'))))

    # a lista do movimento segue a classe do MEDICAMENTO na folha; só quando
    # ele não está na folha é que vale a classe que o agente carimbou
    classe_na_folha = {m['ms']: m['classe'] for m in medicamentos}

    def classe_do_movimento(p):
        return classe_na_folha.get(so_digitos(p['ms']), p.get('classe') or '')

    secoes = []
    conferir = []
    for classe in CLASSES + ('',):
        do_grupo = [m for m in medicamentos if m['classe'] == classe]
        # a lista pode existir só por causa dos medicamentos sem lote para
        # conferir: são trabalho igual, e sumiriam se o corte fosse só o
        # do_grupo
        if not do_grupo and not any(m['classe'] == classe for m in sem_prateleira):
            continue
        for m in do_grupo:
            conferir.extend(m['lotes'])
        # a primeira lista já tem a data no cabeçalho da folha; a partir da
        # segunda a página é outra, e repetir é o que faz a folha solta valer
        nota = origem if secoes else ''
        if not classe:
            nota = ((nota + ' · ') if nota else '') + (
                'classe não marcada no cadastro do Digifarma: estes não '
                'entraram em nenhuma das duas listas.')
        # o filtro da linha de comando também vale para o movimento: folha
        # de um medicamento só com a venda de outro em anexo é ruído
        do_grupo_ms = {m['ms'] for m in do_grupo}
        secoes.append(bloco_conferencia(
            NOME_CLASSE[classe], do_grupo, quebra=bool(secoes), nota=nota,
            sem_prateleira=[m for m in sem_prateleira if m['classe'] == classe],
            movimentos=[p for p in movimentos
                        if (classe_do_movimento(p) == classe
                            and (not filtro or so_digitos(p['ms']) in do_grupo_ms))]))

    fora = []
    if negativos:
        fora.append('%d lote(s) com saldo NEGATIVO no Digifarma' % len(negativos))
    if sem_ms:
        fora.append('%d lote(s) sem registro M.S. no cadastro' % len(sem_ms))

    html = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Conferência Digifarma × SNGPC</title>
<style>%s</style></head><body>
<h1>Conferência Digifarma &times; SNGPC</h1>
<p class="sub">Inventário do SNGPC de %s &middot; último envio em %s &middot;
saldo por LOTES.%s &middot; gerado em %s</p>
%s
%s
<p class="aviso"><strong>Medicamento com lote negativo &mdash; o que fazer com a
contagem.</strong> Não se corrige o lote de uma venda já transmitida, então o
acerto é no estoque, e a contagem diz qual dos dois:<br>
&bull; <strong>contou igual ao SNGPC</strong> &rarr; zere só o(s) lote(s)
negativo(s) e <strong>não encoste no lote cheio</strong>. Os três lados passam a
bater. <strong>Esse acerto NÃO vai para a ANVISA</strong>: ela já está certa, e
transmitir faria o saldo dela subir indevidamente.<br>
&bull; <strong>contou menos que o SNGPC</strong> &rarr; a baixa foi no lote
errado: acerte o lote cheio para o valor contado, zere o negativo, e a diferença
que sobrar contra a ANVISA precisa ser regularizada com ela.</p>
<p class="rodape"><strong>A conta é esta:</strong> SNGPC (foto do último envio)
+ Movim. (o que se moveu depois, e ainda não subiu) = Esperado. A diferença é
<strong>Digifarma &minus; Esperado</strong>, nunca contra a foto do envio — senão
toda venda de hoje vira divergência. O movimento vem detalhado no fim de cada
lista, com número da venda, hora, lote e quantidade.<br>
%d medicamento(s), %d lote(s) no total. Psicotrópicos e antimicrobianos saem em
listas separadas, cada uma em página nova, e dentro de cada lista os
medicamentos vêm em ordem alfabética. A linha em cinza é o medicamento, com a
soma dos lotes abaixo dela — é esse total que aparece na tela do Digifarma. As
linhas seguintes são os lotes, e o SNGPC guarda o estoque assim, lote a lote. Os
lotes que já batem vêm listados de propósito: sem eles a soma não fecha na hora
de conferir a prateleira.</p>
</body></html>
""" % (
        FOLHA_ESTILO,
        br(inventario.get('data')) if inventario.get('data') else '(sem data)',
        br(envio.get('data')) if envio.get('data') else '(sem data)',
        escapar_html(inventario.get('colunaSaldo', '?')),
        datetime.datetime.now().strftime('%d/%m/%Y %H:%M'),
        ('<p class="aviso"><strong>Fora desta folha:</strong> %s. '
         'Não são divergência de estoque e nenhuma contagem os resolve — '
         'são acerto no cadastro do Digifarma. Use --negativos e --tarefas.</p>'
         % '; '.join(fora)) if fora else '',
        '\n'.join(secoes) or '<p class="vazio">Nada a conferir: os lotes que '
                             'entrariam nesta folha já batem com o SNGPC.</p>',
        len(medicamentos), len(conferir))

    caminho = os.path.join(PASTA, 'comparacao_%s.html' % datetime.date.today().isoformat())
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(html)
    print('%d lote(s) na folha de conferência.' % len(conferir))
    for classe in CLASSES + ('',):
        do_grupo = [m for m in medicamentos if m['classe'] == classe]
        soltos = [m for m in sem_prateleira if m['classe'] == classe]
        if do_grupo or soltos:
            print('  %s: %d medicamento(s), %d lote(s)%s' % (
                NOME_CLASSE[classe], len(do_grupo),
                sum(len(m['lotes']) for m in do_grupo),
                (' · %d sem lote para conferir' % len(soltos)) if soltos else ''))
    if sem_prateleira:
        print('%d medicamento(s) só têm lote negativo: vão num bloco à parte, '
              'para quem contar copiar o lote da caixa — é ele que aponta a '
              'nota que nunca foi lançada.' % len(sem_prateleira))
    if movimentos:
        print('%d lançamento(s) desde o último envio vão em anexo (venda, hora, '
              'lote e quantidade): sem eles a contagem do dia acusa divergência '
              'que não existe.' % len(movimentos))
    if fora:
        print('Fora dela: %s.' % '; '.join(fora))
    print('\nGravado em %s' % caminho)
    print('Abra o arquivo (clique duas vezes) e imprima com Ctrl+P.')
    return True


ROTULO_IMPRESSO = {
    'so_na_anvisa': 'O SNGPC tem e o Digifarma não',
    'quantidade': 'Contagem diferente dos dois lados',
    'anvisa_zerada_lote': 'Lote zerado na ANVISA',
    'anvisa_zerada_produto': 'Zerado na ANVISA',
}


def modo_negativos(config, filtro=''):
    """Abre cada lote com saldo negativo: o que entrou, o que foi vendido, e
    quais outros lotes do mesmo medicamento têm saldo.

    A última coluna é a que aponta a causa. Lote negativo com IRMÃO cheio é
    assinatura de venda lançada no lote errado — o produto saiu do lote novo
    e o sistema debitou o antigo. Lote negativo sem irmão nenhum é entrada
    que nunca foi lançada. São consertos diferentes.

    Grava a lista num .txt junto: 39 lotes não se resolvem lendo a tela, se
    resolvem com o papel do lado do Digifarma."""
    saida = []

    def diz(linha=''):
        saida.append(linha)
        print(linha)

    conexao = conectar_firebird(config)
    try:
        por_chave, info = saldo_por_lote(conexao, config)
        negativos = {k: v for k, v in por_chave.items() if v['saldoDigifarma'] < 0}
        if filtro:
            alvo = normalizar_texto(filtro)
            negativos = {k: v for k, v in negativos.items()
                         if alvo in normalizar_texto(v['descricao']) or alvo in k[1]}
        if not negativos:
            diz('Nenhum lote com saldo negativo%s.'
                  % (' para "%s"' % filtro if filtro else ''))
            return True

        colunas = ['L.NUM_LOTE'] + ['L.%s' % info['coluna']]
        if 'QUANTIDADE_COMPRA' in info['campos'] and info['coluna'] != 'QUANTIDADE_COMPRA':
            colunas.append('L.QUANTIDADE_COMPRA')
        if 'ENTRADA_SAIDA' in info['campos']:
            colunas.append('L.ENTRADA_SAIDA')
        # LOTE_ID e PRODUTO_ID identificam a LINHA no banco. A tela do
        # Digifarma costuma esconder lote negativo, zerado ou vencido — e aí
        # a farmácia não acha o que corrigir. Com estes dois números o
        # suporte localiza o registro sem depender da tela.
        for extra in ('LOTE_ID', 'PRODUTO_ID'):
            if extra in info['campos']:
                colunas.append('L.%s' % extra)
        sql_entradas = CONSULTAS['entradas_do_lote'].replace('{COLUNAS}', ', '.join(colunas))

        diz('LOTES COM SALDO NEGATIVO — %d\n' % len(negativos))
        com_irmao, sem_irmao, vencidos = [], [], []
        hoje = datetime.date.today().isoformat()

        for chave, registro in sorted(negativos.items(), key=lambda x: x[1]['saldoDigifarma']):
            ms, lote = chave
            # lote vencido não está na prateleira: nenhuma contagem o
            # resolve, e mandar procurar por ele é gastar a conferência
            venceu = bool(registro['validade']) and registro['validade'][:10] < hoje
            if venceu:
                vencidos.append(chave)
            diz('%s' % (registro['descricao'] or '(sem descrição)'))
            diz('  M.S. %s · lote %s · saldo %g%s%s' % (
                formatar_ms(ms), lote or '(vazio)', registro['saldoDigifarma'],
                ' · vence %s' % br(registro['validade']) if registro['validade'] else '',
                ' · VENCIDO' if venceu else ''))
            if registro.get('codigo'):
                diz('  produto %s no cadastro do Digifarma' % registro['codigo'])

            try:
                entradas = [l for l in consultar(conexao, sql_entradas, (lote,))
                            if so_digitos(l.get('REGISTRO_MS')) == ms]
            except Exception as e:
                registrar('Não consegui ler as entradas do lote %s: %s' % (lote, e))
                entradas = []
            for l in entradas:
                # o que ENTROU e o que RESTA são colunas diferentes: mostrar
                # só o saldo na linha da entrada faz parecer que entrou -3
                comprou = ('comprou %g · ' % numero(l.get('QUANTIDADE_COMPRA'))
                           if 'QUANTIDADE_COMPRA' in l else '')
                # o LOTE_ID é o que a tela não mostra e o suporte precisa
                diz('    entrou   nota %-10s de %-10s  %sresta %g%s' % (
                    texto(l.get('NOTA_FISCAL')) or '—', br(texto(l.get('DATA_RECEBIMENTO'))),
                    comprou, numero(l.get(info['coluna'])),
                    ('   [LOTES.LOTE_ID %s]' % texto(l.get('LOTE_ID')))
                    if l.get('LOTE_ID') else ''))
            if not entradas:
                diz('    entrou   (nenhuma linha de entrada em LOTES)')

            try:
                vendas = [l for l in consultar(conexao, CONSULTAS['vendas_do_lote'], (lote,))]
            except Exception as e:
                registrar('Não consegui ler as vendas do lote %s: %s' % (lote, e))
                vendas = []
            for v in vendas[:12]:
                diz('    vendeu   venda %-8s de %-10s  %g' % (
                    texto(v.get('VENDA_NOTA_ID')), br(texto(v.get('DATA'))),
                    numero(v.get('QUANTIDADE'))))
            if len(vendas) > 12:
                diz('             ... e mais %d venda(s)' % (len(vendas) - 12))

            irmaos = [(k[1], r['saldoDigifarma']) for k, r in por_chave.items()
                      if k[0] == ms and k[1] != lote and r['saldoDigifarma'] > 0]
            if irmaos:
                com_irmao.append(chave)
                diz('    outros lotes deste medicamento COM saldo:')
                for l, s in sorted(irmaos, key=lambda x: -x[1])[:6]:
                    diz('             lote %-14s %g' % (l, s))
                diz('    -> a venda pode ter saído de um destes e sido lançada aqui')
            else:
                sem_irmao.append(chave)
                diz('    -> nenhum outro lote deste medicamento tem saldo:')
                diz('       parece entrada que nunca foi lançada')
            diz('')

        diz('=' * 74)
        diz('%d com outro lote cheio — provável venda lançada no lote errado' % len(com_irmao))
        diz('%d sem nenhum lote cheio — provável entrada não lançada' % len(sem_irmao))
        if vencidos:
            diz('%d em lote VENCIDO — não está na prateleira, então não há o que'
                ' contar: é acerto de escrituração, não conferência' % len(vencidos))
        diz('Faltando ao todo: %g unidade(s).'
            % abs(round(sum(r['saldoDigifarma'] for r in negativos.values()), 3)))
        diz('')
        diz('')
        diz('Se o lote não aparece na tela do Digifarma — é comum esconder lote')
        diz('negativo, zerado ou vencido —, a linha existe no banco assim mesmo.')
        diz('Leve ao suporte o LOTE_ID e o código do produto acima: eles')
        diz('identificam o registro em LOTES sem depender da tela.')
        diz('')
        diz('Nada aqui foi alterado no Digifarma: esta lista só lê.')

        caminho = os.path.join(
            PASTA, 'negativos_%s.txt' % datetime.date.today().isoformat())
        try:
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write('\n'.join(saida) + '\n')
            print('\nGravado em %s' % caminho)
        except Exception as e:
            registrar('Não consegui gravar a lista dos negativos: %s' % e)
        return True
    finally:
        fechar(conexao)


def modo_totais(config, filtro=''):
    """PRODUTOS.PROD_SALDO comparado com a soma dos lotes daquele produto.

    O Digifarma guarda dois saldos: o total do produto e o de cada lote. A
    tela do balcao mostra o primeiro; a conferencia com o SNGPC usa o
    segundo. Se os dois discordam, escrever num deles conserta metade e
    estraga a outra — por isso esta medida vem ANTES de qualquer ajuste."""
    conexao = conectar_firebird(config)
    try:
        info = detectar_coluna_saldo(conexao, config)
        if info['modo'] != 'saldo':
            print('Nesta instalação LOTES é tabela de movimento (%s): a soma'
                  % info['coluna'])
            print('das linhas não é o saldo do lote, e a comparação não vale.')
            return False
        sql = CONSULTAS['totais_produto'].replace('{COLUNA}', info['coluna'])
        linhas = consultar(conexao, sql)
    finally:
        fechar(conexao)

    if filtro:
        alvo = normalizar_texto(filtro)
        linhas = [l for l in linhas if alvo in normalizar_texto(l.get('PRODUTO'))]

    batem, divergem, sem_lote = 0, [], 0
    for l in linhas:
        total = numero(l.get('PROD_SALDO'))
        soma = l.get('SOMA_LOTES')
        if soma is None:
            # produto controlado sem nenhuma linha em LOTES: nao ha o que
            # comparar, e isso por si so pode ser cadastro sem controle de
            # lote — que o SNGPC exige
            sem_lote += 1
            continue
        diferenca = round(total - numero(soma), 3)
        if diferenca:
            divergem.append((diferenca, l, total, numero(soma)))
        else:
            batem += 1

    print('PROD_SALDO (total do produto) x SOMA DOS LOTES — %d controlado(s)'
          % (batem + len(divergem) + sem_lote))
    print('  %d batem' % batem)
    print('  %d divergem' % len(divergem))
    if sem_lote:
        print('  %d sem nenhuma linha em LOTES' % sem_lote)
    print('')

    if divergem:
        divergem.sort(key=lambda x: -abs(x[0]))
        print('%-42s %10s %10s %8s' % ('MEDICAMENTO', 'PRODUTOS', 'LOTES', 'DIF.'))
        for diferenca, l, total, soma in divergem[:60]:
            print('%-42s %10g %10g %+8g'
                  % (texto(l.get('PRODUTO'))[:42], total, soma, -diferenca))
        if len(divergem) > 60:
            print('... e mais %d' % (len(divergem) - 60))
        print('')
        print('A coluna DIF. é quanto os LOTES têm a mais que o total do produto.')
        print('Enquanto isso não fechar, a tela do Digifarma e a conferência do')
        print('SNGPC contam histórias diferentes — e nenhum ajuste deve ser feito')
        print('em cima de um número que só metade do sistema enxerga.')
    else:
        print('Os dois saldos do Digifarma estão de acordo em todos os')
        print('controlados. O total do produto é a soma dos lotes.')
    return True


def modo_produto(config, texto_busca):
    """Mostra o cadastro dos produtos que casam com um nome: código, registro
    M.S., código de barras e a marcação de controlado.

    Serve para o caso do controlado sem registro M.S. — que não é
    transmitido ao SNGPC, nem a entrada nem a venda. O registro em falta NÃO
    se adivinha nem se copia de outro cadastro: ele é do produto daquele
    fabricante, e está impresso na caixa e na nota fiscal. O que este modo
    faz é mostrar o que a farmácia já tem cadastrado — inclusive um segundo
    cadastro do mesmo produto, com o registro preenchido, que é o achado
    mais comum."""
    if not texto_busca:
        print('Diga o que procurar, por exemplo: --produto AMOXICILINA')
        return False

    conexao = conectar_firebird(config)
    try:
        linhas = consultar(conexao, CONSULTAS['produtos_por_nome'],
                           ('%%%s%%' % texto_busca.upper(),))
    finally:
        fechar(conexao)

    if not linhas:
        print('Nenhum cadastro com "%s" no nome.' % texto_busca)
        return True

    print('CADASTROS QUE CASAM COM "%s" — %d\n' % (texto_busca.upper(), len(linhas)))
    sem_ms = 0
    for l in linhas:
        ms = so_digitos(l.get('REGISTRO_MS'))
        marcas = []
        if texto(l.get('PSICOTROPICO')).upper() == 'S':
            marcas.append('psicotrópico')
        if texto(l.get('ANTIMICROBIANO')).upper() == 'S':
            marcas.append('antimicrobiano')
        print('  cód %-8s %s' % (texto(l.get('PRODUTO_ID')), texto(l.get('PRODUTO'))))
        if ms:
            print('    registro M.S. %s' % formatar_ms(ms))
        else:
            print('    registro M.S. EM BRANCO  <-- não vai para o SNGPC')
            if marcas:
                sem_ms += 1
        print('    cód. barras   %s' % (texto(l.get('COD_BARRAS')) or '(vazio)'))
        print('    controlado    %s' % (' e '.join(marcas) or 'não marcado'))
        print('')

    if sem_ms:
        print('=' * 74)
        print('%d controlado(s) sem registro M.S.: enquanto ficar assim, nem a '
              'entrada nem a venda dele são escrituradas.' % sem_ms)
        print('O registro é do produto DAQUELE fabricante — não copie de outro')
        print('cadastro da lista. Ele está impresso na caixa e na nota fiscal de')
        print('entrada, e dá para conferir pelo código de barras no site da ANVISA.')
    return True


def modo_tarefas(config):
    """As divergências viram três listas de trabalho, na ordem em que se
    resolvem: primeiro o que é dado torto no Digifarma (vai reaparecer em
    toda conferência até ser corrigido), depois o que é escrituração, e por
    último o que exige contar prateleira — que é o mais caro e o menor.

    Não escreve no Digifarma nem transmite nada: só lista, com a evidência
    de cada caso do lado, e grava um .txt para imprimir."""
    conexao = conectar_firebird(config)
    try:
        dados = montar_inventario(conexao, config)
        info = detectar_coluna_saldo(conexao, config)
        compras = {}
        if 'QUANTIDADE_COMPRA' in info['campos']:
            compras = total_por_lote(conexao, dict(info, coluna='QUANTIDADE_COMPRA',
                                                   modo='movimento'))
        baixas = baixas_por_lote(conexao)
        entradas = {}
        try:
            for linha in consultar(conexao, CONSULTAS['entradas_por_lote']):
                entradas[(so_digitos(linha.get('REGISTRO_MS')),
                          texto(linha.get('NUM_LOTE')).upper())] = {
                    'nota': int(numero(linha.get('CAB_NOTA_ID'))),
                    'data': texto(linha.get('DATA')),
                }
        except Exception as e:
            registrar('Não consegui datar as entradas dos lotes: %s' % e)
    finally:
        fechar(conexao)

    ponteiro_entrada = int(numero(dados.get('envio', {}).get('ULT_ENTRADA_CAB_NOTA_ID')))

    por_motivo = {}
    for item in dados.get('itens', []):
        if item.get('motivo'):
            por_motivo.setdefault(item['motivo'], []).append(item)

    # lotes cuja entrada já está na fila do próximo envio: não é pendência
    # de ninguém, o envio resolve sozinho
    na_fila = {(so_digitos(p.get('ms')), texto(p.get('lote')).upper())
               for p in dados.get('pendentes', {}).get('entradas', [])}

    linhas = []

    def escrever(texto_linha=''):
        print(texto_linha)
        linhas.append(texto_linha)

    def chave_do(item):
        return (item['ms'], item['lote'])

    escrever('TAREFAS DE SALDO — %s' % datetime.datetime.now().strftime('%d/%m/%Y %H:%M'))
    escrever('inventário da ANVISA de %s · saldo por LOTES.%s'
             % (dados.get('inventario', {}).get('data') or '(sem data)', info['coluna']))
    escrever('=' * 78)

    # ---------- 1 ----------
    negativos = sorted(por_motivo.get('negativo', []), key=lambda i: i['saldoDigifarma'])
    escrever('')
    escrever('1. CORRIGIR NO DIGIFARMA — %d lote(s) com saldo negativo' % len(negativos))
    escrever('   Estoque físico não fica negativo. "Outras saídas" é quanto saiu do')
    escrever('   lote sem ser venda nem perda registrada — é esse número que se')
    escrever('   procura na tela de movimento do lote, no Digifarma.')
    escrever('')
    for i in negativos:
        chave = chave_do(i)
        comprado = compras.get(chave, 0.0)
        baixado = baixas.get(chave, 0.0)
        # o que o Digifarma tirou do lote por fora do que sabemos ler
        outras = round(comprado - baixado - i['saldoDigifarma'], 3)
        escrever('   %-42s lote %-14s saldo %g' % (
            i['descricao'][:42], i['lote'] or '(vazio)', i['saldoDigifarma']))
        escrever('   %-42s M.S. %-14s comprado %g · vendas e perdas %g · outras saídas %g'
                 % ('', i['ms'] or '(sem M.S.)', comprado, baixado, outras))

    # ---------- 1b ----------
    sem_registro = sorted(por_motivo.get('sem_ms', []),
                          key=lambda i: -i['saldoDigifarma'])
    if sem_registro:
        escrever('')
        escrever('1b. CADASTRAR O REGISTRO M.S. — %d lote(s)' % len(sem_registro))
        escrever('   O SNGPC RECUSA medicamento sem registro M.S. Estes nunca foram')
        escrever('   transmitidos — nem a entrada, nem a venda — e não têm como bater')
        escrever('   com a ANVISA. Não é divergência de estoque: enquanto o cadastro')
        escrever('   não for corrigido, é controlado se movimentando sem escrituração.')
        escrever('')
        for i in sem_registro:
            escrever('   %-42s lote %-14s Digifarma %g' % (
                i['descricao'][:42], i['lote'] or '(vazio)', i['saldoDigifarma']))
            escrever('   %-42s cód. %-14s EAN %s' % (
                '', i['codigo'] or '—', i['ean'] or '—'))

    # ---------- 2 ----------
    escrituracao = (sorted(por_motivo.get('anvisa_zerada_produto', []),
                           key=lambda i: -i['saldoDigifarma'])
                    + sorted(por_motivo.get('anvisa_zerada_lote', []),
                             key=lambda i: -i['saldoDigifarma']))
    esperando = [i for i in escrituracao if chave_do(i) in na_fila]
    faltando = [i for i in escrituracao if chave_do(i) not in na_fila]
    # Entrada posterior ao inventário não podia estar nele: não é pendência,
    # é ordem cronológica. Separar as duas evita mandar conferir 39 lotes
    # quando a maioria só precisa do próximo inventário.
    data_inventario = (dados.get('inventario', {}).get('data') or '')[:10]

    def entrou_depois_do_inventario(item):
        data = entradas.get(chave_do(item), {}).get('data', '')
        return bool(data_inventario) and bool(data) and data >= data_inventario

    recentes = [i for i in faltando if entrou_depois_do_inventario(i)]
    antigas = [i for i in faltando if not entrou_depois_do_inventario(i)]

    escrever('')
    escrever('2. ZERADO NA ANVISA — %d lote(s) com saldo aqui e zero lá' % len(escrituracao))
    escrever('   Zero na ANVISA tanto pode ser entrada que não subiu quanto saldo')
    escrever('   errado no Digifarma. Confira o estoque físico ANTES de mexer na')
    escrever('   escrituração: já apareceram os dois casos.')
    if esperando:
        escrever('   %d estão na fila do próximo envio: o envio resolve sozinho.'
                 % len(esperando))
    if recentes:
        escrever('   %d entraram em %s ou depois, e o inventário da ANVISA é de %s:'
                 % (len(recentes), br(data_inventario), br(data_inventario)))
        escrever('   entrada nova não podia estar num inventário mais velho. Estes não')
        escrever('   são pendência — confira no próximo inventário que o Anvisa.exe baixar.')

    escrever('')
    escrever('   PRECISAM DE ALGUÉM: %d lote(s)' % len(antigas))
    if antigas:
        # agrupar por medicamento: quando TODO lote de um produto falta no
        # SNGPC, mês após mês, o problema é o cadastro dele, não o envio
        grupos = {}
        for i in antigas:
            grupos.setdefault((i['ms'], i['descricao']), []).append(i)
        repetidos = {k: v for k, v in grupos.items() if len(v) > 1}
        if repetidos:
            escrever('   Comece por estes: o registro M.S. inteiro está zerado na ANVISA,')
            escrever('   em vários lotes e de notas de meses diferentes. Um M.S. de cada')
            escrever('   vez resolve vários lotes — confira o saldo dele na ANVISA e o')
            escrever('   estoque físico, e veja se o Digifarma é que está errado.')
            for (ms, desc), itens_grupo in sorted(repetidos.items(), key=lambda x: -len(x[1])):
                escrever('      %-42s M.S. %-16s %d lotes' % (desc[:42], formatar_ms(ms),
                                                              len(itens_grupo)))
        escrever('')
    for i in antigas:
        entrada = entradas.get(chave_do(i), {})
        escrever('   %-42s lote %-14s Digifarma %g · SNGPC %g' % (
            i['descricao'][:42], i['lote'] or '(vazio)',
            i['saldoDigifarma'], i['saldoSngpc']))
        escrever('   %-42s M.S. %-16s %s' % (
            '', formatar_ms(i['ms']),
            ('nota %d de %s · %s' % (
                entrada['nota'], br(entrada.get('data')),
                'já transmitida' if entrada['nota'] <= ponteiro_entrada
                else 'não transmitida')) if entrada.get('nota') else ''))

    if recentes:
        escrever('')
        escrever('   — entradas novas, só conferir no próximo inventário da ANVISA —')
        for i in recentes:
            entrada = entradas.get(chave_do(i), {})
            escrever('   %-42s lote %-14s Digifarma %g · entrou %s' % (
                i['descricao'][:42], i['lote'] or '(vazio)',
                i['saldoDigifarma'], br(entrada.get('data'))))
    if esperando:
        escrever('')
        escrever('   — já na fila do próximo envio, só conferir depois que subir —')
        for i in esperando:
            escrever('   %-42s lote %-14s Digifarma %g' % (
                i['descricao'][:42], i['lote'] or '(vazio)', i['saldoDigifarma']))

    # ---------- 3 ----------
    contar = sorted(por_motivo.get('quantidade', []) + por_motivo.get('so_na_anvisa', []),
                    key=lambda i: -abs(i['diferenca']))
    escrever('')
    escrever('3. CONFERIR NA PRATELEIRA — %d lote(s) com contagem diferente' % len(contar))
    escrever('   Os dois lados conhecem o lote e discordam do número.')
    escrever('')
    for i in contar:
        escrever('   %-42s lote %-14s Digifarma %-6g SNGPC %-6g dif %+g' % (
            i['descricao'][:42], i['lote'] or '(vazio)',
            i['saldoDigifarma'], i['saldoSngpc'], i['diferenca']))

    escrever('')
    escrever('=' * 78)
    escrever('Nada aqui foi alterado no Digifarma nem transmitido: esta lista só lê.')

    caminho = os.path.join(PASTA, 'tarefas_saldo_%s.txt'
                           % datetime.date.today().isoformat())
    try:
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas) + '\n')
        print('\nGravado em %s' % caminho)
    except Exception as e:
        registrar('Não consegui gravar o arquivo das tarefas: %s' % e)
    return True


def classificar_inventario_anvisa(conexao):
    """Separa a INVENTARIO_SNGPC em três: o que entra na comparação, o que
    fica de fora por não ser controlado, e o que entra sem ter produto no
    cadastro. Serve ao --inventario e ao diagnóstico que sobe ao app."""
    linhas = consultar(conexao, CONSULTAS['inventario_sngpc'])
    if not linhas:
        return {'total': 0, 'entram': [], 'fora': [], 'semCadastro': [], 'usados': {}}

    campos = list(linhas[0])
    usados = {chave: escolher_campo(campos, regras)
              for chave, regras in CAMPOS_INVENTARIO.items()}
    campo_produto = next((c for c in campos if c.strip().upper() == 'PRODUTO_ID'), None)

    nomes, controlados, conhecidos = {}, set(), set()
    if campo_produto:
        for linha in consultar(conexao, CONSULTAS['produtos_controlados']):
            produto = texto(linha.get('PRODUTO_ID'))
            if not produto:
                continue
            conhecidos.add(produto)
            nomes[produto] = texto(linha.get('PRODUTO'))
            if (texto(linha.get('PSICOTROPICO')).upper() == 'S'
                    or texto(linha.get('ANTIMICROBIANO')).upper() == 'S'):
                controlados.add(produto)

    grupos = {'entram': [], 'fora': [], 'semCadastro': []}
    for linha in linhas:
        produto = texto(linha.get(campo_produto)) if campo_produto else ''
        if not campo_produto:
            nome = 'entram'
        elif produto in controlados:
            nome = 'entram'
        elif produto in conhecidos:
            nome = 'fora'
        else:
            nome = 'semCadastro'
        grupos[nome].append((produto, linha))

    return dict(grupos, total=len(linhas), usados=usados, nomes=nomes,
                temProdutoId=bool(campo_produto))


def snapshot_diagnostico(conexao):
    """Os números que respondem "por que ainda há divergência", num formato
    que cabe na tela do celular. Sobe junto com as vendas, de 5 em 5
    minutos, para quem não está no servidor conseguir ver."""
    linhas = consultar(conexao, CONSULTAS['ponteiros'])
    ponteiros = linhas[0] if linhas else {}
    ptr_venda = int(numero(ponteiros.get('ULT_SAIDA_VENDA_NOTA_ID')))
    ptr_entrada = int(numero(ponteiros.get('ULT_ENTRADA_CAB_NOTA_ID')))

    pendentes = {}
    try:
        pendentes['vendas'] = len(consultar(conexao, CONSULTAS['saidas_pendentes'],
                                            (ptr_venda,)))
        pendentes['entradas'] = len(consultar(conexao, CONSULTAS['entradas_pendentes'],
                                              (ptr_entrada,)))
    except Exception as e:
        registrar('Diagnóstico: não consegui contar os pendentes: %s' % e)

    inventario = {}
    try:
        grupos = classificar_inventario_anvisa(conexao)
        inventario = {
            'linhas': grupos['total'],
            'entram': len(grupos['entram']),
            'foraDoCriterio': len(grupos['fora']),
            'semProdutoNoCadastro': len(grupos['semCadastro']),
        }
    except Exception as e:
        registrar('Diagnóstico: não consegui classificar o inventário: %s' % e)

    return {
        'em': datetime.datetime.now().isoformat(timespec='seconds'),
        'ponteiroVenda': ptr_venda,
        'ponteiroEntrada': ptr_entrada,
        'ultimoEnvio': texto(ponteiros.get('ULTIMO_ENVIO_SNGPC'))[:10] or None,
        'pendentes': pendentes,
        'inventarioSngpc': inventario,
    }


def modo_inventario(config):
    """Abre o inventário do SNGPC linha a linha e diz o que entra, o que sai
    e por quê. Só o banco da farmácia sabe QUAIS são os produtos; este
    comando é o que os nomeia."""
    conexao = conectar_firebird(config)
    try:
        grupos = classificar_inventario_anvisa(conexao)
    finally:
        fechar(conexao)

    if not grupos['total']:
        print('INVENTARIO_SNGPC está vazia. Rode o Anvisa.exe e faça o login.')
        return False

    usados, nomes = grupos['usados'], grupos.get('nomes', {})
    print('INVENTARIO_SNGPC — %d linha(s)' % grupos['total'])
    print('colunas usadas: %s\n' % ', '.join(
        '%s=%s' % (k, v) for k, v in sorted(usados.items()) if v))
    if not grupos.get('temProdutoId'):
        print('A tabela não tem PRODUTO_ID: não dá para dizer quem é controlado,')
        print('e o inventário entra inteiro.')
        return True

    entram, fora, sem_cadastro = grupos['entram'], grupos['fora'], grupos['semCadastro']

    def mostrar(titulo, grupo, explicacao):
        print('%s: %d' % (titulo, len(grupo)))
        print('  %s' % explicacao)
        for produto, linha in grupo[:40]:
            print('     cód %-8s %-38s M.S. %-18s lote %-14s %g' % (
                produto or '—',
                (nomes.get(produto) or texto(linha.get(usados['descricao'])) or '—')[:38],
                formatar_ms(linha.get(usados['ms'])),
                texto(linha.get(usados['lote'])) or '—',
                numero(linha.get(usados['quantidade']))))
        if len(grupo) > 40:
            print('     ... e mais %d' % (len(grupo) - 40))
        print('')

    mostrar('ENTRAM na comparação (controlados)', entram,
            'psicotrópico ou antimicrobiano no cadastro do Digifarma')
    mostrar('FICAM DE FORA (não controlados)', fora,
            'estão no cadastro e NÃO estão marcados: não são do SNGPC')
    mostrar('ENTRAM, mas sem produto no cadastro', sem_cadastro,
            'o SNGPC tem e o Digifarma não conhece — pode ser divergência de verdade')
    return True


def modo_resumo(config):
    """Divergência que sobra é diferença de estoque de verdade ou lote
    escrito diferente dos dois lados? Este resumo separa uma coisa da
    outra antes de alguém sair conferindo prateleira."""
    conexao = conectar_firebird(config)
    try:
        por_chave, info = saldo_por_lote(conexao, config)
        saldo_anvisa, inventario_em, _, _ = ler_inventario_anvisa(conexao)

        digi = {k: v['saldoDigifarma'] for k, v in por_chave.items() if v['saldoDigifarma']}
        anvisa = {k: v for k, v in saldo_anvisa.items() if v}
        descricao = {k: v['descricao'] for k, v in por_chave.items()}

        comuns = set(digi) & set(anvisa)
        iguais = [k for k in comuns if abs(digi[k] - anvisa[k]) < 0.001]
        so_digi = sorted(set(digi) - set(anvisa), key=lambda k: -digi[k])
        so_anvisa = sorted(set(anvisa) - set(digi), key=lambda k: -anvisa[k])

        print('saldo por LOTES.%s (modo %s)' % (info['coluna'], info['modo']))
        print('inventário da ANVISA de %s\n' % (inventario_em or '(sem data)'))
        print('  lotes com saldo no Digifarma: %d' % len(digi))
        print('  lotes com saldo na ANVISA:    %d' % len(anvisa))
        print('  casaram (M.S. + lote):        %d — %d batendo, %d com valor diferente'
              % (len(comuns), len(iguais), len(comuns) - len(iguais)))
        print('  só no Digifarma:              %d' % len(so_digi))
        print('  só na ANVISA:                 %d' % len(so_anvisa))

        # quantas das que não casaram casariam se o lote fosse comparado
        # ignorando zero à esquerda e pontuação
        frouxa_anvisa = {}
        for k in so_anvisa:
            frouxa_anvisa.setdefault(chave_frouxa(k), []).append(k)
        pares = [(k, frouxa_anvisa[chave_frouxa(k)][0])
                 for k in so_digi if chave_frouxa(k) in frouxa_anvisa]

        print('\n  casariam se o lote fosse comparado sem zero à esquerda\n'
              '  e sem pontuação: %d' % len(pares))
        for d, a in pares[:15]:
            print('      %-40s lote Digifarma %-14s ANVISA %-14s'
                  % (descricao.get(d, '')[:40], d[1] or '(vazio)', a[1] or '(vazio)'))

        # mesmo remédio, lote que a ANVISA não tem de jeito nenhum
        ms_anvisa = {k[0] for k in anvisa}
        sem_o_ms = [k for k in so_digi if k[0] not in ms_anvisa]
        print('\n  no Digifarma com saldo e o M.S. nem aparece na ANVISA: %d' % len(sem_o_ms))
        print('  (costuma ser entrada que ainda não foi transmitida)')

        print('\n  maiores diferenças de valor entre os que casaram:')
        for k in sorted(comuns, key=lambda k: -abs(digi[k] - anvisa[k]))[:15]:
            if abs(digi[k] - anvisa[k]) < 0.001:
                break
            print('      %-40s lote %-12s Digifarma %-8g ANVISA %g'
                  % (descricao.get(k, '')[:40], k[1], digi[k], anvisa[k]))

        sem_ms = [k for k in digi if not k[0]]
        if sem_ms:
            print('\n  lotes com saldo e SEM registro M.S. no cadastro: %d' % len(sem_ms))
            print('  (o SNGPC recusa medicamento sem M.S.: nunca foram transmitidos)')
            for k in sorted(sem_ms, key=lambda k: -digi[k])[:10]:
                print('      %-40s lote %-12s %g'
                      % (descricao.get(k, '')[:40], k[1], digi[k]))

        negativos = [k for k in digi if digi[k] < 0]
        if negativos:
            print('\n  lotes com saldo NEGATIVO no Digifarma: %d' % len(negativos))
            print('  (saída lançada sem entrada; é dado torto no Digifarma, não conta do agente)')
            for k in sorted(negativos, key=lambda k: digi[k])[:10]:
                print('      %-40s lote %-12s %g'
                      % (descricao.get(k, '')[:40], k[1], digi[k]))
        return True
    finally:
        fechar(conexao)


def modo_linhas(config, lote):
    """Despeja TUDO que a base guarda sobre um lote: cada linha de LOTES com
    todas as suas colunas, e cada venda daquele lote. É o que mostra se
    existe uma coluna de saldo que o agente ainda não conhece."""
    conexao = conectar_firebird(config)
    try:
        alvo = str(lote or '').strip().upper()
        linhas = consultar(conexao, CONSULTAS['linhas_do_lote'], (alvo,))
        if not linhas:
            print('Nenhuma linha em LOTES com o lote "%s".' % alvo)
            return False

        print('LOTES — %d linha(s) do lote %s\n' % (len(linhas), alvo))
        for i, linha in enumerate(linhas, 1):
            print('  linha %d' % i)
            for campo in sorted(linha):
                # coluna vazia também é notícia: esconder o que está nulo
                # esconde justamente a coluna que a gente procura
                print('    %-26s %s' % (campo, texto(linha[campo]) or '(vazio)'))
            print('')

        try:
            vendas = consultar(conexao, CONSULTAS['vendas_do_lote'], (alvo,))
        except Exception as e:
            registrar('Não consegui listar as vendas do lote: %s' % e)
            vendas = []

        print('ITEM_VENDAS_LOTES — %d venda(s) do lote %s' % (len(vendas), alvo))
        total = 0.0
        for v in vendas:
            contada = (texto(v.get('CANCELADO')).upper() != 'S'
                       and numero(v.get('RECEBIDO')) > 0)
            if contada:
                total += numero(v.get('QUANTIDADE'))
            print('    venda %-10s %s  qtd %-6g %s' % (
                texto(v.get('VENDA_NOTA_ID')), texto(v.get('DATA')),
                numero(v.get('QUANTIDADE')),
                '' if contada else '(fora da conta: cancelada ou não recebida)'))
        print('\n  total descontado pelo agente: %g' % total)
        print('\nCompare com a tela do Digifarma. Se o saldo de lá for outro,')
        print('alguma coluna acima é o saldo verdadeiro — me diga qual.')
        return True
    finally:
        fechar(conexao)


def modo_teste(config):
    print('Banco Firebird: %s' % config['banco'])
    conexao = conectar_firebird(config)
    linhas = consultar(conexao, CONSULTAS['ponteiros'])
    fechar(conexao)
    print('  conectou. Ponteiros do SNGPC: %s' % (linhas[0] if linhas else 'tabela SNGPC vazia'))

    print('Firebase: %s' % config['url_banco'])
    db = conectar_firebase(config)
    try:
        db.reference('farmacia/inventario/atualizadoEm').set(
            datetime.datetime.now().isoformat(timespec='seconds'))
    except Exception as e:
        if erro_de_permissao(e):
            print('\n' + recado_de_permissao(config))
            raise SystemExit(1)
        raise
    print('  escreveu em farmacia/inventario/atualizadoEm.')
    print('\nTudo certo.')


# ============================================================
# ENTRADA
# ============================================================
def principal():
    parser = argparse.ArgumentParser(description='Agente SNGPC — Digifarma para Firebase')
    parser.add_argument('data', nargs='?', help='data do inventário, DD/MM/AAAA')
    parser.add_argument('--auto', action='store_true', help='sincronização completa')
    parser.add_argument('--fila', action='store_true', help='atende os botões do app')
    parser.add_argument('--envio', action='store_true', help='usa o inventário vigente no último envio')
    parser.add_argument('--schema', action='store_true', help='confere as tabelas da base')
    parser.add_argument('--teste', action='store_true', help='testa Firebird e Firebase')
    parser.add_argument('--colunas', metavar='TABELA', nargs='?', const='',
                        help='lista as colunas de uma tabela; sem nome, lista as tabelas')
    parser.add_argument('--saldo', metavar='TEXTO', nargs='?', const='',
                        help='mostra como o saldo de um lote foi apurado')
    parser.add_argument('--linhas', metavar='LOTE',
                        help='despeja todas as colunas de LOTES de um lote')
    parser.add_argument('--resumo', action='store_true',
                        help='separa divergência de verdade de lote escrito diferente')
    parser.add_argument('--inventario', action='store_true',
                        help='mostra o inventário do SNGPC: o que entra, o que sai e por quê')
    parser.add_argument('--tarefas', action='store_true',
                        help='as divergências em três listas de trabalho, na ordem de resolver')
    parser.add_argument('--negativos', metavar='TEXTO', nargs='?', const='',
                        help='abre cada lote negativo: o que entrou, o que vendeu, e os lotes irmãos')
    parser.add_argument('--comparacao', metavar='TEXTO', nargs='?', const='',
                        help='gera a folha de conferência em HTML, para imprimir')
    parser.add_argument('--produto', metavar='TEXTO', nargs='?', const='',
                        help='mostra o cadastro: registro M.S., código de barras e a marcação')
    parser.add_argument('--totais', metavar='TEXTO', nargs='?', const='',
                        help='PRODUTOS.PROD_SALDO comparado com a soma dos lotes')
    parser.add_argument('--atualizar', action='store_true',
                        help='baixa a versão mais nova do agente do GitHub e se substitui')
    parser.add_argument('--config', metavar='CHAVE=VALOR',
                        help='muda uma chave do agente_config.json sem editar JSON à mão')
    args = parser.parse_args()

    config = carregar_config()
    sys.path.insert(0, PASTA)

    data_inventario = None
    if args.data:
        try:
            data_inventario = datetime.datetime.strptime(args.data, '%d/%m/%Y').date().isoformat()
        except ValueError:
            raise SystemExit('Data em formato DD/MM/AAAA, por exemplo 31/07/2026.')

    try:
        if args.colunas is not None:
            # sem o nome da tabela, dizer QUAIS existem é mais útil que o
            # erro do argparse — quem esqueceu o nome não o tem na cabeça
            if not args.colunas:
                print('Diga a tabela, por exemplo: --colunas PRODUTOS\n')
                print('As que este agente conhece:')
                for nome in TABELAS_ESPERADAS:
                    print('  %s' % nome)
                raise SystemExit(1)
            raise SystemExit(0 if modo_colunas(config, args.colunas) else 1)
        if args.totais is not None:
            raise SystemExit(0 if modo_totais(config, args.totais) else 1)
        if args.config:
            raise SystemExit(0 if modo_config(args.config) else 1)
        if args.atualizar:
            print(atualizar_agente(config))
            raise SystemExit(0)
        if args.produto is not None:
            raise SystemExit(0 if modo_produto(config, args.produto) else 1)
        if args.comparacao is not None:
            raise SystemExit(0 if modo_comparacao(config, args.comparacao) else 1)
        if args.negativos is not None:
            raise SystemExit(0 if modo_negativos(config, args.negativos) else 1)
        if args.tarefas:
            raise SystemExit(0 if modo_tarefas(config) else 1)
        if args.inventario:
            raise SystemExit(0 if modo_inventario(config) else 1)
        if args.resumo:
            raise SystemExit(0 if modo_resumo(config) else 1)
        if args.linhas:
            raise SystemExit(0 if modo_linhas(config, args.linhas) else 1)
        if args.saldo is not None:
            raise SystemExit(0 if modo_conferir_saldo(config, args.saldo) else 1)
        if args.schema:
            raise SystemExit(0 if modo_schema(config) else 1)
        if args.teste:
            modo_teste(config)
        elif args.fila:
            modo_fila(config)
        else:
            modo_auto(config, data_inventario, args.envio)
    except SystemExit:
        raise
    except Exception as e:
        registrar('ERRO: %s' % e)
        registrar(traceback.format_exc())
        raise SystemExit(1)


if __name__ == '__main__':
    principal()
