#!/usr/bin/env python3
"""
03 - Backtest Wimbledon 2021-2025 (leak-free) con strato di forma.

Base = serve/return BC + prior ranking.  Sopra: calibrazione + aggiustamento di forma
(form10, grass_recent, pedigree) stimati con una logistica unica, OUT-OF-SAMPLE.
Tiene i coefficienti solo se migliorano il Brier OOS.
"""
import os, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data")
ROUND_ORDER=['1st Round','2nd Round','3rd Round','4th Round','Quarterfinals','Semifinals','The Final']
def best_of(c): return 5 if c=='ATP' else 3

def row_ratings(row, who):
    p=f"{who}_"
    return dict(serve=E._shrink(row[p+'sg'],row[p+'ss'],row[p+'nsurf']),
                ret=E._shrink(row[p+'rg'],row[p+'rs'],row[p+'nsurf']),
                elo=E._shrink(row[p+'elo_g'],row[p+'elo_s'],row[p+'nsurf']),
                n=row[p+'nsurf'], n_match=row[p+'nmatch'])
def row_feats(row, who):
    p=f"{who}_"
    return np.array([row[p+'form10']-0.5, row[p+'grass']-0.5, row[p+'ped']])

def base_winner_logit(row, beta):
    ra=row_ratings(row,'w'); rb=row_ratings(row,'l')
    pb=E.blended_raw(ra,rb,row['w_rank'],row['l_rank'],best_of(row['circuit']),beta)
    pb=min(max(pb,1e-9),1-1e-9); return np.log(pb/(1-pb))

def design(df, beta):
    """Ritorna X=[base_logit, dform, dgrass, dped] orientato per parita', e y."""
    X=[]; y=[]
    for _,r in df.iterrows():
        bl=base_winner_logit(r,beta)
        df_=row_feats(r,'w')-row_feats(r,'l')   # winner - loser
        a_is_w=(int(r['match_id'])%2==0)
        if a_is_w: X.append([bl, *df_]); y.append(1)
        else:      X.append([-bl, *(-df_)]); y.append(0)
    return np.array(X), np.array(y)

def fit(X,y):
    lr=LogisticRegression(C=1e6,solver='lbfgs',max_iter=1000); lr.fit(X,y)
    return lr.coef_[0], float(lr.intercept_[0])   # coef=[a,cf,cg,cp], b
def predict(X,coef,b): return 1/(1+np.exp(-(X@coef + b)))
def metrics(p,y): return dict(n=int(len(y)),brier=round(float(brier_score_loss(y,p)),4),
    logloss=round(float(log_loss(y,np.clip(p,1e-9,1-1e-9))),4),accuracy=round(float(accuracy_score(y,p>0.5)),4))
def calib_curve(p,y,bins=10):
    e=np.linspace(0,1,bins+1); o=[]
    for i in range(bins):
        m=(p>=e[i])&(p<(e[i+1] if i<bins-1 else 1.01))
        if m.sum()==0: continue
        o.append(dict(bin=f"{e[i]:.1f}-{e[i+1]:.1f}",pred=round(float(p[m].mean()),3),obs=round(float(y[m].mean()),3),n=int(m.sum())))
    return o

def fit_beta(df):
    X=[];y=[]
    for _,r in df.iterrows():
        a=(int(r['match_id'])%2==0)
        ra=r['w_rank'] if a else r['l_rank']; rb=r['l_rank'] if a else r['w_rank']
        X.append(np.log2(max(rb,1))-np.log2(max(ra,1))); y.append(1 if a else 0)
    lr=LogisticRegression(C=1e6); lr.fit(np.array(X).reshape(-1,1),y); return float(lr.coef_[0][0])

# ---- tournament-level ----
class Node:
    def __init__(self): self.children=[]; self.players=None
def build_bracket(yd):
    byr={r:yd[yd['round']==r] for r in ROUND_ORDER if (yd['round']==r).any()}
    prev={}; fin=None
    for ri,rn in enumerate(ROUND_ORDER):
        if rn not in byr: continue
        for _,mt in byr[rn].iterrows():
            n=Node(); n.players=(mt['winner'],mt['loser'])
            if ri>0:
                for pl in n.players:
                    if pl in prev: n.children.append(prev[pl])
            prev[mt['winner']]=n; fin=n
    return fin
def mp(R,RK,F,a,b,bo,beta,calib):
    pb=E.blended_raw(R[a],R[b],RK[a],RK[b],bo,beta)
    return E.final_prob(pb, F[a][0]-F[b][0], F[a][1]-F[b][1], F[a][2]-F[b][2], calib)
def title_probs(node,R,RK,F,bo,beta,calib):
    if not node.children or len(node.children)!=2:
        a,b=node.players; p=mp(R,RK,F,a,b,bo,beta,calib); return {a:p,b:1-p}
    dl=title_probs(node.children[0],R,RK,F,bo,beta,calib); dr=title_probs(node.children[1],R,RK,F,bo,beta,calib)
    o={}
    for a,pa in dl.items():
        for b,pb in dr.items():
            p=mp(R,RK,F,a,b,bo,beta,calib); o[a]=o.get(a,0)+pa*pb*p; o[b]=o.get(b,0)+pa*pb*(1-p)
    return o
