/* app.js — caricamento dati, i18n, tabella ordinabile, H2H, backtest, gate email. */
const I18N = {
  it: {
    live: "live", kicker: "The Championships · Wimbledon · 29 giu – 12 lug 2026",
    subtitle: "Modello di previsione del vincitore",
    men: "Maschile", women: "Femminile",
    m_through: "dati aggiornati al", m_sims: "simulazioni", m_brier: "brier (backtest)", m_acc: "accuratezza",
    board_title: "probabilità di titolo", search_ph: "cerca giocatore…",
    th_seed: "testa", th_player: "giocatore", th_title: "titolo", th_final: "finale", th_sf: "semi", th_qf: "quarti",
    wta_warn: "Tabellone femminile: storicamente molto imprevedibile a Wimbledon (vincono spesso outsider non teste di serie). Leggi queste probabilità con più incertezza.",
    h2h_title: "esploratore testa a testa",
    gate_copy: "Inserisci nome ed email per sbloccare il simulatore di singola partita.",
    gate_name: "Nome", gate_email: "Email", gate_btn: "Sblocca",
    gate_consent: "Acconsento a ricevere aggiornamenti sul modello. Niente spam.",
    bt_title: "backtest · wimbledon 2021–2025",
    calib_title: "calibrazione (previsto vs osservato)",
    method_title: "metodologia", limits_title: "limiti dichiarati",
    h2h_win: "vince il match", best_of: "al meglio dei", sets: "set",
    fav: "favorito del modello", champ: "campione effettivo", rankpos: "nel modello",
    legend_pred: "previsto", legend_obs: "osservato",
    withdrawn_label: "Esclusi dal modello — forfait/infortunio",
    movers_label: "movimenti recenti (warm-up su erba)",
  },
  en: {
    live: "live", kicker: "The Championships · Wimbledon · 29 Jun – 12 Jul 2026",
    subtitle: "Champion forecast model",
    men: "Men's", women: "Women's",
    m_through: "data through", m_sims: "simulations", m_brier: "brier (backtest)", m_acc: "accuracy",
    board_title: "title probability", search_ph: "search player…",
    th_seed: "seed", th_player: "player", th_title: "title", th_final: "final", th_sf: "semi", th_qf: "quarter",
    wta_warn: "Women's draw: historically very unpredictable at Wimbledon (unseeded outsiders often win). Read these probabilities with more uncertainty.",
    h2h_title: "head-to-head explorer",
    gate_copy: "Enter your name and email to unlock the single-match simulator.",
    gate_name: "Name", gate_email: "Email", gate_btn: "Unlock",
    gate_consent: "I agree to receive model updates. No spam.",
    bt_title: "backtest · wimbledon 2021–2025",
    calib_title: "calibration (predicted vs observed)",
    method_title: "methodology", limits_title: "stated limitations",
    h2h_win: "wins the match", best_of: "best of", sets: "sets",
    fav: "model favorite", champ: "actual champion", rankpos: "in model",
    legend_pred: "predicted", legend_obs: "observed",
    withdrawn_label: "Excluded from the model — withdrawn/injured",
    movers_label: "recent movements (grass warm-up)",
  }
};

let LANG = (navigator.language || "it").startsWith("en") ? "en" : "it";
let DRAW = "men";
let SORT = { key: "p_title", dir: -1 };
const DATA = {};
let META = null;

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const pct = (x) => (x * 100).toFixed(1) + "%";

async function boot() {
  const [men, women, meta, bt, mov] = await Promise.all([
    fetch("data/forecast_men.json").then(r => r.json()),
    fetch("data/forecast_women.json").then(r => r.json()),
    fetch("data/meta.json").then(r => r.json()),
    fetch("data/backtest.json").then(r => r.json()),
    fetch("data/movements.json").then(r => r.json()).catch(() => null),
  ]);
  DATA.men = men; DATA.women = women; DATA.bt = bt; META = meta; DATA.mov = mov;
  WE.setParams({ beta: meta.params.beta, platt_a: meta.params.platt_a, platt_b: meta.params.platt_b,
    c_rel: meta.params.c_rel, c_form: meta.params.c_form || 0, c_grass: meta.params.c_grass || 0, c_ped: meta.params.c_ped || 0 });
  bindUI();
  applyLang();
  renderMeta();
  renderTable();
  renderWithdrawn();
  renderMovers();
  renderBacktest();
  setupGate();
}

function bindUI() {
  $$(".lang-btn").forEach(b => b.onclick = () => { LANG = b.dataset.lang; $$(".lang-btn").forEach(x => x.classList.toggle("active", x === b)); applyLang(); renderMeta(); renderTable(); renderWithdrawn(); renderMovers(); renderBacktest(); refreshH2H(); });
  $$(".tab").forEach(t => t.onclick = () => { DRAW = t.dataset.draw; $$(".tab").forEach(x => x.classList.toggle("active", x === t)); $("#wta-warn").hidden = DRAW !== "women"; renderTable(); renderWithdrawn(); renderMovers(); populateH2H(); refreshH2H(); });
  $$("th.sortable").forEach(th => th.onclick = () => {
    const k = th.dataset.sort;
    SORT.dir = (SORT.key === k) ? -SORT.dir : -1; SORT.key = k;
    $$("th").forEach(x => x.classList.remove("active")); th.classList.add("active");
    renderTable();
  });
  $("#search").oninput = renderTable;
}

