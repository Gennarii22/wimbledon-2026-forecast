#!/usr/bin/env python3
"""
03 - Backtest obbligatorio su Wimbledon 2021-2025 (leak-free).

Usa i rating PRE-match memorizzati in engineered.parquet (nessun leakage).
  A) Match-level: Brier, log-loss, accuracy + curva di calibrazione.
     - stima beta del prior-ranking (fit 2021-2023) e la calibrazione di Platt OUT-OF-SAMPLE.
  B) Tournament-level: ricostruisce il tabellone reale e calcola la P(titolo) ESATTA
     pre-torneo (DP sull'albero) -> dove si piazzava il campione effettivo.

Salva i parametri in data/calibration.json e il report in data/backtest.json.
"""
import os, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score
import engine as E

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
ROUND_ORDER = ['1st Round','2nd Round','3rd Round','4th Round','Quarterfinals','Semifinals','The Final']

def best_of(circuit): return 5 if circuit == 'ATP' else 3

def row_ratings(row, who):
    p = f"{who}_"
    return dict(serve=E._shrink(row[p+'sg'], row[p+'ss'], row[p+'nsurf']),
                ret  =E._shrink(row[p+'rg'], row[p+'rs'], row[p+'nsurf']),
                elo  =E._shrink(row[p+'elo_g'], row[p+'elo_s'], row[p+'nsurf']),
                n=row[p+'nsurf'], n_match=row[p+'nmatch'])

def raw_winner_prob(row, beta):
    ra = row_ratings(row,'w'); rb = row_ratings(row,'l')
    return E.blended_raw(ra, rb, row['w_rank'], row['l_rank'], best_of(row['circuit']), beta)

def oriented(df, beta):
    logits, labels, probs = [], [], []
    for _, r in df.iterrows():
        pw = min(max(raw_winner_prob(r, beta), 1e-9), 1-1e-9)
        a_is_winner = (int(r['match_id']) % 2 == 0)
        pa = pw if a_is_winner else 1-pw
        lab = 1 if a_is_winner else 0
        pa = min(max(pa, 1e-9), 1-1e-9)
        logits.append(np.log(pa/(1-pa))); labels.append(lab); probs.append(pa)
    return np.array(logits), np.array(labels), np.array(probs)

def fit_beta(df):
    """beta ottimale del prior-ranking via logistica su (log2 rankB - log2 rankA) orientata."""
    X, y = [], []
    for _, r in df.iterrows():
        a_is_winner = (int(r['match_id']) % 2 == 0)
        ra = r['w_rank'] if a_is_winner else r['l_rank']
        rb = r['l_rank'] if a_is_winner else r['w_rank']
        X.append(np.log2(max(rb,1)) - np.log2(max(ra,1)))
        y.append(1 if a_is_winner else 0)
    lr = LogisticRegression(C=1e6); lr.fit(np.array(X).reshape(-1,1), y)
    return float(lr.coef_[0][0])

def fit_platt(logits, labels):
    lr = LogisticRegression(C=1e6, solver='lbfgs'); lr.fit(logits.reshape(-1,1), labels)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])

def apply_platt(logits, a, b): return 1.0/(1.0+np.exp(-(a*logits+b)))

def metrics(probs, labels):
    return dict(n=int(len(labels)),
                brier=round(float(brier_score_loss(labels, probs)),4),
                logloss=round(float(log_loss(labels, np.clip(probs,1e-9,1-1e-9))),4),
                accuracy=round(float(accuracy_score(labels, probs>0.5)),4))

def calib_curve(probs, labels, bins=10):
    edges = np.linspace(0,1,bins+1); out=[]
    for i in range(bins):
        m = (probs>=edges[i]) & (probs<(edges[i+1] if i<bins-1 else 1.01))
        if m.sum()==0: continue
        out.append(dict(bin=f"{edges[i]:.1f}-{edges[i+1]:.1f}",
                        pred=round(float(probs[m].mean()),3),
                        obs=round(float(labels[m].mean()),3), n=int(m.sum())))
    return out

class Node:
    def __init__(self): self.children=[]; self.match=None; self.players=None

def build_bracket(year_df):
    by_round = {r: year_df[year_df['round']==r] for r in ROUND_ORDER if (year_df['round']==r).any()}
    prev_node = {}; final_node = None
    for ri, rname in enumerate(ROUND_ORDER):
        if rname not in by_round: continue
        for _, m in by_round[rname].iterrows():
            n = Node(); n.match = m; n.players = (m['winner'], m['loser'])
            if ri > 0:
                for pl in (m['winner'], m['loser']):
                    if pl in prev_node: n.children.append(prev_node[pl])
            prev_node[m['winner']] = n; final_node = n
    return final_node

def match_prob_pre(R, RK, a, b, bo, beta, calib):
    return E.platt(E.blended_raw(R[a], R[b], RK[a], RK[b], bo, beta), *calib)

