# -*- coding: utf-8 -*-
"""
teste_agente.py — roda o agente com um banco simulado.

Não abre o Digifarma nem escreve no Firebase: substitui a função
consultar() por respostas fixas e confere o que sai. Serve para
validar uma alteração no agente_auto.py antes de levar ao servidor.

    python teste_agente.py
"""

import datetime
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
        {'VENDA_NOTA_ID': 8830, 'DATA': datetime.date(2026, 8, 6), 'PRODUTO': 'CLONAZEPAM',
         'REGISTRO_MS': '1003301220019', 'COD_BARRAS': '789', 'NUM_LOTE': 'L2345A', 'QUANTIDADE': 30},
    ],
    'entradas_pendentes': [
        {'CAB_NOTA_ID': 3315, 'NOTA_FISCAL': '206800', 'DATA_RECEBIMENTO': datetime.date(2026, 8, 6),
         'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1444400010023', 'COD_BARRAS': '790',
         'NUM_LOTE': 'B77Z', 'QUANTIDADE': 20},
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
    'inventario_sngpc': [
        {'REGISTRO_MS': '1023506630204', 'MEDICAMENTO': 'ALPRAZOLAM', 'LOTE': '5F9779',
         'QUANTIDADE': 8, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'REGISTRO_MS': '1057306610050', 'MEDICAMENTO': 'ARIPIPRAZOL', 'LOTE': '2604608',
         'QUANTIDADE': 2, 'DATA_ATUALIZACAO': '2026-08-05'},
        {'REGISTRO_MS': '1122233340001', 'MEDICAMENTO': 'DIAZEPAM', 'LOTE': 'K1',
         'QUANTIDADE': 10, 'DATA_ATUALIZACAO': '2026-08-05'},
    ],
    'saldo_digifarma': [
        # 5 no Digifarma contra 8 na ANVISA -> falta 3
        {'PRODUTO_ID': 100, 'PRODUTO': 'ALPRAZOLAM', 'REGISTRO_MS': '1023506630204',
         'COD_BARRAS': '789', 'NUM_LOTE': '5F9779', 'LOTE_VENCIMENTO': datetime.date(2027, 9, 30), 'SALDO': 5},
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
             dados['inventario']['itens'] == 3, dados['inventario'])

    diferencas = {i['ms']: i['diferenca'] for i in dados['itens']}
    conferir('diferença de saldo por M.S. + lote',
             diferencas.get('1023506630204') == -3.0, diferencas)
    conferir('lote que bate não vira divergência',
             diferencas.get('1057306610050') == 0.0, diferencas)

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
    # o M.S. do diazepam tem lote K1 nos dois cadastros: o total por M.S.
    # é o que permite conferir contra a tela do Digifarma, que soma os lotes
    conferir('medicamento de um lote só não carrega total por M.S.',
             'saldoDigifarmaMs' not in next(
                 i for i in dados['itens'] if i['ms'] == '1023506630204'))

    negativo = next(i for i in dados['itens'] if i['lote'] == 'BLGH23013')
    conferir('lote negativo não é classificado como sobra',
             negativo.get('motivo') == 'negativo', negativo)

    zerados = [i for i in dados['itens'] if i['ms'] == '1777700010001']
    conferir('lote zerado nos dois lados não vai para o app', not zerados, zerados)

    conferir('vendas pendentes saem pelo ponteiro, não por data',
             dados['resumoPendentes']['vendas'] == 1, dados['resumoPendentes'])
    conferir('entradas pendentes saem pelo ponteiro',
             dados['resumoPendentes']['entradas'] == 1, dados['resumoPendentes'])

    fora = [c for c in dados.get('conferencia_xml', []) if c['situacao'] == 'fora_do_xml']
    conferir('venda que não subiu no XML vira divergência',
             any(c['ms'] == '1999900090011' for c in fora), fora)
    conferir('entrada do XML não é confundida com venda',
             not any(c['ms'] == '1052500680092' for c in dados.get('conferencia_xml', [])))

    conferir('venda de controlado sem receita é classificada',
             dados['vendas_problema'][0]['motivo'] == 'sem_receita')

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

    shutil.rmtree(pasta, ignore_errors=True)
    print('\n%s\n' % ('%d falha(s)' % len(falhas) if falhas else 'Tudo passou.'))
    return 1 if falhas else 0


if __name__ == '__main__':
    raise SystemExit(principal())