function applyLang() {
  const t = I18N[LANG];
  document.documentElement.lang = LANG;
  $$("[data-i18n]").forEach(el => { const k = el.dataset.i18n; if (t[k] != null) el.textContent = t[k]; });
  $$("[data-i18n-ph]").forEach(el => { const k = el.dataset.i18nPh; if (t[k] != null) el.placeholder = t[k]; });
  $("#wta-warn").textContent = t.wta_warn;
}

function renderMeta() {
  const tx = META.text[LANG];
  $("#intro").textContent = tx.intro;
  $("#m-through").textContent = META.data_through;
  $("#m-sims").textContent = Number(DATA.men.n_sims).toLocaleString(LANG);
  $("#m-brier").textContent = META.backtest_summary.all.brier;
  $("#m-acc").textContent = Math.round(META.backtest_summary.all.accuracy * 100) + "%";
  $("#tagline").textContent = tx.tagline;
  $("#disclaimer").textContent = tx.disclaimer;
  $("#bt-note").textContent = tx.backtest_note;
  const ml = $("#method-list"); ml.innerHTML = "";
  tx.method.forEach(s => { const li = document.createElement("li"); li.textContent = s; ml.appendChild(li); });
  const ll = $("#limits-list"); ll.innerHTML = "";
  tx.limits.forEach(s => { const li = document.createElement("li"); li.textContent = s; ll.appendChild(li); });
}

function renderMovers() {
  const t = I18N[LANG];
  const wrap = $("#movers-wrap");
  const mv = DATA.mov && DATA.mov.movements ? DATA.mov.movements[DRAW === "men" ? "ATP" : "WTA"] : null;
  if (!mv || !mv.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  $("#movers-label").textContent = t.movers_label + (DATA.mov.data_through ? " · " + DATA.mov.data_through : "");
  $("#movers").innerHTML = mv.map(m => {
    const up = m.delta > 0;
    return `<span class="mvr ${up ? "up" : "down"}"><span class="ar">${up ? "▲" : "▼"}</span>` +
      `<span class="pn">${m.player}</span><span class="dv">${(m.now*100).toFixed(1)}% (${up?"+":""}${(m.delta*100).toFixed(1)})</span></span>`;
  }).join("");
}

function renderWithdrawn() {
  const t = I18N[LANG];
  const wd = (META.withdrawals || {})[DRAW === "men" ? "ATP" : "WTA"] || [];
  const el = $("#withdrawn");
  if (!wd.length) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<span class="wl">${t.withdrawn_label}</span><b>${wd.join("</b> · <b>")}</b>`;
}

function renderTable() {
  const t = I18N[LANG];
  const q = $("#search").value.trim().toLowerCase();
  let rows = DATA[DRAW].forecast.slice();
  if (q) rows = rows.filter(r => r.player.toLowerCase().includes(q));
  rows.sort((a, b) => {
    let va = a[SORT.key], vb = b[SORT.key];
    if (SORT.key === "player") return SORT.dir * String(va).localeCompare(String(vb));
    if (SORT.key === "seed") { va = va || 999; vb = vb || 999; }
    return SORT.dir * (va - vb) || (b.p_title - a.p_title);
  });
  const max = Math.max(...DATA[DRAW].forecast.map(r => r.p_title)) || 1;
  const body = $("#forecast-body"); body.innerHTML = "";
  rows.forEach((r, i) => {
    const tr = document.createElement("tr");
    if (i === 0 && SORT.key === "p_title" && SORT.dir === -1 && !q) tr.className = "rank1";
    const seed = r.seed ? `<span class="seed-badge">${r.seed}</span>` : `<span class="seed-badge" style="opacity:.4">·</span>`;
    const barW = Math.max(2, (r.p_title / max) * 64);
    tr.innerHTML =
      `<td class="c-rank">${seed}</td>` +
      `<td class="c-name">${r.player}</td>` +
      `<td class="c-prob"><div class="pcell"><span class="pbar" style="width:${barW}px"></span><span class="ptxt ptitle">${pct(r.p_title)}</span></div></td>` +
      `<td class="c-prob">${pct(r.p_final)}</td>` +
      `<td class="c-prob">${pct(r.p_sf)}</td>` +
      `<td class="c-prob">${pct(r.p_qf)}</td>`;
    body.appendChild(tr);
  });
}

function renderBacktest() {
  const t = I18N[LANG];
  const s = META.backtest_summary;
  const cells = [
    ["Brier · all", s.all.brier], ["Brier · ATP", s.atp.brier],
    ["Brier · WTA", s.wta.brier], ["Brier · OOS 2025", s.oos2025.brier],
  ];
  const g = $("#bt-grid"); g.innerHTML = "";
  cells.forEach(([lab, v]) => {
    const d = document.createElement("div"); d.className = "bt-cell";
    d.innerHTML = `<span class="mono-label">${lab}</span><span class="num">${v}</span>`;
    g.appendChild(d);
  });
  // calibrazione (usa la curva calibrata "all")
  const curve = DATA.bt.match_level.all_2021_2025.calibration_curve;
  const cc = $("#calib-chart"); cc.innerHTML = "";
  curve.forEach(b => {
    const col = document.createElement("div"); col.className = "cbin";
    const ph = Math.round(b.pred * 100), oh = Math.round(b.obs * 100);
    col.innerHTML = `<div class="cbar-wrap"><div class="cbar pred" style="height:${ph}%" title="pred ${ph}%"></div><div class="cbar obs" style="height:${oh}%" title="obs ${oh}%"></div></div><div class="cbin-label">${b.bin}</div>`;
    cc.appendChild(col);
  });
  if (!$("#calib-legend")) {
    const leg = document.createElement("div"); leg.className = "calib-legend"; leg.id = "calib-legend";
    leg.innerHTML = `<span><i style="background:rgba(110,138,60,.35)"></i>${t.legend_pred}</span><span><i style="background:#C9A24A"></i>${t.legend_obs}</span>`;
    $(".calib").appendChild(leg);
  } else {
    $("#calib-legend").innerHTML = `<span><i style="background:rgba(110,138,60,.35)"></i>${t.legend_pred}</span><span><i style="background:#C9A24A"></i>${t.legend_obs}</span>`;
  }
  // tournament-level cards
  const tc = $("#tourney"); tc.innerHTML = "";
  DATA.bt.tournament_level.forEach(x => {
    const d = document.createElement("div"); d.className = "tcard";
    d.innerHTML =
      `<div class="yr">${x.year} · ${x.circuit}</div>` +
      `<div class="fav">${x.top3[0][0]}</div>` +
      `<div class="favp">${t.fav}: ${pct(x.top3[0][1])}</div>` +
      `<div class="champ">${t.champ}: <b>${x.actual_winner}</b> · ${pct(x.winner_pretourney_prob)} · #${x.winner_rank_in_model} ${t.rankpos}</div>`;
    tc.appendChild(d);
  });
}

