/* engine.js — math identica a pipeline/engine.py (per l'esploratore testa-a-testa lato client).
   I rating serve/ret/elo nei JSON sono GIA' efficaci (post-shrinkage), quindi qui non si ri-shrinka. */
const WE = (function () {
  let P = { beta: 0.42, platt_a: 1.0, platt_b: 0.0, c_rel: 150.0, c_form: 0.0, c_grass: 0.0, c_ped: 0.0 };
  function setParams(p) { P = Object.assign(P, p); }

  function expScore(ra, rb) { return 1 / (1 + Math.pow(10, (rb - ra) / 400)); }

  function setProb(pgA, pgB) {
    const pbA = 1 - pgB;
    const prob = Array.from({ length: 8 }, () => new Float64Array(8));
    prob[0][0] = 1;
    for (let i = 0; i < 7; i++) for (let j = 0; j < 7; j++) {
      if (prob[i][j] === 0) continue;
      if ((i === 6 && j <= 4) || (j === 6 && i <= 4)) continue;
      if ((i === 7 && j === 5) || (j === 7 && i === 5)) continue;
      if (i === 6 && j === 6) continue;
      const aServ = ((i + j) % 2 === 0);
      const pw = aServ ? pgA : pbA;
      prob[i + 1][j] += prob[i][j] * pw;
      prob[i][j + 1] += prob[i][j] * (1 - pw);
    }
    let p = 0; for (let k = 0; k < 5; k++) p += prob[6][k]; p += prob[7][5];
    p += prob[6][6] * ((pgA + pbA) / 2);
    return p;
  }
  function matchFromSet(ps, bo) {
    if (bo === 5) return ps ** 3 + 3 * ps ** 3 * (1 - ps) + 6 * ps ** 3 * (1 - ps) ** 2;
    return ps ** 2 + 2 * ps ** 2 * (1 - ps);
  }
  function rankProb(ra, rb) {
    ra = Math.max(ra || 999, 1); rb = Math.max(rb || 999, 1);
    const z = P.beta * (Math.log2(rb) - Math.log2(ra));
    return 1 / (1 + Math.exp(-z));
  }
  const rel = (n) => n / (n + P.c_rel);
  function finalProb(pBase, dForm, dGrass, dPed) {
    pBase = Math.min(Math.max(pBase, 1e-9), 1 - 1e-9);
    let z = Math.log(pBase / (1 - pBase));
    z = P.platt_a * z + P.platt_b + P.c_form * dForm + P.c_grass * dGrass + P.c_ped * dPed;
    return 1 / (1 + Math.exp(-z));
  }
  /* a, b = oggetti giocatore {serve,ret,elo,n_match,rank,form10,grass,ped}; bo = 5|3 */
  const agePen = (act) => Math.min(Math.max(0, (act || 0) - 14) * 6, 80);
  function prob(a, b, bo) {
    const pa = agePen(a.active), pb = agePen(b.active);
    a = { ...a, serve: a.serve - pa, ret: a.ret - pa };
    b = { ...b, serve: b.serve - pb, ret: b.ret - pb };
    const holdA = expScore(a.serve, b.ret), holdB = expScore(b.serve, a.ret);
    const pBc = matchFromSet(setProb(holdA, holdB), bo);
    const pRk = rankProb(a.rank, b.rank);
    const r = Math.min(rel(a.n_match), rel(b.n_match));
    const base = r * pBc + (1 - r) * pRk;
    return finalProb(base, (a.form10||0.5)-(b.form10||0.5), (a.grass||0.5)-(b.grass||0.5), (a.ped||0)-(b.ped||0));
  }
  return { setParams, prob, expScore };
})();
