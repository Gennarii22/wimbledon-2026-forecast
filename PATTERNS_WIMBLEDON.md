# Wimbledon — Report sui pattern storici

**Generato il 18 giugno 2026.** Base dati: 5.461 match di Wimbledon, ATP 2000–2025 (25 edizioni) + WTA 2007–2025 (18 edizioni). Confronto col Roland Garros (terra) per il dominio del servizio. Tutti i numeri sono calcolati dal nostro DB, leak-free.

> The numbers don't lie. You just can't read them.

---

## 1. Sintesi: i due Wimbledon

Wimbledon non è un torneo, sono due. Il maschile è il torneo più **prevedibile** dello sport; il femminile è tra i più **aperti**. Ogni pattern qui sotto ruota attorno a questo.

| Pattern | ATP (uomini) | WTA (donne) |
|---|---|---|
| Campione top-4 al via | **84%** | 33% |
| Campione top-10 al via | 92% | 67% |
| Rank mediano del campione | **2** | 7 |
| Campioni distinti (sul periodo) | 9 / 25 | 12 / 18 |
| Campione uscente si ripete | 35% | 19% |
| Il favorito (rank) vince — totale | 69,5% | 67,5% |
| Il favorito vince — semifinali/finale | **76–78%** | **56%** |
| Break rate (dominio servizio) | **8,8%** | 12,3% |
| Tiebreak per set | **19,7%** | 10,1% |
| Set secchi | 49% | 68% |

---

## 2. Pattern del campione

**ATP — la dittatura dei top.** In 25 edizioni solo **9 giocatori diversi** hanno vinto. Il campione è una testa di serie top-4 nell'**84%** dei casi, top-10 nel 92%. Rank mediano: 2. Le uniche due eccezioni fuori dai top-10: **Ivanisevic 2001 (#125, wildcard)** e **Djokovic 2018 (#21, rientro da infortunio)** — entrambe storie irripetibili, non rumore statistico. Il campione uscente si ripete il 35% delle volte.

