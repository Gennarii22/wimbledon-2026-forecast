#!/usr/bin/env python3
"""
Pattern mining storico di Wimbledon (dal DB del modello).
Calcola regolarita' del torneo: seed del campione, hold dei favoriti per turno,
upset, dominio del servizio (vs terra), tiebreak, set secchi, betting patterns.
Stampa numeri puliti -> base per il report.
"""
import os, sqlite3, json
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DB=os.path.join(ROOT,"data","tennis.db")
RO=['1st Round','2nd Round','3rd Round','4th Round','Quarterfinals','Semifinals','The Final']

def holds_breaks(wg,lg):
    if pd.isna(wg) or pd.isna(lg): return 0,0,0,0
    wg,lg=int(wg),int(lg)
    if wg==7 and lg==6: return 6,0,6,0
    if wg==7 and lg==5: return 6,1,5,0
    tot=wg+lg
    if tot==0: return 0,0,0,0
    gw=(tot+1)//2; bw=max(0,wg-gw)
    return wg-bw,bw,lg,0

def load(con, tour):
    q=f"""SELECT circuit,year,round,best_of,winner,loser,w_rank,l_rank,
          w1,l1,w2,l2,w3,l3,w4,l4,w5,l5,wsets,lsets,psw,psl,maxw,maxl
          FROM matches WHERE tournament LIKE '%{tour}%'"""
    return pd.read_sql(q,con)

def serve_metrics(df):
    """break rate e tiebreak% su un set di match."""
    sv=0; br=0; tb=0; sets=0
    for _,r in df.iterrows():
        for k in range(1,6):
            wg,lg=r[f'w{k}'],r[f'l{k}']
            if pd.isna(wg) or pd.isna(lg): continue
            try: wgi,lgi=int(wg),int(lg)
            except: continue
            if wgi+lgi==0: continue
            sets+=1
            if (wgi,lgi) in [(7,6),(6,7)]: tb+=1
            hw,bw,hl,bl=holds_breaks(wg,lg)
            sv+=(hw+bw+hl+bl); br+=(bw+bl)
    return dict(break_rate=br/sv if sv else None, tb_pct=tb/sets if sets else None, n_sets=sets)

