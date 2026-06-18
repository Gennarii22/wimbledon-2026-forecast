#!/usr/bin/env python3
"""
04 - Campo proiettato Wimbledon 2026 (tabellone non ancora sorteggiato).

Il sorteggio ufficiale esce ~26-27 giugno. In assenza, proiettiamo il campo dai ranking
correnti: top 128 per ranking tra i giocatori attivi nel 2026, teste di serie = top 32.
Limite dichiarato: niente entry-list ufficiale, niente qualificati/wildcard reali, niente
informazioni su infortuni/forfait.

Output: data/field_men.json, data/field_women.json
"""
import os, json, pickle
import engine as E

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data")

FORM=json.load(open(os.path.join(DATA,"form_state.json"))) if os.path.exists(os.path.join(DATA,"form_state.json")) else {}
_wd=json.load(open(os.path.join(DATA,"withdrawals.json"))) if os.path.exists(os.path.join(DATA,"withdrawals.json")) else {}
WITHDRAWN={c:set(_wd.get(c,[])) for c in ('ATP','WTA')}

def build(circuit, state, n=128, n_seeds=32):
    cand=[]
    seen=set()
    out=WITHDRAWN.get(circuit,set())
    pool=[(p, state['last_rank'].get(p)) for p in state['circ']
          if state['circ'][p]==circuit and state['last_date'].get(p,'')>='2026-04-01'
          and state['last_rank'].get(p) and state['last_rank'].get(p)>0
          and p not in out]
    # ordina per rank, tie-break per rating-erba (serve+return shrinkati)
    def grass_strength(p):
        r=E.get_ratings(state,p,'Grass'); return -(r['serve']+r['ret'])
    pool.sort(key=lambda x:(x[1], grass_strength(x[0])))
    field=[]
    for p,rk in pool:
        if p in seen: continue
        seen.add(p)
        r=E.get_ratings(state,p,'Grass')
        fm=FORM.get(p,{})
        field.append(dict(player=p, rank=int(rk),
                          serve=round(r['serve'],1), ret=round(r['ret'],1),
                          elo=round(r['elo'],1), n_grass=int(r['n']),
                          form10=round(fm.get('form10',0.5),3), grass=round(fm.get('grass',0.5),3),
                          ped=float(fm.get('ped',0.0)),
                          last_date=state['last_date'].get(p)))
        if len(field)>=n: break
    for i,f in enumerate(field):
        f['seed']=(i+1) if i<n_seeds else None
    return field

def main():
    state=pickle.load(open(os.path.join(DATA,"ratings_state.pkl"),"rb"))
    for circuit,fn in [('ATP','field_men.json'),('WTA','field_women.json')]:
        field=build(circuit,state)
        json.dump(field, open(os.path.join(DATA,fn),"w"), indent=2)
        print(f"{circuit}: {len(field)} giocatori. Top8 teste di serie:")
        for f in field[:8]:
            print(f"  [{f['seed']:>2}] {f['player']:22s} rank {f['rank']:>3}  S={f['serve']:.0f} R={f['ret']:.0f} ngrass={f['n_grass']}")

if __name__=="__main__":
    main()