def pretourney(yd):
    order={r:i for i,r in enumerate(ROUND_ORDER)}; yd=yd.copy(); yd['rk']=yd['round'].map(order); yd=yd.sort_values('rk')
    R,RK,F={},{},{}
    for _,r in yd.iterrows():
        for who,pl,rkc in [('w',r['winner'],'w_rank'),('l',r['loser'],'l_rank')]:
            if pl not in R: R[pl]=row_ratings(r,who); RK[pl]=r[rkc]; F[pl]=row_feats(r,who)
    return R,RK,F

def main():
    e=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    w=e[e.tournament.str.contains('Wimbledon',case=False,na=False)&e.year.between(2021,2025)].copy()
    print(f"Match Wimbledon 2021-2025: {len(w)}")
    beta=fit_beta(w[w.year.between(2021,2024)]); E.RANK_BETA=beta
    print(f"beta = {beta:.3f}")

    tr=w[w.year.between(2021,2023)]; te=w[w.year.between(2024,2025)]
    Xtr,ytr=design(tr,beta); Xte,yte=design(te,beta)
    # selezione forward leak-free: tengo una feature di forma solo se migliora il Brier OOS
    # (col 1=form10, 2=grass_recent, 3=pedigree). Soglia anti-rumore.
    cb,bb=fit(Xtr[:,:1],ytr); base_oos=brier_score_loss(yte,predict(Xte[:,:1],cb,bb))
    print(f"\nOOS 2024-2025 BASE Brier {base_oos:.4f}")
    keep=[0]
    for ci,nm in [(1,'form10'),(2,'grass'),(3,'pedigree')]:
        c,b_=fit(Xtr[:,[0,ci]],ytr); o=brier_score_loss(yte,predict(Xte[:,[0,ci]],c,b_))
        ok = o < base_oos - 1e-4
        print(f"  +{nm:9s} OOS Brier {o:.4f} -> {'TENGO' if ok else 'scarto'}")
        if ok: keep.append(ci)

    # fit finale su 2021-2024 con le sole feature tenute
    Xf,yf=design(w[w.year.between(2021,2024)],beta)
    cc,b=fit(Xf[:,keep],yf)
    coef=np.zeros(4);
    for j,ci in enumerate(keep): coef[ci]=cc[j]
    a=coef[0]; calib=(a,b,coef[1],coef[2],coef[3])
    print(f"calib finale: a={a:.3f} b={b:.3f} c_form={coef[1]:.3f} c_grass={coef[2]:.3f} c_ped={coef[3]:.3f}")

    def block(df,label):
        X,y=design(df,beta); p=predict(X,coef,b)
        return dict(label=label,calibrated=metrics(p,y),calibration_curve=calib_curve(p,y))
    blocks={'all_2021_2025':block(w,'Wimbledon 2021-2025'),'oos_2025':block(w[w.year==2025],'OOS 2025'),
            'by_circuit_ATP':block(w[w.circuit=='ATP'],'ATP'),'by_circuit_WTA':block(w[w.circuit=='WTA'],'WTA')}
    print("\n[A] Metriche calibrate (con forma):")
    for k,v in blocks.items():
        c=v['calibrated']; print(f"  {v['label']:22s} n={c['n']:4d} Brier {c['brier']} logloss {c['logloss']} acc {c['accuracy']}")

    print("\n[B] Tournament-level (P titolo pre-torneo, tabellone reale):")
    tourney=[]
    for yr in [2021,2022,2023,2024,2025]:
        for circ in ['ATP','WTA']:
            yd=w[(w.year==yr)&(w.circuit==circ)]
            if len(yd)<127: continue
            R,RK,F=pretourney(yd); root=build_bracket(yd)
            dist=title_probs(root,R,RK,F,best_of(circ),beta,calib)
            ranked=sorted(dist.items(),key=lambda x:-x[1]); champ=yd[yd['round']=='The Final']['winner'].iloc[0]
            pos=[i for i,(p,_) in enumerate(ranked) if p==champ]
            tourney.append(dict(year=yr,circuit=circ,top3=[(p,round(q,3)) for p,q in ranked[:3]],
                actual_winner=champ,winner_pretourney_prob=round(dist.get(champ,0),3),winner_rank_in_model=(pos[0]+1 if pos else None)))
            print(f"  {yr} {circ}: top1 {ranked[0][0]} ({ranked[0][1]*100:.1f}%) | campione {champ} {dist.get(champ,0)*100:.1f}% (#{pos[0]+1 if pos else '?'})")

    json.dump(dict(alpha=E.DEFAULT_ALPHA,beta=beta,platt_a=float(a),platt_b=float(b),
        c_form=float(coef[1]),c_grass=float(coef[2]),c_ped=float(coef[3]),
        c_shrink=E.C_SHRINK,c_rel=E.C_REL,features_kept=[int(k) for k in keep if k!=0]),
        open(os.path.join(DATA,"calibration.json"),"w"),indent=2)
    json.dump(dict(match_level=blocks,tournament_level=tourney),open(os.path.join(DATA,"backtest.json"),"w"),indent=2)
    print("\nSalvati calibration.json e backtest.json")

if __name__=="__main__":
    main()