def title_probs(node, R, RK, bo, beta, calib):
    if not node.children or len(node.children)!=2:
        a,b = node.players; pa = match_prob_pre(R,RK,a,b,bo,beta,calib); return {a:pa, b:1-pa}
    dl = title_probs(node.children[0], R,RK,bo,beta,calib)
    dr = title_probs(node.children[1], R,RK,bo,beta,calib)
    out={}
    for a,pa in dl.items():
        for b,pb in dr.items():
            p = match_prob_pre(R,RK,a,b,bo,beta,calib)
            out[a]=out.get(a,0)+pa*pb*p; out[b]=out.get(b,0)+pa*pb*(1-p)
    return out

def pretourney(year_df):
    order={r:i for i,r in enumerate(ROUND_ORDER)}
    yd=year_df.copy(); yd['rk']=yd['round'].map(order); yd=yd.sort_values(['rk'])
    R, RK = {}, {}
    for _, r in yd.iterrows():
        if r['winner'] not in R: R[r['winner']]=row_ratings(r,'w'); RK[r['winner']]=r['w_rank']
        if r['loser']  not in R: R[r['loser']] =row_ratings(r,'l'); RK[r['loser']] =r['l_rank']
    return R, RK

def main():
    e = pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    w = e[e.tournament.str.contains('Wimbledon',case=False,na=False) & e.year.between(2021,2025)].copy()
    # ATP a Wimbledon e' sempre BO5; correggi eventuali best_of sporchi non usati (usiamo best_of(circuit))
    print(f"Match Wimbledon 2021-2025: {len(w)}")
    train = w[w.year.between(2021,2023)]; test = w[w.year.between(2024,2025)]

    beta = fit_beta(w[w.year.between(2021,2024)]); E.RANK_BETA = beta
    print(f"\nbeta prior-ranking (fit 2021-2024) = {beta:.3f}")

    ltr, ytr, _ = oriented(train, beta); lte, yte, _ = oriented(test, beta)
    a,b = fit_platt(ltr, ytr)
    print(f"Calibrazione OOS check (fit 21-23 -> test 24-25): {metrics(apply_platt(lte,a,b), yte)}")

    lf, yf, _ = oriented(w[w.year.between(2021,2024)], beta)
    cal_a, cal_b = fit_platt(lf, yf)
    print(f"Platt finale (fit 2021-2024) a={cal_a:.3f} b={cal_b:.3f}")

    def block(df, label):
        l, y, praw = oriented(df, beta); pcal = apply_platt(l, cal_a, cal_b)
        return dict(label=label, raw=metrics(praw,y), calibrated=metrics(pcal,y),
                    calibration_curve=calib_curve(pcal,y))
    blocks = {'all_2021_2025': block(w,'Wimbledon 2021-2025 (tutti)'),
              'oos_2025': block(w[w.year==2025],'Out-of-sample 2025'),
              'by_circuit_ATP': block(w[w.circuit=='ATP'],'ATP'),
              'by_circuit_WTA': block(w[w.circuit=='WTA'],'WTA')}
    print("\n[A] Metriche calibrate:")
    for k,v in blocks.items():
        c=v['calibrated']; print(f"  {v['label']:32s} n={c['n']:4d}  Brier {c['brier']}  logloss {c['logloss']}  acc {c['accuracy']}")

    print("\n[B] Tournament-level (P titolo esatta pre-torneo, tabellone reale):")
    tourney=[]
    for year in [2021,2022,2023,2024,2025]:
        for circuit in ['ATP','WTA']:
            yd = w[(w.year==year)&(w.circuit==circuit)]
            if len(yd)<127: continue
            R, RK = pretourney(yd); root = build_bracket(yd); bo=best_of(circuit)
            dist = title_probs(root, R, RK, bo, beta, (cal_a,cal_b))
            ranked = sorted(dist.items(), key=lambda x:-x[1])
            champ = yd[yd['round']=='The Final']['winner'].iloc[0]
            pos = [i for i,(p,_) in enumerate(ranked) if p==champ]
            top3 = [(p,round(pr,3)) for p,pr in ranked[:3]]
            tourney.append(dict(year=year, circuit=circuit, top3=top3, actual_winner=champ,
                                winner_pretourney_prob=round(dist.get(champ,0),3),
                                winner_rank_in_model=(pos[0]+1 if pos else None)))
            print(f"  {year} {circuit}: top1={top3[0][0]} ({top3[0][1]}) | campione {champ} "
                  f"P={dist.get(champ,0):.3f} (rank #{pos[0]+1 if pos else '?'})")

    json.dump(dict(alpha=E.DEFAULT_ALPHA, beta=beta, platt_a=cal_a, platt_b=cal_b,
                   c_shrink=E.C_SHRINK, c_rel=E.C_REL),
              open(os.path.join(DATA,"calibration.json"),"w"), indent=2)
    json.dump(dict(match_level=blocks, tournament_level=tourney),
              open(os.path.join(DATA,"backtest.json"),"w"), indent=2)
    print("\nSalvati calibration.json e backtest.json")

if __name__=="__main__":
    main()
