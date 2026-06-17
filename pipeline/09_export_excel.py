#!/usr/bin/env python3
"""
09 - Esporta in Excel TUTTE le partite valutate dal modello (con quote), con la
selezione di valore (lato con EV piu' alto a quota MAX) e il risultato.

Colonne: Data | Circuito | Competizione | Tipo competizione | Evento |
         Esito desiderato | Quota Pinnacle | Quota MAX | Probabilita' |
         EV Pinnacle | EV MAX | Risultato finale
"""
import os, json, sqlite3
import numpy as np, pandas as pd
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); OUT=os.path.join(ROOT,"exports")
os.makedirs(OUT, exist_ok=True)

def row_ratings(row, who):
    p=f"{who}_"
    return dict(serve=E._shrink(row[p+'sg'],row[p+'ss'],row[p+'nsurf']),
                ret=E._shrink(row[p+'rg'],row[p+'rs'],row[p+'nsurf']),
                elo=E._shrink(row[p+'elo_g'],row[p+'elo_s'],row[p+'nsurf']),
                n_match=row[p+'nmatch'])

def main():
    e=pd.read_parquet(os.path.join(DATA,"engineered.parquet"))
    con=sqlite3.connect(os.path.join(DATA,"tennis.db"))
    meta=pd.read_sql("SELECT id as match_id, series, tier, location, maxw, maxl FROM matches", con); con.close()
    e=e.merge(meta, on='match_id', how='left')
    e=e[e.psw.notna() | e.maxw.notna()].copy()
    cal=json.load(open(os.path.join(DATA,"calibration.json")))
    beta=cal['beta']; calib=(cal['platt_a'],cal['platt_b']); E.RANK_BETA=beta
    print(f"Partite da esportare: {len(e)}")

    out=[]
    for i,(_,r) in enumerate(e.iterrows()):
        bo = 5 if r['circuit']=='ATP' else 3
        pa = E.platt(E.blended_raw(row_ratings(r,'w'), row_ratings(r,'l'),
                                   r['w_rank'], r['l_rank'], bo, beta), *calib)
        if not np.isfinite(pa): continue
        psw, psl = r['psw'], r['psl']; mxw, mxl = r['maxw'], r['maxl']
        # due lati: W = vincitore reale (vinto), L = perdente reale (perso)
        def ev(p, o): return (p*o - 1.0) if (pd.notna(o) and o>1) else np.nan
        sides = {
          'W': dict(player=r['winner'], p=pa,     oP=psw, oM=mxw, won=True),
          'L': dict(player=r['loser'],  p=1-pa,   oP=psl, oM=mxl, won=False),
        }
        for k,s in sides.items():
            s['evP']=ev(s['p'], s['oP']); s['evM']=ev(s['p'], s['oM'])
        # pick = EV MAX piu' alto (fallback EV Pinnacle)
        def keyf(k):
            s=sides[k]; v=s['evM'] if pd.notna(s['evM']) else s['evP']
            return v if pd.notna(v) else -9
        pick = max(sides, key=keyf); s=sides[pick]
        tipo = r['series'] if r['circuit']=='ATP' else r['tier']
        out.append({
            'Data': str(r['date'])[:10],
            'Circuito': r['circuit'],
            'Competizione': r['tournament'],
            'Tipo competizione': tipo,
            'Evento': f"{r['winner']} vs {r['loser']}",
            'Esito desiderato': f"{s['player']} vince",
            'Quota Pinnacle': round(s['oP'],2) if pd.notna(s['oP']) else None,
            'Quota MAX': round(s['oM'],2) if pd.notna(s['oM']) else None,
            "Probabilita'": round(s['p'],3),
            'EV Pinnacle': round(s['evP'],3) if pd.notna(s['evP']) else None,
            'EV MAX': round(s['evM'],3) if pd.notna(s['evM']) else None,
            'Risultato finale': 'Vinto' if s['won'] else 'Perso',
        })
        if (i+1)%20000==0: print(f"  {i+1} elaborate...")

    df=pd.DataFrame(out).sort_values('Data').reset_index(drop=True)
    path=os.path.join(OUT,"partite_modello.xlsx")
    with pd.ExcelWriter(path, engine='openpyxl') as xl:
        df.to_excel(xl, index=False, sheet_name='Partite modello')
        ws=xl.sheets['Partite modello']
        ws.freeze_panes='A2'
        ws.auto_filter.ref=ws.dimensions
        widths={'A':11,'B':9,'C':26,'D':17,'E':40,'F':28,'G':13,'H':11,'I':12,'J':12,'K':10,'L':14}
        for col,w in widths.items(): ws.column_dimensions[col].width=w
    print(f"\nSalvato: {path}")
    print(f"Righe: {len(df)} | con EV MAX positivo: {(df['EV MAX']>0).sum()} | EV MAX>=15%: {(df['EV MAX']>=0.15).sum()}")
    print(df.head(6).to_string())

if __name__=="__main__":
    main()