def main():
    con=sqlite3.connect(DB)
    w=load(con,'Wimbledon'); rg=load(con,'French Open');
    # alcuni anni il Roland Garros e' "French Open" in tennis-data
    con.close()
    w=w[w.year>=2000]
    print(f"Wimbledon match caricati: {len(w)} | anni {w.year.min()}-{w.year.max()}")

    for circ in ['ATP','WTA']:
        d=w[w.circuit==circ].copy()
        yrs=sorted(d.year.unique())
        print(f"\n{'#'*70}\n# {circ}  (anni: {len(yrs)}, {yrs[0]}-{yrs[-1]})\n{'#'*70}")

        # --- 1. campione: rank pre-torneo ---
        champ=d[d['round']=='The Final'][['year','winner','w_rank']].copy()
        champ['rank']=pd.to_numeric(champ['w_rank'],errors='coerce')
        print("\n[1] SEED/RANK DEL CAMPIONE")
        print(f"  rank #1 al via: {(champ['rank']==1).sum()}/{len(champ)}  ({(champ['rank']==1).mean()*100:.0f}%)")
        print(f"  top-4 al via:   {(champ['rank']<=4).sum()}/{len(champ)}  ({(champ['rank']<=4).mean()*100:.0f}%)")
        print(f"  top-10 al via:  {(champ['rank']<=10).sum()}/{len(champ)} ({(champ['rank']<=10).mean()*100:.0f}%)")
        print(f"  fuori top-10:   {(champ['rank']>10).sum()}/{len(champ)}")
        print(f"  rank mediano campione: {champ['rank'].median():.0f}")
        # campioni distinti / first-time (proxy: prima apparizione come campione nel periodo)
        seen=set(); ft=0
        for _,c in champ.sort_values('year').iterrows():
            if c['winner'] not in seen: ft+=1
            seen.add(c['winner'])
        print(f"  campioni distinti: {champ['winner'].nunique()} su {len(champ)} edizioni")

        # --- 2. ripetizione campione ---
        cw=champ.sort_values('year').set_index('year')['winner'].to_dict()
        rep=sum(1 for y in cw if (y-1) in cw and cw[y]==cw[y-1])
        elig=sum(1 for y in cw if (y-1) in cw)
        print(f"\n[2] CAMPIONE USCENTE si ripete: {rep}/{elig} ({rep/elig*100:.0f}%)")

        # --- 3. hold del favorito (per rank) per turno ---
        d['rk_w']=pd.to_numeric(d['w_rank'],errors='coerce')
        d['rk_l']=pd.to_numeric(d['l_rank'],errors='coerce')
        d2=d.dropna(subset=['rk_w','rk_l'])
        d2=d2[d2.rk_w!=d2.rk_l]
        d2['fav_won']=d2.rk_w<d2.rk_l
        print("\n[3] IL FAVORITO (rank) VINCE, per turno")
        for rnd in RO:
            s=d2[d2['round']==rnd]
            if len(s): print(f"  {rnd:14s}: {s['fav_won'].mean()*100:4.1f}%  (n={len(s)})")
        print(f"  TUTTI i turni: {d2['fav_won'].mean()*100:.1f}% (n={len(d2)})")

        # --- 4. upset: rank gap grande ---
        big=d2[(d2.rk_l<=10)&(d2.rk_w>30)]  # un top-10 (per rank) battuto da uno oltre il 30
        print(f"\n[4] UPSET: un top-10 perde contro un giocatore oltre rank 30: {len(big)} casi "
              f"({len(big)/len(d2[d2.rk_l<=10])*100:.1f}% dei match con un top-10 sfavorito... circa)")

        # --- 5. set secchi e decisivi ---
        d['ls']=pd.to_numeric(d['lsets'],errors='coerce')
        bo=5 if circ=='ATP' else 3
        straight=(d['ls']==0).mean()
        decider=(d['ls']==(bo-1)).mean()
        print(f"\n[5] FORMATO match (BO{bo})")
        print(f"  set secchi (perdente 0 set): {straight*100:.1f}%")
        print(f"  al set decisivo:             {decider*100:.1f}%")

        # --- 6. dominio servizio: break rate e tiebreak, Wimbledon vs Roland Garros ---
        sm_w=serve_metrics(d)
        rgc=rg[(rg.circuit==circ)&(rg.year>=2000)]
        sm_rg=serve_metrics(rgc)
        print(f"\n[6] DOMINIO DEL SERVIZIO (erba vs terra)")
        print(f"  Wimbledon  break rate: {sm_w['break_rate']*100:4.1f}%  tiebreak/set: {sm_w['tb_pct']*100:4.1f}%")
        print(f"  RolandGarros break rate: {sm_rg['break_rate']*100:4.1f}%  tiebreak/set: {sm_rg['tb_pct']*100:4.1f}%")

        # --- 7. betting: favorito Pinnacle per turno + per fascia quota (yield flat a MAX) ---
        b=d.dropna(subset=['psw','psl']).copy()
        b['fav_won']=b.psw<b.psl
        print(f"\n[7] MERCATO: il favorito Pinnacle vince: {b['fav_won'].mean()*100:.1f}% (n={len(b)})")
        # yield se scommetto SEMPRE il favorito di chiusura a flat (a quota MAX del favorito)
        bm=b.dropna(subset=['maxw','maxl']).copy()
        # quota max del favorito = maxw se psw<psl else maxl
        bm['fav_odds_max']=np.where(bm.psw<bm.psl, bm.maxw, bm.maxl)
        bm['fav_win']=bm.psw<bm.psl
        pl=np.where(bm.fav_win, bm.fav_odds_max-1, -1)
        print(f"  scommettere SEMPRE il favorito (a quota MAX, flat): yield {pl.sum()/len(bm)*100:+.2f}% (n={len(bm)})")
        # per fascia quota del favorito
        print("  yield favorito per fascia quota (MAX):")
        for lo,hi in [(1.0,1.3),(1.3,1.6),(1.6,2.0),(2.0,5.0)]:
            m=bm[(bm.fav_odds_max>=lo)&(bm.fav_odds_max<hi)]
            if len(m):
                p=np.where(m.fav_win,m.fav_odds_max-1,-1)
                print(f"    quota {lo:.1f}-{hi:.1f}: n={len(m):4d} winFav={m.fav_win.mean()*100:4.1f}% yield={p.sum()/len(m)*100:+6.2f}%")

if __name__=="__main__":
    main()
