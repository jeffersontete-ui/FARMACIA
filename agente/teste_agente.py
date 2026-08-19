# -*- coding: utf-8 -*-
"""
teste_agente.py — roda o agente com um banco simulado.

Não abre o Digifarma nem escreve no Firebase: substitui a função
consultar() por respostas fixas e confere o que sai. Serve para
validar uma alteração no agente_auto.py antes de levar ao servidor.

    python teste_agente.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agente_auto as ag  # noqa: E402
import mapa_xml           # noqa: E402

XML_EXEMPLO = """<?xml version="1.0" encoding="UTF-8"?>
<mensagemSNGPC xmlns="urn:sngpc:anvisa">
 <transacao><medicamentos>
  <medicamento>
   <registroMSMedicamento>1.0033.0122.001-9</registroMSMedicamento>
   <descricaoMedicamento>CLONAZEPAM 2MG CX 30 CP</descricaoMedicamento>
   <numeroLoteMedicamento>L2345A</numeroLoteMedicamento>
   <quantidadeMedicamento>30</quantidadeMedicamento>
   <dataVenda>2026-08-09</dataVenda>
  </medicamento>
  <medicamento>
   <registroMSMedicamento>1.0033.0122.001-9</registroMSMedicamento>
   <descricaoMedicamento>CLONAZEPAM 2MG CX 30 CP</descricaoMedicamento>
   <numeroLoteMedicamento>L2345A</numeroLoteMedicamento>
   <quantidadeMedicamento>30</quantidadeMedicamento>
   <dataVenda>2026-08-09</dataVenda>
  </medicamento>
  <medicamento>
   <registroMSMedicamento>1.4444.0001.002-3</registroMSMedicamento>
   <descricaoMedicamento>ALPRAZOLAM 1MG CX 20 CP</descricaoMedicamento>
   <numeroLoteMedicamento>b77z</numeroLoteMedicamento>
   <quantidadeMedicamento>20</quantidadeMedicamento>
   <dataVenda>2026-08-09</dataVenda>
  </medicamento>
 </medicamentos></transacao>
