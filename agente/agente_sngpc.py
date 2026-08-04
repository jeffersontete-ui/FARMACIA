#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exporta o INVENTÁRIO DE CONTROLADOS (SNGPC) do Digifarma para um arquivo JSON
que o app de Estoque importa.

Lê os produtos psicotrópicos COM SALDO da base Firebird do Digifarma, junta a
validade do lote mais próximo, e grava 'inventario_sngpc.json'.

NÃO lê dados de clientes, médicos ou receitas — apenas medicamento + saldo + lote.

COMO USAR (no PC da farmácia):
    1. Instale o Python 3 (python.org) marcando "Add to PATH".
    2. Instale o driver:  pip install firebird-driver
    3. Tenha o Firebird instalado (o Digifarma já instala).
    4. Rode:  python agente_sngpc.py
    O arquivo 'inventario_sngpc.json' aparece na mesma pasta.
    Depois, no app: Painel ADM → Config → Importar inventário → escolha o arquivo.
"""

import json, re, sys, os

# ===== CONFIGURAÇÃO — ajuste se necessário =====
DB_PATH  = r"C:\Digifarma\Dados\digifarma6-.fdb"   # caminho do banco no PC
DB_USER  = "SYSDBA"
DB_PASS  = "masterkey"                             # senha do Firebird
DB_HOST  = "localhost"                             # ou o IP do servidor Firebird
SAIDA    = "inventario_sngpc.json"

def conectar():
    try:
        import firebird.driver as fb
    except ImportError:
        print("❌ Falta o driver. Rode:  pip install firebird-driver")
        sys.exit(1)
    dsn = f"{DB_HOST}:{DB_PATH}" if DB_HOST else DB_PATH
    return fb.connect(dsn, user=DB_USER, password=DB_PASS, charset="ISO8859_1")

SQL = """
SELECT
  P.PRODUTO_ID,
  P.PRODUTO, P.APRESENTACAO, P.COD_BARRAS,
  CAST(P.PROD_SALDO AS INTEGER),
  CAST(COALESCE(P.PROD_ESTMINIMO,0) AS INTEGER),
  L.LOTE_VENCIMENTO, L.NUM_LOTE
FROM PRODUTOS P
LEFT JOIN LOTES L ON L.PRODUTO_ID = P.PRODUTO_ID AND L.LOTE_QUANTIDADE > 0
WHERE P.PSICOTROPICO = 'S' AND P.PROD_SALDO > 0
ORDER BY P.PRODUTO
"""

def mmyy(dt):
    if not dt: return ""
    try: return f"{dt.month:02d}/{str(dt.year)[2:]}"
    except Exception: return ""

def vkey(v):
    try:
        mo, yr = v.split("/"); return (int("20"+yr), int(mo))
    except Exception: return (9999, 99)

def main():
    con = conectar()
    cur = con.cursor()
    cur.execute(SQL)
    prods = {}
    for pid, prod, apres, cod, saldo, minimo, venc, lote in cur:
        pid = str(pid)
        nome = re.sub(r"\s+", " ", f"{(prod or '').strip()} {(apres or '').strip()}").strip().upper()
        v = mmyy(venc)
        if pid not in prods:
            prods[pid] = {"id":"dg"+pid, "n":nome, "q":int(saldo or 0),
                          "v":"", "lab":"", "cod":(cod or "").strip(),
                          "min":int(minimo or 0), "farmacia":0, "_v":[]}
        if v: prods[pid]["_v"].append(v)
    con.close()

    meds = []
    for p in prods.values():
        if p["_v"]: p["v"] = sorted(set(p["_v"]), key=vkey)[0]
        del p["_v"]; meds.append(p)
    meds.sort(key=lambda x: x["n"])

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(meds, f, ensure_ascii=False, indent=1)

    print(f"✅ {len(meds)} controlados exportados para {os.path.abspath(SAIDA)}")
    print(f"   Total de unidades: {sum(m['q'] for m in meds)}")

if __name__ == "__main__":
    main()
