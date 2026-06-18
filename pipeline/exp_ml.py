#!/usr/bin/env python3
"""
R&D: modello ML (gradient boosting + logistica) su TUTTO il dataset vs il nostro motore.
Train 2010-2021, validation 2022-2023, test 2024-2025 (e Wimbledon). Confronto accuracy + Brier
contro (a) il nostro engine attuale, (b) il mercato (favorito Pinnacle chiusura).
Tutto leak-free: feature pre-match, split temporale.
"""
import os, sqlite3
import numpy as np, pandas as pd
from datetime import datetime
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, accuracy_score, log_loss
import importlib.util as iu
spec=iu.spec_from_file_location('bt','03_backtest.py'); bt=iu.module_from_spec(spec); spec.loader.exec_module(bt)
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,"data")
def pdate(s):
    try: return datetime.strptime(str(s)[:10],'%Y-%m-%d')
    except: return None

# --- h2h e riposo (chronological) ---
con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
mm=pd.read_sql("SELECT id as match_id,winner,loser,surface,date FROM matches WHERE date IS NOT NULL AND winner IS NOT NULL ORDER BY date ASC,id ASC",con); con.close()
mm['d']=mm['date'].map(pdate); mm=mm.dropna(subset=['d'])
h2h={}; hist={}; extra={}
for _,r in mm.iterrows():
    w,l,d=r['winner'],r['loser'],r['d']; key=tuple(sorted([w,l]))
    wl=h2h.get(key,(0,0)); w_net=(wl[0]-wl[1]) if key[0]==w else (wl[1]-wl[0])
    rw=(d-hist[w][-1]).days if w in hist else 30; rl=(d-hist[l][-1]).days if l in hist else 30
    extra[r['match_id']]=(w_net,rw,rl)
    h2h[key]=(wl[0]+(key[0]==w),wl[1]+(key[0]==l))
    hist.setdefault(w,[]).append(d); hist.setdefault(l,[]).append(d)

e=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
e=e[e.psw.notna()&e.psl.notna()&(e.psw>1)&(e.psl>1)&(e.year>=2010)].copy()
ex=pd.DataFrame.from_dict(extra,orient='index',columns=['h2h','w_rest','l_rest']); ex.index.name='match_id'
e=e.merge(ex.reset_index(),on='match_id',how='left')

def feats(r):
    sw=E._shrink(r['w_sg'],r['w_ss'],r['w_nsurf']); rw=E._shrink(r['w_rg'],r['w_rs'],r['w_nsurf'])
    sl=E._shrink(r['l_sg'],r['l_ss'],r['l_nsurf']); rl=E._shrink(r['l_rg'],r['l_rs'],r['l_nsurf'])
    eg=E._shrink(r['w_elo_g'],r['w_elo_s'],r['w_nsurf']); el=E._shrink(r['l_elo_g'],r['l_elo_s'],r['l_nsurf'])
    return dict(d_serve=sw-sl,d_ret=rw-rl,d_elo=eg-el,
                d_rank=np.log2(max(r['l_rank'],1))-np.log2(max(r['w_rank'],1)),
                d_form=r['w_form10']-r['l_form10'],d_grass=r['w_grass']-r['l_grass'],
                d_ped=r['w_ped']-r['l_ped'],d_active=r['w_active']-r['l_active'],
                d_h2h=r.get('h2h',0) or 0,d_rest=(r.get('w_rest',30) or 30)-(r.get('l_rest',30) or 30),
                d_nmatch=r['w_nmatch']-r['l_nmatch'],d_nsurf=r['w_nsurf']-r['l_nsurf'],
                grass=1 if r['surface']=='Grass' else 0,clay=1 if r['surface']=='Clay' else 0,
                bo=int(r['best_of']) if r['best_of'] in (3,5) else 3)
F=pd.DataFrame([feats(r) for _,r in e.iterrows()]); F['year']=e['year'].values; F['mid']=e['match_id'].values
F['circuit']=e['circuit'].values; F['surface']=e['surface'].values
# orientamento per parita': A = vincitore se mid pari, altrimenti perdente (label di conseguenza)
cols=['d_serve','d_ret','d_elo','d_rank','d_form','d_grass','d_ped','d_active','d_h2h','d_rest','d_nmatch','d_nsurf','grass','clay','bo']
sign=np.where(F['mid']%2==0,1,-1)
X=F[cols].copy()
for c in ['d_serve','d_ret','d_elo','d_rank','d_form','d_grass','d_ped','d_active','d_h2h','d_rest','d_nmatch','d_nsurf']:
    X[c]=X[c]*sign
y=(sign==1).astype(int)
X=X.fillna(0)

def split(mask): return X[mask].values,y[mask]
tr=(F.year<=2021).values; va=((F.year>=2022)&(F.year<=2023)).values; te=((F.year>=2024)).values
wimb_te=te & e['tournament'].str.contains('Wimbledon',case=False,na=False).values
Xtr,ytr=split(tr); Xte,yte=split(te); Xwt,ywt=split(wimb_te)

gb=HistGradientBoostingClassifier(max_iter=300,learning_rate=0.05,max_depth=4,l2_regularization=1.0,
    validation_fraction=0.15,random_state=0).fit(Xtr,ytr)
lr=LogisticRegression(max_iter=2000,C=1.0).fit(Xtr,ytr)

def report(name,Xs,ys):
    pg=gb.predict_proba(Xs)[:,1]; pl=lr.predict_proba(Xs)[:,1]
    print(f"  {name:18s} n={len(ys):6d}  GB acc {accuracy_score(ys,pg>.5)*100:5.1f}% Brier {brier_score_loss(ys,pg):.4f}  | "
          f"LOGIT acc {accuracy_score(ys,pl>.5)*100:5.1f}% Brier {brier_score_loss(ys,pl):.4f}")

print("=== ML (HistGradientBoosting + Logistica) ===")
report("TEST 2024-25",Xte,yte)
report("Wimbledon 24-25",Xwt,ywt)

# --- confronto: nostro engine + mercato, sugli stessi match test ---
beta=bt.fit_beta(e[(e.year<=2024)&e.tournament.str.contains('Wimbledon',case=False,na=False)]) if False else 0.42
E.RANK_BETA=0.42
ete=e[(e.year>=2024)].copy()
def engine_p(r):
    ra=bt.row_ratings(r,'w'); rb=bt.row_ratings(r,'l')
    return E.blended_raw(ra,rb,r['w_rank'],r['l_rank'],int(r['best_of']) if r['best_of'] in(3,5) else 3,0.42)
ete['pe']=ete.apply(engine_p,axis=1)
# orienta come y per confronto equo
s2=np.where(ete['match_id'].values%2==0,1,1)  # engine_p e' P(winner); accuracy = pe>0.5 vince winner
acc_e=(ete['pe']>0.5).mean()
br_e=brier_score_loss(np.ones(len(ete)),ete['pe'])  # label=1 (winner)
mk=(ete.psw<ete.psl).astype(int)
print("\n=== Riferimenti sugli stessi match TEST 2024-25 ===")
print(f"  Nostro engine      acc {acc_e*100:.1f}%  Brier {br_e:.4f}")
print(f"  Mercato (Pinnacle) acc {mk.mean()*100:.1f}%")
print(f"  importanza feature GB (top):")
imp=getattr(gb,'feature_importances_',None)