/* ---------- email gate + H2H ---------- */
function setupGate() {
  const unlocked = localStorage.getItem("wm_unlocked") === "1";
  if (unlocked) { $("#gate").hidden = true; $("#h2h-tool").hidden = false; }
  populateH2H();
  $("#gate-form").addEventListener("submit", (e) => {
    const form = e.target;
    const fd = new FormData(form);
    fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(fd).toString() }).catch(() => {});
    e.preventDefault();
    localStorage.setItem("wm_unlocked", "1");
    $("#gate").hidden = true; $("#h2h-tool").hidden = false;
    populateH2H(); refreshH2H();
  });
  $("#pa").onchange = refreshH2H; $("#pb").onchange = refreshH2H;
}

function populateH2H() {
  const list = DATA[DRAW].forecast.slice().sort((a, b) => a.player.localeCompare(b.player));
  const opts = list.map(p => `<option value="${p.player}">${p.player}${p.seed ? " (" + p.seed + ")" : ""}</option>`).join("");
  const pa = $("#pa"), pb = $("#pb");
  if (!pa) return;
  pa.innerHTML = opts; pb.innerHTML = opts;
  const top = DATA[DRAW].forecast;
  pa.value = top[0].player; pb.value = top[1].player;
}

function refreshH2H() {
  if ($("#h2h-tool").hidden) return;
  const t = I18N[LANG];
  const f = DATA[DRAW].forecast;
  const a = f.find(x => x.player === $("#pa").value);
  const b = f.find(x => x.player === $("#pb").value);
  if (!a || !b) return;
  const bo = DRAW === "men" ? 5 : 3;
  let pa = a.player === b.player ? 0.5 : WE.prob(a, b, bo);
  const wa = Math.round(pa * 100), wb = 100 - wa;
  $("#h2h-result").innerHTML =
    `<div class="h2h-bar"><div class="a" style="width:${wa}%"><span>${wa}%</span></div><div class="b" style="width:${wb}%"><span>${wb}%</span></div></div>` +
    `<div class="h2h-names"><span>${a.player}</span><span>${b.player}</span></div>` +
    `<div class="h2h-detail">${t.best_of} ${bo} ${t.sets} · serve/return Elo + rank prior · ${a.player}: S ${Math.round(a.serve)} / R ${Math.round(a.ret)} — ${b.player}: S ${Math.round(b.serve)} / R ${Math.round(b.ret)}</div>`;
}

boot();
