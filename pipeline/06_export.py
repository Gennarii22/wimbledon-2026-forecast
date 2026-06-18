#!/usr/bin/env python3
"""
06 - Assembla i dati per la dashboard statica (site/data/).
Produce meta.json (data snapshot, parametri, metodologia e limiti bilingue) e copia backtest.json.
"""
import os, json, shutil, sqlite3
from datetime import datetime, timezone

HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
DATA=os.path.join(ROOT,"data"); SITE=os.path.join(ROOT,"site","data")
os.makedirs(SITE, exist_ok=True)

def main():
    cal=json.load(open(os.path.join(DATA,"calibration.json")))
    bt=json.load(open(os.path.join(DATA,"backtest.json")))
    shutil.copyfile(os.path.join(DATA,"backtest.json"), os.path.join(SITE,"backtest.json"))

    conn=sqlite3.connect(os.path.join(DATA,"tennis.db"))
    last_date=conn.execute("SELECT MAX(date) FROM matches").fetchone()[0]
    n_atp=conn.execute("SELECT COUNT(*) FROM matches WHERE circuit='ATP'").fetchone()[0]
    n_wta=conn.execute("SELECT COUNT(*) FROM matches WHERE circuit='WTA'").fetchone()[0]
    conn.close()

    bl = bt['match_level']['all_2021_2025']['calibrated']
    atp_m = bt['match_level']['by_circuit_ATP']['calibrated']
    wta_m = bt['match_level']['by_circuit_WTA']['calibrated']
    oos = bt['match_level']['oos_2025']['calibrated']

    wd=json.load(open(os.path.join(DATA,"withdrawals.json"))) if os.path.exists(os.path.join(DATA,"withdrawals.json")) else {}
    withdrawals={c:wd.get(c,[]) for c in ('ATP','WTA')}

    meta=dict(
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        data_through=last_date, n_matches_atp=n_atp, n_matches_wta=n_wta,
        params=cal, withdrawals=withdrawals,
        backtest_summary=dict(all=bl, atp=atp_m, wta=wta_m, oos2025=oos),
        text=dict(
            it=dict(
                tagline="The numbers don't lie. You just can't read them.",
                subtitle="Modello di previsione del vincitore — Wimbledon 2026",
                intro=("Probabilita' di titolo stimate con un motore Barnett-Clarke su Elo Serve/Return "
                       "specifico per l'erba, ancorato al ranking per i giocatori con pochi dati, e "
                       f"{int(json.load(open(os.path.join(SITE,'forecast_men.json')))['n_sims']):,} "
                       "simulazioni Monte Carlo del tabellone a 128."),
                method=[
                    "Elo Serve/Return per superficie (erba): la forza al servizio e alla risposta di ogni giocatore, calcolata partita per partita dal 2000.",
                    "Shrinkage verso il rating generale quando i match su erba sono pochi (la stagione e' cortissima).",
                    "Motore Barnett-Clarke: dalla probabilita' di tenere il servizio -> set -> match (5 set uomini, 3 set donne), calcolo esatto.",
                    "Prior da ranking (Koning 2010) per i giocatori con pochi match, per non fidarsi di un Elo gonfiato da pochi risultati.",
                    "Iperparametri di shrinkage/affidabilita' ottimizzati out-of-sample (C_SHRINK=50, C_REL=100).",
                    "Overlay veterani solo sul forecast live: penalita' Elo per eta'/anzianita' di carriera (>14 anni nel circuito), per correggere il rating gonfiato dal prime di chi e' a fine carriera. E' un prior dichiarato, non validato dal backtest (nell'era di test i veterani vincevano ancora).",
                    "Calibrazione di Platt stimata out-of-sample sulle edizioni di Wimbledon 2021-2024.",
                    "Monte Carlo del tabellone a 128: il sorteggio ufficiale non e' ancora uscito, quindi simuliamo migliaia di sorteggi con le teste di serie nei loro slot canonici.",
                ],
                limits=[
                    "Il tabellone ufficiale non e' ancora sorteggiato: il campo e' proiettato dai ranking correnti (top 128). Niente qualificati, wildcard o entry-list reale.",
                    "Nessuna informazione su infortuni, forfait o ritiri.",
                    "Il dataset non contiene la nazionalita': il vantaggio-campo dei britannici (documentato ma piccolo) e' deliberatamente escluso.",
                    "L'Elo Serve/Return e' stimato dai punteggi dei set (hold/break), non dai dati punto-per-punto.",
                    "Il tabellone femminile e' strutturalmente piu' imprevedibile: il backtest mostra che a Wimbledon vincono spesso outsider non testa di serie. Le probabilita' WTA vanno lette con piu' incertezza.",
                ],
                backtest_note=("Backtest leak-free su Wimbledon 2021-2025 (1.270 match). "
                    f"Brier {bl['brier']} complessivo (ATP {atp_m['brier']}, WTA {wta_m['brier']}), "
                    f"accuratezza {int(bl['accuracy']*100)}%. Out-of-sample 2025: Brier {oos['brier']}. "
                    "A livello torneo il favorito del modello ha vinto il titolo ATP nel 2021, 2022 e 2025."),
                disclaimer="Strumento analitico a scopo informativo. Nessuna garanzia di risultato. Gioca responsabilmente.",
            ),
            en=dict(
                tagline="The numbers don't lie. You just can't read them.",
                subtitle="Champion forecast model — Wimbledon 2026",
                intro=("Title probabilities from a Barnett-Clarke engine built on grass-specific "
                       "Serve/Return Elo, anchored to ranking for low-data players, and "
                       f"{int(json.load(open(os.path.join(SITE,'forecast_men.json')))['n_sims']):,} "
                       "Monte Carlo simulations of the 128-player draw."),
                method=[
                    "Surface-specific Serve/Return Elo (grass): each player's serving and returning strength, computed match-by-match since 2000.",
                    "Shrinkage toward the general rating when a player has few grass matches (the season is very short).",
                    "Barnett-Clarke engine: from hold probability -> set -> match (best-of-5 men, best-of-3 women), exact computation.",
                    "Ranking prior (Koning 2010) for low-match players, to avoid trusting an Elo inflated by a small sample.",
                    "Shrinkage/reliability hyperparameters tuned out-of-sample (C_SHRINK=50, C_REL=100).",
                    "Veteran overlay on the live forecast only: an Elo penalty for age/career length (>14 years on tour), to correct prime-inflated ratings of late-career players. A stated prior, not backtest-validated (in the test era the veterans were still winning).",
                    "Platt calibration estimated out-of-sample on Wimbledon 2021-2024.",
                    "128-draw Monte Carlo: the official draw is not out yet, so we simulate thousands of draws with seeds in their canonical slots.",
                ],
                limits=[
                    "The official draw is not out yet: the field is projected from current rankings (top 128). No qualifiers, wildcards or real entry list.",
                    "No information on injuries, walkovers or withdrawals.",
                    "The dataset has no nationality field: the (documented but small) British home advantage is deliberately excluded.",
                    "Serve/Return Elo is estimated from set scores (holds/breaks), not point-by-point data.",
                    "The women's draw is structurally less predictable: the backtest shows unseeded outsiders often win Wimbledon. Read WTA probabilities with more uncertainty.",
                ],
                backtest_note=("Leak-free backtest on Wimbledon 2021-2025 (1,270 matches). "
                    f"Brier {bl['brier']} overall (ATP {atp_m['brier']}, WTA {wta_m['brier']}), "
                    f"accuracy {int(bl['accuracy']*100)}%. Out-of-sample 2025: Brier {oos['brier']}. "
                    "At tournament level the model favorite won the ATP title in 2021, 2022 and 2025."),
                disclaimer="Analytical tool for informational purposes. No guarantee of outcome. Gamble responsibly.",
            ),
        ),
    )
    json.dump(meta, open(os.path.join(SITE,"meta.json"),"w"), indent=2, ensure_ascii=False)
    print("meta.json + backtest.json esportati in site/data/")
    print(f"  data_through={last_date}  Brier all={bl['brier']} ATP={atp_m['brier']} WTA={wta_m['brier']}")

if __name__=="__main__":
    main()
