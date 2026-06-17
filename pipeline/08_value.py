#!/usr/bin/env python3
"""
08 - Value betting backtest, metodo esplicito (leak-free).

Per OGNI partita:
  1) prob del modello per ENTRAMBI i tennisti: pA (vincitore reale) e pB = 1-pA  (calibrate)
  2) per OGNI fonte di quote disponibile (Pinnacle, MAX di mercato, Bet365, Media):
       EV_lato = pWin*(quota-1) - pLose*1   ==   pWin*quota - 1
     calcolato su entrambi i lati (giocatore A e giocatore B)
  3) si scommette OGNI selezione con EV>soglia, staking flat 1 unita'
  4) analisi per fonte di quote, per soglia EV, per fascia di quota

yield = P/L totale / totale puntato.  P/L per bet = (quota-1) se vinta, -1 se persa.
"""
import os, json, sqlite3
import numpy as np, pandas as pd
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); SITE=os.path.join(ROOT,"site","data")

ODDS_SOURCES = {  # nome -> (colonna quota vincitore, colonna quota perdente)
    "Pinnacle": ("psw","psl"),
    "MAX mercato": ("maxw","maxl"),
    "Bet365": ("b365w","b365l"),
    "Media": ("avgw","avgl"),
}

def row_ratings(row, who):
    p=f"{who}_"
    return dict(serve=E._shrink(row[p+'sg'],row[p+'ss'],row[p+'nsurf']),
                ret=E._shrink(row[p+'rg'],row[p+'rs'],row[p+'nsurf']),
                elo=E._shrink(row[p+'elo_g'],row[p+'elo_s'],row[p+'nsurf']),
                n_match=row[p+'nmatch'])

def pA_calibrated(row, beta, calib):
    """P(il vincitore reale vince), calibrata, leak-free."""
    bo = 5 if row['circuit']=='ATP' else 3
    return E.platt(E.blended_raw(row_ratings(row,'w'), row_ratings(row,'l'),
                                 row['w_rank'], row['l_rank'], bo, beta), *calib)

def build_bets(df, beta, calib):
    """Restituisce un DataFrame con UNA riga per (match, lato) e l'EV per ogni fonte di quote."""
    rows=[]
    for _, r in df.iterrows():
        pa = pA_calibrated(r, beta, calib)
        if not np.isfinite(pa): continue
        # lato A = vincitore reale (esito=1), lato B = perdente reale (esito=0)
        for side, p, win, wcol_idx in [("W", pa, 1, 0), ("L", 1-pa, 0, 1)]:
            rec = dict(match_id=r['match_id'], year=r['year'], surface=r['surface'],
                       tournament=r['tournament'], side=side, p=p, won=win)
            for name,(wc,lc) in ODDS_SOURCES.items():
                o = r[wc] if wcol_idx==0 else r[lc]
                if pd.isna(o) or o<=1: rec[f"ev_{name}"]=np.nan; rec[f"od_{name}"]=np.nan
                else:
                    rec[f"ev_{name}"]= p*o - 1.0      # = p*(o-1) - (1-p)
                    rec[f"od_{name}"]= o
            rows.append(rec)
    return pd.DataFrame(rows)

def simulate(bets, source, ev_thr, odds_lo=1.01, odds_hi=1e9):
    ev=bets[f"ev_{source}"]; od=bets[f"od_{source}"]
    m = (ev>ev_thr) & od.notna() & (od>=odds_lo) & (od<odds_hi)
    s=bets[m]
    if len(s)==0: return dict(n=0,winrate=None,yield_pct=None,avg_odds=None,profit=None)
    odds=od[m].values; won=s['won'].values
    pl=np.where(won==1, odds-1, -1.0)
    return dict(n=int(len(s)), winrate=round(float(won.mean()),3),
                yield_pct=round(float(pl.sum()/len(s)*100),2),
                avg_odds=round(float(odds.mean()),2), profit=round(float(pl.sum()),1))

def main():
    e=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
    odds=pd.read_sql("SELECT id as match_id, maxw,maxl,b365w,b365l,avgw,avgl FROM matches", con); con.close()
    e=e.merge(odds, on='match_id', how='left')
    cal=json.load(open(os.path.join(DATA,"calibration.json")))
    beta=cal['beta']; calib=(cal['platt_a'],cal['platt_b']); E.RANK_BETA=beta

    slam=r'Australian Open|French Open|Roland|Wimbledon|US Open|U.S. Open'
    scopes={
        "Grand Slam 2022-2025": e[e.tournament.str.contains(slam,case=False,na=False) & e.year.between(2022,2025)],
        "Wimbledon 2021-2025": e[e.tournament.str.contains('Wimbledon',case=False,na=False) & e.year.between(2021,2025)],
    }
    report={}
    for scope_name, df in scopes.items():
        bets=build_bets(df, beta, calib)
        print(f"\n{'='*78}\n{scope_name}  —  match {df.shape[0]}, selezioni valutate {len(bets)} (2 per match)\n{'='*78}")
        # esempio esplicito: prime 3 selezioni
        print("Esempio (come si calcola), prime 3 selezioni lato vincitore:")
        ex=bets[bets.side=='W'].head(3)
        for _,b in ex.iterrows():
            print(f"  p={b['p']:.3f}  Pinn quota={b.get('od_Pinnacle')}  EV_Pinn={b.get('ev_Pinnacle'):+.3f}  | "
                  f"MAX quota={b.get('od_MAX mercato')}  EV_MAX={b.get('ev_MAX mercato'):+.3f}")
        scope_rep={}
        for src in ODDS_SOURCES:
            print(f"\n  -- Fonte quote: {src} --  (scommetto OGNI selezione con EV>soglia)")
            print(f"     {'soglia':>7} {'bets':>6} {'win%':>6} {'avgQ':>6} {'yield%':>8}")
            srow={}
            for thr in [0.0,0.05,0.10,0.15,0.20]:
                m=simulate(bets, src, thr)
                srow[f"EV>={int(thr*100)}%"]=m
                print(f"     {int(thr*100):6d}% {str(m['n']):>6} {('%.1f'%(m['winrate']*100)) if m['winrate'] is not None else '-':>6} "
                      f"{str(m['avg_odds']):>6} {str(m['yield_pct']):>8}")
            scope_rep[src]=srow
        # vista per fascia quota (solo MAX, EV>=10%) — favoriti vs underdog
        print(f"\n  -- MAX mercato, EV>=10%, per fascia di quota --")
        bands=[(1.0,1.5),(1.5,2.0),(2.0,3.0),(3.0,5.0),(5.0,1e9)]
        for lo,hi in bands:
            m=simulate(bets,"MAX mercato",0.10,lo,hi)
            lbl=f"{lo:.1f}-{hi:.0f}" if hi<1e8 else f"{lo:.0f}+"
            print(f"     quota {lbl:>8}: n={str(m['n']):>5} win={('%.1f'%(m['winrate']*100)) if m['winrate'] else '-':>5} yield={str(m['yield_pct']):>7}%")
        report[scope_name]=scope_rep
    json.dump(report, open(os.path.join(SITE,"value.json"),"w"), indent=2, ensure_ascii=False)
    print("\nSalvato site/data/value.json")

if __name__=="__main__":
    main()
