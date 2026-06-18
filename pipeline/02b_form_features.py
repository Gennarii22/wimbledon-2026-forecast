#!/usr/bin/env python3
"""
02b - Feature di forma (leak-free), fuse in engineered.parquet.
Segnali sopravvissuti al test di correlazione parziale (oltre il ranking):
  - form10      : win rate ultimi 10 match (qualsiasi superficie) PRIMA del match
  - grass_recent: win rate ultimi 10 match SU ERBA prima del match (warm-up + forma erba)
  - pedigree    : match vinti in QUESTO torneo nell'edizione precedente (a Wimbledon = pedigree Wimbledon)
Salva anche lo snapshot per-giocatore corrente (per il forecast 2026) in data/form_state.json.
"""
import os, sqlite3, json
import numpy as np, pandas as pd
from datetime import datetime

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); DB=os.path.join(DATA,"tennis.db")

def pdate(s):
    try: return datetime.strptime(str(s)[:10],'%Y-%m-%d')
    except: return None

def main():
    con=sqlite3.connect(DB)
    m=pd.read_sql("""SELECT id as match_id, circuit, year, tournament, surface, date, winner, loser
                     FROM matches WHERE date IS NOT NULL AND winner IS NOT NULL AND loser IS NOT NULL
                     ORDER BY date ASC, id ASC""", con)
    con.close()
    m['d']=m['date'].map(pdate); m=m.dropna(subset=['d'])
    print(f"Match: {len(m)}")

    recent={}      # player -> [won bool] (ultimi risultati)
    grass={}       # player -> [won bool] su erba
    ty_wins={}     # (player,tournament,year) -> wins
    last_seen={}   # player -> ultima data (per snapshot attivi)
    first_seen={}  # player -> prima data vista (proxy eta'/anzianita' di carriera)

    def f10(p):
        r=recent.get(p,[]); return float(np.mean(r[-10:])) if len(r)>=3 else 0.5
    def fg(p):
        r=grass.get(p,[]); return float(np.mean(r[-10:])) if len(r)>=2 else 0.5
    def ped(p,tour,yr):
        return float(ty_wins.get((p,tour,yr-1),0))

    def active(p, d):
        fs=first_seen.get(p)
        return round((d-fs).days/365.25,2) if fs else 0.0

    rows=[]
    for _,r in m.iterrows():
        w,l,tour,yr,surf,d=r['winner'],r['loser'],r['tournament'],int(r['year']),r['surface'],r['d']
        if w not in first_seen: first_seen[w]=d
        if l not in first_seen: first_seen[l]=d
        rows.append(dict(match_id=r['match_id'],
            w_form10=f10(w), l_form10=f10(l),
            w_grass=fg(w),   l_grass=fg(l),
            w_ped=ped(w,tour,yr), l_ped=ped(l,tour,yr),
            w_active=active(w,d), l_active=active(l,d)))
        # update (post-match)
        recent.setdefault(w,[]).append(True);  recent.setdefault(l,[]).append(False)
        if surf=='Grass':
            grass.setdefault(w,[]).append(True); grass.setdefault(l,[]).append(False)
        ty_wins[(w,tour,yr)]=ty_wins.get((w,tour,yr),0)+1
        ty_wins.setdefault((l,tour,yr),ty_wins.get((l,tour,yr),0))
        last_seen[w]=r['date']; last_seen[l]=r['date']

    feat=pd.DataFrame(rows)
    eng=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    eng=eng.drop(columns=[c for c in feat.columns if c!='match_id' and c in eng.columns], errors='ignore')
    eng=eng.merge(feat,on='match_id',how='left')
    eng.to_parquet(os.path.join(DATA,"engineered.parquet"))
    print(f"engineered.parquet aggiornato: {eng.shape[1]} colonne")

    # snapshot per-giocatore corrente + pedigree Wimbledon 2026 (= wins Wimbledon 2025)
    snap={}
    wkey=[k for k in ty_wins if 'Wimbledon' in k[1] and k[2]==2025]
    wimb25={k[0]:v for k,v in ty_wins.items() if 'Wimbledon' in k[1] and k[2]==2025}
    wimb_start_2026=datetime(2026,6,29)
    for p in recent:
        snap[p]=dict(form10=f10(p), grass=fg(p), ped=float(wimb25.get(p,0)),
                     active=round((wimb_start_2026-first_seen[p]).days/365.25,2) if p in first_seen else 0.0,
                     last=last_seen.get(p))
    json.dump(snap, open(os.path.join(DATA,"form_state.json"),"w"))
    print(f"form_state.json: {len(snap)} giocatori. Esempio pedigree Wimbledon 2025>0:",
          sorted([(p,v['ped']) for p,v in snap.items() if v['ped']>0], key=lambda x:-x[1])[:6])

if __name__=="__main__":
    main()
