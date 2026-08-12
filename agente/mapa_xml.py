# -*- coding: utf-8 -*-
"""
mapa_xml.py — lê o XML que o Digifarma gera a cada transmissão ao SNGPC.

O arquivo fica em C:\\Digifarma\\Aplicativos\\VerificaXML.
SNGPC.XML, MOVIMENTACAO.XML e sngpc.zip são o MESMO conteúdo e são
SOBRESCRITOS a cada envio — por isso o agente arquiva uma cópia em
VerificaXML\\enviados\\sngpc_AAAA-MM-DD.xml antes de qualquer coisa.

O casamento com o banco é por registroMSMedicamento + numeroLoteMedicamento.

A leitura aqui é deliberadamente tolerante: o layout do SNGPC mudou de
versão algumas vezes e os nomes vêm com prefixo de namespace. Em vez de
fixar um caminho, procuramos por sufixo de tag.
"""

import os
import re
import zipfile
from xml.etree import ElementTree

# sufixos de tag procurados, em ordem de preferência
TAGS_MS = ('registroMSMedicamento', 'registroMs', 'registroMS')
TAGS_LOTE = ('numeroLoteMedicamento', 'numeroLote', 'lote')
TAGS_QTD = ('quantidadeMedicamento', 'quantidade', 'qtdeMedicamento', 'qtde')
TAGS_DESCRICAO = ('descricaoMedicamento', 'nomeMedicamento', 'descricao')
TAGS_DATA = ('dataVendaMedicamento', 'dataRecebimentoMedicamento',
             'dataVenda', 'dataMovimento', 'dataTransacao', 'data')

# o cabeçalho do XML real traz o período exato da transmissão —
# é dele que sai a data, não do nome do arquivo
TAGS_CABECALHO = ('cnpjEmissor', 'cpfTransmissor', 'dataInicio', 'dataFim')

# como classificar o movimento: procuramos estas palavras na cadeia de
# ancestrais do nó do medicamento (confirmado no XML de 04/08/2026:
# medicamentoEntrada < entradaMedicamentos, medicamentoVenda <
# saidaMedicamentoVendaAoConsumidor)
TIPOS = (
    ('entrada', ('entrada',)),
    ('venda', ('venda', 'saida')),
    ('perda', ('perda',)),
    ('transferencia', ('transferencia',)),
)


def _sufixo(tag):
    """Tira o namespace: '{urn:x}registroMSMedicamento' -> 'registroMSMedicamento'."""
    return tag.rsplit('}', 1)[-1]


def _procurar(elemento, sufixos):
    """Primeiro descendente cuja tag termine em um dos sufixos. Devolve o texto."""
    for filho in elemento.iter():
        nome = _sufixo(filho.tag)
        for s in sufixos:
            if nome == s or nome.lower() == s.lower():
                if filho.text and filho.text.strip():
                    return filho.text.strip()
    return None


def _so_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def _numero(valor):
    if valor is None:
        return 0.0
    texto = str(valor).strip().replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0


def abrir(caminho):
    """Devolve a árvore XML a partir de um .xml ou de um .zip que contenha um."""
    if caminho.lower().endswith('.zip'):
        with zipfile.ZipFile(caminho) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith('.xml')]
            if not nomes:
                raise ValueError('O zip %s não tem nenhum .xml dentro.' % caminho)
            with z.open(nomes[0]) as f:
                return ElementTree.parse(f).getroot()
    return ElementTree.parse(caminho).getroot()


def _classificar(elemento, pais):
    """Olha a cadeia de ancestrais e diz se o movimento é entrada, venda,
    perda ou transferência. Sem isso, entrada e saída entram no mesmo balde
    e a conferência contra as vendas do banco fica errada."""
    cadeia = []
    no = pais.get(elemento)
    while no is not None:
        cadeia.append(_sufixo(no.tag).lower())
        no = pais.get(no)
    texto_cadeia = ' '.join(cadeia)
    for tipo, palavras in TIPOS:
        if any(p in texto_cadeia for p in palavras):
            return tipo
    return 'outro'


