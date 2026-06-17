#!/usr/bin/env python3
"""
02 - Motore di rating (leak-free, una sola passata cronologica).

Calcola per ogni match, usando SOLO i dati precedenti:
  - Elo generale e Elo per superficie (K dinamico 538: K = 250/(m+5)^0.4)
  - Serve-Elo / Return-Elo generale e per superficie (update per game, da hold/break stimati dai set)
Salva:
  - data/engineered.parquet : una riga per match con i rating PRE-match (per il backtest)
  - data/ratings_state.pkl  : stato finale dei rating + conteggi + ultimo rank/pts (per costruire il campo)

Nota metodologica: i Serve/Return Elo per superficie sono rumorosi quando un giocatore ha pochi match
sull'erba. Lo shrinkage verso il rating generale viene applicato a valle (03_engine), non qui:
qui salviamo anche il numero di game disputati sull'erba per pesare quello shrinkage.
"""
import os, sqlite3, pickle
import numpy as np, pandas as pd
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data"); DB = os.path.join(DATA, "tennis.db")

def k_dyn(m):  # FiveThirtyEight dynamic K
    return 250.0 / ((m + 5.0) ** 0.4)

def exp_score(ra, rb):
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

def k_sr(g):  # serve/return Elo K
    return 8.0 if g < 100 else 4.0

def k_layoff(gap_days):
    """K maggiorato dopo una lunga assenza (infortunio/pausa): piu' incertezza sul rating.
    Idea da Glicko (RD) e confermata da Green Code. Nessun effetto entro 60 giorni."""
    if gap_days is None or gap_days <= 60: return 1.0
    return min(1.0 + (gap_days - 60) / 365.0 * 0.6, 1.6)  # fino a +60% dopo ~1 anno

def _pdate(s):
    try: return datetime.strptime(str(s)[:10], '%Y-%m-%d')
    except: return None

def holds_breaks(wg, lg):
    """Stima hold/break del vincitore-set da un punteggio set (wg-lg)."""
    if wg is None or lg is None: return 0,0,0,0
    try: wg, lg = int(wg), int(lg)
    except: return 0,0,0,0
    if wg == 7 and lg == 6: return 6,0,6,0
    if wg == 7 and lg == 5: return 6,1,5,0
    tot = wg + lg
    if tot == 0: return 0,0,0,0
    gw = (tot + 1)//2; gl = tot - gw
    bw = max(0, wg - gw); hw = wg - bw
    return hw, bw, lg, 0

