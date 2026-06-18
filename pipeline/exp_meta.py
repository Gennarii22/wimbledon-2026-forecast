#!/usr/bin/env python3
"""R&D dati nuovi: età reale, altezza, nazionalità (vantaggio-campo GBR) da metadati Sackmann/scraping.
Test OOS sopra il modello base, ATP Wimbledon (dove il fattore casa britannico conta)."""
import os, numpy as np, pandas as pd
from datetime import datetime
import importlib.util as iu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, accuracy_score
spec=iu.spec_from_file_location('bt','03_backtest.py'); bt=iu.module_from_spec(spec); spec.loader.exec_module(bt)
import engine as E
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

p=pd.read_csv('/tmp/pmeta/atp_p.csv',low_memory=False)
def key(a,b): return f'{str(b).strip()} {str(a).strip()[0]}.' if pd.notna(a) and str(a).strip() and pd.notna(b) else None
p['k']=[key(a,b) for a,b in zip(p.first_name,p.last_name)]
def pdob(s):
    try: return datetime.strptime(str(s),'%Y.%m.%d')
    except: return None
DOB={k:pdob(b) for k,b in zip(p.k,p.birthdate) if pdob(b)}
HT={k:h for k,h in zip(p.k,p.height_cm) if pd.notna(h)}
GBR={k:(1 if c=='GBR' else 0) for k,c in zip(p.k,p.country_code) if pd.notna(c)}

e=pd.read_parquet(os.path.join(ROOT,'data','engineered.parquet'))
w=e[(e.circuit=='ATP')&e.tournament.str.contains('Wimbledon',case=False,na=False)&e.year.between(2021,2025)].copy()
w['md']=pd.to_datetime(w['date'],errors='coerce')
beta=bt.fit_beta(w[w.year.between(2021,2024)]); E.RANK_BETA=beta

def age(pl,d):
    b=DOB.get(pl); return (d-b).days/365.25 if (b is not None and pd.notna(d)) else np.nan
def feats(r):
    aw,al=age(r['winner'],r['md']),age(r['loser'],r['md'])
    hw,hl=HT.get(r['winner'],np.nan),HT.get(r['loser'],np.nan)
    return dict(
        d_age=(aw-al) if (pd.notna(aw) and pd.notna(al)) else 0.0,
        d_decline=(max(0,aw-30)-max(0,al-30)) if (pd.notna(aw) and pd.notna(al)) else 0.0,
        d_height=(hw-hl) if (pd.notna(hw) and pd.notna(hl)) else 0.0,
        d_home=GBR.get(r['winner'],0)-GBR.get(r['loser'],0))
fe=pd.DataFrame([feats(r) for _,r in w.iterrows()]);
for c in fe.columns: w[c]=fe[c].values

def design(df,col):
    X=[];y=[]
    for _,r in df.iterrows():
        bl=bt.base_winner_logit(r,beta); dd=r[col] if col else 0; aw=(int(r['match_id'])%2==0)
        row=[bl,dd] if col else [bl]
        if aw: X.append(row);y.append(1)
        else: X.append([-x for x in row]);y.append(0)
    return np.array(X),np.array(y)
tr=w[w.year.between(2021,2023)]; te=w[w.year==2025]
Xb,yb=design(tr,None); Xeb,yeb=design(te,None)
lr=LogisticRegression(C=1e6,max_iter=1000).fit(Xb,yb); base=brier_score_loss(yeb,1/(1+np.exp(-(Xeb@lr.coef_[0]+lr.intercept_[0]))))
print(f"BASE ATP Wimbledon OOS 2025 Brier: {base:.4f}  (n_test={len(te)})")
print(f"{'feature nuova':16s} {'OOS Brier':>10} {'coef':>8} {'esito':>8}")
for col,nm in [('d_age','età'),('d_decline','declino>30'),('d_height','altezza'),('d_home','casa GBR')]:
    Xtr,ytr=design(tr,col); Xte,yte=design(te,col)
    lr=LogisticRegression(C=1e6,max_iter=1000).fit(Xtr,ytr)
    p2=1/(1+np.exp(-(Xte@lr.coef_[0]+lr.intercept_[0])))
    print(f"  {nm:14s} {brier_score_loss(yte,p2):>10.4f} {lr.coef_[0][1]:>8.3f} {'MEGLIO' if brier_score_loss(yte,p2)<base-1e-4 else 'no':>8}")
# copertura feature
print(f"\ncopertura: età {(w.d_age!=0).mean():.0%}, altezza {(w.d_height!=0).mean():.0%}, casa GBR match con un britannico {(w.d_home!=0).mean():.0%}")
