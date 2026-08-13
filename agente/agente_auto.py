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
    "modo_saldo": "auto"
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
    "perdas_pendentes": """
        SELECT PP.PERDA_ID, PP.DATA, PP.LOTE AS NUM_LOTE, PP.QUANTIDADE,
               P.PRODUTO, P.REGISTRO_MS
          FROM PERDAS_PSICOTROPICOS PP
          LEFT JOIN PRODUTOS P ON (P.PRODUTO_ID = PP.PRODUTO_ID)
         WHERE PP.DATA >= ? AND PP.PERDA_ID > ?
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
    "inventario_sngpc": "SELECT * FROM INVENTARIO_SNGPC",

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
         GROUP BY P.REGISTRO_MS, PP.LOTE
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
COLUNAS_SALDO = ('SALDO', 'SALDO_LOTE', 'SALDO_ATUAL', 'ESTOQUE', 'ESTOQUE_ATUAL',
                 'QUANTIDADE_ATUAL', 'QTD_ATUAL', 'QUANTIDADE_ESTOQUE',
                 'QUANTIDADE_ATU', 'QTD_SALDO')
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


def ler_inventario_anvisa(conexao):
    """Lê INVENTARIO_SNGPC — a tabela que o Anvisa.exe regrava com o
    inventário do site da ANVISA. Devolve (saldo, data, colunas usadas)."""
    try:
        linhas = consultar(conexao, CONSULTAS['inventario_sngpc'])
    except Exception as e:
        registrar('Não consegui ler INVENTARIO_SNGPC: %s' % e)
        return {}, None, {}
    if not linhas:
        registrar('INVENTARIO_SNGPC está vazia — sem o lado ANVISA, todo lote do '
                  'Digifarma vira "sobra". Rode o Anvisa.exe e faça o login no site.')
        return {}, None, {}

    campos = list(linhas[0])
    usados = {chave: escolher_campo(campos, regras)
              for chave, regras in CAMPOS_INVENTARIO.items()}
    campo_ms, campo_lote = usados['ms'], usados['lote']
    campo_qtd, campo_desc, campo_data = usados['quantidade'], usados['descricao'], usados['data']

    if not (campo_ms and campo_qtd):
        registrar('INVENTARIO_SNGPC tem colunas inesperadas: %s' % ', '.join(campos))
        return {}, None, {'colunas': campos}

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
    return saldo, atualizado, usados


DESCRICOES = {}        # (ms, lote) -> descrição, vinda do inventário da ANVISA
DESCRICOES_POR_MS = {}  # ms -> descrição, vinda do cadastro do Digifarma


def so_digitos(valor):
    return ''.join(c for c in str(valor or '') if c.isdigit())


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
    ptr_venda = int(numero(ponteiros.get('ULT_SAIDA_VENDA_NOTA_ID')))
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
            'descricao': texto(l.get('PRODUTO')),
            'ms': texto(l.get('REGISTRO_MS')),
            'lote': texto(l.get('NUM_LOTE')),
            'quantidade': numero(l.get('QUANTIDADE')),
        } for l in linhas_tipo]
        for tipo, linhas_tipo in pendentes.items()
    }
    resultado['resumoPendentes'] = {t: len(v) for t, v in resultado['pendentes'].items()}

    # ------------------------------------------------------------
    # 4. saldo do Digifarma × inventário da ANVISA
    # ------------------------------------------------------------
    saldo_anvisa, inventario_em, campos_anvisa = ler_inventario_anvisa(conexao)
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
    }

    itens = []
    try:
        por_chave, info_saldo = saldo_por_lote(conexao, config)
        resultado['inventario']['colunaSaldo'] = info_saldo['coluna']
        resultado['inventario']['modoSaldo'] = info_saldo['modo']

        for chave, registro in por_chave.items():
            anvisa = saldo_anvisa.pop(chave, 0.0)
            # lote zerado dos dois lados não é divergência nem notícia:
            # publicar tudo só engorda o farmacia/inventario
            if not registro['saldoDigifarma'] and not anvisa:
                continue
            registro['saldoSngpc'] = round(anvisa, 3)
            registro['diferenca'] = round(registro['saldoDigifarma'] - anvisa, 3)
            itens.append(registro)
    except Exception as e:
        registrar('Falha ao levantar o saldo por lote: %s' % e)

    # o que a ANVISA tem e o Digifarma não
    for (ms, lote), quantidade in saldo_anvisa.items():
        itens.append({
            'codigo': '',
            'descricao': (DESCRICOES.get((ms, lote))
                          or DESCRICOES_POR_MS.get(ms)
                          or '(só no inventário da ANVISA)'),
            'ms': ms, 'ean': '', 'lote': lote, 'validade': '',
            'saldoDigifarma': 0.0, 'saldoSngpc': round(quantidade, 3),
            'diferenca': round(-quantidade, 3),
        })
    resultado['itens'] = itens

    # ------------------------------------------------------------
    # 5. conferência do XML contra as vendas do período
    # ------------------------------------------------------------
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
        divergencias = mapa_xml.comparar(dados_xml['movimentos'].get('venda', {}), do_banco)
        periodo = '%s a %s' % (br(periodo_de), br(periodo_ate))
        for d in divergencias:
            d['periodo'] = periodo
            d['arquivo'] = dados_xml['arquivo']
        resultado['conferencia_xml'] = divergencias

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

    # ------------------------------------------------------------
    # 7. saúde da sincronização com o site da ANVISA
    # ------------------------------------------------------------
    resultado['anvisa'] = estado_do_anvisa(config, inventario_em)

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


# ============================================================
# MODOS
# ============================================================
def modo_auto(config, data_inventario=None, usar_envio=False):
    db = conectar_firebase(config)
    conexao = conectar_firebird(config)
    try:
        dados = montar_inventario(conexao, config, data_inventario, usar_envio)
        publicar(db, dados)
    finally:
        fechar(conexao)


def modo_fila(config):
    """Atende o pedido dos botões do app. Roda de 5 em 5 minutos."""
    db = conectar_firebase(config)
    ref = db.reference('farmacia/comando')
    pedido = ref.get()
    if not pedido or pedido.get('estado') != 'pendente':
        registrar('Fila vazia.')
        return

    acao = pedido.get('acao')
    registrar('Atendendo "%s" pedido por %s.' % (acao, pedido.get('pedidoPor')))
    try:
        modo_auto(config, usar_envio=(acao == 'atualizar_envio'))
        ref.update({
            'estado': 'concluido',
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

        saldo_anvisa, inventario_em, campos_anvisa = ler_inventario_anvisa(conexao)
        print('inventário da ANVISA: %d lote(s), colunas %s, carimbo %s\n' % (
            len(saldo_anvisa),
            ', '.join('%s=%s' % (k, v) for k, v in sorted((campos_anvisa or {}).items()) if v)
            or '(nenhuma reconhecida)',
            inventario_em or '(sem data)'))

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
            print('  SALDO PUBLICADO: %g     ANVISA: %g\n'
                  % (round(saldo, 3), round(saldo_anvisa.get(chave, 0.0), 3)))
        print('Se o SALDO PUBLICADO não bater com a tela do Digifarma, fixe a coluna')
        print('certa em agente_config.json ("coluna_saldo" e "modo_saldo").')
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
    db.reference('farmacia/inventario/atualizadoEm').set(
        datetime.datetime.now().isoformat(timespec='seconds'))
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
    parser.add_argument('--colunas', metavar='TABELA', help='lista as colunas de uma tabela')
    parser.add_argument('--saldo', metavar='TEXTO', nargs='?', const='',
                        help='mostra como o saldo de um lote foi apurado')
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
        if args.colunas:
            raise SystemExit(0 if modo_colunas(config, args.colunas) else 1)
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