def main():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT id, circuit, year, tournament, date, surface, round, best_of,
               winner, loser, w_rank, l_rank, w_pts, l_pts,
               w1,l1,w2,l2,w3,l3,w4,l4,w5,l5, psw, psl
        FROM matches
        WHERE date IS NOT NULL AND winner IS NOT NULL AND loser IS NOT NULL
        ORDER BY date ASC, id ASC
    """, conn)
    conn.close()
    print(f"Match caricati: {len(df)}")

    elo_g, elo_s = {}, {}                 # generale, (p,surf)
    sg, rg = {}, {}                        # serve/return generale
    ss, rr = {}, {}                        # serve/return (p,surf)
    n_match, n_surf = {}, {}               # conteggi
    g_serv, g_ret = {}, {}                 # game serviti/risposti (per K serve/return)
    g_serv_s, g_ret_s = {}, {}
    last_date, last_rank, last_pts = {}, {}, {}

    rows = []
    for i, r in df.iterrows():
        w, l, surf = r['winner'], r['loser'], r['surface']
        # --- valori PRE-match ---
        ewg, elg = elo_g.get(w,1500.0), elo_g.get(l,1500.0)
        ews, els = elo_s.get((w,surf),1500.0), elo_s.get((l,surf),1500.0)
        swg, rwg = sg.get(w,1500.0), rg.get(w,1500.0)
        slg, rlg = sg.get(l,1500.0), rg.get(l,1500.0)
        sws, rws = ss.get((w,surf),1500.0), rr.get((w,surf),1500.0)
        sls, rls = ss.get((l,surf),1500.0), rr.get((l,surf),1500.0)
        nw_s, nl_s = n_surf.get((w,surf),0), n_surf.get((l,surf),0)

        rows.append(dict(
            match_id=r['id'], circuit=r['circuit'], year=r['year'], tournament=r['tournament'],
            round=r['round'], date=r['date'], surface=surf, best_of=r['best_of'],
            winner=w, loser=l,
            w_elo_g=ewg, l_elo_g=elg, w_elo_s=ews, l_elo_s=els,
            w_sg=swg, w_rg=rwg, l_sg=slg, l_rg=rlg,
            w_ss=sws, w_rs=rws, l_ss=sls, l_rs=rls,
            w_nsurf=nw_s, l_nsurf=nl_s,
            w_nmatch=n_match.get(w,0), l_nmatch=n_match.get(l,0),
            w_rank=(r['w_rank'] if r['w_rank'] else 999),
            l_rank=(r['l_rank'] if r['l_rank'] else 999),
            psw=r['psw'], psl=r['psl']
        ))

        # --- layoff: giorni dall'ultimo match (last_date contiene la data PRECEDENTE) ---
        md = _pdate(r['date'])
        def _gap(p):
            ld = _pdate(last_date.get(p)) if last_date.get(p) else None
            return (md - ld).days if (md and ld) else None
        lf_w, lf_l = k_layoff(_gap(w)), k_layoff(_gap(l))

        # --- update Elo generale + superficie (K scalato per layoff) ---
        mw, ml = n_match.get(w,0), n_match.get(l,0)
        kw, kl = k_dyn(mw)*lf_w, k_dyn(ml)*lf_l
        ew = exp_score(ewg, elg)
        elo_g[w] = ewg + kw*(1-ew); elo_g[l] = elg + kl*(0-(1-ew))
        ms_w, ms_l = n_surf.get((w,surf),0), n_surf.get((l,surf),0)
        kws, kls = k_dyn(ms_w)*lf_w, k_dyn(ms_l)*lf_l
        ews_e = exp_score(ews, els)
        elo_s[(w,surf)] = ews + kws*(1-ews_e); elo_s[(l,surf)] = els + kls*(0-(1-ews_e))

        # --- update Serve/Return Elo (da hold/break) ---
        thw=tbw=thl=tbl=0
        for k in range(1,6):
            hw,bw,hl,bl = holds_breaks(r[f'w{k}'], r[f'l{k}'])
            thw+=hw; tbw+=bw; thl+=hl; tbl+=bl
        serv_w = thw + tbl   # game serviti dal vincitore
        serv_l = thl + tbw
        if serv_w > 0 and serv_l > 0:
            kw_s = k_sr(g_serv.get(w,0)); kl_s = k_sr(g_serv.get(l,0))
            kw_r = k_sr(g_ret.get(w,0));  kl_r = k_sr(g_ret.get(l,0))
            kw_ss = k_sr(g_serv_s.get((w,surf),0)); kl_ss = k_sr(g_serv_s.get((l,surf),0))
            kw_rs = k_sr(g_ret_s.get((w,surf),0));  kl_rs = k_sr(g_ret_s.get((l,surf),0))
            eh_w = exp_score(swg, rlg); eh_l = exp_score(slg, rwg)
            eh_ws = exp_score(sws, rls); eh_ls = exp_score(sls, rws)
            ah_w = thw/serv_w; ah_l = thl/serv_l
            sg[w] = swg + kw_s*serv_w*(ah_w-eh_w); rg[l] = rlg - kl_r*serv_w*(ah_w-eh_w)
            sg[l] = slg + kl_s*serv_l*(ah_l-eh_l); rg[w] = rwg - kw_r*serv_l*(ah_l-eh_l)
            ss[(w,surf)] = sws + kw_ss*serv_w*(ah_w-eh_ws); rr[(l,surf)] = rls - kl_rs*serv_w*(ah_w-eh_ws)
            ss[(l,surf)] = sls + kl_ss*serv_l*(ah_l-eh_ls); rr[(w,surf)] = rws - kw_rs*serv_l*(ah_l-eh_ls)
            g_serv[w]=g_serv.get(w,0)+serv_w; g_ret[w]=g_ret.get(w,0)+serv_l
            g_serv[l]=g_serv.get(l,0)+serv_l; g_ret[l]=g_ret.get(l,0)+serv_w
            g_serv_s[(w,surf)]=g_serv_s.get((w,surf),0)+serv_w; g_ret_s[(w,surf)]=g_ret_s.get((w,surf),0)+serv_l
            g_serv_s[(l,surf)]=g_serv_s.get((l,surf),0)+serv_l; g_ret_s[(l,surf)]=g_ret_s.get((l,surf),0)+serv_w

        # --- conteggi e ultimi metadati ---
        n_match[w]=mw+1; n_match[l]=ml+1
        n_surf[(w,surf)]=ms_w+1; n_surf[(l,surf)]=ms_l+1
        d = r['date']
        last_date[w]=d; last_date[l]=d
        if r['w_rank'] is not None: last_rank[w]=r['w_rank']; last_pts[w]=r['w_pts']
        if r['l_rank'] is not None: last_rank[l]=r['l_rank']; last_pts[l]=r['l_pts']

        if (i+1)%20000==0: print(f"  {i+1} match...")

    eng = pd.DataFrame(rows)
    eng.to_parquet(os.path.join(DATA,"engineered.parquet"))
    print(f"engineered.parquet: {len(eng)} righe, {eng.shape[1]} colonne")

    # circuito per giocatore (ultimo visto)
    circ = {}
    for _, r in df.iterrows():
        circ[r['winner']]=r['circuit']; circ[r['loser']]=r['circuit']

    state = dict(elo_g=elo_g, elo_s=elo_s, sg=sg, rg=rg, ss=ss, rr=rr,
                 n_match=n_match, n_surf=n_surf, g_serv=g_serv, g_ret=g_ret,
                 last_date=last_date, last_rank=last_rank, last_pts=last_pts, circ=circ)
    with open(os.path.join(DATA,"ratings_state.pkl"),"wb") as f:
        pickle.dump(state, f)
    print("ratings_state.pkl salvato.")

    # sanity: top 10 grass serve+return (uomini) tra chi ha giocato di recente
    print("\nSanity - top grass (serve+return surf, ATP, attivi 2026):")
    cand=[]
    for p,c in circ.items():
        if c!='ATP': continue
        if last_date.get(p,'')<'2026-01-01': continue
        s=ss.get((p,'Grass'),1500.0); rt=rr.get((p,'Grass'),1500.0)
        cand.append((p, s+rt, round(s,0), round(rt,0), n_surf.get((p,'Grass'),0)))
    for p,tot,s,rt,n in sorted(cand,key=lambda x:-x[1])[:10]:
        print(f"  {p:22s} S+R={tot:7.0f}  S={s:5.0f} R={rt:5.0f}  ngrass={n}")

if __name__=="__main__":
    main()
