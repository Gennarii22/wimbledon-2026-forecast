#!/usr/bin/env python3
"""
live_update.py - Aggiornamento live del forecast Wimbledon 2026.

Rieseguе l'intera pipeline coi dati piu' freschi (warm-up su erba ora, turni di Wimbledon dopo
il sorteggio), poi:
  - confronta col forecast precedente e calcola i MOVIMENTI (chi sale / chi scende)
  - appende uno snapshot allo storico (site/data/history.json) per il grafico-traiettoria
  - salva i top-mover in site/data/movements.json (mostrati in dashboard)

Uso:  python3 live_update.py          (refresh completo: scarica dati + ricostruisce + forecast)
      python3 live_update.py --no-fetch   (salta il download, ricostruisce dai dati gia' presenti)
"""
import os, sys, json, subprocess, shutil
from datetime import datetime, timezone

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); SITE=os.path.join(ROOT,"site","data")
NO_FETCH="--no-fetch" in sys.argv

def snapshot_titles():
    out={}
    for circ,f in [('ATP','forecast_men.json'),('WTA','forecast_women.json')]:
        p=os.path.join(SITE,f)
        if os.path.exists(p):
            out[circ]={x['player']:x['p_title'] for x in json.load(open(p))['forecast']}
    return out

def run(step, args=None):
    print(f"  → {step} {' '.join(args or [])}".rstrip())
    r=subprocess.run([sys.executable, step]+(args or []), cwd=HERE, capture_output=True, text=True)
    if r.returncode!=0:
        print(r.stdout[-1500:]); print(r.stderr[-1500:])
        raise SystemExit(f"FALLITO: {step}")

def main():
    print("=== AGGIORNAMENTO LIVE Wimbledon 2026 ===")
    before=snapshot_titles()

    run("01_build_db.py", ["--no-fetch"] if NO_FETCH else [])
    for s in ["02c_player_meta.py","02_ratings.py","02b_form_features.py",
              "03_backtest.py","04_field.py","05_montecarlo.py","06_export.py"]:
        run(s)

    after=snapshot_titles()

    # data fino a cui arriva il dato
    meta=json.load(open(os.path.join(SITE,"meta.json")))
    through=meta.get("data_through","?")
    now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # MOVIMENTI per circuito
    movements={}
    print(f"\nDati fino al {through}. Movimenti vs run precedente:")
    for circ in ['ATP','WTA']:
        b=before.get(circ,{}); a=after.get(circ,{})
        movers=[]
        for p,now_p in a.items():
            prev=b.get(p)
            if prev is None: continue
            d=now_p-prev
            if abs(d)>=0.005:  # soglia 0.5 punti
                movers.append((p, round(prev,4), round(now_p,4), round(d,4)))
        movers.sort(key=lambda x:-abs(x[3]))
        movements[circ]=[dict(player=p,prev=pv,now=nw,delta=dl) for p,pv,nw,dl in movers[:8]]
        if not b:
            print(f"  {circ}: nessun forecast precedente (prima esecuzione).")
        elif not movers:
            print(f"  {circ}: nessun movimento significativo.")
        else:
            print(f"  {circ}:")
            for p,pv,nw,dl in movers[:6]:
                arrow="▲" if dl>0 else "▼"
                print(f"    {arrow} {p:20s} {pv*100:5.1f}% → {nw*100:5.1f}%  ({dl*100:+.1f})")

    json.dump(dict(generated=now, data_through=through, movements=movements),
              open(os.path.join(SITE,"movements.json"),"w"), indent=2, ensure_ascii=False)

    # STORICO (append snapshot top-12 per circuito)
    hpath=os.path.join(SITE,"history.json")
    hist=json.load(open(hpath)) if os.path.exists(hpath) else []
    snap={"date":through,"generated":now,"top":{}}
    for circ,f in [('ATP','forecast_men.json'),('WTA','forecast_women.json')]:
        fc=json.load(open(os.path.join(SITE,f)))['forecast'][:12]
        snap["top"][circ]={x['player']:round(x['p_title'],4) for x in fc}
    # evita doppioni se stesso data_through+stesso top1
    if not hist or hist[-1].get("date")!=through or hist[-1]["top"]!=snap["top"]:
        hist.append(snap); json.dump(hist, open(hpath,"w"), indent=2, ensure_ascii=False)
        print(f"\nStorico: {len(hist)} snapshot salvati (history.json).")
    else:
        print("\nStorico: nessun cambiamento dal precedente snapshot.")
    print("Aggiornamento live completato.")

if __name__=="__main__":
    main()
