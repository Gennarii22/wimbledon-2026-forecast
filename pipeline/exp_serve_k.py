#!/usr/bin/env python3
"""
Esperimento strutturale: ri-tara il K-factor del Serve/Return Elo.
Ricalcola serve/return (generale + erba) con vari K, ricostruisce la prob base del modello
sui match Wimbledon 2021-2025 e misura il Brier (vero holdout 2025 e 2024-2025).
"""
import os, sqlite3
import numpy as np, pandas as pd
import importlib.util as iu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, accuracy_score
spec=iu.spec_from_file_location('bt','03_backtest.py'); bt=iu.module_from_spec(spec); spec.loader.exec_module(bt)
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,"data")

def holds_breaks(wg,lg):
    if pd.isna(wg) or pd.isna(lg): return 0,0,0,0
    try: wg,lg=int(wg),int(lg)
    except: return 0,0,0,0
    if wg==7 and lg==6: return 6,0,6,0
    if wg==7 and lg==5: return 6,1,5,0
    tot=wg+lg
    if tot==0: return 0,0,0,0
    gw=(tot+1)//2; bw=max(0,wg-gw)
    return wg-bw,bw,lg,0

con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
df=pd.read_sql("""SELECT id,circuit,year,tournament,surface,date,winner,loser,
    w1,l1,w2,l2,w3,l3,w4,l4,w5,l5 FROM matches
    WHERE date IS NOT NULL AND winner IS NOT NULL ORDER BY date ASC, id ASC""",con); con.close()

def compute(k_lo,k_hi,thr):
    sg={};rg={};ss={};rr={};gs={};gr={}
    def ksr(g): return k_lo if g<thr else k_hi
    rows={}
    for _,r in df.iterrows():
        w,l,surf=r['winner'],r['loser'],r['surface']
        swg,rwg=sg.get(w,1500.),rg.get(w,1500.); slg,rlg=sg.get(l,1500.),rg.get(l,1500.)
        sws,rws=ss.get((w,surf),1500.),rr.get((w,surf),1500.); sls,rls=ss.get((l,surf),1500.),rr.get((l,surf),1500.)
        rows[r['id']]=(swg,rwg,slg,rlg,sws,rws,sls,rls)
        thw=tbw=thl=tbl=0
        for k in range(1,6):
            hw,bw,hl,bl=holds_breaks(r[f'w{k}'],r[f'l{k}']); thw+=hw;tbw+=bw;thl+=hl;tbl+=bl
        sv_w=thw+tbl; sv_l=thl+tbw
        if sv_w>0 and sv_l>0:
            kws=ksr(gs.get(w,0));kls=ksr(gs.get(l,0));kwr=ksr(gr.get(w,0));klr=ksr(gr.get(l,0))
            kwss=ksr(gs.get((w,surf),0));klss=ksr(gs.get((l,surf),0));kwrs=ksr(gr.get((w,surf),0));klrs=ksr(gr.get((l,surf),0))
            ehw=E.exp_score(swg,rlg);ehl=E.exp_score(slg,rwg);ehws=E.exp_score(sws,rls);ehls=E.exp_score(sls,rws)
            ahw=thw/sv_w;ahl=thl/sv_l
            sg[w]=swg+kws*sv_w*(ahw-ehw);rg[l]=rlg-klr*sv_w*(ahw-ehw)
            sg[l]=slg+kls*sv_l*(ahl-ehl);rg[w]=rwg-kwr*sv_l*(ahl-ehl)
            ss[(w,surf)]=sws+kwss*sv_w*(ahw-ehws);rr[(l,surf)]=rls-klrs*sv_w*(ahw-ehws)
            ss[(l,surf)]=sls+klss*sv_l*(ahl-ehls);rr[(w,surf)]=rws-kwrs*sv_l*(ahl-ehls)
            gs[w]=gs.get(w,0)+sv_w;gr[w]=gr.get(w,0)+sv_l;gs[l]=gs.get(l,0)+sv_l;gr[l]=gr.get(l,0)+sv_w
            gs[(w,surf)]=gs.get((w,surf),0)+sv_w;gr[(w,surf)]=gr.get((w,surf),0)+sv_l
            gs[(l,surf)]=gs.get((l,surf),0)+sv_l;gr[(l,surf)]=gr.get((l,surf),0)+sv_w
    return rows

eng=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
W=eng[eng.tournament.str.contains('Wimbledon',case=False,na=False)&eng.year.between(2021,2025)].copy()
beta=bt.fit_beta(W[W.year.between(2021,2024)]); E.RANK_BETA=beta

def evalK(k_lo,k_hi,thr):
    rows=compute(k_lo,k_hi,thr)
    w=W.copy()
    sv=w['match_id'].map(rows)
    for i,c in enumerate(['w_sg','w_rg','l_sg','l_rg','w_ss','w_rs','l_ss','l_rs']):
        w[c]=[t[i] if isinstance(t,tuple) else np.nan for t in sv]
    def design(d):
        X=[];y=[]
        for _,r in d.iterrows():
            bl=bt.base_winner_logit(r,beta); aw=(int(r['match_id'])%2==0)
            X.append([bl if aw else -bl]); y.append(1 if aw else 0)
        return np.array(X),np.array(y)
    tr=w[w.year.between(2021,2023)]
    for label,ev in [('2024-25',w[w.year.between(2024,2025)]),('2025',w[w.year==2025])]:
        Xtr,ytr=design(tr); Xe,ye=design(ev)
        lr=LogisticRegression(C=1e6,max_iter=1000).fit(Xtr,ytr)
        p=1/(1+np.exp(-(Xe@lr.coef_[0]+lr.intercept_[0])))
        if label=='2024-25': b1=brier_score_loss(ye,p)
        else: b2=brier_score_loss(ye,p); acc=accuracy_score(ye,p>0.5)
    return b1,b2,acc

print(f"{'K (lo/hi/thr)':16s} {'Brier24-25':>11} {'Brier2025':>10} {'acc2025':>8}")
for cfg in [(8,4,100),(12,6,100),(16,8,150),(20,10,200),(6,3,80)]:
    b1,b2,acc=evalK(*cfg)
    print(f"  {str(cfg):14s} {b1:>11.4f} {b2:>10.4f} {acc*100:>7.1f}%")
print("  (attuale = 8/4/100)")
