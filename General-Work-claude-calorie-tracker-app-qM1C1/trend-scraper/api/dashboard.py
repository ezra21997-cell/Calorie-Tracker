"""
Dashboard route – serves a self-contained HTML page at GET /dashboard.

The page fetches data from the existing API endpoints using vanilla JS
and refreshes automatically every 60 seconds.  No extra dependencies are
required beyond what is already installed.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

dashboard_router = APIRouter()

# ── HTML template ─────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Trend Scraper ✦ Dashboard</title>

  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Exo+2:wght@300;400;600;700&display=swap" rel="stylesheet" />

  <style>
    /* ── Reset ────────────────────────────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* ── Palette ─────────────────────────────────────────────────────── */
    :root {
      --bg:         #050510;
      --panel:      rgba(10, 10, 40, 0.85);
      --border:     #1a1a6e;
      --pink:       #ff2d78;
      --cyan:       #00e5ff;
      --purple:     #b000ff;
      --gold:       #ffd700;
      --green:      #00ff88;
      --text:       #c8d4f0;
      --dim:        #556080;
      --glow-pink:  0 0 12px #ff2d78aa, 0 0 28px #ff2d7844;
      --glow-cyan:  0 0 12px #00e5ffaa, 0 0 28px #00e5ff44;
      --glow-purp:  0 0 12px #b000ffaa, 0 0 28px #b000ff44;
    }

    /* ── Starfield ────────────────────────────────────────────────────── */
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Exo 2', sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
      position: relative;
    }

    #stars {
      position: fixed; inset: 0; z-index: 0;
      background:
        radial-gradient(1px 1px at 10% 15%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 25% 40%, #aaf 0%, transparent 100%),
        radial-gradient(1.5px 1.5px at 40% 5%, #ffd 0%, transparent 100%),
        radial-gradient(1px 1px at 55% 80%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 70% 25%, #ccf 0%, transparent 100%),
        radial-gradient(1.5px 1.5px at 80% 60%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 90% 10%, #fdf 0%, transparent 100%),
        radial-gradient(1px 1px at 15% 70%, #aff 0%, transparent 100%),
        radial-gradient(1px 1px at 35% 55%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 60% 45%, #faf 0%, transparent 100%),
        radial-gradient(1px 1px at 75% 90%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 5%  90%, #ddf 0%, transparent 100%),
        radial-gradient(1px 1px at 50% 20%, #fff 0%, transparent 100%),
        radial-gradient(1px 1px at 88% 78%, #aff 0%, transparent 100%),
        radial-gradient(1px 1px at 45% 92%, #fff 0%, transparent 100%);
    }

    /* moving nebula blobs */
    #stars::before {
      content: '';
      position: absolute; inset: 0;
      background:
        radial-gradient(ellipse 60% 40% at 20% 30%, rgba(176,0,255,.08) 0%, transparent 70%),
        radial-gradient(ellipse 50% 30% at 75% 65%, rgba(255,45,120,.07) 0%, transparent 70%),
        radial-gradient(ellipse 40% 60% at 55% 10%, rgba(0,229,255,.06) 0%, transparent 70%);
      animation: nebula 18s ease-in-out infinite alternate;
    }

    @keyframes nebula {
      0%   { opacity: .6; transform: scale(1)   rotate(0deg);   }
      100% { opacity: 1;  transform: scale(1.06) rotate(3deg);  }
    }

    /* ── Layout ──────────────────────────────────────────────────────── */
    #app {
      position: relative; z-index: 1;
      max-width: 1400px;
      margin: 0 auto;
      padding: 0 20px 60px;
    }

    /* ── Header ──────────────────────────────────────────────────────── */
    header {
      text-align: center;
      padding: 40px 0 30px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 28px;
    }

    .logo {
      font-family: 'Orbitron', sans-serif;
      font-size: clamp(1.8rem, 5vw, 3.2rem);
      font-weight: 900;
      letter-spacing: .12em;
      background: linear-gradient(90deg, var(--pink), var(--cyan), var(--purple), var(--pink));
      background-size: 300% 100%;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      animation: shimmer 4s linear infinite;
    }

    @keyframes shimmer {
      0%   { background-position: 0%   50%; }
      100% { background-position: 300% 50%; }
    }

    .tagline {
      margin-top: 8px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .85rem;
      color: var(--dim);
      letter-spacing: .15em;
    }

    /* ── Status bar ──────────────────────────────────────────────────── */
    #status-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 20px;
      margin-bottom: 24px;
      backdrop-filter: blur(8px);
    }

    .status-pill {
      display: flex; align-items: center; gap: 8px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .78rem;
      color: var(--dim);
    }

    .dot {
      width: 9px; height: 9px; border-radius: 50%;
      background: var(--dim);
      transition: background .3s, box-shadow .3s;
    }
    .dot.ok    { background: var(--green);  box-shadow: 0 0 8px var(--green); }
    .dot.error { background: var(--pink);   box-shadow: 0 0 8px var(--pink);  }

    #refresh-countdown {
      font-family: 'Share Tech Mono', monospace;
      font-size: .78rem;
      color: var(--cyan);
    }

    #total-badge {
      font-family: 'Share Tech Mono', monospace;
      font-size: .78rem;
      color: var(--purple);
    }

    /* ── Controls ────────────────────────────────────────────────────── */
    #controls {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }

    .tab-group {
      display: flex;
      gap: 4px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 4px;
    }

    .tab {
      font-family: 'Orbitron', sans-serif;
      font-size: .7rem;
      font-weight: 700;
      letter-spacing: .1em;
      padding: 7px 18px;
      border-radius: 6px;
      border: none;
      background: transparent;
      color: var(--dim);
      cursor: pointer;
      transition: all .2s;
    }

    .tab:hover { color: var(--text); }

    .tab.active-all    { background: rgba(176,0,255,.25);  color: var(--purple); box-shadow: var(--glow-purp); }
    .tab.active-reddit { background: rgba(255,45,120,.25); color: var(--pink);   box-shadow: var(--glow-pink); }
    .tab.active-google { background: rgba(0,229,255,.25);  color: var(--cyan);   box-shadow: var(--glow-cyan); }

    .top-n-group {
      display: flex; align-items: center; gap: 8px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .78rem; color: var(--dim);
    }

    .top-n-group select {
      background: var(--panel);
      border: 1px solid var(--border);
      color: var(--cyan);
      border-radius: 6px;
      padding: 6px 10px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .78rem;
      outline: none;
      cursor: pointer;
    }

    .btn-refresh {
      margin-left: auto;
      font-family: 'Orbitron', sans-serif;
      font-size: .68rem;
      font-weight: 700;
      letter-spacing: .1em;
      padding: 8px 20px;
      border-radius: 8px;
      border: 1px solid var(--cyan);
      background: rgba(0,229,255,.08);
      color: var(--cyan);
      cursor: pointer;
      transition: all .2s;
    }

    .btn-refresh:hover {
      background: rgba(0,229,255,.2);
      box-shadow: var(--glow-cyan);
    }

    /* ── Grid ────────────────────────────────────────────────────────── */
    #grid {
      display: grid;
      grid-template-columns: 1fr 340px;
      gap: 24px;
      align-items: start;
    }

    @media (max-width: 900px) {
      #grid { grid-template-columns: 1fr; }
    }

    /* ── Panel card ──────────────────────────────────────────────────── */
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
      backdrop-filter: blur(10px);
    }

    .card-title {
      font-family: 'Orbitron', sans-serif;
      font-size: .8rem;
      font-weight: 700;
      letter-spacing: .14em;
      margin-bottom: 18px;
      display: flex; align-items: center; gap: 10px;
    }

    .card-title .icon { font-size: 1.1rem; }

    /* ── Trend list (main column) ────────────────────────────────────── */
    #trend-list { display: flex; flex-direction: column; gap: 10px; }

    .trend-item {
      display: grid;
      grid-template-columns: 36px 1fr auto;
      gap: 14px;
      align-items: center;
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.05);
      border-radius: 10px;
      padding: 14px 16px;
      transition: border-color .2s, background .2s;
      cursor: default;
      animation: fadeSlide .3s ease both;
    }

    @keyframes fadeSlide {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0);   }
    }

    .trend-item:hover {
      border-color: rgba(176,0,255,.35);
      background: rgba(176,0,255,.06);
    }

    .rank {
      font-family: 'Orbitron', sans-serif;
      font-size: .9rem;
      font-weight: 900;
      text-align: center;
      color: var(--dim);
    }

    .rank.r1 { color: var(--gold);   text-shadow: 0 0 12px var(--gold); }
    .rank.r2 { color: #c0c0c0;      text-shadow: 0 0 10px #c0c0c0; }
    .rank.r3 { color: #cd7f32;      text-shadow: 0 0 10px #cd7f3266; }

    .trend-body { overflow: hidden; }

    .trend-title {
      font-size: .92rem;
      font-weight: 600;
      color: #dde6ff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 5px;
    }

    .trend-meta {
      display: flex; gap: 10px; flex-wrap: wrap;
      font-family: 'Share Tech Mono', monospace;
      font-size: .68rem; color: var(--dim);
    }

    .source-badge {
      padding: 2px 8px;
      border-radius: 20px;
      font-size: .65rem;
      font-weight: 700;
      letter-spacing: .06em;
      text-transform: uppercase;
    }

    .src-reddit { background: rgba(255,45,120,.18); color: var(--pink);   border: 1px solid rgba(255,45,120,.35); }
    .src-google { background: rgba(0,229,255,.15);  color: var(--cyan);   border: 1px solid rgba(0,229,255,.3);  }
    .src-other  { background: rgba(176,0,255,.15);  color: var(--purple); border: 1px solid rgba(176,0,255,.3);  }

    .trend-score-block { text-align: right; min-width: 70px; }

    .score-val {
      font-family: 'Orbitron', sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
    }

    .score-label {
      font-family: 'Share Tech Mono', monospace;
      font-size: .62rem;
      color: var(--dim);
      margin-top: 2px;
    }

    .score-bar-wrap {
      height: 3px;
      background: rgba(255,255,255,.08);
      border-radius: 2px;
      margin-top: 6px;
      overflow: hidden;
    }

    .score-bar {
      height: 100%;
      border-radius: 2px;
      transition: width .8s cubic-bezier(.4,0,.2,1);
    }

    /* ── Top panel (right column) ────────────────────────────────────── */
    #top-list { display: flex; flex-direction: column; gap: 8px; }

    .top-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.05);
      transition: background .2s;
      animation: fadeSlide .3s ease both;
    }

    .top-item:hover { background: rgba(255,45,120,.06); }

    .top-rank {
      font-family: 'Orbitron', sans-serif;
      font-weight: 900;
      font-size: .75rem;
      color: var(--dim);
      width: 22px;
      text-align: center;
      flex-shrink: 0;
    }

    .top-rank.t1 { color: var(--gold); }
    .top-rank.t2 { color: #c0c0c0; }
    .top-rank.t3 { color: #cd7f32; }

    .top-title {
      font-size: .8rem;
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--text);
    }

    .top-score {
      font-family: 'Share Tech Mono', monospace;
      font-size: .72rem;
      color: var(--pink);
      flex-shrink: 0;
    }

    /* ── Stats panel ─────────────────────────────────────────────────── */
    #stats-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 20px;
    }

    .stat-box {
      background: rgba(255,255,255,.03);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      text-align: center;
    }

    .stat-val {
      font-family: 'Orbitron', sans-serif;
      font-size: 1.4rem;
      font-weight: 700;
    }

    .stat-label {
      font-family: 'Share Tech Mono', monospace;
      font-size: .65rem;
      color: var(--dim);
      margin-top: 3px;
      letter-spacing: .08em;
    }

    /* ── Source breakdown ────────────────────────────────────────────── */
    .breakdown-row {
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 10px;
    }

    .bd-label {
      font-family: 'Share Tech Mono', monospace;
      font-size: .72rem;
      width: 56px;
      flex-shrink: 0;
    }

    .bd-bar-wrap {
      flex: 1; height: 6px;
      background: rgba(255,255,255,.07);
      border-radius: 3px; overflow: hidden;
    }

    .bd-bar {
      height: 100%; border-radius: 3px;
      transition: width 1s cubic-bezier(.4,0,.2,1);
    }

    .bd-count {
      font-family: 'Share Tech Mono', monospace;
      font-size: .68rem;
      color: var(--dim);
      width: 30px;
      text-align: right;
      flex-shrink: 0;
    }

    /* ── Loading / empty ─────────────────────────────────────────────── */
    .placeholder {
      text-align: center;
      padding: 40px 20px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .82rem;
      color: var(--dim);
    }

    .spinner {
      display: inline-block;
      width: 28px; height: 28px;
      border: 2px solid rgba(176,0,255,.2);
      border-top-color: var(--purple);
      border-radius: 50%;
      animation: spin .8s linear infinite;
      margin-bottom: 12px;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Footer ──────────────────────────────────────────────────────── */
    footer {
      text-align: center;
      padding-top: 40px;
      font-family: 'Share Tech Mono', monospace;
      font-size: .7rem;
      color: var(--dim);
      letter-spacing: .1em;
    }

    footer a { color: var(--purple); text-decoration: none; }
    footer a:hover { color: var(--pink); }

    /* ── Scrollbar ───────────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--purple); }
  </style>
</head>

<body>
<div id="stars"></div>

<div id="app">

  <!-- Header -->
  <header>
    <div class="logo">✦ TREND SCRAPER ✦</div>
    <div class="tagline">REAL-TIME VIRAL INTELLIGENCE DASHBOARD</div>
  </header>

  <!-- Status bar -->
  <div id="status-bar">
    <div class="status-pill">
      <div class="dot" id="db-dot"></div>
      <span id="db-status">CHECKING…</span>
    </div>
    <div id="total-badge">— TRENDS IN DB</div>
    <div id="refresh-countdown">REFRESH IN —</div>
    <span style="font-family:'Share Tech Mono',monospace;font-size:.7rem;color:var(--dim)" id="last-updated"></span>
  </div>

  <!-- Controls -->
  <div id="controls">
    <div class="tab-group">
      <button class="tab active-all" data-src="all"    onclick="setSource('all')">✦ ALL</button>
      <button class="tab"            data-src="reddit" onclick="setSource('reddit')">▲ REDDIT</button>
      <button class="tab"            data-src="google" onclick="setSource('google')">◉ GOOGLE</button>
    </div>

    <div class="top-n-group">
      SHOW
      <select id="page-size" onchange="refresh()">
        <option value="20">20</option>
        <option value="50" selected>50</option>
        <option value="100">100</option>
      </select>
      TRENDS
    </div>

    <button class="btn-refresh" onclick="refresh()">⟳ REFRESH NOW</button>
  </div>

  <!-- Main grid -->
  <div id="grid">

    <!-- Left: main trend list -->
    <div>
      <div class="card">
        <div class="card-title">
          <span class="icon">📡</span>
          <span style="color:var(--cyan)">LIVE TRENDS</span>
        </div>
        <div id="trend-list">
          <div class="placeholder"><div class="spinner"></div><br>SCANNING THE INTERNET…</div>
        </div>
      </div>
    </div>

    <!-- Right: sidebar -->
    <div style="display:flex;flex-direction:column;gap:20px">

      <!-- Stats -->
      <div class="card">
        <div class="card-title">
          <span class="icon">⚡</span>
          <span style="color:var(--pink)">STATS</span>
        </div>
        <div id="stats-grid">
          <div class="stat-box">
            <div class="stat-val" id="stat-total" style="color:var(--cyan)">—</div>
            <div class="stat-label">TOTAL TRENDS</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" id="stat-top-score" style="color:var(--pink)">—</div>
            <div class="stat-label">TOP SCORE</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" id="stat-reddit" style="color:var(--pink)">—</div>
            <div class="stat-label">REDDIT</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" id="stat-google" style="color:var(--cyan)">—</div>
            <div class="stat-label">GOOGLE</div>
          </div>
        </div>

        <!-- Source bars -->
        <div id="breakdown"></div>
      </div>

      <!-- Top 10 -->
      <div class="card">
        <div class="card-title">
          <span class="icon">🏆</span>
          <span style="color:var(--gold)">TOP 10 RIGHT NOW</span>
        </div>
        <div id="top-list">
          <div class="placeholder"><div class="spinner"></div></div>
        </div>
      </div>

    </div>
  </div>

  <footer>
    <p>TREND SCRAPER &nbsp;|&nbsp; <a href="/docs">API DOCS</a> &nbsp;|&nbsp; DATA REFRESHES EVERY 15 MINUTES</p>
  </footer>

</div>

<script>
  // ── State ──────────────────────────────────────────────────────────────────
  let currentSource = 'all';
  let countdownVal  = 60;
  let countdownTimer;

  // ── Source tabs ────────────────────────────────────────────────────────────
  function setSource(src) {
    currentSource = src;
    document.querySelectorAll('.tab').forEach(t => {
      t.className = 'tab';
      if (t.dataset.src === src) t.classList.add('active-' + src);
    });
    refresh();
  }

  // ── Score colour helper ────────────────────────────────────────────────────
  function scoreColor(score) {
    if (score === null || score === undefined) return '#556080';
    if (score >= 70) return '#ff2d78';
    if (score >= 40) return '#b000ff';
    if (score >= 15) return '#00e5ff';
    return '#00ff88';
  }

  function scoreBarColor(score) {
    if (score === null || score === undefined) return 'rgba(255,255,255,.1)';
    if (score >= 70) return 'linear-gradient(90deg,#ff2d78,#ff7eb3)';
    if (score >= 40) return 'linear-gradient(90deg,#b000ff,#d066ff)';
    if (score >= 15) return 'linear-gradient(90deg,#00e5ff,#66f0ff)';
    return 'linear-gradient(90deg,#00ff88,#66ffb8)';
  }

  function fmtScore(score) {
    if (score === null || score === undefined) return '—';
    return score.toFixed(1);
  }

  function fmtNum(n) {
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000)    return (n/1000).toFixed(1) + 'K';
    return String(n);
  }

  function timeAgo(isoStr) {
    const diff = (Date.now() - new Date(isoStr)) / 1000;
    if (diff < 60)   return Math.floor(diff) + 's ago';
    if (diff < 3600) return Math.floor(diff/60) + 'm ago';
    return Math.floor(diff/3600) + 'h ago';
  }

  function sourceBadge(src) {
    const cls = src === 'reddit' ? 'src-reddit' : src === 'google' ? 'src-google' : 'src-other';
    const icon = src === 'reddit' ? '▲' : src === 'google' ? '◉' : '✦';
    return `<span class="source-badge ${cls}">${icon} ${src.toUpperCase()}</span>`;
  }

  // ── Render main list ───────────────────────────────────────────────────────
  function renderTrends(items, maxScore) {
    const el = document.getElementById('trend-list');
    if (!items.length) {
      el.innerHTML = '<div class="placeholder">NO TRENDS YET — RUN THE SCHEDULER</div>';
      return;
    }

    el.innerHTML = items.map((item, i) => {
      const rankNum = i + 1;
      const rankClass = rankNum === 1 ? 'r1' : rankNum === 2 ? 'r2' : rankNum === 3 ? 'r3' : '';
      const scoreRaw = item.latest_score;
      const barPct   = maxScore > 0 && scoreRaw !== null ? Math.min((scoreRaw / maxScore) * 100, 100) : 0;
      const color    = scoreColor(scoreRaw);

      return `
        <div class="trend-item" style="animation-delay:${i * 0.03}s">
          <div class="rank ${rankClass}">${rankNum}</div>
          <div class="trend-body">
            <div class="trend-title" title="${escHtml(item.title)}">${escHtml(item.title)}</div>
            <div class="trend-meta">
              ${sourceBadge(item.source)}
              <span>${timeAgo(item.ingested_at)}</span>
              <span>RAW: ${fmtNum(item.raw_score)}</span>
            </div>
            <div class="score-bar-wrap">
              <div class="score-bar" style="width:${barPct}%;background:${scoreBarColor(scoreRaw)}"></div>
            </div>
          </div>
          <div class="trend-score-block">
            <div class="score-val" style="color:${color}">${fmtScore(scoreRaw)}</div>
            <div class="score-label">SCORE</div>
          </div>
        </div>`;
    }).join('');
  }

  // ── Render top-10 sidebar ─────────────────────────────────────────────────
  function renderTop(items) {
    const el = document.getElementById('top-list');
    if (!items.length) {
      el.innerHTML = '<div class="placeholder" style="padding:20px">NO DATA YET</div>';
      return;
    }
    el.innerHTML = items.slice(0,10).map((item, i) => {
      const rankNum = i + 1;
      const cls = rankNum === 1 ? 't1' : rankNum === 2 ? 't2' : rankNum === 3 ? 't3' : '';
      return `
        <div class="top-item" style="animation-delay:${i * 0.04}s">
          <div class="top-rank ${cls}">${rankNum}</div>
          <div class="top-title" title="${escHtml(item.title)}">${escHtml(item.title)}</div>
          <div class="top-score">${fmtScore(item.latest_score)}</div>
        </div>`;
    }).join('');
  }

  // ── Render stats ───────────────────────────────────────────────────────────
  function renderStats(allItems, topItems) {
    const reddit = allItems.filter(i => i.source === 'reddit').length;
    const google = allItems.filter(i => i.source === 'google').length;
    const topScore = topItems[0]?.latest_score ?? null;
    const total = allItems.length;

    document.getElementById('stat-total').textContent   = fmtNum(total);
    document.getElementById('stat-top-score').textContent = fmtScore(topScore);
    document.getElementById('stat-reddit').textContent  = fmtNum(reddit);
    document.getElementById('stat-google').textContent  = fmtNum(google);
    document.getElementById('total-badge').textContent  = `${fmtNum(total)} TRENDS IN DB`;

    const bd = document.getElementById('breakdown');
    if (!total) { bd.innerHTML = ''; return; }

    const sources = [
      { label: 'REDDIT', count: reddit, color: 'var(--pink)' },
      { label: 'GOOGLE', count: google, color: 'var(--cyan)' },
    ];

    bd.innerHTML = sources.map(s => {
      const pct = total > 0 ? Math.round((s.count / total) * 100) : 0;
      return `
        <div class="breakdown-row">
          <span class="bd-label" style="color:${s.color}">${s.label}</span>
          <div class="bd-bar-wrap">
            <div class="bd-bar" style="width:${pct}%;background:${s.color}"></div>
          </div>
          <span class="bd-count">${s.count}</span>
        </div>`;
    }).join('');
  }

  // ── Health check ───────────────────────────────────────────────────────────
  async function checkHealth() {
    try {
      const r = await fetch('/health');
      const d = await r.json();
      const dot = document.getElementById('db-dot');
      const lbl = document.getElementById('db-status');
      if (d.database) {
        dot.className = 'dot ok';
        lbl.textContent = 'DB ONLINE';
        lbl.style.color = 'var(--green)';
      } else {
        dot.className = 'dot error';
        lbl.textContent = 'DB OFFLINE';
        lbl.style.color = 'var(--pink)';
      }
    } catch {
      document.getElementById('db-dot').className = 'dot error';
      document.getElementById('db-status').textContent = 'API OFFLINE';
    }
  }

  // ── Main fetch + render ────────────────────────────────────────────────────
  async function refresh() {
    resetCountdown();

    const pageSize = document.getElementById('page-size').value;
    const srcParam = currentSource === 'all' ? '' : `&source=${currentSource}`;

    try {
      const [trendsResp, topResp] = await Promise.all([
        fetch(`/trends?page=1&page_size=${pageSize}${srcParam}`),
        fetch(`/trends/top?n=10${srcParam}`),
      ]);

      const trendsData = await trendsResp.json();
      const topData    = await topResp.json();

      const items    = trendsData.items || [];
      const topItems = Array.isArray(topData) ? topData : [];
      const maxScore = Math.max(...items.map(i => i.latest_score ?? 0), 1);

      renderTrends(items, maxScore);
      renderTop(topItems);
      renderStats(items, topItems);

      const now = new Date();
      document.getElementById('last-updated').textContent =
        `UPDATED ${now.toLocaleTimeString()}`;

    } catch (err) {
      document.getElementById('trend-list').innerHTML =
        `<div class="placeholder">⚠ COULD NOT REACH API<br><small>${err.message}</small></div>`;
    }

    await checkHealth();
  }

  // ── Countdown ─────────────────────────────────────────────────────────────
  function resetCountdown() {
    clearInterval(countdownTimer);
    countdownVal = 60;
    countdownTimer = setInterval(() => {
      countdownVal--;
      document.getElementById('refresh-countdown').textContent =
        `REFRESH IN ${countdownVal}s`;
      if (countdownVal <= 0) refresh();
    }, 1000);
  }

  // ── Util ───────────────────────────────────────────────────────────────────
  function escHtml(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Boot ───────────────────────────────────────────────────────────────────
  refresh();
</script>
</body>
</html>"""


@dashboard_router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    """Serve the interactive trend dashboard."""
    return _HTML
