#!/usr/bin/env python3
"""
02c - Metadati giocatore (età reale, altezza, nazionalità) da fonte esterna scraped (Sackmann-style).
Fonte: chboudry/PariTennis (atp_players). Salva data/player_meta.json keyed col formato DB 'Cognome I.'.
Per il WTA i metadati non sono disponibili facilmente: si usa il proxy anni-carriera a valle.
"""
import os, json, urllib.request
from datetime import datetime
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,"data")
SRC="https://raw.githubusercontent.com/chboudry/PariTennis/master/data_scrapped/atp_players.csv"
WIMB_2026=datetime(2026,6,29)

def key(fn,ln):
    return f"{str(ln).strip()} {str(fn).strip()[0]}." if (pd.notna(fn) and str(fn).strip() and pd.notna(ln)) else None
def pdob(s):
    try: return datetime.strptime(str(s),'%Y.%m.%d')
    except: return None

def main():
    dest=os.path.join(DATA,"atp_players.csv")
    try:
        urllib.request.urlretrieve(SRC, dest)
    except Exception as ex:
        print("WARN download:", ex)
        if not os.path.exists(dest): return
    p=pd.read_csv(dest, low_memory=False)
    meta={}
    for _,r in p.iterrows():
        k=key(r['first_name'], r['last_name'])
        if not k: continue
        b=pdob(r['birthdate'])
        meta[k]=dict(
            age=round((WIMB_2026-b).days/365.25,1) if b else None,
            height=float(r['height_cm']) if pd.notna(r.get('height_cm')) else None,
            country=str(r['country_code']) if pd.notna(r.get('country_code')) else None)
    json.dump(meta, open(os.path.join(DATA,"player_meta.json"),"w"))
    n_age=sum(1 for v in meta.values() if v['age'])
    print(f"player_meta.json: {len(meta)} giocatori ATP, {n_age} con età.")
    for p_ in ['Sinner J.','Djokovic N.','Zverev A.','Shelton B.']:
        print(f"  {p_}: {meta.get(p_)}")

if __name__=="__main__":
    main()
