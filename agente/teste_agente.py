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
    ],
}

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
            return [{'CAMPO': c} for c in ('LOTE_ID', 'PRODUTO_ID', 'NUM_LOTE', 'SALDO')]
        if sql in por_sql:
            return por_sql[sql]
        # saldo_digifarma tem o {SALDO} trocado antes de rodar
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

    shutil.rmtree(pasta, ignore_errors=True)
    print('\n%s\n' % ('%d falha(s)' % len(falhas) if falhas else 'Tudo passou.'))
    return 1 if falhas else 0


if __name__ == '__main__':
    raise SystemExit(principal())
