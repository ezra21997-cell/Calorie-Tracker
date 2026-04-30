/* global React, SourceBadge, TrendRow, TopRow, fmtScore, fmtNum */

// ── Card shell ──────────────────────────────────────────────────────────────
function Card({ titleIcon, titleText, titleColor, children }) {
  return (
    <div className="ts-card">
      <div className="ts-card-title">
        <span className="ts-card-icon">{titleIcon}</span>
        <span style={{ color: titleColor }}>{titleText}</span>
      </div>
      {children}
    </div>
  );
}

// ── Stat box ────────────────────────────────────────────────────────────────
function StatBox({ val, label, color }) {
  return (
    <div className="ts-stat-box">
      <div className="ts-stat-val" style={{ color }}>{val}</div>
      <div className="ts-stat-label">{label}</div>
    </div>
  );
}

// ── Source-breakdown bar ────────────────────────────────────────────────────
function BreakdownRow({ label, count, total, color }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="ts-breakdown-row">
      <span className="ts-bd-label" style={{ color }}>{label}</span>
      <div className="ts-bd-bar-wrap">
        <div className="ts-bd-bar" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="ts-bd-count">{count}</span>
    </div>
  );
}

// ── Stats card (full) ───────────────────────────────────────────────────────
function StatsCard({ items, topScore }) {
  const reddit = items.filter(i => i.source === 'reddit').length;
  const google = items.filter(i => i.source === 'google').length;
  const total = items.length;
  return (
    <Card titleIcon="⚡" titleText="STATS" titleColor="var(--pink)">
      <div className="ts-stats-grid">
        <StatBox val={fmtNum(total)}       label="TOTAL TRENDS" color="var(--cyan)" />
        <StatBox val={fmtScore(topScore)}  label="TOP SCORE"    color="var(--pink)" />
        <StatBox val={fmtNum(reddit)}      label="REDDIT"       color="var(--pink)" />
        <StatBox val={fmtNum(google)}      label="GOOGLE"       color="var(--cyan)" />
      </div>
      <div className="ts-breakdown">
        <BreakdownRow label="REDDIT" count={reddit} total={total} color="var(--pink)" />
        <BreakdownRow label="GOOGLE" count={google} total={total} color="var(--cyan)" />
      </div>
    </Card>
  );
}

// ── Top-10 card ─────────────────────────────────────────────────────────────
function TopCard({ items }) {
  return (
    <Card titleIcon="🏆" titleText="TOP 10 RIGHT NOW" titleColor="var(--gold)">
      <div className="ts-top-list">
        {items.length === 0
          ? <div className="ts-placeholder">NO DATA YET</div>
          : items.slice(0, 10).map((it, i) => (
              <TopRow key={it.id} item={it} rank={i+1} delay={i * 0.04} />
            ))
        }
      </div>
    </Card>
  );
}

// ── Live trends card ────────────────────────────────────────────────────────
function LiveTrendsCard({ items }) {
  const maxScore = Math.max(...items.map(i => i.latest_score ?? 0), 1);
  return (
    <Card titleIcon="📡" titleText="LIVE TRENDS" titleColor="var(--cyan)">
      <div className="ts-trend-list">
        {items.length === 0
          ? <div className="ts-placeholder"><div className="ts-spinner"/><br/>SCANNING THE INTERNET…</div>
          : items.map((it, i) => (
              <TrendRow key={it.id} item={it} rank={i+1} maxScore={maxScore} delay={i * 0.03} />
            ))
        }
      </div>
    </Card>
  );
}

Object.assign(window, { Card, StatBox, BreakdownRow, StatsCard, TopCard, LiveTrendsCard });