def ler(caminho):
    """
    Lê o XML da transmissão e devolve:
        {
          'arquivo': nome do arquivo,
          'cabecalho': {cnpjEmissor, cpfTransmissor, dataInicio, dataFim},
          'movimentos': { 'entrada'|'venda'|'perda'|'transferencia':
                          { (ms, lote): {...} } },
          'itens': atalho para movimentos['venda'] (é o que se cruza com as vendas),
          'total': soma das quantidades de venda,
          'datas': datas encontradas
        }
    """
    raiz = abrir(caminho)
    pais = {filho: pai for pai in raiz.iter() for filho in pai}

    # --- cabeçalho: período exato da transmissão ---
    cabecalho = {}
    for elemento in raiz.iter():
        nome = _sufixo(elemento.tag)
        if nome in TAGS_CABECALHO and elemento.text:
            cabecalho.setdefault(nome, elemento.text.strip())

    # --- nós de medicamento: o PAI da tag do registro M.S. ---
    nos = []
    for elemento in raiz.iter():
        nome = _sufixo(elemento.tag)
        if any(nome.lower() == s.lower() for s in TAGS_MS) and elemento in pais:
            no = pais[elemento]
            if no not in nos:
                nos.append(no)

    movimentos = {}
    datas = set()

    for elemento in nos:
        ms = _procurar(elemento, TAGS_MS)
        if not ms:
            continue
        tipo = _classificar(elemento, pais)
        lote = (_procurar(elemento, TAGS_LOTE) or '').strip().upper()
        chave = (_so_digitos(ms), lote)

        balde = movimentos.setdefault(tipo, {})
        registro = balde.setdefault(chave, {
            'ms': chave[0],
            'lote': chave[1],
            'descricao': _procurar(elemento, TAGS_DESCRICAO) or '',
            'quantidade': 0.0,
            'ocorrencias': 0,
        })
        registro['quantidade'] += _numero(_procurar(elemento, TAGS_QTD)) or 1.0
        registro['ocorrencias'] += 1

        # a data pode estar no nó do medicamento ou no bloco que o contém
        data = _procurar(elemento, TAGS_DATA)
        if not data and elemento in pais:
            data = _procurar(pais[elemento], TAGS_DATA)
        if data:
            datas.add(data[:10])

    vendas = movimentos.get('venda', {})
    if cabecalho.get('dataInicio'):
        datas.add(cabecalho['dataInicio'][:10])
    if cabecalho.get('dataFim'):
        datas.add(cabecalho['dataFim'][:10])

    return {
        'arquivo': os.path.basename(caminho),
        'cabecalho': cabecalho,
        'movimentos': movimentos,
        'itens': vendas,
        'total': round(sum(i['quantidade'] for i in vendas.values()), 3),
        'datas': sorted(datas),
    }


def comparar(itens_xml, itens_banco):
    """
    Cruza o XML com as saídas do banco no mesmo período.

    itens_banco: lista de dicts com ms, lote, quantidade, descricao, venda.
    Devolve a lista de divergências no formato que o app espera:
        situacao = fora_do_xml | so_no_xml | quantidade
    """
    do_banco = {}
    for linha in itens_banco:
        chave = (_so_digitos(linha.get('ms')), str(linha.get('lote') or '').strip().upper())
        registro = do_banco.setdefault(chave, {
            'ms': chave[0], 'lote': chave[1],
            'descricao': linha.get('descricao') or '',
            'quantidade': 0.0, 'vendas': [],
        })
        registro['quantidade'] += _numero(linha.get('quantidade'))
        if linha.get('venda') is not None:
            registro['vendas'].append(linha['venda'])

    divergencias = []
    for chave in sorted(set(do_banco) | set(itens_xml)):
        no_banco = do_banco.get(chave)
        no_xml = itens_xml.get(chave)
        qtd_banco = round(no_banco['quantidade'], 3) if no_banco else 0.0
        qtd_xml = round(no_xml['quantidade'], 3) if no_xml else 0.0
        if abs(qtd_banco - qtd_xml) < 0.001:
            continue
        if qtd_xml == 0:
            situacao = 'fora_do_xml'
        elif qtd_banco == 0:
            situacao = 'so_no_xml'
        else:
            situacao = 'quantidade'
        divergencias.append({
            'situacao': situacao,
            'ms': chave[0],
            'lote': chave[1],
            'descricao': (no_banco or no_xml).get('descricao', ''),
            'qtdBanco': qtd_banco,
            'qtdXml': qtd_xml,
            'vendas': (no_banco or {}).get('vendas', [])[:20],
        })
    return divergencias


if __name__ == '__main__':
    import sys
    import json
    if len(sys.argv) < 2:
        print('uso: python mapa_xml.py CAMINHO_DO_XML')
        raise SystemExit(1)
    resultado = ler(sys.argv[1])
    print(json.dumps({
        'arquivo': resultado['arquivo'],
        'total': resultado['total'],
        'datas': resultado['datas'],
        'itens': [dict(v) for v in resultado['itens'].values()][:20],
    }, indent=2, ensure_ascii=False))