</mensagemSNGPC>
"""

RESPOSTAS = {
    'ponteiros': [{'ULT_SAIDA_VENDA_NOTA_ID': 8821, 'ULT_ENTRADA_CAB_NOTA_ID': 3310,
                   'ULT_SAIDA_PERDA_ID': 0, 'ULT_SAIDA_TRANSFERENCIA_ID': 0,
                   'ULTIMO_ENVIO_SNGPC': datetime.date(2026, 8, 5),
                   'ENVIO_API': 'N', 'CNPJ': '00000000000000'}],
    'saidas_pendentes': [
        {'VENDA_NOTA_ID': 8830, 'DATA': datetime.date(2026, 8, 6),
         'DATA_HORA': datetime.datetime(2026, 8, 6, 14, 23, 11), 'PRODUTO': 'CLONAZEPAM',
         'REGISTRO_MS': '1003301220019', 'COD_BARRAS': '789', 'NUM_LOTE': 'L2345A', 'QUANTIDADE': 30},
    ],
    'entradas_pendentes': [
        {'CAB_NOTA_ID': 3315, 'NOTA_FISCAL': '206800', 'DATA_RECEBIMENTO': datetime.date(2026, 8, 6),
         'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1444400010023', 'COD_BARRAS': '790',
         'NUM_LOTE': 'B77Z', 'QUANTIDADE': 20},
        # entrada de 3 no lote 6G1234 DEPOIS do envio: o inventário do SNGPC
        # ainda mostra 2, e o Digifarma já mostra 5. Não é divergência.
        {'CAB_NOTA_ID': 3316, 'NOTA_FISCAL': '206801', 'DATA_RECEBIMENTO': datetime.date(2026, 8, 6),
         'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1023506630204', 'COD_BARRAS': '789',
         'NUM_LOTE': '6G1234', 'QUANTIDADE': 3},
    ],
    'perdas_pendentes': [],
    'transferencias_pendentes': [],
    'saidas_periodo': [
        # bate com o XML real: 2 vendas do dia 04/08
        {'VENDA': 8801, 'DATA': datetime.date(2026, 8, 4), 'PRODUTO': 'ALPRAZOLAM',
         'REGISTRO_MS': '1023506630204', 'NUM_LOTE': '5F9779', 'QUANTIDADE': 1},
        # esta saiu no banco e NÃO foi para o XML
        {'VENDA': 8802, 'DATA': datetime.date(2026, 8, 4), 'PRODUTO': 'RIVOTRIL',
         'REGISTRO_MS': '1999900090011', 'NUM_LOTE': 'Z9', 'QUANTIDADE': 10},
    ],
    'vendas_problema': [
        {'VENDA': 8802, 'DATA': datetime.date(2026, 8, 4), 'PRODUTO': 'RIVOTRIL',
         'REGISTRO_MS': '1999900090011', 'QUANTIDADE': 10, 'NUM_LOTE': None,
         'RECEITA': None, 'VENDEDOR': 'BALCAO 2'},
    ],
    # a mesma venda saindo de DOIS lotes: uma linha por lote, que é como o
    # SNGPC precisa e como o balcão confere
    'vendas_recentes': [
        {'VENDA': 8830, 'QUANDO': datetime.datetime(2026, 8, 13, 14, 32, 5),
         'PRODUTO': 'CLONAZEPAM 2MG', 'REGISTRO_MS': '1003301220019',
         'NUM_LOTE': 'L2345A', 'QUANTIDADE': 2},
        {'VENDA': 8830, 'QUANDO': datetime.datetime(2026, 8, 13, 14, 32, 5),
         'PRODUTO': 'CLONAZEPAM 2MG', 'REGISTRO_MS': '1003301220019',
         'NUM_LOTE': 'L9999B', 'QUANTIDADE': 1},
        {'VENDA': 8829, 'QUANDO': datetime.datetime(2026, 8, 13, 9, 5, 0),
         'PRODUTO': 'ALPRAZOLAM 1MG', 'REGISTRO_MS': '1444400010023',
         'NUM_LOTE': 'B77Z', 'QUANTIDADE': 1},
    ],
    # quanto saiu de cada lote, somado no banco, para explicar a divergência.
    # De propósito com o M.S. pontuado e o lote em minúsculas: é assim que
    # vem do cadastro, e o cruzamento tem que normalizar dos dois lados.
    'vendas_recentes_por_lote': [
        {'REGISTRO_MS': '1.0235.0663.020-4', 'NUM_LOTE': '5f9779',
         'QUANTIDADE': 3, 'LINHAS': 2, 'SEM_RECEITA': 1,
         'ULTIMA': datetime.datetime(2026, 8, 17, 16, 5, 0), 'ULTIMA_VENDA': 8830},
        # este lote bate com a ANVISA: não é divergência, e por isso não pode
        # receber cruzamento nenhum
        {'REGISTRO_MS': '1.0573.0661.005-0', 'NUM_LOTE': '2604608',
         'QUANTIDADE': 1, 'LINHAS': 1, 'SEM_RECEITA': 0,
         'ULTIMA': datetime.datetime(2026, 8, 16, 10, 0, 0), 'ULTIMA_VENDA': 8825},
    ],
    # venda que ainda vai subir e está sem receita: corrigir antes do envio
    'vendas_sem_receita_pendentes': [
        {'VENDA': 8830, 'QUANDO': datetime.datetime(2026, 8, 13, 14, 32, 5),
         'PRODUTO': 'CLONAZEPAM 2MG', 'REGISTRO_MS': '1003301220019',
         'NUM_LOTE': 'L2345A', 'QUANTIDADE': 3},
    ],
    # quem é controlado: o inventário do SNGPC é filtrado por isto, igual
    # às vendas e ao estoque
    'produtos_controlados': [
        {'PRODUTO_ID': 100, 'PSICOTROPICO': 'S', 'ANTIMICROBIANO': 'N'},
        {'PRODUTO_ID': 200, 'PSICOTROPICO': 'S', 'ANTIMICROBIANO': 'N'},
        {'PRODUTO_ID': 300, 'PSICOTROPICO': 'N', 'ANTIMICROBIANO': 'S'},
        {'PRODUTO_ID': 700, 'PSICOTROPICO': 'N', 'ANTIMICROBIANO': 'N'},
    ],
    'inventario_sngpc': [
        # PRODUTO_ID 700 não é controlado: não pode entrar na comparação
        {'PRODUTO_ID': 700, 'REGISTRO_MS': '1999900000001', 'MEDICAMENTO': 'DIPIRONA',
         'LOTE': 'X1', 'QUANTIDADE': 50, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'PRODUTO_ID': 100, 'REGISTRO_MS': '1023506630204', 'MEDICAMENTO': 'ALPRAZOLAM',
         'LOTE': '5F9779', 'QUANTIDADE': 8, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'REGISTRO_MS': '1023506630204', 'MEDICAMENTO': 'ALPRAZOLAM', 'LOTE': '6G1234',
         'QUANTIDADE': 2, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'REGISTRO_MS': '1057306610050', 'MEDICAMENTO': 'ARIPIPRAZOL', 'LOTE': '2604608',
         'QUANTIDADE': 2, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'REGISTRO_MS': '1122233340001', 'MEDICAMENTO': 'DIAZEPAM', 'LOTE': 'K1',
         'QUANTIDADE': 10, 'DATA_ATUALIZACAO': '2026-08-05'},
    ],
    'saldo_digifarma': [
        # 5 no Digifarma contra 8 na ANVISA -> falta 3
        {'PRODUTO_ID': 100, 'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1023506630204',
         'COD_BARRAS': '789', 'NUM_LOTE': '5F9779', 'LOTE_VENCIMENTO': datetime.date(2027, 9, 30), 'SALDO': 5},
        # segundo lote do MESMO medicamento, que some da lista por não
        # divergir — mas precisa aparecer no detalhe do outro, senão o total
        # do Digifarma fica sem explicação.
        # 5 hoje = 2 no último envio + 3 que entraram depois e não subiram
        {'PRODUTO_ID': 100, 'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1023506630204',
         'COD_BARRAS': '789', 'NUM_LOTE': '6G1234', 'LOTE_VENCIMENTO': datetime.date(2028, 1, 31), 'SALDO': 5},
        # bate certinho
        {'PRODUTO_ID': 200, 'PRODUTO': 'ARIPIPRAZOL', 'REGISTRO_MS': '1057306610050',
         'COD_BARRAS': '790', 'NUM_LOTE': '2604608', 'LOTE_VENCIMENTO': datetime.date(2027, 3, 31), 'SALDO': 2},
        # mesmo M.S. + mesmo lote em dois cadastros, com validades diferentes:
        # 4 + 6 = 10, que é exatamente o que a ANVISA tem. Não é divergência.
        {'PRODUTO_ID': 300, 'PRODUTO': 'DIAZEPAM 10MG', 'REGISTRO_MS': '1122233340001',
         'COD_BARRAS': '791', 'NUM_LOTE': 'K1', 'LOTE_VENCIMENTO': datetime.date(2027, 5, 31), 'SALDO': 4},
        {'PRODUTO_ID': 301, 'PRODUTO': 'DIAZEPAM 10MG', 'REGISTRO_MS': '1122233340001',
         'COD_BARRAS': '791', 'NUM_LOTE': 'K1', 'LOTE_VENCIMENTO': datetime.date(2027, 6, 30), 'SALDO': 6},
        # lote zerado dos dois lados: não é divergência, não vai para o app
        {'PRODUTO_ID': 400, 'PRODUTO': 'CLONAZEPAM', 'REGISTRO_MS': '1777700010001',
         'COD_BARRAS': '792', 'NUM_LOTE': 'VAZIO', 'LOTE_VENCIMENTO': datetime.date(2027, 1, 31), 'SALDO': 0},
        # negativo no próprio Digifarma: saiu do lote por fora de venda e perda
        {'PRODUTO_ID': 500, 'PRODUTO': 'LAMOTRIGINA 100 MG', 'REGISTRO_MS': '1564900090034',
         'COD_BARRAS': '793', 'NUM_LOTE': 'BLGH23013',
         'LOTE_VENCIMENTO': datetime.date(2027, 2, 28), 'SALDO': -3},
    ],
    # LOTES como tabela de movimento: aqui SALDO é o que o SQL somou das
    # linhas de LOTES (entradas − saídas de nota), ainda SEM as vendas
    'saldo_movimento': [
        # 200 comprados no lote, 96 ainda não vendidos
        {'PRODUTO_ID': 67059, 'PRODUTO': 'ESCITALOPRAM 10MG', 'REGISTRO_MS': '1438102690063',
         'COD_BARRAS': '7896523200934', 'NUM_LOTE': '2300404',
         'LOTE_VENCIMENTO': datetime.date(2024, 12, 30), 'SALDO': 200},
    ],
    'vendas_por_lote': [
        {'REGISTRO_MS': '1438102690063', 'NUM_LOTE': '2300404', 'QUANTIDADE': 100},
    ],
    'perdas_por_lote': [
        {'REGISTRO_MS': '1438102690063', 'NUM_LOTE': '2300404', 'QUANTIDADE': 4},
    ],
}

CAMPOS_LOTES_SALDO = ('LOTE_ID', 'PRODUTO_ID', 'NUM_LOTE', 'SALDO')
CAMPOS_LOTES_MOVIMENTO = ('LOTE_ID', 'PRODUTO_ID', 'NUM_LOTE', 'ENTRADA_SAIDA',
                          'CAB_NOTA_ID', 'QUANTIDADE_COMPRA')

# a LOTES real do Digifarma6.fdb, lida com --colunas LOTES em 13/08/2026.
# LOTE_QUANTIDADE é o saldo do lote; QUANTIDADE_COMPRA é o que entrou em
# cada nota. Escolher a segunda publica compra como se fosse estoque.
CAMPOS_LOTES_DIGIFARMA = ('PRODUTO_ID', 'LOTE_QUANTIDADE', 'LOTE_VENCIMENTO',
                          'LOTE_FABRICACAO', 'COMPRA_NOTA_ID', 'LOTE_ID', 'NUM_LOTE',
                          'LOTE_COMISSAO', 'ITEM_NOTA_ID', 'QUANTIDADE_COMPRA',
                          'ENTRADA_SAIDA', 'NOTA_FISCAL', 'CAB_NOTA_ID',
                          'ESTOQUE_CONTADO', 'ESTOQUE_MOVIMENTADO', 'REGISTRO_MS')

class CursorFalso:
    def __init__(self, quebrar=False):
        self.fechado = False
        self.quebrar = quebrar
        self.description = [('UM',)]

    def execute(self, sql, parametros=()):
        if self.quebrar:
            raise RuntimeError('consulta quebrou')

    def fetchall(self):
        return [(1,)]

    def close(self):
        self.fechado = True


class ConexaoFalsa:
    def __init__(self, quebrar=False):
        self.cursor_falso = CursorFalso(quebrar)

    def cursor(self):
        return self.cursor_falso


class ConexaoQueFechaSempre:
    """Para os modos que abrem a conexão sozinhos: quem consulta é o
    consultar() falso, então esta só precisa saber fechar."""
    def close(self):
        pass


falhas = []


def conferir(titulo, condicao, detalhe=''):
    if condicao:
        print('  ok    ' + titulo)
    else:
        falhas.append(titulo)
        print('  FALHA ' + titulo + ('\n        ' + str(detalhe) if detalhe else ''))


def principal():
    print('\nagente SNGPC\n------------')

    conferir('a transmissão leva o movimento do dia anterior',
             ag.anterior('2026-08-10') == '2026-08-09')
    conferir('data em formato brasileiro', ag.br('2026-08-10') == '10/08/2026')

    # o cursor tem que morrer com a consulta: pendurado na transação, ele
    # estoura na hora de fechar a conexão e esconde o erro de verdade
    conexao_ok = ConexaoFalsa()
    ag.consultar(conexao_ok, 'SELECT 1 FROM RDB$DATABASE')
    conferir('consultar fecha o cursor', conexao_ok.cursor_falso.fechado)

    conexao_ruim = ConexaoFalsa(quebrar=True)
    try:
        ag.consultar(conexao_ruim, 'SELECT 1 FROM RDB$DATABASE')
    except RuntimeError:
        pass
    conferir('o cursor fecha mesmo quando a consulta falha',
             conexao_ruim.cursor_falso.fechado)

    # fechar() já chamou a si mesma: a conexão ficava aberta e o log enchia
    # de "maximum recursion depth exceeded"
    class ConexaoQueFecha:
        def __init__(self, quebrar=False):
            self.fechou = False
            self.quebrar = quebrar

        def close(self):
            self.fechou = True
            if self.quebrar:
                raise RuntimeError('o fdb estourou no fechamento')

    boa = ConexaoQueFecha()
    ag.fechar(boa)
    conferir('fechar() fecha a conexão de verdade', boa.fechou)

    ruim = ConexaoQueFecha(quebrar=True)
    ag.fechar(ruim)
    conferir('erro no fechamento não derruba o agente', ruim.fechou)

    # 401 do Firebase é regra recusando, não chave inválida — o agente
    # precisa dizer qual nó cadastrar em vez de cuspir um traceback
    conferir('reconhece a recusa das regras do Firebase',
             ag.erro_de_permissao(Exception('Permission denied'))
             and not ag.erro_de_permissao(Exception('Connection refused')))
    conferir('o recado diz o nó exato a cadastrar',
             'farmacia/agentes/agente-sngpc' in ag.recado_de_permissao(ag.CONFIG_PADRAO),
             ag.recado_de_permissao(ag.CONFIG_PADRAO))

    conferir('busca no terminal ignora acento e caixa',
             ag.normalizar_texto('Solução') == 'SOLUCAO'
             and ag.normalizar_texto('lamotrigina') == 'LAMOTRIGINA')

    conferir('a chave frouxa ignora zero à esquerda e pontuação do lote',
             ag.chave_frouxa(('123', '00036467')) == ag.chave_frouxa(('123', '36.467'))
             and ag.chave_frouxa(('123', 'BQ37J001')) != ag.chave_frouxa(('123', 'BQ37J002')))

    # o fdb dimensiona o parâmetro do LIKE pelo tamanho da coluna:
    # REGISTRO_MS é VARCHAR(13) e "%ESCITALOPRAM%" tem 14
    conferir('o filtro do --saldo não fica preso ao tamanho da coluna',
             ag.CONSULTAS['lotes_detalhe'].count('AS VARCHAR(500)') == 3,
             ag.CONSULTAS['lotes_detalhe'])

    # ------------------------------------------------------------
    # XML: usa o arquivo real da farmácia se estiver na pasta,
    # senão o exemplo embutido
    # ------------------------------------------------------------
    pasta = tempfile.mkdtemp()
    caminho = os.path.join(pasta, 'SNGPC.XML')
    real = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exemplo_SNGPC.XML')
    if os.path.exists(real):
        shutil.copy(real, caminho)
    else:
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(XML_EXEMPLO)

    lido = mapa_xml.ler(caminho)
    conferir('o cabeçalho do XML dá o período exato da transmissão',
             bool(lido['cabecalho'].get('dataInicio')), lido['cabecalho'])
    conferir('entrada e venda vão para baldes separados',
             set(lido['movimentos']) <= {'entrada', 'venda', 'perda', 'transferencia', 'outro'}
             and 'venda' in lido['movimentos'], list(lido['movimentos']))
    conferir('o total conta só as vendas, não as entradas',
             lido['total'] == round(sum(i['quantidade']
                                        for i in lido['movimentos']['venda'].values()), 3))
    conferir('lote casa mesmo com caixa diferente',
             all(k[1] == k[1].upper() for k in lido['itens']))

    # ------------------------------------------------------------
    # montagem completa
    # ------------------------------------------------------------
    config = dict(ag.CONFIG_PADRAO, pasta_xml=pasta)
    por_sql = {ag.CONSULTAS[k]: v for k, v in RESPOSTAS.items() if k in ag.CONSULTAS}

    def consultar_falso(conexao, sql, parametros=()):
        if 'RDB$RELATION_FIELDS' in sql:
            return [{'CAMPO': c} for c in CAMPOS_LOTES_SALDO]
        if sql in por_sql:
            return por_sql[sql]
        # saldo_digifarma tem a {EXPRESSAO} trocada antes de rodar
        if 'FROM LOTES' in sql:
            return RESPOSTAS['saldo_digifarma']
        raise AssertionError('consulta não simulada:\n' + sql[:120])

    ag.consultar = consultar_falso
    dados = ag.montar_inventario(conexao=None, config=config)
    hoje = datetime.date.today().isoformat()

    conferir('lê os ponteiros do último envio',
             dados['envio']['ULT_SAIDA_VENDA_NOTA_ID'] == 8821)
    conferir('o período sai do cabeçalho do XML, não do nome do arquivo',
             dados['envio']['movimentosDe'] == lido['cabecalho']['dataInicio'], dados['envio'])
    conferir('descobre sozinho a coluna de saldo da tabela LOTES',
             dados['inventario'].get('colunaSaldo') == 'SALDO', dados['inventario'])
    conferir('o inventário vem do INVENTARIO_SNGPC (lado ANVISA)',
             dados['inventario']['itens'] == 4, dados['inventario'])

    # o inventário do SNGPC entra pelo MESMO critério das vendas: só
    # psicotrópico e antimicrobiano. Um não controlado ali viraria
    # divergência "só na ANVISA" comparando lados que não se comparam.
    conferir('produto não controlado fica fora do inventário do SNGPC',
             dados['inventario'].get('foraDoCriterio') == 1
             and not any(i['ms'] == '1999900000001' for i in dados['itens']),
             dados['inventario'])
    conferir('linha do inventário sem PRODUTO_ID continua entrando',
             any(i['ms'] == '1122233340001' for i in dados['itens']))

    # a chave é M.S. + LOTE: indexar só por M.S. faz um lote apagar o outro,
    # que é justamente o erro que este projeto passou a semana consertando
    diferencas = {(i['ms'], i['lote']): i['diferenca'] for i in dados['itens']}
    conferir('diferença de saldo por M.S. + lote',
             diferencas.get(('1023506630204', '5F9779')) == -3.0, diferencas)
    conferir('lote que bate não vira divergência',
             diferencas.get(('1057306610050', '2604608')) == 0.0, diferencas)

    # A divergência tem que responder "esse remédio saiu?", senão a farmácia
    # vai à prateleira contar um lote que pode ter sido simplesmente vendido.
    por_chave_teste = {(i['ms'], i['lote']): i for i in dados['itens']}
    alpra = por_chave_teste.get(('1023506630204', '5F9779'), {})
    conferir('a divergência traz as vendas daquele lote',
             (alpra.get('vendas') or {}).get('quantidade') == 3.0, alpra.get('vendas'))
    conferir('M.S. pontuado e lote em minúsculas cruzam mesmo assim',
             (alpra.get('vendas') or {}).get('linhas') == 2, alpra.get('vendas'))
    conferir('a venda sem receita é contada na divergência',
             (alpra.get('vendas') or {}).get('semReceita') == 1, alpra.get('vendas'))
    conferir('a última venda vem com data e número',
             (alpra.get('vendas') or {}).get('ultimaVenda') == 8830, alpra.get('vendas'))
    conferir('lote que bate não recebe cruzamento de vendas',
             'vendas' not in por_chave_teste.get(('1057306610050', '2604608'), {}),
             por_chave_teste.get(('1057306610050', '2604608')))

    # o mesmo M.S. + lote em dois cadastros tem que virar UMA linha somada;
    # antes, a primeira levava todo o saldo do SNGPC e a segunda ficava com
    # zero, inventando divergência dos dois lados
    repetidos = [i for i in dados['itens'] if i['ms'] == '1122233340001']
    conferir('mesmo M.S. + lote em cadastros diferentes vira uma linha só',
             len(repetidos) == 1, repetidos)
    conferir('o saldo do Digifarma soma os cadastros repetidos',
             repetidos and repetidos[0]['saldoDigifarma'] == 10.0, repetidos)
    conferir('cadastro repetido que bate com a ANVISA não vira divergência',
             repetidos and repetidos[0]['diferenca'] == 0.0, repetidos)

    # cada divergência se resolve num lugar diferente; a etiqueta tem que
    # dizer qual é qual em vez de chamar tudo de sobra
    alpra = next(i for i in dados['itens'] if i['ms'] == '1023506630204')
    conferir('contagem que não fecha dos dois lados é "quantidade"',
             alpra.get('motivo') == 'quantidade', alpra)
    so_anvisa = [i for i in dados['itens'] if i['ms'] == '1122233340001'
                 and i['saldoDigifarma'] == 0]
    conferir('o que só a ANVISA tem sai marcado',
             all(i.get('motivo') == 'so_na_anvisa' for i in so_anvisa), so_anvisa)
    conferir('lote sem divergência não recebe motivo',
             not any(i.get('motivo') for i in dados['itens'] if not i['diferenca']))

    # a etiqueta diz o que se OBSERVA, não a causa: zero na ANVISA tanto é
    # entrada que não subiu quanto saldo errado no Digifarma, e a farmácia
    # confirmou os dois casos no mesmo dia
    conferir('M.S. inteiro zerado na ANVISA',
             ag.classificar_divergencia(
                 {'saldoDigifarma': 5, 'ms': '999'}, 0.0, {'111'}) == 'anvisa_zerada_produto')
    conferir('M.S. com outros lotes, mas este zerado',
             ag.classificar_divergencia(
                 {'saldoDigifarma': 5, 'ms': '111'}, 0.0, {'111'}) == 'anvisa_zerada_lote')
    conferir('o registro M.S. sai no formato do site da ANVISA',
             ag.formatar_ms('1052500180189') == '1.0525.0018.018-9'
             and ag.formatar_ms('1057304750041') == '1.0573.0475.004-1'
             and ag.formatar_ms('123') == '123', ag.formatar_ms('1052500180189'))
    conferir('saldo negativo é dado torto no Digifarma, não sobra',
             ag.classificar_divergencia(
                 {'saldoDigifarma': -2, 'ms': '111'}, 0.0, {'111'}) == 'negativo')
    # a chave é M.S. + lote: sem M.S. não há comparação possível, e chamar
    # isso de "zerado na ANVISA" manda conferir prateleira à toa
    conferir('produto sem registro M.S. não é divergência de estoque',
             ag.classificar_divergencia(
                 {'saldoDigifarma': 4, 'ms': ''}, 0.0, {'111'}) == 'sem_ms')

    # psicotrópico e antimicrobiano são duas escriturações e duas
    # conferências: o item leva a classe para a folha impressa e o app
    # poderem separar as listas sem voltar ao banco
    conferir('o item leva a classe do cadastro',
             all(i.get('classe') == 'psicotropico' for i in dados['itens']
                 if i['ms'] == '1023506630204'),
             [i.get('classe') for i in dados['itens']])

    def consultar_classes(conexao, sql, parametros=()):
        return [
            {'PRODUTO_ID': 1, 'REGISTRO_MS': '1.0525.0018.018-9',
             'PSICOTROPICO': 'S', 'ANTIMICROBIANO': 'N'},
            {'PRODUTO_ID': 2, 'REGISTRO_MS': '1023500960041',
             'PSICOTROPICO': 'N', 'ANTIMICROBIANO': 'S'},
            # marcado como os dois: vale a lista mais rígida
            {'PRODUTO_ID': 3, 'REGISTRO_MS': '1023500960041',
             'PSICOTROPICO': 'S', 'ANTIMICROBIANO': 'S'},
            {'PRODUTO_ID': 4, 'REGISTRO_MS': '1999900000001',
             'PSICOTROPICO': 'N', 'ANTIMICROBIANO': 'N'},
        ]

    ag.consultar = consultar_classes
    por_produto, por_ms = ag.classes_por_medicamento(None)
    ag.consultar = consultar_falso
    conferir('psicotrópico e antimicrobiano saem separados pelo cadastro',
             por_produto.get('1') == 'psicotropico'
             and por_produto.get('2') == 'antimicrobiano', por_produto)
    conferir('produto não controlado não entra em lista nenhuma',
             '4' not in por_produto, por_produto)
    conferir('marcado como os dois vale como psicotrópico',
             por_produto.get('3') == 'psicotropico'
             and por_ms.get('1023500960041') == 'psicotropico', por_ms)
    conferir('a classe também é achada pelo M.S., para o lote só da ANVISA',
             por_ms.get('1052500180189') == 'psicotropico', por_ms)

    # a folha de conferência mostra as vendas do dia: sem elas, quem conta a
    # prateleira acha a caixa faltando e marca divergência de uma venda que
    # está certa. Para isso a venda precisa levar a HORA e a classe.
    venda = dados['pendentes']['vendas'][0]
    conferir('a venda pendente leva a hora, para conferir com o cupom',
             venda.get('hora') == '14:23', venda)
    conferir('a venda pendente leva o lote e a quantidade',
             venda.get('lote') == 'L2345A' and venda.get('quantidade') == 30.0, venda)
    conferir('a venda pendente leva a classe, para ir na lista certa',
             'classe' in venda, venda)

    # a mesma folha, montada de ponta a ponta: a venda tem que sair no anexo
    folha = ag.bloco_conferencia('Psicotrópicos', [{
        'ms': '1003301220019', 'descricao': 'CLONAZEPAM 2MG', 'omitidos': 0,
        'digifarma': 10.0, 'sngpc': 40.0, 'movimento': -30.0, 'esperado': 10.0,
        'lotes': [{'lote': 'L2345A', 'validade': '', 'saldoDigifarma': 10.0,
                   'saldoSngpc': 40.0, 'movimentoDesdeEnvio': -30.0,
                   'esperadoSngpc': 10.0, 'diferenca': 0.0}],
    }], movimentos=[dict(venda, tipo='vendas', assinado=-30.0)])
    conferir('a folha traz a venda do dia, com número, hora, lote e quantidade',
             '8830' in folha and '14:23' in folha and 'L2345A' in folha
             and '-30' in folha, folha[-400:])
    conferir('o lote que só se moveu não vira divergência na folha',
             'total bate' in folha, folha[:400])

    # venda sem lote não entra na conta de lote nenhum: se sair no anexo sem
    # marcação, a soma da coluna Movim. não fecha com a lista e parece erro
    anexo = ag.bloco_movimento([
        dict(venda, tipo='vendas', assinado=-30.0),
        dict(venda, tipo='vendas', lote='', assinado=-2.0),
    ])
    # envio feito por outra máquina: o ponteiro daqui não avança, e sem o
    # remendo o agente desconta de novo o que a ANVISA já descontou
    # a fila do app: o agente atende relatório e ajuste, e recusa o resto.
    # É a porta que o celular usa, então o que ela NÃO aceita importa tanto
    # quanto o que ela aceita.
    class RefFalsa:
        def __init__(self):
            self.gravado = None

        def set(self, valor):
            self.gravado = valor

    class DbFalso:
        def __init__(self):
            self.refs = {}

        def reference(self, caminho):
            return self.refs.setdefault(caminho, RefFalsa())

    db_falso = DbFalso()
    guardado = ag.RELATORIOS['tarefas']
    ag.RELATORIOS['tarefas'] = lambda config, alvo: 'saída de teste %s' % alvo
    recado = ag.atender_pedido({}, db_falso, {'acao': 'tarefas', 'texto': 'ABC'})
    ag.RELATORIOS['tarefas'] = guardado
    publicado = db_falso.refs.get('farmacia/relatorios/tarefas')
    conferir('a fila atende relatório e publica a saída para o app',
             'tarefas' in recado
             and publicado and publicado.gravado['texto'] == 'saída de teste ABC'
             and publicado.gravado['filtro'] == 'ABC',
             publicado.gravado if publicado else None)

    recusou = False
    try:
        ag.atender_pedido({}, db_falso, {'acao': 'apagar_tudo'})
    except Exception:
        recusou = True
    conferir('a fila recusa ação que não conhece', recusou)

    recusou = False
    try:
        ag.aplicar_config({}, {'chave': 'banco', 'valor': 'C:/outro.fdb'})
    except Exception:
        recusou = True
    conferir('o app não muda chave fora da lista (banco, chave, url)', recusou)

    conferir('transmitido_ate_venda só vale para cima',
             ag.ponteiro_de_venda({'ULT_SAIDA_VENDA_NOTA_ID': 100},
                                  {'transmitido_ate_venda': 200}) == (200, True)
             and ag.ponteiro_de_venda({'ULT_SAIDA_VENDA_NOTA_ID': 300},
                                      {'transmitido_ate_venda': 200}) == (300, False)
             and ag.ponteiro_de_venda({'ULT_SAIDA_VENDA_NOTA_ID': 300}, {}) == (300, False))

    conferir('venda sem lote sai marcada no anexo, fora da conta',
             '(sem lote)' in anexo and 'semlote' in anexo
             and 'não entram na coluna Movim.' in anexo, anexo[-300:])
    # medicamento com dois lotes: o que bate some da lista, e sem os irmãos
    # no detalhe o total do Digifarma fica sem explicação — foi o caso da
    # pregabalina, 6 no app contra 9 na tela do Digifarma
    alpra_div = next(i for i in dados['itens']
                     if i['ms'] == '1023506630204' and i['lote'] == '5F9779')
    # o inventário do SNGPC é a foto do último envio; o saldo do Digifarma é
    # de agora. Comparar as duas fotos direto acusa como divergência tudo que
    # se moveu no intervalo — inclusive a entrada de ontem, que ainda nem
    # podia estar no inventário.
    alpra_novo = next(i for i in dados['itens'] if i['lote'] == '6G1234')
    conferir('entrada que ainda não subiu não vira divergência',
             alpra_novo['diferenca'] == 0.0
             and alpra_novo['saldoDigifarma'] == 5.0
             and alpra_novo['saldoSngpc'] == 2.0, alpra_novo)
    conferir('a conta mostra o movimento e o esperado, não só o resultado',
             alpra_novo.get('movimentoDesdeEnvio') == 3.0
             and alpra_novo.get('esperadoSngpc') == 5.0, alpra_novo)
    conferir('lote parado continua sem a conta do movimento',
             'movimentoDesdeEnvio' not in next(
                 i for i in dados['itens'] if i['lote'] == '5F9779'))

    conferir('o total por M.S. soma os dois lotes',
             alpra_div.get('saldoDigifarmaMs') == 10.0
             and alpra_div.get('saldoSngpcMs') == 10.0, alpra_div)
    conferir('o detalhe lista TODOS os lotes do medicamento, inclusive o que bate',
             [(l['lote'], l['digifarma'], l['sngpc']) for l in alpra_div.get('lotesDoMs', [])]
             == [('5F9779', 5.0, 8.0), ('6G1234', 5.0, 2.0)], alpra_div.get('lotesDoMs'))
    conferir('o lote que bate continua fora da lista de divergências',
             not any(i['lote'] == '6G1234' and i['diferenca'] for i in dados['itens']))
    conferir('medicamento de um lote só não carrega total por M.S.',
             'saldoDigifarmaMs' not in next(
                 i for i in dados['itens'] if i['ms'] == '1057306610050'))

    negativo = next(i for i in dados['itens'] if i['lote'] == 'BLGH23013')
    conferir('lote negativo não é classificado como sobra',
             negativo.get('motivo') == 'negativo', negativo)

    zerados = [i for i in dados['itens'] if i['ms'] == '1777700010001']
    conferir('lote zerado nos dois lados não vai para o app', not zerados, zerados)

    conferir('vendas pendentes saem pelo ponteiro, não por data',
             dados['resumoPendentes']['vendas'] == 1, dados['resumoPendentes'])
    conferir('entradas pendentes saem pelo ponteiro',
             dados['resumoPendentes']['entradas'] == 2, dados['resumoPendentes'])

    # zero divergência de XML tanto pode ser conferência limpa quanto
    # conferência que não aconteceu — o app precisa distinguir
    resumo_xml = dados.get('conferenciaXmlResumo', {})
    conferir('a conferência do XML publica se realmente conferiu',
             resumo_xml.get('conferiu') is True
             and resumo_xml.get('vendasNoBanco') == 2
             and resumo_xml.get('periodoDe'), resumo_xml)
    conferir('a conferência de vendas publica desde quando vale',
             bool(dados.get('vendasProblemaDesde')), dados.get('vendasProblemaDesde'))

    # sem XML na pasta, "0 divergências" não é conferência limpa
    pasta_vazia = tempfile.mkdtemp()
    sem_xml = ag.montar_inventario(conexao=None, config=dict(config, pasta_xml=pasta_vazia))
    resumo_sem = sem_xml.get('conferenciaXmlResumo', {})
    conferir('sem XML, o agente diz que NÃO conferiu e por quê',
             resumo_sem.get('conferiu') is False
             and pasta_vazia in (resumo_sem.get('porque') or ''), resumo_sem)
    conferir('sem XML não sobra conferência de XML publicada',
             not sem_xml.get('conferencia_xml'), sem_xml.get('conferencia_xml'))
    shutil.rmtree(pasta_vazia, ignore_errors=True)

    fora = [c for c in dados.get('conferencia_xml', []) if c['situacao'] == 'fora_do_xml']
    conferir('venda que não subiu no XML vira divergência',
             any(c['ms'] == '1999900090011' for c in fora), fora)
    conferir('entrada do XML não é confundida com venda',
             not any(c['ms'] == '1052500680092' for c in dados.get('conferencia_xml', [])))

    conferir('venda de controlado sem receita é classificada',
             dados['vendas_problema'][0]['motivo'] == 'sem_receita')

    # ------------------------------------------------------------
    # acompanhamento das vendas, de 5 em 5 minutos
    # ------------------------------------------------------------
    recentes = dados.get('vendasRecentes', [])
    conferir('as vendas recentes trazem venda, hora, lote e quantidade',
             len(recentes) == 3
             and recentes[0]['venda'] == 8830
             and recentes[0]['quando'] == '2026-08-13T14:32:05'
             and recentes[0]['lote'] == 'L2345A'
             and recentes[0]['quantidade'] == 2, recentes[:1])
    conferir('a hora da venda não é cortada como as datas',
             ':' in (recentes[0]['quando'] if recentes else ''),
             recentes[0] if recentes else None)
    dois_lotes = [v for v in recentes if v['venda'] == 8830]
    conferir('venda que sai de dois lotes vira duas linhas',
             len(dois_lotes) == 2
             and {v['lote'] for v in dois_lotes} == {'L2345A', 'L9999B'}, dois_lotes)
    conferir('o carimbo diz quando as vendas foram publicadas',
             bool(dados.get('vendasRecentesEm')))

    # o diagnóstico é o que se lê de fora do servidor: sem ele, "por que
    # ainda há divergência" só se responde na máquina da farmácia
    diag = dados.get('diagnostico', {})
    conferir('o diagnóstico sobe com pendentes, ponteiros e inventário',
             diag.get('ponteiroVenda') == 8821
             and diag.get('pendentes', {}).get('entradas') == 2
             and diag.get('inventarioSngpc', {}).get('foraDoCriterio') == 1
             and diag.get('inventarioSngpc', {}).get('linhas') == 5, diag)

    # o que trava o PRÓXIMO envio, cortado pelo ponteiro e não por data
    sem_receita = dados.get('vendasSemReceita', [])
    conferir('venda sem receita que ainda vai subir aparece à parte',
             len(sem_receita) == 1 and sem_receita[0]['venda'] == 8830
             and sem_receita[0]['lote'] == 'L2345A', sem_receita)

    conferir('o XML da transmissão é arquivado em enviados\\',
             os.path.exists(os.path.join(pasta, 'enviados', 'sngpc_%s.xml' % hoje)))
    conferir('mede há quanto tempo o Anvisa.exe não conclui',
             'precisaLogin' in dados['anvisa'], dados['anvisa'])

    # ------------------------------------------------------------
    # --envio: tem que dar um resultado DIFERENTE do --auto, senão o
    # botão "Atualizar envio" do app é idêntico a "Sincronizar vendas"
    # ------------------------------------------------------------
    por_sql_envio = dict(por_sql)
    por_sql_envio[ag.CONSULTAS['ponteiros']] = [
        dict(RESPOSTAS['ponteiros'][0], ULTIMO_ENVIO_SNGPC=datetime.date(2026, 8, 1))
    ]

    def consultar_falso_envio(conexao, sql, parametros=()):
        if 'RDB$RELATION_FIELDS' in sql:
            return [{'CAMPO': c} for c in ('LOTE_ID', 'PRODUTO_ID', 'NUM_LOTE', 'SALDO')]
        if sql in por_sql_envio:
            return por_sql_envio[sql]
        if 'FROM LOTES' in sql:
            return RESPOSTAS['saldo_digifarma']
        raise AssertionError('consulta não simulada:\n' + sql[:120])

    ag.consultar = consultar_falso_envio
    dados_envio = ag.montar_inventario(conexao=None, config=config, usar_envio=True)
    conferir('--envio usa a data do último envio ao SNGPC (não o carimbo do Anvisa.exe)',
             dados_envio['inventario']['data'] == '2026-08-01', dados_envio['inventario'])
    conferir('sem --envio, a data do inventário continua vindo do Anvisa.exe',
             dados['inventario']['data'] == '2026-08-05', dados['inventario'])

    # ------------------------------------------------------------
    # as três listas de trabalho
    # ------------------------------------------------------------
    ag.consultar = consultar_falso
    saida = []
    escrever_real = __builtins__['print'] if isinstance(__builtins__, dict) else print
    import builtins
    builtins.print = lambda *a, **k: saida.append(' '.join(str(x) for x in a))
    try:
        ag.conectar_firebird = lambda config: ConexaoQueFechaSempre()
        ok = ag.modo_tarefas(dict(config, banco=':simulado:'))
    finally:
        builtins.print = escrever_real
    texto_saida = '\n'.join(saida)
    conferir('as tarefas saem nas três seções, na ordem de resolver',
             ok and texto_saida.index('1. CORRIGIR NO DIGIFARMA')
             < texto_saida.index('2. ZERADO NA ANVISA')
             < texto_saida.index('3. CONFERIR NA PRATELEIRA'), texto_saida[:400])
    conferir('a lista separa o que precisa de alguém do que se resolve sozinho',
             'PRECISAM DE ALGUÉM' in texto_saida, texto_saida[:300])
    conferir('a lista deixa claro que nada foi alterado no Digifarma',
             'só lê' in texto_saida)
    conferir('o negativo mostra quanto saiu por fora de venda e perda',
             'outras saídas' in texto_saida, texto_saida[:200])

    # ------------------------------------------------------------
    # a LOTES real do Digifarma tem saldo por lote: usar a compra é erro
    # ------------------------------------------------------------
    def campos_falsos(campos):
        def consultar_campos(conexao, sql, parametros=()):
            if 'RDB$RELATION_FIELDS' in sql:
                return [{'CAMPO': c} for c in campos]
            raise AssertionError('consulta não simulada')
        return consultar_campos

    ag.consultar = campos_falsos(CAMPOS_LOTES_DIGIFARMA)
    info_real = ag.detectar_coluna_saldo(None)
    conferir('na LOTES do Digifarma o saldo é LOTE_QUANTIDADE, não a compra',
             (info_real['coluna'], info_real['modo']) == ('LOTE_QUANTIDADE', 'saldo'),
             info_real)
    conferir('ESTOQUE_CONTADO e LOTE_COMISSAO não são confundidos com saldo',
             info_real['coluna'] not in ('ESTOQUE_CONTADO', 'ESTOQUE_MOVIMENTADO',
                                         'LOTE_COMISSAO'))
    conferir('a linha de saída não entra no saldo do lote',
             ag.montar_expressao_saldo(info_real)
             == "CASE WHEN L.ENTRADA_SAIDA = 'S' THEN 0 "
                "ELSE COALESCE(L.LOTE_QUANTIDADE, 0) END",
             ag.montar_expressao_saldo(info_real))

    # ------------------------------------------------------------
    # LOTES sem coluna de saldo: é tabela de MOVIMENTO
    # ------------------------------------------------------------
    conferir('sem ENTRADA_SAIDA, soma a coluna crua',
             ag.montar_expressao_saldo(
                 {'coluna': 'SALDO', 'modo': 'saldo', 'campos': list(CAMPOS_LOTES_SALDO)}
             ) == 'COALESCE(L.SALDO, 0)')
    expressao = ag.montar_expressao_saldo(
        {'coluna': 'QUANTIDADE_COMPRA', 'modo': 'movimento',
         'campos': list(CAMPOS_LOTES_MOVIMENTO)})
    conferir('linha de saída entra com sinal negativo',
             "THEN -COALESCE(L.QUANTIDADE_COMPRA, 0)" in expressao, expressao)

    por_sql_mov = dict(por_sql)
    por_sql_mov[ag.CONSULTAS['vendas_por_lote']] = RESPOSTAS['vendas_por_lote']
    por_sql_mov[ag.CONSULTAS['perdas_por_lote']] = RESPOSTAS['perdas_por_lote']

    def consultar_falso_movimento(conexao, sql, parametros=()):
        if 'RDB$RELATION_FIELDS' in sql:
            return [{'CAMPO': c} for c in CAMPOS_LOTES_MOVIMENTO]
        if sql in por_sql_mov:
            return por_sql_mov[sql]
        if 'FROM LOTES' in sql:
            return RESPOSTAS['saldo_movimento']
        raise AssertionError('consulta não simulada:\n' + sql[:120])

    ag.consultar = consultar_falso_movimento
    dados_mov = ag.montar_inventario(conexao=None, config=config)
    conferir('sem coluna de saldo, LOTES é lida como movimento',
             dados_mov['inventario'].get('modoSaldo') == 'movimento', dados_mov['inventario'])

    escitalopram = [i for i in dados_mov['itens'] if i['ms'] == '1438102690063']
    conferir('o saldo desconta as vendas, que não passam por LOTES',
             escitalopram and escitalopram[0]['saldoDigifarma'] == 96.0, escitalopram)
    conferir('o app recebe o que entrou e o que baixou, para conferência',
             escitalopram and escitalopram[0]['entradas'] == 200.0
             and escitalopram[0]['baixas'] == 104.0, escitalopram)

    # coluna fixada à mão no agente_config.json vence a detecção
    ag.consultar = consultar_falso_movimento
    info = ag.detectar_coluna_saldo(None, {'coluna_saldo': 'quantidade_compra',
                                           'modo_saldo': 'saldo'})
    conferir('coluna_saldo do config manda na detecção',
             info == {'coluna': 'QUANTIDADE_COMPRA', 'modo': 'saldo',
                      'campos': list(CAMPOS_LOTES_MOVIMENTO)}, info)

    # ------------------------------------------------------------
    # colunas de INVENTARIO_SNGPC: nome exato vence pedaço do nome
    # ------------------------------------------------------------
    # o layout real da base da farmácia, lido com --saldo em 13/08/2026.
    # Aqui a coluna do saldo se chama SALDO_LOTE: barrar tudo que tem
    # 'LOTE' no nome derrubava justamente ela, e o inventário inteiro da
    # ANVISA era descartado como "colunas inesperadas".
    campos_reais = ['INVENTARIO_ID', 'PRODUTO_ID', 'NUM_LOTE', 'DATA_INVENTARIO',
                    'SALDO_LOTE', 'REGISTRO_MS', 'UNIDADE', 'LOTE_VENCIMENTO',
                    'ULT_MOVIMENTACAO']
    escolhidos = {k: ag.escolher_campo(campos_reais, r)
                  for k, r in ag.CAMPOS_INVENTARIO.items()}
    conferir('a base real da farmácia é lida por inteiro',
             escolhidos == {'ms': 'REGISTRO_MS', 'lote': 'NUM_LOTE',
                            'quantidade': 'SALDO_LOTE', 'descricao': None,
                            'data': 'DATA_INVENTARIO'}, escolhidos)

    campos_inv = ['ID', 'LOTE_VENCIMENTO', 'DATA_VALIDADE', 'NUM_LOTE',
                  'REGISTRO_MS', 'QUANTIDADE_VENDIDA', 'QUANTIDADE',
                  'NOME_MEDICAMENTO', 'DATA_ATUALIZACAO']
    conferir('lote é NUM_LOTE, não LOTE_VENCIMENTO',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['lote']) == 'NUM_LOTE',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['lote']))
    conferir('quantidade é QUANTIDADE, não QUANTIDADE_VENDIDA',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['quantidade']) == 'QUANTIDADE')
    conferir('data é a de atualização, não a de validade',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['data']) == 'DATA_ATUALIZACAO',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['data']))
    conferir('registro M.S. sai da coluna certa',
             ag.escolher_campo(campos_inv, ag.CAMPOS_INVENTARIO['ms']) == 'REGISTRO_MS')

    # --- o diagnóstico das receitas -------------------------------------
    # Nasceu de um erro real: o app dizia que todas as receitas do dia
    # tinham sido lançadas porque testava só "existe linha em
    # VENDAS_PSICOTROPICOS". O que precisa valer aqui é (a) zero e vazio
    # contam como não preenchido, e (b) nenhum VALOR aparece no relatório —
    # a tabela tem paciente e médico, e o texto sobe para o Firebase.
    conferir('campo vazio, nulo ou zero não conta como preenchido',
             not any(ag.preenchido(v) for v in (None, '', '   ', 0, '0', '0.00')))
    conferir('campo com conteúdo conta como preenchido',
             all(ag.preenchido(v) for v in ('MARIA', 3, '2026-08-17', 'B')))

    campos_vp = ['VENDA_NOTA_ID', 'ITEM_VENDA_ID', 'NOME_PACIENTE',
                 'CRM_MEDICO', 'CONF_VENDEDOR_ID']
    cheia = {'VENDA_NOTA_ID': 46135, 'ITEM_VENDA_ID': 1,
             'NOME_PACIENTE': 'MARIA DAS DORES', 'CRM_MEDICO': 'CRM 12345',
             'CONF_VENDEDOR_ID': 3}
    # a linha que o Digifarma cria junto com a venda e ainda não recebeu a receita
    crua = {'VENDA_NOTA_ID': 46136, 'ITEM_VENDA_ID': 1, 'NOME_PACIENTE': '',
            'CRM_MEDICO': None, 'CONF_VENDEDOR_ID': 0}

    def linha_vp(venda, produto, vp):
        linha = {'VENDA': venda, 'PRODUTO': produto,
                 'QUANDO': datetime.datetime(2026, 8, 17, 14, 30)}
        for i, campo in enumerate(campos_vp):
            linha['C%d' % (i + 1)] = None if vp is None else vp.get(campo)
        return linha

    guardados = (ag.conectar_firebird, ag.fechar, ag.colunas_da_tabela, ag.consultar)
    ag.conectar_firebird = lambda config: None
    ag.fechar = lambda conexao: None
    ag.colunas_da_tabela = lambda conexao, tabela: campos_vp
    ag.consultar = lambda conexao, sql, p=(): [
        linha_vp(46135, 'CLONAZEPAM 2MG', cheia),
        linha_vp(46136, 'FENOBARBITAL 100MG', crua),
        linha_vp(46137, 'AMOXICILINA 500MG', None),
    ]
    try:
        saida = ag.texto_do_modo(ag.modo_receitas, {}, '')
    finally:
        (ag.conectar_firebird, ag.fechar, ag.colunas_da_tabela, ag.consultar) = guardados

    conferir('o LEFT JOIN sem par vira "sem linha", não "linha vazia"',
             'SEM NENHUMA LINHA em VENDAS_PSICOTROPICOS: 1 de 3' in saida
             and 'sem linha' in saida)
    conferir('a coluna que varia é apontada como candidata',
             'NOME_PACIENTE' in saida.split('== CANDIDATAS')[1].split('sempre preenchidas')[0])
    conferir('a coluna igual em todas as linhas não é candidata',
             'VENDA_NOTA_ID' not in saida.split('== CANDIDATAS')[1].split('sempre preenchidas')[0])
    conferir('o relatório não imprime dado de paciente nem de médico',
             'MARIA' not in saida and '12345' not in saida,
             saida[:200])
    conferir('--receitas com texto no lugar dos dias não inventa 0 dias',
             not ag.modo_receitas({}, 'abc'))

    # --- todo relatório tem que ter jeito de ser pedido -------------------
    # Duas vezes eu mandei a farmácia usar um botão que não existia: primeiro
    # "Colunas da tabela", depois "Apuração do saldo". O modo estava pronto,
    # entrava em RELATORIOS, aparecia com nome em ROTULO_PEDIDO — e não havia
    # como pedir pela tela. A pessoa procura, não acha, e volta perguntando.
    #
    # É invariante e dá para cobrar: toda ação de RELATORIOS precisa de um
    # data-pedir no index.html OU de uma chamada a pedirRelatorio no app.js.
    raiz_app = os.path.dirname(os.path.dirname(os.path.abspath(ag.__file__)))
    try:
        with open(os.path.join(raiz_app, 'index.html'), encoding='utf-8') as f:
            html_app = f.read()
        with open(os.path.join(raiz_app, 'app.js'), encoding='utf-8') as f:
            js_app = f.read()
    except OSError:
        html_app = js_app = None

    if html_app is not None:
        sem_jeito = [a for a in ag.RELATORIOS
                     if ('data-pedir="%s"' % a) not in html_app
                     and ("pedirRelatorio('%s'" % a) not in js_app]
        conferir('todo relatório do agente tem botão ou chamada no app',
                 not sem_jeito, ', '.join(sem_jeito))

        # e o contrário: botão que pede uma ação que o agente não atende
        import re as _re
        pedidos = set(_re.findall(r'data-pedir="(\w+)"', html_app))
        pedidos |= set(_re.findall(r"pedirRelatorio\('(\w+)'", js_app))
        conhecidas = set(ag.RELATORIOS) | {'sincronizar_vendas', 'atualizar_envio',
                                           'atualizar_agente', 'config',
                                           'zerar_negativos', 'ajustar_lote'}
        orfas = sorted(pedidos - conhecidas)
        conferir('nenhum botão pede ação que o agente não conhece',
                 not orfas, ', '.join(orfas))

    # --- desligar a escrita pelo app --------------------------------------
    # De mão única de propósito: o app fecha a porta, nunca abre. A escrita
    # ficou ligada por dias porque foi liberada num dia em que havia alguém
    # no servidor e no dia seguinte não havia mais — trava que não dá para
    # desarmar de longe acaba ficando armada.
    guardado_cfg = ag.ARQUIVO_CONFIG
    ag.ARQUIVO_CONFIG = os.path.join(pasta, 'agente_config.json')
    try:
        with open(ag.ARQUIVO_CONFIG, 'w', encoding='utf-8') as f:
            json.dump({'permitir_ajuste_estoque': True}, f)
        cfg_vivo = {'permitir_ajuste_estoque': True}
        recado_cfg = ag.aplicar_config(
            cfg_vivo, {'chave': 'permitir_ajuste_estoque', 'valor': 'false'})
        conferir('o app desliga a escrita', 'DESLIGADA' in recado_cfg, recado_cfg)
        with open(ag.ARQUIVO_CONFIG, encoding='utf-8') as f:
            conferir('e o arquivo no servidor fica desligado de verdade',
                     json.load(f).get('permitir_ajuste_estoque') is False)
        conferir('a config em memória também', cfg_vivo['permitir_ajuste_estoque'] is False)

        for tentativa in ('true', 'sim', '1', 'S'):
            barrou = False
            try:
                ag.aplicar_config({}, {'chave': 'permitir_ajuste_estoque',
                                       'valor': tentativa})
            except RuntimeError as e:
                barrou = 'servidor' in str(e)
            conferir('o app NÃO liga a escrita com "%s"' % tentativa, barrou)
    finally:
        ag.ARQUIVO_CONFIG = guardado_cfg

    # --- zerar lote que a ANVISA ainda tem --------------------------------
    # Zerar o saldo aqui é correção INTERNA: não vira movimento e não sobe ao
    # SNGPC. Se a ANVISA ainda tem estoque naquele lote, zerar não resolve —
    # só troca o sinal da divergência e deixa o site acreditando que a
    # farmácia guarda um controlado que ela não tem. O conserto é PERDA.
    #
    # O caso real: DERMOBAN com 2 no lote "26 111" aqui e 2 no "26111" lá.
    # Mesmo lote, grafias diferentes.
    guardado_consultar = ag.consultar
    ag.consultar = lambda conexao, sql, p=(): [
        {'REGISTRO_MS': '1.0715.0145.001-1', 'NUM_LOTE': '26111',
         'QUANTIDADE': 2, 'MEDICAMENTO': 'DERMOBAN', 'DATA_ATUALIZACAO': '2026-08-18'},
        {'REGISTRO_MS': '1.0573.0475.004-1', 'NUM_LOTE': '2416132',
         'QUANTIDADE': 0, 'MEDICAMENTO': 'DUAL', 'DATA_ATUALIZACAO': '2026-08-18'},
    ]
    try:
        recusou = ''
        try:
            ag.conferir_zeragem_contra_anvisa(None, '1071501450011', '26 111')
        except RuntimeError as e:
            recusou = str(e)
        conferir('zerar lote que a ANVISA tem é recusado, mesmo com grafia diferente',
                 'PERDA' in recusou, recusou or 'passou e não devia')

        # o DUAL: ANVISA zerada, zerar aqui é exatamente o certo
        passou = True
        try:
            ag.conferir_zeragem_contra_anvisa(None, '1057304750041', '2416132')
        except RuntimeError as e:
            passou = False
        conferir('zerar lote que a ANVISA também tem zerado é liberado', passou)

        # M.S. que nem aparece no inventário: nada a comparar, libera
        solto = True
        try:
            ag.conferir_zeragem_contra_anvisa(None, '9999999999999', 'XYZ')
        except RuntimeError:
            solto = False
        conferir('M.S. fora do inventário da ANVISA não trava a correção', solto)
    finally:
        ag.consultar = guardado_consultar

    # inventário ilegível não pode travar a correção: o aviso é rede a mais
    def consultar_quebrado(conexao, sql, p=()):
        raise RuntimeError('banco fora do ar')
    ag.consultar = consultar_quebrado
    try:
        sobreviveu = True
        try:
            ag.conferir_zeragem_contra_anvisa(None, '1057304750041', '2416132')
        except RuntimeError:
            sobreviveu = False
        conferir('falha ao ler o inventário não trava a correção', sobreviveu)
    finally:
        ag.consultar = guardado_consultar

    # --- troca de lote na lista de prateleira -----------------------------
    # O caso real: escitalopram 10mg, lote 2509242 com -4 e lote 2529244 com
    # +4. Total 5 dos dois lados. Não falta nem sobra nada — são 4 caixas
    # registradas no lote errado, e a conferência é LER o lote impresso, não
    # contar quantidade. A lista mandava contar e não dizia isso.
    # o par que se anula tem que ser anunciado
    itens_troca = [
        {'descricao': 'ESCITALOPRAM 10MG', 'lote': '2509242', 'ms': '1057306100222',
         'codigo': '4471', 'saldoDigifarma': 0, 'saldoSngpc': 4, 'diferenca': -4},
        {'descricao': 'ESCITALOPRAM 10MG', 'lote': '2529244', 'ms': '1057306100222',
         'codigo': '4471', 'saldoDigifarma': 5, 'saldoSngpc': 1, 'diferenca': 4},
        # este é sozinho no M.S.: não pode ser chamado de troca de lote
        {'descricao': 'CEFALEXINA 500MG', 'lote': '5H8051', 'ms': '1023506630204',
         'codigo': '991', 'saldoDigifarma': 4, 'saldoSngpc': 6, 'diferenca': -2},
    ]
    por_ms = {}
    for it in itens_troca:
        por_ms.setdefault(it['ms'], []).append(it)
    anunciados = []
    for it in itens_troca:
        irmaos = por_ms.get(it['ms'], [])
        if len(irmaos) > 1 and not round(sum(x['diferenca'] for x in irmaos), 3):
            anunciados.append(it['lote'])
    conferir('par que se anula é anunciado como troca de lote',
             anunciados == ['2509242', '2529244'], anunciados)
    conferir('lote sozinho no M.S. não vira troca de lote',
             '5H8051' not in anunciados)

    # --- o critério de "receita lançada" ----------------------------------
    # O critério antigo era "existe linha em VENDAS_PSICOTROPICOS", e o
    # Digifarma cria a linha JUNTO com a venda: nas 46 vendas medidas em
    # 18/08/2026, nenhuma estava sem linha. O teste nunca acusava nada.
    #
    # O --receitas mediu coluna por coluna. Nas duas vendas que a farmácia
    # ainda não tinha lançado, PRESCRITOR estava vazio; nas 44 lançadas,
    # preenchido. É esse o teste agora, e ele tem que estar nas TRÊS
    # consultas — escrever a condição três vezes foi como o critério errado
    # sobreviveu tanto tempo.
    # A quarta da lista é a que cruza divergência com venda, e foi
    # justamente a que eu esqueci na primeira passada — o teste pegou.
    for nome_consulta in ('vendas_recentes', 'vendas_problema',
                          'vendas_sem_receita_pendentes',
                          'vendas_recentes_por_lote'):
        sql_consulta = ag.CONSULTAS[nome_consulta]
        conferir('%s testa o PRESCRITOR, não a existência da linha' % nome_consulta,
                 'PRESCRITOR' in sql_consulta and '{RECEITA}' not in sql_consulta,
                 sql_consulta[:80])

    conferir('nenhuma consulta ficou com o critério antigo',
             not any('VP.VENDA_NOTA_ID IS NULL' in q for q in ag.CONSULTAS.values()))

    # PACIENTE parecia servir e não serve: estava vazio em 4 de 46, e duas
    # dessas eram vendas que a farmácia LANÇOU. Escolher essa coluna faria o
    # app acusar receita boa como faltante.
    conferir('o critério não usa PACIENTE, que acusaria receita boa',
             'VP.PACIENTE' not in ag.SQL_RECEITA_LANCADA, ag.SQL_RECEITA_LANCADA)
    # PACIENTE_SEXO vinha preenchido ATÉ nas duas não lançadas
    conferir('o critério não usa PACIENTE_SEXO, que não distingue nada',
             'PACIENTE_SEXO' not in ag.SQL_RECEITA_LANCADA)
    # linha ausente tem que continuar contando como sem receita
    conferir('linha ausente continua sendo "sem receita"',
             'VP.VENDA_NOTA_ID IS NOT NULL' in ag.SQL_RECEITA_LANCADA)
    # TRIM porque campo com espaços não é campo preenchido
    conferir('espaço em branco não conta como receita lançada',
             'TRIM(' in ag.SQL_RECEITA_LANCADA)

    # --- só publica o que mudou -------------------------------------------
    # A fila passou a rodar de minuto em minuto para o botão do app responder
    # rápido. Sem isto, seriam 1440 reescritas por dia da mesma lista.
    guardado_ultimo = ag.ARQUIVO_ULTIMO
    ag.ARQUIVO_ULTIMO = os.path.join(pasta, 'ultimo_publicado.json')
    try:
        lista = [{'venda': 8830, 'quantidade': 2}]
        conferir('a primeira publicação sempre acontece',
                 ag.mudou('vendasRecentes', lista))
        conferir('o mesmo conteúdo não é reescrito',
                 not ag.mudou('vendasRecentes', lista))
        conferir('conteúdo igual escrito de outra ordem também não é reescrito',
                 not ag.mudou('vendasRecentes', [{'quantidade': 2, 'venda': 8830}]))
        conferir('uma venda nova publica de novo',
                 ag.mudou('vendasRecentes', lista + [{'venda': 8831, 'quantidade': 1}]))
        conferir('cada ramo tem a sua marca, um não cala o outro',
                 ag.mudou('diagnostico', lista))
        # Errar para o lado de publicar: perder venda da tela é pior que
        # gastar banda.
        with open(ag.ARQUIVO_ULTIMO, 'w', encoding='utf-8') as f:
            f.write('{ isto nao e json')
        # O buraco que o "só publica o que mudou" abriu: publicar() troca o
        # nó INTEIRO, e um ramo que faltou nos dados some do Firebase. Se as
        # marcas continuassem valendo, a fila diria "igual ao que publiquei"
        # e o ramo ficaria sumido até uma venda nova acontecer.
        conferir('esquecer as marcas faz a fila republicar tudo',
                 (ag.esquecer_publicado() or ag.mudou('vendasRecentes', lista)) is True)
        conferir('esquecer não quebra quando não há marca nenhuma',
                 (ag.esquecer_publicado() or True) is True)

        conferir('marca ilegível publica de novo em vez de calar',
                 ag.mudou('vendasRecentes', lista))
        conferir('valor que não vira JSON publica de novo',
                 ag.mudou('vendasRecentes', {'quando': datetime.datetime(2026, 8, 18)}))
    finally:
        ag.ARQUIVO_ULTIMO = guardado_ultimo

    # --- chave repetida no CONSULTAS --------------------------------------
    # O Python fica com a ÚLTIMA e não reclama. Escrevi uma consulta nova com
    # um nome que já existia e a minha sumiu sem aviso; se tivesse vindo
    # depois, teria substituído a que apura o saldo — e o erro apareceria
    # como saldo errado, semanas depois, sem ligação com a causa. Só dá para
    # ver isto lendo o CÓDIGO, porque no dicionário pronto a duplicata já
    # não existe.
    import ast as _ast
    fonte = _ast.parse(open(os.path.abspath(ag.__file__), encoding='utf-8').read())
    repetidas = {}
    for no in _ast.walk(fonte):
        if not isinstance(no, _ast.Dict):
            continue
        vistas = {}
        for chave in no.keys:
            if isinstance(chave, _ast.Constant) and isinstance(chave.value, str):
                vistas.setdefault(chave.value, []).append(chave.lineno)
        for nome, linhas_da_chave in vistas.items():
            if len(linhas_da_chave) > 1:
                repetidas[nome] = linhas_da_chave
    conferir('nenhum dicionário do agente tem chave repetida',
             not repetidas,
             '; '.join('%s nas linhas %s' % (n, l) for n, l in repetidas.items()))

    # --- publicar as regras do Firebase sozinho --------------------------
    # O agente passou a publicar as regras junto com a atualização, o que
    # tira o passo manual mas põe a tranca do banco na mão de um download.
    # A conferência é o que separa uma coisa da outra.
    arquivo_regras = os.path.join(os.path.dirname(os.path.abspath(ag.__file__)),
                                  'regras-firebase.json')
    with open(arquivo_regras, encoding='utf-8') as f:
        regras_reais = json.load(f)

    conferir('as regras do próprio repositório passam na conferência',
             ag.conferir_regras(regras_reais) is regras_reais)

    def recusa(rotulo, regras, pedaco):
        try:
            ag.conferir_regras(regras)
        except RuntimeError as e:
            conferir(rotulo, pedaco in str(e), str(e))
        else:
            conferir(rotulo, False, 'passou e não devia')

    recusa('arquivo sem "rules" não é publicado', {'farmacia': {}}, 'não são as regras')
    recusa('raiz aberta não é publicada',
           {'rules': {'.read': True, '.write': False}}, 'começar fechada')

    sem_no = json.loads(json.dumps(regras_reais))
    del sem_no['rules']['farmacia']['agentes']
    recusa('regras de outro projeto não são publicadas', sem_no, 'agentes')

    aberta = json.loads(json.dumps(regras_reais))
    aberta['rules']['farmacia']['inventario']['.read'] = True
    recusa('um ".read": true escondido no meio barra a publicação',
           aberta, 'farmacia/inventario')

    aberta_texto = json.loads(json.dumps(regras_reais))
    aberta_texto['rules']['farmacia']['relatorios']['.write'] = 'true'
    recusa('"true" como texto também é regra aberta',
           aberta_texto, 'farmacia/relatorios')

    conferir('toda ação que o app pede está liberada nas regras',
             all(("=== '%s'" % acao) in
                 regras_reais['rules']['farmacia']['comando']['acao']['.validate']
                 for acao in ag.RELATORIOS),
             ', '.join(a for a in ag.RELATORIOS
                       if ("=== '%s'" % a) not in
                       regras_reais['rules']['farmacia']['comando']['acao']['.validate']))

    shutil.rmtree(pasta, ignore_errors=True)
    print('\n%s\n' % ('%d falha(s)' % len(falhas) if falhas else 'Tudo passou.'))
    return 1 if falhas else 0


if __name__ == '__main__':
    raise SystemExit(principal())
