#!/usr/bin/env python3
"""
01 - Costruzione DB locale del Wimbledon Model.

Strategia:
  - Copia il DB storico (sorgente sola-lettura in 3 RESOURCES) nel progetto.
  - Scarica i file ATP/WTA dell'anno corrente da tennis-data.co.uk (fonte del DB storico)
    e rimpiazza le righe dell'anno corrente con la versione aggiornata (include la stagione erba).
  - Questo passo e' CI-friendly: rieseguendolo si aggiorna il dato senza toccare la sorgente.

Output: data/tennis.db
"""
import os, sys, shutil, sqlite3, urllib.request, datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

SRC_DB = "/Users/gennaropancia/Desktop/3 RESOURCES/Betting/Tennis/Tennis-Data/tennis_data.db"
DB = os.path.join(DATA, "tennis.db")

CURRENT_YEAR = 2026
URLS = {
    "ATP": f"http://www.tennis-data.co.uk/{CURRENT_YEAR}/{CURRENT_YEAR}.xlsx",
    "WTA": f"http://www.tennis-data.co.uk/{CURRENT_YEAR}w/{CURRENT_YEAR}.xlsx",
}

# Mapping Excel -> colonne DB (coerente con build_database.py della sorgente)
COLMAP = {
    'Location':'location','Tournament':'tournament','Date':'date','Series':'series','Tier':'tier',
    'Court':'court','Surface':'surface','Round':'round','Best of':'best_of','Winner':'winner','Loser':'loser',
    'WRank':'w_rank','LRank':'l_rank','WPts':'w_pts','LPts':'l_pts',
    'W1':'w1','L1':'l1','W2':'w2','L2':'l2','W3':'w3','L3':'l3','W4':'w4','L4':'l4','W5':'w5','L5':'l5',
    'Wsets':'wsets','Lsets':'lsets','Comment':'comment',
    'B365W':'b365w','B365L':'b365l','PSW':'psw','PSL':'psl','MaxW':'maxw','MaxL':'maxl','AvgW':'avgw','AvgL':'avgl',
}
INT_COLS = {'best_of','w_rank','l_rank','w_pts','l_pts','w1','l1','w2','l2','w3','l3','w4','l4','w5','l5','wsets','lsets'}
TXT_COLS = {'location','tournament','date','series','tier','court','surface','round','winner','loser','comment'}

def si(v):
    if pd.isna(v): return None
    try: return int(round(float(v)))
    except: return None

def sf(v):
    if pd.isna(v): return None
    try: return float(v)
    except: return None

def fetch(url, dest):
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest,'wb') as f:
            f.write(r.read())
        return True
    except Exception as e:
        print(f"  WARN download fallito {url}: {e}")
        return False

def rows_from_xlsx(path, circuit, year):
    df = pd.read_excel(path)
    df = df.dropna(subset=['Winner','Loser'], how='all')
    out = []
    for _, row in df.iterrows():
        d = {'circuit':circuit, 'year':year, 'source_file':os.path.basename(path), 'tour_event_id':None}
        d['series'] = str(row['Series']).strip() if ('Series' in row and not pd.isna(row['Series'])) else None
        d['tier']   = str(row['Tier']).strip()   if ('Tier'   in row and not pd.isna(row['Tier']))   else None
        for ex, db in COLMAP.items():
            if db in ('series','tier'): continue
            if ex not in row: d[db]=None; continue
            v = row[ex]
            if db=='date':
                if isinstance(v, pd.Timestamp): d[db]=v.strftime('%Y-%m-%d')
                elif not pd.isna(v):
                    try: d[db]=pd.to_datetime(v).strftime('%Y-%m-%d')
                    except: d[db]=str(v).strip()
                else: d[db]=None
            elif db in TXT_COLS:
                d[db]=str(v).strip() if not pd.isna(v) else None
            elif db in INT_COLS:
                d[db]=si(v)
            else:
                d[db]=sf(v)
        out.append(d)
    return out

def main():
    # Base del DB: la sorgente locale sola-lettura se presente (sviluppo),
    # altrimenti il DB gia' committato nel repo (CI / GitHub Actions).
    if os.path.exists(SRC_DB):
        print("Copia DB storico dalla sorgente locale...")
        shutil.copyfile(SRC_DB, DB)
    elif os.path.exists(DB):
        print("Sorgente locale assente: uso il DB committato nel repo come base (CI).")
    else:
        raise SystemExit("Nessun DB base disponibile (ne' sorgente locale ne' data/tennis.db).")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(matches)").fetchall() if r[1] != 'id']

    print(f"Refresh anno {CURRENT_YEAR} da tennis-data.co.uk...")
    refreshed = 0
    for circuit, url in URLS.items():
        dest = os.path.join(DATA, f"{circuit.lower()}_{CURRENT_YEAR}.xlsx")
        if not fetch(url, dest):
            if not os.path.exists(dest):
                print(f"  Salto {circuit}: nessun file disponibile.")
                continue
        rows = rows_from_xlsx(dest, circuit, CURRENT_YEAR)
        cur.execute("DELETE FROM matches WHERE circuit=? AND year=?", (circuit, CURRENT_YEAR))
        for d in rows:
            placeholders = ",".join("?"*len(cols))
            cur.execute(f"INSERT INTO matches ({','.join(cols)}) VALUES ({placeholders})",
                        [d.get(c) for c in cols])
        refreshed += len(rows)
        print(f"  {circuit}: {len(rows)} match {CURRENT_YEAR} aggiornati (max date "
              f"{max((r['date'] for r in rows if r['date']), default='?')})")
    conn.commit()

    print("\nVerifica:")
    for r in cur.execute("SELECT circuit, MIN(year), MAX(year), COUNT(*), MAX(date) FROM matches GROUP BY circuit"):
        print(f"  {r[0]}: anni {r[1]}-{r[2]}, {r[3]} match, ultima data {r[4]}")
    g = cur.execute("SELECT circuit, COUNT(*) FROM matches WHERE surface='Grass' AND year=? GROUP BY circuit",
                    (CURRENT_YEAR,)).fetchall()
    print(f"  Grass {CURRENT_YEAR}: {dict(g)}")
    conn.close()
    print(f"\nDB pronto: {DB}")

if __name__ == "__main__":
    main()
