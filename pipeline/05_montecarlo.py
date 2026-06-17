#!/usr/bin/env python3
"""
05 - Simulazione Monte Carlo del tabellone a 128 (>=20.000 run).

Il tabellone ufficiale non e' ancora uscito: marginalizziamo l'incertezza del sorteggio.
Ogni simulazione:
  - posiziona le 32 teste di serie nei loro slot canonici (separazione standard);
  - distribuisce i 96 non-teste-di-serie a caso nei restanti slot;
  - gioca i 7 turni con la probabilita' del modello (calibrata), BO5 uomini / BO3 donne;
  - registra titolo / finale / semifinale / quarti per ogni giocatore.
Le probabilita' di match sono precalcolate in una matrice 128x128 (veloce).

Output: site/data/forecast_men.json, forecast_women.json (+ R1 canonico per la scheda match)
"""
import os, json, pickle
import numpy as np
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); SITE=os.path.join(ROOT,"site","data")
os.makedirs(SITE, exist_ok=True)
N_SIMS=30000
rng=np.random.default_rng(20260629)

def seed_slot_order(num):
    """Ordine canonico delle posizioni del tabellone (separazione massima delle teste di serie)."""
    order=[1,2]
    while len(order)<num:
        m=len(order)*2; new=[]
        for x in order: new.append(x); new.append(m+1-x)
        order=new
    return order  # order[k]=valore-seed assegnato alla posizione k

def precompute_matrix(field, state, bo, calib):
    nP=len(field)
    R=[E.get_ratings(state,f['player'],'Grass') for f in field]
    P=np.zeros((nP,nP))
    for i in range(nP):
        for j in range(nP):
            if i==j: continue
            hold_a=E.exp_score(R[i]['serve'],R[j]['ret']); hold_b=E.exp_score(R[j]['serve'],R[i]['ret'])
            p_bc=E.match_from_set(E.compute_set_probability(hold_a,hold_b),bo)
            p_elo=E.exp_score(R[i]['elo'],R[j]['elo'])
            P[i][j]=E.platt(E.DEFAULT_ALPHA*p_bc+(1-E.DEFAULT_ALPHA)*p_elo, *calib)
    return P

def run(field, state, bo, calib, circuit):
    nP=len(field)  # 128
    order=seed_slot_order(nP)
    pos_of_seed={order[k]:k for k in range(nP)}          # seed-rank -> slot
    seed_slots=[pos_of_seed[r] for r in range(1,33)]     # slot occupati dalle 32 teste
    seed_idx=list(range(32))                              # indici field delle teste (gia' ordinati)
    nonseed_idx=list(range(32,nP))                        # indici field dei non-teste
    nonseed_slots=[k for k in range(nP) if k not in set(seed_slots)]

    P=precompute_matrix(field,state,bo,calib)
    rounds=7  # 128->1
    counts=np.zeros((nP,5))  # [title, final, sf, qf, r16] reach counts per player (index field)

    slot_player=np.empty(nP, dtype=int)
    for _ in range(N_SIMS):
        # piazza teste di serie
        for s,slot in zip(seed_idx, seed_slots):
            slot_player[slot]=s
        # piazza non-teste a caso
        perm=rng.permutation(nonseed_idx)
        for slot,pl in zip(nonseed_slots, perm):
            slot_player[slot]=pl
        alive=slot_player.copy()
        size=nP
        for r in range(rounds):
            nxt=np.empty(size//2, dtype=int)
            for m in range(size//2):
                a=alive[2*m]; b=alive[2*m+1]
                nxt[m]= a if rng.random()<P[a][b] else b
            alive=nxt; size//=2
            # registra "reach" del turno appena concluso
            # dopo round r restano i vincitori = quelli che hanno raggiunto il turno r+1
            if size==4: # raggiunto semifinale
                for p in alive: counts[p][2]+=1
            elif size==2: # raggiunto finale
                for p in alive: counts[p][1]+=1
            elif size==1: # campione
                counts[alive[0]][0]+=1
            elif size==8: # quarti
                for p in alive: counts[p][3]+=1
            elif size==16: # ottavi
                for p in alive: counts[p][4]+=1

    res=[]
    for i,f in enumerate(field):
        res.append(dict(player=f['player'], seed=f['seed'], rank=f['rank'],
                        serve=f['serve'], ret=f['ret'], elo=f['elo'], n_grass=f['n_grass'],
                        n_match=int(state['n_match'].get(f['player'],0)),
                        p_title=round(counts[i][0]/N_SIMS,4),
                        p_final=round(counts[i][1]/N_SIMS,4),
                        p_sf=round(counts[i][2]/N_SIMS,4),
                        p_qf=round(counts[i][3]/N_SIMS,4),
                        p_r16=round(counts[i][4]/N_SIMS,4)))
    res.sort(key=lambda x:-x['p_title'])

    # bracket canonico (teste ai loro slot, non-teste per ranking) -> R1 per la scheda match
    for s,slot in zip(seed_idx,seed_slots): slot_player[slot]=s
    for slot,pl in zip(nonseed_slots, nonseed_idx): slot_player[slot]=pl
    r1=[]
    for m in range(nP//2):
        a=int(slot_player[2*m]); b=int(slot_player[2*m+1])
        r1.append(dict(a=field[a]['player'], a_seed=field[a]['seed'],
                       b=field[b]['player'], b_seed=field[b]['seed'],
                       p_a=round(float(P[a][b]),3)))
    return res, r1

def main():
    state=pickle.load(open(os.path.join(DATA,"ratings_state.pkl"),"rb"))
    caljson=json.load(open(os.path.join(DATA,"calibration.json")))
    E.DEFAULT_ALPHA=caljson['alpha']; calib=(caljson['platt_a'],caljson['platt_b'])
    for circuit,ff,of in [('ATP','field_men.json','forecast_men.json'),
                          ('WTA','field_women.json','forecast_women.json')]:
        field=json.load(open(os.path.join(DATA,ff)))
        bo=5 if circuit=='ATP' else 3
        print(f"\n{circuit}: Monte Carlo {N_SIMS} simulazioni (BO{bo})...")
        res,r1=run(field,state,bo,calib,circuit)
        json.dump(dict(circuit=circuit, n_sims=N_SIMS, alpha=E.DEFAULT_ALPHA,
                       forecast=res, r1_canonical=r1),
                  open(os.path.join(SITE,of),"w"), indent=2)
        print(f"  Top 10 P(titolo):")
        for f in res[:10]:
            print(f"    [{str(f['seed'] or '-'):>3}] {f['player']:22s} title {f['p_title']*100:5.1f}%  "
                  f"final {f['p_final']*100:5.1f}%  sf {f['p_sf']*100:5.1f}%")
        print(f"  Sum P(title)={sum(x['p_title'] for x in res):.3f} (atteso ~1.0)")

if __name__=="__main__":
    main()
