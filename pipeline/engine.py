#!/usr/bin/env python3
"""
engine.py - Cuore probabilistico (importabile da backtest e montecarlo).

Pipeline di una singola partita:
  1) Shrinkage del Serve/Return Elo per superficie verso il rating generale:
       eff = elo_generale + w*(elo_superficie - elo_generale),  w = n_grass/(n_grass+C_SHRINK)
  2) Hold probability: logistica 400 su (serve_eff vs return_eff avversario).
  3) Barnett-Clarke: hold -> probabilita' set (DP esatto con tiebreak) -> match (BO3/BO5)  => p_bc
  4) Prior da ranking (Koning 2010, logistica su log2 del rank)                            => p_rank
  5) Blend per AFFIDABILITA': i giocatori con pochi match (Elo cold-start gonfiato) vengono
     ancorati al ranking; i veterani usano il modello.  rel = n_match/(n_match+C_REL)
       p = rel*p_bc + (1-rel)*p_rank   (rel = min dei due giocatori)
  6) Calibrazione di Platt (a,b) stimata out-of-sample nel backtest.

Niente vantaggio-campo: il dataset non contiene la nazionalita' (limite dichiarato).
"""
import numpy as np

C_SHRINK = 25.0       # match-erba per peso 0.5 sullo specifico-superficie
C_REL    = 150.0      # match totali per affidabilita' 0.5 (ancoraggio al ranking)
DEFAULT_ALPHA = 1.0   # (mantenuto per compatibilita'; il blend ora e' rank-based)
RANK_BETA = 0.40      # pendenza logistica sul log2-rank (fit nel backtest)

def exp_score(ra, rb):
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

def _shrink(general, surface, n):
    w = n / (n + C_SHRINK)
    return general + w * (surface - general)

def compute_set_probability(p_g_a, p_g_b):
    """P(A vince un set) dati hold di A e B; A serve per primo. DP esatto (incl. tiebreak)."""
    p_break_a = 1.0 - p_g_b
    prob = np.zeros((8, 8)); prob[0][0] = 1.0
    for i in range(7):
        for j in range(7):
            if prob[i][j] == 0: continue
            if (i == 6 and j <= 4) or (j == 6 and i <= 4): continue
            if (i == 7 and j == 5) or (j == 7 and i == 5): continue
            if i == 6 and j == 6: continue
            a_serving = ((i + j) % 2 == 0)
            pw = p_g_a if a_serving else p_break_a
            prob[i+1][j] += prob[i][j] * pw
            prob[i][j+1] += prob[i][j] * (1.0 - pw)
    p = sum(prob[6][k] for k in range(5)) + prob[7][5]
    p += prob[6][6] * ((p_g_a + p_break_a) / 2.0)
    return p

def match_from_set(p_s, best_of):
    if best_of == 5:
        return p_s**3 + 3*(p_s**3)*(1-p_s) + 6*(p_s**3)*((1-p_s)**2)
    return p_s**2 + 2*(p_s**2)*(1-p_s)

def get_ratings(state, player, surface='Grass'):
    sg = state['sg'].get(player, 1500.0); rg = state['rg'].get(player, 1500.0)
    ss = state['ss'].get((player, surface), 1500.0); rr = state['rr'].get((player, surface), 1500.0)
    n = state['n_surf'].get((player, surface), 0)
    eg = state['elo_g'].get(player, 1500.0); es = state['elo_s'].get((player, surface), 1500.0)
    nm = state['n_match'].get(player, 0)
    return dict(serve=_shrink(sg, ss, n), ret=_shrink(rg, rr, n),
                elo=_shrink(eg, es, n), n=n, n_match=nm)

def rank_prob(rank_a, rank_b, beta=None):
    """Prior basato sul ranking: P(A batte B) ~ logistica sul log2 del rank."""
    if beta is None: beta = RANK_BETA
    ra = max(rank_a or 999, 1); rb = max(rank_b or 999, 1)
    z = beta * (np.log2(rb) - np.log2(ra))
    return 1.0 / (1.0 + np.exp(-z))

def reliability(n_match):
    return n_match / (n_match + C_REL)

def platt(p, a=1.0, b=0.0):
    p = min(max(p, 1e-9), 1 - 1e-9)
    z = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-(a * z + b)))

def final_prob(p_base, dform, dgrass, dped, calib):
    """Calibrazione + aggiustamento di forma in un colpo solo.
    calib = (a, b, c_form, c_grass, c_ped). deltas = feat_A - feat_B (gia' orientati su A)."""
    a, b, cf, cg, cp = calib
    p = min(max(p_base, 1e-9), 1 - 1e-9)
    z = np.log(p / (1 - p))
    z = a * z + b + cf * dform + cg * dgrass + cp * dped
    return 1.0 / (1.0 + np.exp(-z))

def blended_raw(ra, rb, rank_a, rank_b, best_of, beta=None):
    """Probabilita' grezza (pre-Platt) con blend rank-based per affidabilita'."""
    hold_a = exp_score(ra['serve'], rb['ret']); hold_b = exp_score(rb['serve'], ra['ret'])
    p_bc = match_from_set(compute_set_probability(hold_a, hold_b), best_of)
    p_rk = rank_prob(rank_a, rank_b, beta)
    rel = min(reliability(ra['n_match']), reliability(rb['n_match']))
    return rel * p_bc + (1 - rel) * p_rk

def match_prob(state, player_a, player_b, best_of, rank_a, rank_b,
               surface='Grass', beta=None, calib=(1.0, 0.0)):
    ra = get_ratings(state, player_a, surface)
    rb = get_ratings(state, player_b, surface)
    return platt(blended_raw(ra, rb, rank_a, rank_b, best_of, beta), *calib)
