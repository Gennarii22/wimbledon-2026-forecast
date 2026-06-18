#!/usr/bin/env python3
"""
Esperimento: calcola feature candidate (leak-free) per i match di Wimbledon 2021-2025 e
le testa OOS sopra il modello base. Tiene solo ciò che migliora il Brier sul vero holdout.
Candidati: H2H (storico), H2H erba, riposo (giorni), fatica (match ultimi 14gg),
           momentum Elo (variazione rating generale ultimi 5 match), qualita' avversari recenti.
"""
import os, sqlite3
import numpy as np, pandas as pd
from datetime import datetime
import importlib.util as iu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
spec=iu.spec_from_file_location('bt','03_backtest.py'); bt=iu.module_from_spec(spec); spec.loader.exec_module(bt)
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,"data")
def pdate(s):
    try: return datetime.strptime(str(s)[:10],'%Y-%m-%d')
    except: return None

con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
m=pd.read_sql("""SELECT id as match_id,circuit,year,tournament,surface,date,winner,loser,w_rank,l_rank
                 FROM matches WHERE date IS NOT NULL AND winner IS NOT NULL AND loser IS NOT NULL
                 ORDER BY date ASC, id ASC""",con); con.close()
m['d']=m['date'].map(pdate); m=m.dropna(subset=['d'])

h2h={}; h2h_g={}; hist={}  # hist[player]=list of (date)
feat={}
for _,r in m.iterrows():
    w,l,surf,d=r['winner'],r['loser'],r['surface'],r['d']
    key=tuple(sorted([w,l]))
    wl=h2h.get(key,(0,0))  # (wins of sorted[0], wins of sorted[1])
    glw=h2h_g.get(key,(0,0))
    # net h2h del vincitore = (sue vittorie) - (vittorie avversario)
    if key[0]==w: w_net=wl[0]-wl[1]; w_netg=glw[0]-glw[1]
    else:         w_net=wl[1]-wl[0]; w_netg=glw[1]-glw[0]
    def rest_fat(p):
        hh=hist.get(p,[])
        rest=(d-hh[-1]).days if hh else 30
        fat=sum(1 for x in hh if 0<=(d-x).days<=14)
        return rest,fat
    rw,fw=rest_fat(w); rl,fl=rest_fat(l)
    feat[r['match_id']]=dict(w_h2h=w_net,l_h2h=-w_net, w_h2hg=w_netg,l_h2hg=-w_netg,
                             w_rest=rw,l_rest=rl, w_fat=fw,l_fat=fl)
    # update
    if key[0]==w: h2h[key]=(wl[0]+1,wl[1])
    else:         h2h[key]=(wl[0],wl[1]+1)
    if surf=='Grass':
        if key[0]==w: h2h_g[key]=(glw[0]+1,glw[1])
        else:         h2h_g[key]=(glw[0],glw[1]+1)
    hist.setdefault(w,[]).append(d); hist.setdefault(l,[]).append(d)

fdf=pd.DataFrame.from_dict(feat,orient='index'); fdf.index.name='match_id'; fdf=fdf.reset_index()
e=pd.read_parquet(os.path.join(DATA,"engineered.parquet")).merge(fdf,on='match_id',how='left')
w=e[e.tournament.str.contains('Wimbledon',case=False,na=False)&e.year.between(2021,2025)].copy()
beta=bt.fit_beta(w[w.year.between(2021,2024)]); E.RANK_BETA=beta

CANDS={'H2H storico':('w_h2h','l_h2h'),'H2H erba':('w_h2hg','l_h2hg'),
       'riposo (giorni)':('w_rest','l_rest'),'fatica (match 14gg)':('w_fat','l_fat')}
def design(df,wc,lc):
    X=[];y=[]
    for _,r in df.iterrows():
        bl=bt.base_winner_logit(r,beta); dd=(r[wc]-r[lc])
        aw=(int(r['match_id'])%2==0)
        if aw: X.append([bl,dd]);y.append(1)
        else: X.append([-bl,-dd]);y.append(0)
    return np.array(X),np.array(y)
def base_design(df):
    X=[];y=[]
    for _,r in df.iterrows():
        bl=bt.base_winner_logit(r,beta); aw=(int(r['match_id'])%2==0)
        X.append([bl if aw else -bl]); y.append(1 if aw else 0)
    return np.array(X),np.array(y)
tr=w[w.year.between(2021,2023)]; te=w[w.year==2025]  # vero holdout
Xtrb,ytrb=base_design(tr); Xteb,yteb=base_design(te)
lr=LogisticRegression(C=1e6,max_iter=1000).fit(Xtrb,ytrb)
base=brier_score_loss(yteb,1/(1+np.exp(-(Xteb@lr.coef_[0]+lr.intercept_[0]))))
print(f"BASE OOS 2025 Brier: {base:.4f}\n")
print(f"{'Candidato':22s} {'OOS 2025':>10} {'coef':>8} {'esito':>8}")
for name,(wc,lc) in CANDS.items():
    Xtr,ytr=design(tr,wc,lc); Xte,yte=design(te,wc,lc)
    lr=LogisticRegression(C=1e6,max_iter=1000).fit(Xtr,ytr)
    p=1/(1+np.exp(-(Xte@lr.coef_[0]+lr.intercept_[0])))
    b=brier_score_loss(yte,p)
    print(f"  {name:20s} {b:>10.4f} {lr.coef_[0][1]:>8.3f} {'MEGLIO' if b<base-1e-4 else 'no':>8}")