**WTA — porta girevole.** 12 campionesse diverse in 18 anni, rank mediano **7**, e **6 campionesse fuori dai top-10 al via**: V. Williams (#31, 2007), Bartoli (#15, 2013), Muguruza (#15, 2017), **Rybakina (#23, 2022), Vondrousova (#42 — la più bassa di sempre, 2023), Krejcikova (#32, 2024)**. Le ultime tre edizioni vinte da outsider profonde. Campionessa uscente si ripete solo il 19%.

→ *Questo è esattamente il limite che il nostro modello dichiara: sul WTA le campionesse sono outsider che nessun modello pre-torneo può prezzare al rialzo.*

## 3. Il favorito per turno (la forma della varianza)

Quanto spesso vince il giocatore meglio classificato, turno per turno:

| Turno | ATP | WTA |
|---|---|---|
| 1° turno | 67% | 69% |
| 3° turno | 70% | 64% |
| Quarti | **78%** | 68% |
| Semifinali | **78%** | 56% |
| Finale | 76% | **56%** |

**Pattern opposti.** Negli uomini il favorito si **consolida**: più si avanza, più vince (78% nei turni finali). Nelle donne il segnale **evapora**: semifinale e finale sono quasi un lancio di moneta (56%). Negli uomini i turni decisivi sono i più "chalk"; nelle donne sono i più imprevedibili.

## 4. Dominio del servizio (la firma dell'erba)

| | Break rate | Tiebreak/set |
|---|---|---|
| **Wimbledon (erba)** ATP | **8,8%** | **19,7%** |
| Roland Garros (terra) ATP | 10,7% | 13,9% |
| **Wimbledon (erba)** WTA | 12,3% | 10,1% |
| Roland Garros (terra) WTA | 13,3% | 8,8% |

Sull'erba si strappa meno il servizio e si va più spesso al tiebreak — soprattutto nel maschile (**1 set su 5 finisce 7-6**). Conferma quantitativa del perché il nostro motore è costruito sul **Serve/Return Elo**: a Wimbledon il servizio è l'asse portante. Più il break è raro, più piccoli margini di servizio decidono i match → la varianza per-punto è alta ma il favorito-servitore tiene.

## 5. Formato dei match

| | Set secchi | Al set decisivo |
|---|---|---|
| ATP (BO5) | 49% | 19,3% (3-2) |
| WTA (BO3) | 68% | 31,8% (2-1) |

Il BO5 maschile fa il suo lavoro: metà dei match finiscono in tre set secchi (il più forte chiude), solo 1 su 5 va alla "lotteria" del quinto. Il BO3 femminile è più volatile: 1 match su 3 si decide al terzo.

---

## 6. Pattern di betting (onesti)

Test su tutte le edizioni, scommettendo a **quota MAX di mercato** (best price ottenibile, flat).

**ATP — backare il favorito di chiusura PAGA (poco ma reale):**

| Fascia quota favorito | n | Fav vince | Yield |
|---|---|---|---|
| 1.0–1.3 (super favoriti) | 870 | 88% | −0,4% |
| **1.3–1.6** | 569 | 73% | **+3,8%** |
| **1.6–2.0** | 423 | 60% | **+4,3%** |
| 2.0+ | 35 | 54% | +18,6% (n basso) |
| **Tutti i favoriti** | **1.897** | 77% | **+2,24%** |

**WTA — backare il favorito NON paga:**

| Fascia quota favorito | n | Fav vince | Yield |
|---|---|---|---|
| 1.0–1.3 | 651 | 85% | −0,5% |
| 1.3–1.6 | 698 | 70% | −0,4% |
| 1.6–2.0 | 529 | 56% | −1,8% |
| **Tutti i favoriti** | **1.899** | 72% | **−1,0%** |

Il pattern più forte e più semplice del report: **sull'ATP a Wimbledon, backare il favorito Pinnacle a best-odds nella fascia 1.3–2.0 ha reso +4% storico**; sul WTA lo stesso identico approccio perde. Il mercato femminile prezza correttamente la sua imprevedibilità; quello maschile lascia sul tavolo un piccolo premio sui favoriti di fascia media (dipende dal line-shopping: a quota media/singolo book sparisce).

---

## 7. Cosa significa per il nostro modello

1. **ATP è il nostro terreno forte** (backtest: Brier 0.190, favorito-campione 2021/22/25). I pattern lo confermano: torneo prevedibile, favorito che si consolida → il modello ha senso e il piccolo edge di betting esiste sui favoriti di fascia media.
2. **WTA va trattato con umiltà**: semifinali/finali sono coin-flip, le campionesse sono outsider. Niente strategia "backa il favorito"; semmai il valore (se c'è) è altrove (lato underdog selettivo, o non scommettere).
3. **Il servizio è l'asse giusto**: il dominio del servizio sull'erba giustifica il motore Serve/Return.
4. **Sweet-spot betting**: favoriti ATP a quota 1.3–2.0, best-odds. È il pattern da testare in avanti col modello (incrociando la nostra EV).

---

## 8. Limiti dichiarati

1. "Seed" è approssimato col **ranking** (il DB non ha le teste di serie ufficiali): un top-32 per ranking ≈ testa di serie, ma nei singoli anni può differire.
2. Break rate e tiebreak sono **stimati dai punteggi dei set** (non dai punti reali): la direzione è solida, i livelli sono approssimati.
3. Niente nazionalità/età/mano nel dataset → niente pattern su britannici, mancini, età dei campioni.
4. Gli yield di betting sono storici e **dipendono dal line-shopping** (quota MAX): a quota media il margine sparisce. Campioni piccoli nelle fasce di quota alta.
5. WTA copre dal 2007 (18 edizioni): campione più piccolo, conclusioni più rumorose del maschile.
