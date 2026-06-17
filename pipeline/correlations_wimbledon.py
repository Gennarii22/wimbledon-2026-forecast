#!/usr/bin/env python3
"""
Correlazioni complesse: quanto i segnali PRE-Wimbledon predicono il rendimento a Wimbledon,
e soprattutto se aggiungono valore OLTRE il ranking.

Outcome = numero di match vinti a Wimbledon quell'anno (0 = fuori al 1° turno, 7 = campione).
Feature pre-torneo (solo dati precedenti l'inizio del torneo): warm-up erba, forma recente,
risultato Roland Garros, riposo, Wimbledon dell'anno prima.

Per ogni feature: correlazione di Spearman grezza E parziale (controllando il ranking).
Il numero che conta e' la PARZIALE: se sopravvive al ranking, e' segnale vero.
"""
import os, sqlite3
import numpy as np, pandas as pd
from datetime import datetime
from scipy.stats import spearmanr

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DB=os.path.join(ROOT,"data","tennis.db")
RO={'1st Round':1,'2nd Round':2,'3rd Round':3,'4th Round':4,'Quarterfinals':5,'Semifinals':6,'The Final':7}

def pdate(s):
    try: return datetime.strptime(str(s)[:10],'%Y-%m-%d')
    except: return None

def main():
    con=sqlite3.connect(DB)
    m=pd.read_sql("""SELECT circuit,year,tournament,surface,date,round,winner,loser,w_rank,l_rank
                     FROM matches WHERE date IS NOT NULL AND winner IS NOT NULL""",con)
    con.close()
    m['d']=m['date'].map(pdate); m=m.dropna(subset=['d'])

    rows=[]
    for circ in ['ATP','WTA']:
        c=m[m.circuit==circ]
        # storia per giocatore (date+surface+win)
        hist={}
        for _,r in c.iterrows():
            hist.setdefault(r['winner'],[]).append((r['d'],r['surface'],True,r['tournament']))
            hist.setdefault(r['loser'],[]).append((r['d'],r['surface'],False,r['tournament']))
        for p in hist: hist[p].sort()
        years=sorted(c[c.tournament.str.contains('Wimbledon',case=False,na=False)].year.unique())
        for yr in years:
            if yr<2005: continue
            wm=c[(c.year==yr)&(c.tournament.str.contains('Wimbledon',case=False,na=False))]
            if len(wm)<100: continue
            wstart=wm['d'].min()
            # rank pre-torneo per giocatore (dal suo primo match Wimbledon)
            players={}
            for _,r in wm.iterrows():
                for who,rk in [('winner','w_rank'),('loser','l_rank')]:
                    pl=r[who]
                    if pl not in players: players[pl]=pd.to_numeric(r[rk],errors='coerce')
            # wins a Wimbledon
            wins={pl:0 for pl in players}
            for _,r in wm.iterrows(): wins[r['winner']]=wins.get(r['winner'],0)+1
            for pl,rk in players.items():
                if pd.isna(rk): continue
                h=hist.get(pl,[])
                pre=[x for x in h if x[0]<wstart]
                ssn=[x for x in pre if x[0].year==yr]               # stagione corrente pre-W
                grass=[x for x in ssn if x[1]=='Grass']
                rg=[x for x in ssn if 'French Open' in x[3] or 'Roland' in x[3]]
                clay=[x for x in ssn if x[1]=='Clay']
                last10=pre[-10:]
                prevW=[x for x in pre if x[0].year==yr-1 and 'Wimbledon' in x[3]]
                rest=(wstart - pre[-1][0]).days if pre else np.nan
                rows.append(dict(circ=circ, year=yr, player=pl, rank=float(rk), wins=wins[pl],
                    grass_w=sum(1 for x in grass if x[2]), grass_n=len(grass),
                    rg_w=sum(1 for x in rg if x[2]),
                    clay_w=sum(1 for x in clay if x[2]),
                    form10=np.mean([x[2] for x in last10]) if last10 else np.nan,
                    rest=rest,
                    prevW_w=sum(1 for x in prevW if x[2])))
    df=pd.DataFrame(rows)

    def partial_spearman(d, feat, ctrl='rank', out='wins'):
        """Spearman parziale: correlazione dei ranghi residui dopo aver tolto 'ctrl'."""
        s=d.dropna(subset=[feat,ctrl,out])
        if len(s)<50: return None,None,len(s)
        # rango
        rf=s[feat].rank(); rc=s[ctrl].rank(); ro=s[out].rank()
        # residui di feat e out rispetto a ctrl (regressione lineare sui ranghi)
        def resid(y,x):
            x=np.c_[np.ones(len(x)),x]; b=np.linalg.lstsq(x,y,rcond=None)[0]; return y-x@b
        ef=resid(rf.values,rc.values); eo=resid(ro.values,rc.values)
        from scipy.stats import pearsonr
        pr,pp=pearsonr(ef,eo)
        raw,_=spearmanr(s[feat],s[out])
        return raw,pr,len(s)

    feats={'grass_w':'vittorie warm-up erba (anno)','grass_n':'match erba giocati (anno)',
           'rg_w':'vittorie Roland Garros (anno)','clay_w':'vittorie su terra (anno)',
           'form10':'forma ultimi 10 match','rest':'giorni di riposo pre-W',
           'prevW_w':'vittorie Wimbledon anno prima'}
    for circ in ['ATP','WTA']:
        d=df[df.circ==circ]
        print(f"\n{'='*72}\n{circ}  (osservazioni giocatore-Wimbledon: {len(d)}, anni 2005-2025)\n{'='*72}")
        print(f"  {'feature':32s} {'corr grezza':>12} {'corr PARZIALE':>14} {'n':>6}")
        # baseline: rank vs wins
        raw,_=spearmanr(d['rank'],d['wins']); print(f"  {'ranking (baseline)':32s} {raw:>12.3f} {'—':>14} {d.dropna(subset=['rank']).shape[0]:>6}")
        for f,lab in feats.items():
            raw,par,n=partial_spearman(d,f)
            if raw is None: continue
            print(f"  {lab:32s} {raw:>12.3f} {par:>14.3f} {n:>6}")
        # esempio leggibile: chi vince un titolo/finale warm-up erba quanto va a W (per fascia rank)
        print("\n  --- Warm-up erba: media vittorie a Wimbledon (controllo per fascia ranking) ---")
        for lo,hi,lbl in [(1,10,'top-10'),(11,32,'11-32'),(33,2000,'oltre 32')]:
            band=d[(d['rank']>=lo)&(d['rank']<=hi)]
            hot=band[band.grass_w>=2]; cold=band[band.grass_w==0]
            if len(hot)>=10 and len(cold)>=10:
                print(f"    rank {lbl:8s}: con >=2 vittorie warm-up erba -> {hot.wins.mean():.2f} match vinti (n={len(hot)}) | "
                      f"con 0 -> {cold.wins.mean():.2f} (n={len(cold)})  delta {hot.wins.mean()-cold.wins.mean():+.2f}")

if __name__=="__main__":
    main()
