# Wimbledon 2026 — Champion Forecast

Modello di previsione del vincitore di Wimbledon 2026, con dashboard statica bilingue (IT/EN) e auto-aggiornamento.

> The numbers don't lie. You just can't read them.

## Metodo

1. **Elo Serve/Return per superficie (erba)** — forza al servizio e alla risposta di ogni giocatore, calcolata partita per partita dal 2000 (ATP) / 2007 (WTA). K dinamico (FiveThirtyEight).
2. **Shrinkage verso il rating generale** quando i match su erba sono pochi (stagione cortissima).
3. **Motore Barnett-Clarke** — dalla probabilità di tenere il servizio → set → match (best-of-5 uomini, best-of-3 donne), calcolo esatto via programmazione dinamica.
4. **Prior da ranking** (Koning 2010) per i giocatori con pochi match, per non fidarsi di un Elo gonfiato dal cold-start.
5. **Calibrazione di Platt** stimata out-of-sample su Wimbledon 2021–2024.
6. **Monte Carlo del tabellone a 128** (30.000 simulazioni): il sorteggio non è ancora uscito, quindi si marginalizza l'incertezza con le teste di serie nei loro slot canonici.

## Backtest (leak-free, Wimbledon 2021–2025, 1.270 match)

| Segmento | Brier | Log-loss | Accuratezza |
|---|---|---|---|
| Tutti | 0.200 | 0.585 | 69% |
| ATP | 0.190 | 0.558 | 70% |
| WTA | 0.211 | 0.612 | 68% |
| Out-of-sample 2025 | 0.208 | — | 69% |

A livello torneo, il favorito del modello ha vinto il titolo ATP nel 2021, 2022 e 2025.

## Limiti dichiarati

- Campo proiettato dai ranking (top 128): niente entry-list ufficiale, qualificati o wildcard.
- Nessun dato su infortuni, forfait, ritiri.
- Il dataset non contiene la nazionalità: vantaggio-campo britannico escluso.
- Serve/Return Elo stimato dai punteggi dei set (hold/break), non punto-per-punto.
- Tabellone femminile strutturalmente più imprevedibile (lo conferma il backtest).

## Pipeline

```bash
pip install -r requirements.txt
cd pipeline
python3 01_build_db.py     # DB locale + refresh anno corrente da tennis-data.co.uk
python3 02_ratings.py      # rating leak-free (una passata cronologica)
python3 03_backtest.py     # gate obbligatorio: Brier/log-loss/calibrazione
python3 04_field.py        # campo proiettato 2026
python3 05_montecarlo.py   # Monte Carlo del tabellone -> site/data/forecast_*.json
python3 06_export.py       # meta bilingue + backtest -> site/data
```

`site/` è la dashboard statica (nessun build step). Auto-update via GitHub Actions → deploy Netlify a ogni push.

Fonte dati: [tennis-data.co.uk](http://www.tennis-data.co.uk). Strumento analitico a scopo informativo.
