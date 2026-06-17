#!/usr/bin/env python3
"""
07 - Backtest scommesse match-per-match (leak-free) vs quote Pinnacle di CHIUSURA.

Battere la linea di chiusura di Pinnacle e' il test piu' severo che esista: se il modello
trova valore positivo contro quella linea, e' edge vero. Onesta' totale sui numeri.

Per ogni match con quote Pinnacle (psw/psl):
  - prob del modello (calibrata, leak-free) per il vincitore effettivo
  - confronto col mercato (devig), edge, simulazione flat + Kelly frazionario
  - benchmark: accuratezza modello vs accuratezza mercato; Brier modello vs Brier mercato

Domini: Wimbledon 2021-2025 (primario, dominio del modello) e tutta l'erba.
Riporta separatamente l'out-of-sample 2025 (la calibrazione e' tarata su 2021-2024).
"""
import os, json
import numpy as np, pandas as pd
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); SITE=os.path.join(ROOT,"site","data")

def row_ratings(row, who):
    p=f"{who}_"
    return dict(serve=E._shrink(row[p+'sg'],row[p+'ss'],row[p+'nsurf']),
                ret=E._shrink(row[p+'rg'],row[p+'rs'],row[p+'nsurf']),
                elo=E._shrink(row[p+'elo_g'],row[p+'elo_s'],row[p+'nsurf']),
                n=row[p+'nsurf'], n_match=row[p+'nmatch'])

def winner_prob(row, beta, calib):
    bo = 5 if row['circuit']=='ATP' else 3
    ra=row_ratings(row,'w'); rb=row_ratings(row,'l')
    return E.platt(E.blended_raw(ra,rb,row['w_rank'],row['l_rank'],bo,beta), *calib)

def devig(psw, psl):
    iw, il = 1/psw, 1/psl
    return iw/(iw+il)   # prob mercato del vincitore

def simulate(df, beta, calib, kelly_frac=0.25, cap=0.05):
    """Ritorna metriche per varie soglie di edge."""
    rows=[]
    for _, r in df.iterrows():
        psw, psl = r['psw'], r['psl']
        if pd.isna(psw) or pd.isna(psl) or psw<=1 or psl<=1: continue
        pw = winner_prob(r, beta, calib)          # P(vincitore reale vince)
        if not np.isfinite(pw): continue
        rows.append((pw, psw, psl))
    out={}
    for thr in [0.0,0.02,0.05,0.10]:
        nb=0; profit=0.0; wins=0; bank=1.0; staked=0.0; odds_sum=0.0
        for pw, psw, psl in rows:
            e_win = pw*psw - 1.0
            e_los = (1-pw)*psl - 1.0
            if e_win>=e_los and e_win>thr:
                side_win=True; odds=psw; edge=e_win
            elif e_los>e_win and e_los>thr:
                side_win=False; odds=psl; edge=e_los
            else:
                continue
            nb+=1; staked+=1.0; odds_sum+=odds
            won = side_win  # il vincitore reale e' "win"; il lato perdente perde sempre
            if won: profit += (odds-1); wins+=1
            else: profit -= 1
            f = min(max(0.0, edge/(odds-1))*kelly_frac, cap)
            bank *= (1 + f*(odds-1)) if won else (1 - f)
        out[thr]=dict(n_bets=nb, hit=round(wins/nb,3) if nb else None,
                      yield_flat=round(profit/staked*100,2) if staked else None,
                      profit_u=round(profit,1),
                      kelly_growth=round((bank-1)*100,1) if nb else None,
                      avg_odds=round(odds_sum/nb,2) if nb else None)
    return out, len(rows)

def benchmark(df, beta, calib):
    """Accuratezza e Brier: modello vs mercato (devig)."""
    mp, mk, y = [], [], []
    for _, r in df.iterrows():
        if pd.isna(r['psw']) or pd.isna(r['psl']) or r['psw']<=1 or r['psl']<=1: continue
        p=winner_prob(r,beta,calib)
        if not np.isfinite(p): continue
        mp.append(p); mk.append(devig(r['psw'],r['psl'])); y.append(1)
    mp=np.array(mp); mk=np.array(mk); y=np.array(y)
    # tutti orientati col vincitore = esito 1
    acc_model = float((mp>0.5).mean())
    acc_market= float((mk>0.5).mean())
    brier_model = float(np.mean((mp-1)**2))
    brier_market= float(np.mean((mk-1)**2))
    return dict(n=len(y), acc_model=round(acc_model,3), acc_market=round(acc_market,3),
                brier_model=round(brier_model,4), brier_market=round(brier_market,4))

def main():
    e=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    cal=json.load(open(os.path.join(DATA,"calibration.json")))
    beta=cal['beta']; calib=(cal['platt_a'],cal['platt_b']); E.RANK_BETA=beta

    wimb = e[e.tournament.str.contains('Wimbledon',case=False,na=False) & e.year.between(2021,2025)]
    grass = e[(e.surface=='Grass') & e.year.between(2021,2025)]
    segments = {
        'Wimbledon 2021-2025': wimb,
        'Wimbledon 2025 (OOS)': wimb[wimb.year==2025],
        'Tutta erba 2021-2025': grass,
        'Erba 2025 (OOS)': grass[grass.year==2025],
    }
    report={}
    for name, df in segments.items():
        sim, n = simulate(df, beta, calib)
        bm = benchmark(df, beta, calib)
        report[name]=dict(n_with_odds=n, betting=sim, benchmark=bm)
        print(f"\n=== {name}  (match con quote: {n}) ===")
        print(f"  BENCHMARK  acc modello {bm['acc_model']*100:.1f}% vs mercato {bm['acc_market']*100:.1f}% | "
              f"Brier modello {bm['brier_model']} vs mercato {bm['brier_market']}")
        print(f"  {'soglia':>7} {'bets':>5} {'hit':>6} {'yield%':>8} {'profit_u':>9} {'kelly%':>8} {"avg_odds":>10}")
        for thr,m in sim.items():
            print(f"  {thr*100:6.0f}% {str(m['n_bets']):>5} {str(m['hit']):>6} {str(m['yield_flat']):>8} "
                  f"{str(m['profit_u']):>9} {str(m['kelly_growth']):>8} {str(m["avg_odds"]):>10}")
    json.dump(report, open(os.path.join(SITE,"betting.json"),"w"), indent=2, ensure_ascii=False)
    print("\nSalvato site/data/betting.json")

if __name__=="__main__":
    main()
