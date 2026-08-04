#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENTE DE SINCRONIZAÇÃO AUTOMÁTICA — Digifarma -> Firebase

Lê o estoque do Digifarma (Firebird) e PUBLICA direto no Firebase.
O app apenas mostra o que este agente publicar. O Digifarma é a verdade.

Roda sozinho pelo Agendador de Tarefas do Windows (ver INSTALAR.txt).
Não lê clientes, médicos nem receitas — apenas medicamento + saldo + lote.

CONFIGURAÇÃO: ajuste as três seções marcadas com >>> abaixo.
"""

import re, sys, os, datetime

# >>> 1. BANCO DIGIFARMA (Firebird) ─────────────────────────────
DB_PATH = r"C:\Digifarma\Dados\digifarma6-.fdb"
DB_USER = "SYSDBA"
DB_PASS = "masterkey"
DB_HOST = "localhost"

# >>> 2. FIREBASE ───────────────────────────────────────────────
# Baixe a chave de serviço no Console do Firebase:
#   Configurações do projeto > Contas de serviço > Gerar nova chave privada
# Salve o arquivo como 'chave-firebase.json' NESTA MESMA PASTA.
# NUNCA suba esse arquivo no GitHub (o .gitignore já bloqueia).
CHAVE_FIREBASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chave-firebase.json")
FIREBASE_URL   = "https://estoque-remedios-7b785-default-rtdb.firebaseio.com"

# >>> 3. O QUE SINCRONIZAR ──────────────────────────────────────
#   "controlados" = só os psicotrópicos com saldo (o SNGPC, ~97 itens)
#   "com_saldo"   = todo produto com saldo > 0 (~2.500 itens)
ESCOPO = "controlados"

# ================================================================
CAMINHO_FIREBASE = "farmacia/inventario"   # onde publica no banco

def conectar_digifarma():
    try:
        import firebird.driver as fb
    except ImportError:
        print("❌ Falta o driver do Firebird. Rode:  pip install firebird-driver")
        sys.exit(1)
    # Se o PC tiver uma versão antiga do Firebird e der erro de "on-disk structure",
    # aponte aqui o caminho do cliente Firebird 4/5 (ex.: fbclient.dll):
    #   fb.driver_config.fb_client_library.value = r"C:\caminho\fbclient.dll"
    dsn = f"{DB_HOST}:{DB_PATH}" if DB_HOST else DB_PATH
    return fb.connect(dsn, user=DB_USER, password=DB_PASS, charset="ISO8859_1")

def where_escopo():
    if ESCOPO == "controlados":
        return "P.PSICOTROPICO = 'S' AND P.PROD_SALDO > 0"
    return "P.PROD_SALDO > 0"

SQL = """
SELECT
  P.PRODUTO_ID, P.PRODUTO, P.APRESENTACAO, P.COD_BARRAS,
  CAST(P.PROD_SALDO AS INTEGER),
  CAST(COALESCE(P.PROD_ESTMINIMO,0) AS INTEGER),
  P.PSICOTROPICO,
  L.LOTE_VENCIMENTO, L.NUM_LOTE
FROM PRODUTOS P
LEFT JOIN LOTES L ON L.PRODUTO_ID = P.PRODUTO_ID AND L.LOTE_QUANTIDADE > 0
WHERE {cond}
ORDER BY P.PRODUTO
"""

def mmyy(dt):
    try: return f"{dt.month:02d}/{str(dt.year)[2:]}"
    except Exception: return ""

def vkey(v):
    try: mo,yr=v.split("/"); return (int("20"+yr),int(mo))
    except Exception: return (9999,99)

def ler_digifarma():
    con = conectar_digifarma()
    cur = con.cursor()
    cur.execute(SQL.format(cond=where_escopo()))
    prods = {}
    for pid, prod, apres, cod, saldo, minimo, psico, venc, lote in cur:
        pid = str(pid)
        nome = re.sub(r"\s+"," ",f"{(prod or '').strip()} {(apres or '').strip()}").strip().upper()
        v = mmyy(venc)
        if pid not in prods:
            prods[pid] = {"id":"dg"+pid,"n":nome,"q":int(saldo or 0),
                          "v":"","lab":"","cod":(cod or "").strip(),
                          "min":int(minimo or 0),"farmacia":0,
                          "ctrl": (psico=="S"),"_v":[]}
        if v: prods[pid]["_v"].append(v)
    con.close()
    meds = []
    for p in prods.values():
        if p["_v"]: p["v"] = sorted(set(p["_v"]),key=vkey)[0]
        del p["_v"]; meds.append(p)
    meds.sort(key=lambda x:x["n"])
    return meds

def publicar(meds):
    import firebase_admin
    from firebase_admin import credentials, db
    if not os.path.exists(CHAVE_FIREBASE):
        print(f"❌ Não achei a chave: {CHAVE_FIREBASE}")
        print("   Baixe em: Console Firebase > Config. do projeto > Contas de serviço.")
        sys.exit(1)
    if not firebase_admin._apps:
        cred = credentials.Certificate(CHAVE_FIREBASE)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
    ref = db.reference(CAMINHO_FIREBASE)
    ref.set({
        "itens": meds,
        "total": len(meds),
        "unidades": sum(m["q"] for m in meds),
        "escopo": ESCOPO,
        "atualizado_em": datetime.datetime.now().isoformat(timespec="seconds")
    })

def main():
    print(f"[{datetime.datetime.now():%d/%m %H:%M}] Lendo Digifarma ({ESCOPO})...")
    meds = ler_digifarma()
    print(f"   {len(meds)} itens, {sum(m['q'] for m in meds)} unidades. Publicando...")
    publicar(meds)
    print("✅ Publicado no Firebase em /farmacia/inventario")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ ERRO: {e}")
        # registra num log para o Agendador não perder o erro
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"agente_erro.log"),"a") as f:
            f.write(f"{datetime.datetime.now().isoformat()}  {e}\n")
        sys.exit(1)
