#!/usr/bin/env python3
"""
DNA del campione di Wimbledon: filtri storici (ATP 2000-2025, WTA 2007-2025) + scorecard 2026.
Per ogni filtro: % di campioni che lo rispettano. Poi segna i contendenti 2026 (campo senza forfait).
Tutto leak-free per la parte storica.
"""
import os, sqlite3, json
import numpy as np, pandas as pd
from datetime import datetime
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); DATA=os.path.join(ROOT,"data")
SLAM=r'Australian Open|French Open|Roland|Wimbledon|US Open|U.S. Open'

def pdate(s):
    try: return datetime.strptime(str(s)[:10],'%Y-%m-%d')
    except: return None

def main():
    con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
    m=pd.read_sql("""SELECT circuit,year,tournament,surface,date,round,winner,loser,w_rank,l_rank
                     FROM matches WHERE date IS NOT NULL AND winner IS NOT NULL""",con); con.close()
    m['d']=m['date'].map(pdate); m=m.dropna(subset=['d'])

    # vincitori di tutti gli Slam per anno (per "ex campione Slam")
    slam_finals=m[(m['round']=='The Final') & m.tournament.str.contains(SLAM,case=False,na=False)]
    slam_win_year={}  # (circuit) -> {player: [years]}
    for _,r in slam_finals.iterrows():
        slam_win_year.setdefault(r['circuit'],{}).setdefault(r['winner'],[]).append(int(r['year']))

    # vittorie a Wimbledon per (circuit,player,year)
    wimb=m[m.tournament.str.contains('Wimbledon',case=False,na=False)]
    wwins={}
    for _,r in wimb.iterrows():
        wwins[(r['circuit'],r['winner'],int(r['year']))]=wwins.get((r['circuit'],r['winner'],int(r['year'])),0)+1

    eng=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    engW=eng[eng.tournament.str.contains('Wimbledon',case=False,na=False)]

    def grass_elo_rank(circuit, year, player):
        """Rango del giocatore nel campo Wimbledon di quell'anno per serve+return erba (shrunk)."""
        yd=engW[(engW.circuit==circuit)&(engW.year==year)]
        vals={}
        for _,r in yd.iterrows():
            for who,pl in [('w',r['winner']),('l',r['loser'])]:
                if pl in vals: continue
                s=E._shrink(r[f'{who}_sg'],r[f'{who}_ss'],r[f'{who}_nsurf'])
                rt=E._shrink(r[f'{who}_rg'],r[f'{who}_rs'],r[f'{who}_nsurf'])
                vals[pl]=s+rt
        order=sorted(vals,key=lambda p:-vals[p])
        return (order.index(player)+1) if player in order else 999

    def grass_warmup_wins(circuit, year, player, wstart):
        h=m[(m.circuit==circuit)&(m.surface=='Grass')&(m.year==year)&(m['d']<wstart)]
        return int(((h.winner==player)).sum())

    def prior_wimb_best(circuit, player, year):
        ws=[w for (c,p,y),w in wwins.items() if c==circuit and p==player and y<year]
        return max(ws) if ws else 0

    def prior_slam(circuit, player, year):
        ys=slam_win_year.get(circuit,{}).get(player,[])
        return any(y<year for y in ys)

    FILTERS=['Top-4 ranking','Top-10 ranking','Ex campione Slam',
             'Pedigree Wimbledon (ottavi+ in passato)','Warm-up erba (≥2 vittorie)','Elite erba (top-8 del campo)']

    def player_filters(circuit, year, player, rank, wstart):
        return {
            'Top-4 ranking': rank<=4,
            'Top-10 ranking': rank<=10,
            'Ex campione Slam': prior_slam(circuit,player,year),
            'Pedigree Wimbledon (ottavi+ in passato)': prior_wimb_best(circuit,player,year)>=3,
            'Warm-up erba (≥2 vittorie)': grass_warmup_wins(circuit,year,player,wstart)>=2,
            'Elite erba (top-8 del campo)': grass_elo_rank(circuit,year,player)<=8,
        }

    # ---- storico: % campioni per filtro ----
    print("="*78); print("DNA DEL CAMPIONE — % di campioni che rispettano ogni filtro"); print("="*78)
    hit={'ATP':{f:0 for f in FILTERS},'WTA':{f:0 for f in FILTERS}}; nC={'ATP':0,'WTA':0}
    champ_rows=[]
    for circuit in ['ATP','WTA']:
        yrs=sorted(wimb[wimb.circuit==circuit].year.unique())
        for yr in yrs:
            fin=wimb[(wimb.circuit==circuit)&(wimb.year==yr)&(wimb['round']=='The Final')]
            if len(fin)==0: continue
            champ=fin.iloc[0]['winner']; rank=pd.to_numeric(fin.iloc[0]['w_rank'],errors='coerce')
            if pd.isna(rank): continue
            wstart=wimb[(wimb.circuit==circuit)&(wimb.year==yr)]['d'].min()
            f=player_filters(circuit,yr,champ,rank,wstart)
            nC[circuit]+=1
            for k,v in f.items(): hit[circuit][k]+= 1 if v else 0
            champ_rows.append((circuit,yr,champ,sum(f.values())))
    print(f"\n{'Filtro':42s} {'ATP':>8} {'WTA':>8}")
    for f in FILTERS:
        a=hit['ATP'][f]/nC['ATP']*100; w=hit['WTA'][f]/nC['WTA']*100
        print(f"  {f:40s} {a:6.0f}% {w:7.0f}%")
    print(f"\n  (campioni analizzati: ATP {nC['ATP']}, WTA {nC['WTA']})")
    print("  filtri medi rispettati dal campione: ATP %.1f/6, WTA %.1f/6"%(
        np.mean([r[3] for r in champ_rows if r[0]=='ATP']), np.mean([r[3] for r in champ_rows if r[0]=='WTA'])))

    # ---- scorecard 2026 ----
    cal=json.load(open(os.path.join(DATA,"calibration.json")))
    for circuit,ff,of in [('ATP','field_men.json','forecast_men.json'),('WTA','field_women.json','forecast_women.json')]:
        field=json.load(open(os.path.join(DATA,ff)))
        fc={x['player']:x for x in json.load(open(os.path.join(ROOT,'site','data',of)))['forecast']}
        # elite erba 2026: top-8 per serve+ret nel campo
        order=sorted(field,key=lambda x:-(x['serve']+x['ret'])); elite=set(p['player'] for p in order[:8])
        wstart=datetime(2026,6,29)
        rows=[]
        for x in field:
            p=x['player']; rank=x['rank']
            f={
                'Top-4 ranking': rank<=4,
                'Top-10 ranking': rank<=10,
                'Ex campione Slam': prior_slam(circuit,p,2026),
                'Pedigree Wimbledon (ottavi+ in passato)': prior_wimb_best(circuit,p,2026)>=3,
                'Warm-up erba (≥2 vittorie)': grass_warmup_wins(circuit,2026,p,wstart)>=2,
                'Elite erba (top-8 del campo)': p in elite,
            }
            rows.append((p, sum(f.values()), f, fc.get(p,{}).get('p_title',0)))
        rows.sort(key=lambda r:(-r[1],-r[3]))
        print(f"\n{'='*78}\nSCORECARD 2026 — {circuit} (campo senza forfait) — migliori per filtri rispettati\n{'='*78}")
        print(f"  {'Giocatore':20s} {'Filtri':>7} {'P(tit)':>7}  T4 T10 Slam Ped Warm Elite")
        for p,score,f,pt in rows[:10]:
            mk=lambda b:' ✓' if b else ' ·'
            print(f"  {p:20s} {score:>4}/6 {pt*100:6.1f}% "
                  f"{mk(f['Top-4 ranking'])}{mk(f['Top-10 ranking'])}{mk(f['Ex campione Slam'])}"
                  f"{mk(f['Pedigree Wimbledon (ottavi+ in passato)'])}{mk(f['Warm-up erba (≥2 vittorie)'])}{mk(f['Elite erba (top-8 del campo)'])}")

if __name__=="__main__":
    main()
