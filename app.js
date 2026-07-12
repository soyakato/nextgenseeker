/*
 * NextGenSeeker — UIレンダリング（客観ファクター専用）
 * v4.1: 主観フレーム（旧NVIDIA-DNAレンズ）を完全削除。採点は客観9ファクターのみ。
 */

const state = {
  foresightWeights: { ...FORESIGHT_DEFAULT_WEIGHTS },
  selected: null,
};

let LIVE_UNIVERSE = [];   // 客観ユニバース（liveの全銘柄、固定リストなし）
let LAST_RANKED = [];     // 現在のランキング順（詳細パネルの前後ナビ用）

function fPillars(c) { return c.foresight || null; }

function compositeOf(c) {
  const p = fPillars(c);
  return p ? foresightCompositeFrom(p, state.foresightWeights) : 0;
}

function activeUniverse() {
  return LIVE_UNIVERSE.length ? LIVE_UNIVERSE : [];
}

function rankActive(list) {
  const w = state.foresightWeights;
  return list
    .map((c) => ({ c, p: fPillars(c) }))
    .filter((x) => x.p)
    .map(({ c, p }) => ({ ...c, composite: foresightCompositeFrom(p, w) }))
    .sort((a, b) => b.composite - a.composite);
}

function lookupCompany(ticker) {
  return LIVE_UNIVERSE.find((x) => x.ticker === ticker) || null;
}

// ── 外部チャートリンク（Yahoo Finance / TradingView） ──
function extLinks(ticker) {
  const y = encodeURIComponent(ticker);
  const tv = encodeURIComponent(ticker.replace(/\..*$/, ''));
  return `
    <div class="ext-links">
      <a href="https://finance.yahoo.com/quote/${y}" target="_blank" rel="noopener">Yahoo Finance ↗</a>
      <a href="https://www.tradingview.com/symbols/${tv}/" target="_blank" rel="noopener">TradingView ↗</a>
    </div>`;
}

// ── Framework legend ──────────────────────
function renderFramework() {
  const el = document.getElementById('framework');
  el.innerHTML = FORESIGHT_PILLARS.map((p) => `
    <div class="pillar-card" style="--pc:${p.color}">
      <div class="pk">${p.short}</div>
      <div class="pl">${p.label}</div>
      <div class="pd">${p.desc}</div>
    </div>`).join('');
  el.classList.add('six');
}

// ── Weight sliders ───────────────────────
function renderControls() {
  const el = document.getElementById('weight-group');
  const wobj = state.foresightWeights;
  el.innerHTML = FORESIGHT_PILLARS.map((p) => `
    <div class="slider-block">
      <label>${p.label} <span class="val" id="wv-${p.key}">${wobj[p.key]}</span></label>
      <input type="range" min="0" max="40" value="${wobj[p.key]}" data-key="${p.key}" class="w-slider">
    </div>`).join('');

  el.querySelectorAll('.w-slider').forEach((sl) => {
    sl.addEventListener('input', (e) => {
      const k = e.target.dataset.key;
      wobj[k] = +e.target.value;
      document.getElementById(`wv-${k}`).textContent = e.target.value;
      rerender();
    });
  });
}

// ── Presets ──────────────────────────────
const FORESIGHT_PRESETS = {
  balanced:  { label: '均衡（学術頑健）', weights: { ...FORESIGHT_DEFAULT_WEIGHTS } },
  leverage:  { label: '営業レバレッジ重視', weights: { operating_leverage: 30, cost_stickiness: 15, survival_dd: 10, rnd_intensity: 8, contrarian_inflection: 8, capital_momentum: 8, holding_trend: 7, earnings_drift: 8, value_yield: 6 } },
  survival:  { label: '生存力（低倒産）', weights: { operating_leverage: 9, cost_stickiness: 5, survival_dd: 32, rnd_intensity: 9, contrarian_inflection: 8, capital_momentum: 11, holding_trend: 10, earnings_drift: 8, value_yield: 8 } },
  rnd:       { label: 'R&D強度重視', weights: { operating_leverage: 9, cost_stickiness: 5, survival_dd: 12, rnd_intensity: 32, contrarian_inflection: 9, capital_momentum: 10, holding_trend: 8, earnings_drift: 9, value_yield: 6 } },
  contrarian:{ label: '逆張り変曲', weights: { operating_leverage: 12, cost_stickiness: 7, survival_dd: 12, rnd_intensity: 7, contrarian_inflection: 30, capital_momentum: 8, holding_trend: 8, earnings_drift: 8, value_yield: 8 } },
  holders:   { label: '機関・保有期間重視', weights: { operating_leverage: 8, cost_stickiness: 5, survival_dd: 11, rnd_intensity: 6, contrarian_inflection: 8, capital_momentum: 23, holding_trend: 23, earnings_drift: 9, value_yield: 7 } },
  pead:      { label: '決算ドリフト重視', weights: { operating_leverage: 11, cost_stickiness: 5, survival_dd: 12, rnd_intensity: 7, contrarian_inflection: 9, capital_momentum: 9, holding_trend: 7, earnings_drift: 32, value_yield: 8 } },
  value:     { label: 'バリュー（FCF利回り）', weights: { operating_leverage: 9, cost_stickiness: 5, survival_dd: 16, rnd_intensity: 5, contrarian_inflection: 12, capital_momentum: 7, holding_trend: 7, earnings_drift: 7, value_yield: 32 } },
};
let activePreset = 'balanced';

function renderPresets() {
  const el = document.getElementById('presets');
  el.innerHTML = Object.entries(FORESIGHT_PRESETS).map(([k, p]) =>
    `<button class="btn preset ${k === activePreset ? 'active' : ''}" data-preset="${k}">${p.label}</button>`).join('');
  el.querySelectorAll('.preset').forEach((b) => {
    b.addEventListener('click', () => {
      activePreset = b.dataset.preset;
      state.foresightWeights = { ...FORESIGHT_PRESETS[activePreset].weights };
      renderControls();
      renderPresets();
      rerender();
    });
  });
}

function detectPreset() {
  for (const [k, p] of Object.entries(FORESIGHT_PRESETS)) {
    if (Object.keys(p.weights).every((key) => p.weights[key] === state.foresightWeights[key])) return k;
  }
  return null;
}

// ── Ranking table ────────────────────────
function renderRanking() {
  const ranked = rankActive(activeUniverse());
  LAST_RANKED = ranked.map((c) => c.ticker);

  const rows = ranked.map((c, i) => {
    const g = grade(c.composite);
    const col = scoreColor(c.composite);
    const sel = state.selected === c.ticker ? 'selected' : '';
    const dd = c.foresight ? c.foresight.survival_dd : null;
    return `
      <tr class="company-row ${sel}" data-ticker="${c.ticker}">
        <td class="rk ${i < 3 ? 'top' : ''}">${String(i + 1).padStart(2, '0')}</td>
        <td>
          <div class="tk">${c.ticker.replace(/\..*/, '')}</div>
          <div class="nm">${c.name}</div>
        </td>
        <td class="nm">${c.layer}</td>
        <td><span class="grade-badge" style="background:${col}22;color:${col};border:1px solid ${col}55">${g}</span></td>
        <td class="num">
          <div class="score-bar-wrap">
            <div class="mini-bar"><i style="width:${c.composite}%;background:${col}"></i></div>
            <span class="score-num" style="color:${col}">${c.composite.toFixed(1)}</span>
          </div>
        </td>
        <td class="num">${dd == null ? '<span class="risk-chip">—</span>'
          : `<span class="risk-chip" style="color:${scoreColor(dd)}" title="距離デフォルト(客観)">${Math.round(dd)}</span>`}</td>
      </tr>`;
  }).join('');

  document.getElementById('rank-body').innerHTML = rows
    || '<tr><td colspan="6" class="nm" style="padding:16px">ライブデータ読み込み中…</td></tr>';

  document.querySelectorAll('.company-row').forEach((r) => {
    r.addEventListener('click', () => selectCompany(r.dataset.ticker, true));
  });
}

// ── Radar chart (SVG) ────────────────────
function radarSVG(company, size = 240) {
  const cs = fPillars(company) || {};
  const cx = size / 2, cy = size / 2 + 6, R = size * 0.32;
  const keys = FORESIGHT_PILLARS.map((p) => p.key);
  const n = keys.length;
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2;

  let rings = '';
  for (let g = 1; g <= 4; g++) {
    const rr = (R * g) / 4;
    const pts = keys.map((_, i) => `${cx + rr * Math.cos(angle(i))},${cy + rr * Math.sin(angle(i))}`).join(' ');
    rings += `<polygon points="${pts}" fill="none" stroke="var(--border)" stroke-width="1"/>`;
  }
  let spokes = '', labels = '';
  keys.forEach((k, i) => {
    const x = cx + R * Math.cos(angle(i)), y = cy + R * Math.sin(angle(i));
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
    const lx = cx + (R + 18) * Math.cos(angle(i)), ly = cy + (R + 18) * Math.sin(angle(i));
    const anchor = Math.abs(Math.cos(angle(i))) < 0.3 ? 'middle' : (Math.cos(angle(i)) > 0 ? 'start' : 'end');
    labels += `<text x="${lx}" y="${ly + 3}" text-anchor="${anchor}" class="quad-label">${FORESIGHT_PILLARS[i].short}</text>`;
  });

  const poly = keys.map((k, i) => {
    const v = (cs[k] || 0) / 100;
    return `${cx + R * v * Math.cos(angle(i))},${cy + R * v * Math.sin(angle(i))}`;
  }).join(' ');

  return `
  <svg viewBox="0 0 ${size} ${size + 20}" class="radar" width="${size}" height="${size + 20}">
    ${rings}${spokes}
    <polygon points="${poly}" fill="rgba(11,92,255,0.10)" stroke="var(--accent)" stroke-width="2"/>
    ${keys.map((k, i) => {
      const v = (cs[k] || 0) / 100;
      return `<circle cx="${cx + R * v * Math.cos(angle(i))}" cy="${cy + R * v * Math.sin(angle(i))}" r="2.5" fill="var(--accent)"/>`;
    }).join('')}
    ${labels}
  </svg>`;
}

// ── Bottom tabs（モバイル・アプリシェル） ──
let ACTIVE_TAB = 'today';
const isTabMode = () => window.innerWidth <= 1080;

function applyTabs() {
  const mobile = isTabMode();
  document.querySelectorAll('[data-tab]').forEach((el) => {
    el.classList.toggle('tab-hidden', mobile && el.dataset.tab !== ACTIVE_TAB);
  });
  document.querySelectorAll('.tab-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.tabgo === ACTIVE_TAB);
  });
}

function setTab(tab) {
  ACTIVE_TAB = tab;
  closeDetailSheet();
  applyTabs();
  window.scrollTo(0, 0);
}

// 前後ナビ共通化（ボタン＋スワイプの両方から使う）
function navDetail(dir) {
  const i = LAST_RANKED.indexOf(state.selected);
  if (i < 0) return;
  const t = LAST_RANKED[i + dir];
  if (t) selectCompany(t, false);
}

// ── Detail sheet（モバイルのマスター・ディテール） ──
function openDetailSheet() {
  const p = document.querySelector('.detail-panel');
  const b = document.getElementById('sheet-backdrop');
  if (p) { p.classList.add('open'); p.scrollTop = 0; }
  if (b) b.classList.add('on');
  document.body.classList.add('sheet-open');
}
function closeDetailSheet() {
  const p = document.querySelector('.detail-panel');
  const b = document.getElementById('sheet-backdrop');
  if (p) p.classList.remove('open');
  if (b) b.classList.remove('on');
  document.body.classList.remove('sheet-open');
}

// ── Detail panel ─────────────────────────
function selectCompany(ticker, userAction) {
  state.selected = ticker;
  renderRanking();
  renderDetail();
  renderQuadrant();
  // モバイル: ページをスクロールさせず、詳細をボトムシートとして重ねる
  if (userAction && window.innerWidth <= 1080) openDetailSheet();
  const p = document.querySelector('.detail-panel.open');
  if (p) p.scrollTop = 0;
}

function renderDetail() {
  const el = document.getElementById('detail-body');
  if (!state.selected) {
    el.innerHTML = `<div class="empty-detail"><div class="big">◎</div>ランキングから銘柄を選ぶと、<br>9ファクター・レーダーと内訳を表示します。</div>`;
    return;
  }
  const c = lookupCompany(state.selected);
  if (!c) { el.innerHTML = ''; return; }
  const comp = compositeOf(c);
  const col = scoreColor(comp);
  const f = fPillars(c);

  const rawFmt = (k) => {
    const r = c.foresightRaw ? c.foresightRaw[k] : null;
    return r == null ? '—' : (typeof r === 'number' ? r.toFixed(2) : r);
  };
  const foresightBreakdown = f ? `
    <div class="fbreak">
      <div class="fbreak-head">
        <span class="obj-tag">客観ファクター（実データのみ）</span>
        <span class="fbreak-hint">バー=横断パーセンタイル / 括弧=生の実測値</span>
      </div>
      ${FORESIGHT_PILLARS.map((p) => {
        const v = f[p.key] || 0;
        return `
        <div class="fbreak-row">
          <span class="fbk" title="${p.desc}">${p.label}</span>
          <div class="fbk-bar"><i style="width:${v}%;background:${p.color}"></i></div>
          <span class="fbv" style="color:${p.color}">${Math.round(v)}<em class="fbv-der">(${rawFmt(p.key)})</em></span>
        </div>`;
      }).join('')}
    </div>` : '';

  // 前後ナビ: リストへ戻らずランキング順に銘柄を切替できる
  const navIdx = LAST_RANKED.indexOf(state.selected);
  const prevT = navIdx > 0 ? LAST_RANKED[navIdx - 1] : null;
  const nextT = (navIdx >= 0 && navIdx < LAST_RANKED.length - 1) ? LAST_RANKED[navIdx + 1] : null;
  const navRow = LAST_RANKED.length ? `
    <div class="detail-nav">
      <button class="dnav-btn" id="dnav-prev" ${prevT ? '' : 'disabled'}>‹ ${prevT ? prevT.replace(/\..*/, '') : '前へ'}</button>
      <span class="dnav-pos">${navIdx >= 0 ? `ランキング ${navIdx + 1} / ${LAST_RANKED.length}` : ''}</span>
      <button class="dnav-btn" id="dnav-next" ${nextT ? '' : 'disabled'}>${nextT ? nextT.replace(/\..*/, '') : '次へ'} ›</button>
    </div>` : '';

  el.innerHTML = `
    ${navRow}
    <div class="detail-head">
      <div>
        <div class="dt" style="color:${col}">${c.ticker.replace(/\..*/, '')}</div>
        <div class="dn">${c.name} · ${c.sector}</div>
      </div>
      <div style="text-align:right">
        <div class="grade-badge" style="font-size:18px;padding:4px 12px;background:${col}22;color:${col};border:1px solid ${col}55">${grade(comp)}</div>
        <div style="font-family:var(--mono);font-size:22px;font-weight:800;color:${col};margin-top:4px">${comp.toFixed(1)}</div>
      </div>
    </div>
    ${extLinks(c.ticker)}

    <div class="radar-wrap">${radarSVG(c)}</div>

    ${foresightBreakdown}
    ${ownershipBlock(c)}
    ${liveFinancialBlock(c)}

    <div class="thesis-block down">
      <h4>▼ 集計方法の明示</h4>
      <p>財務諸表・株価から機械算出した9ファクターの横断パーセンタイル（同値タイは平均ランク）。変化系（DOL・コスト硬直性）は年次＋四半期の<b>前年同期比</b>で季節性を排除。R&D未計上は<b>0として採点</b>（Chan et al.慣行）。Merton距離のデフォルトポイントはKMV慣行。生値「—」のみ真の欠損として中立50。</p>
    </div>`;

  const pv = document.getElementById('dnav-prev');
  const nx = document.getElementById('dnav-next');
  if (pv && prevT) pv.addEventListener('click', () => navDetail(-1));
  if (nx && nextT) nx.addEventListener('click', () => navDetail(1));
}

// ── Ownership block（機関保有・保有期間の変遷） ──
function ownershipBlock(c) {
  const o = c.own;
  if (!o) return '';
  const pct = (v, d = 1) => (v == null ? '—' : (v * 100).toFixed(d) + '%');
  const flowCls = o.flow_13f == null ? 'flat' : (o.flow_13f > 0.005 ? 'up' : (o.flow_13f < -0.005 ? 'down' : 'flat'));
  const flowSym = o.flow_13f == null ? '—' : (o.flow_13f > 0 ? '▲ 買い越し ' : (o.flow_13f < 0 ? '▼ 売り越し ' : '→ ')) + pct(o.flow_13f);
  const adCls = o.ad60 == null ? 'flat' : (o.ad60 > 0.05 ? 'up' : (o.ad60 < -0.05 ? 'down' : 'flat'));
  const delta = (typeof ownershipDelta === 'function') ? ownershipDelta(c.ticker) : null;
  const deltaTxt = delta
    ? `保有率 ${delta.dPct >= 0 ? '+' : ''}${delta.dPct.toFixed(2)}pt${delta.dCnt != null ? ` · 機関数 ${delta.dCnt >= 0 ? '+' : ''}${delta.dCnt}` : ''}（${delta.days}日間の自前観測）`
    : '変遷は観測蓄積中（実行ごとに記録）';
  return `
    <div class="own-block">
      <div class="own-head"><span class="own-tag">機関保有・保有期間（参考）</span>
        <span class="fbreak-hint">13F系は四半期＋45日遅延の遅効データ — スコアには不使用。A/D・保有期間のみ日次で採点に使用</span></div>
      <div class="own-grid">
        <div><span>機関保有率</span><b>${pct(o.inst_pct)}</b></div>
        <div><span>機関数</span><b>${o.inst_count != null ? o.inst_count.toLocaleString() : '—'}</b></div>
        <div><span>13F上位フロー<em>${o.flow_date ? ' ' + o.flow_date : ''}</em></span><b class="trend ${flowCls}">${flowSym}</b></div>
        <div><span>A/D蓄積60日<em>（日次代理）</em></span><b class="trend ${adCls}">${o.ad60 == null ? '—' : (o.ad60 > 0 ? '+' : '') + o.ad60}</b></div>
        <div><span>推定保有期間</span><b>${o.hp_days != null ? o.hp_days + '日' : '—'}</b></div>
        <div><span>直近EPSサプライズ<em>${o.surprise && o.surprise.date ? ' ' + o.surprise.date : ''}</em></span><b class="trend ${o.surprise && o.surprise.pct != null ? (o.surprise.pct > 0 ? 'up' : (o.surprise.pct < 0 ? 'down' : 'flat')) : 'flat'}">${o.surprise && o.surprise.pct != null ? (o.surprise.pct > 0 ? '+' : '') + o.surprise.pct + '%' : '—'}</b></div>
        <div><span>次回決算</span><b>${o.surprise && o.surprise.next ? o.surprise.next : '—'}</b></div>
      </div>
      <div class="own-delta">${deltaTxt}</div>
    </div>`;
}

// ── Live financial block ─────────────────
function liveFinancialBlock(c) {
  const d = c.live;
  if (!d || !d.ok) return '';
  const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%');
  const money = (v) => {
    if (v == null) return '—';
    const a = Math.abs(v);
    if (a >= 1e12) return (v / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return (v / 1e6).toFixed(0) + 'M';
    return String(v);
  };
  return `
    <div class="live-fin">
      <div class="live-fin-head">
        <span class="live-tag">LIVE 実財務</span>
        <span class="live-fin-sym">${d.symbol}</span>
      </div>
      <div class="live-fin-grid">
        <div><span>粗利率</span><b>${pct(d.gross_margin)}</b></div>
        <div><span>売上成長</span><b>${pct(d.revenue_growth)}</b></div>
        <div><span>FCF変換</span><b>${pct(d.fcf_conversion)}</b></div>
        <div><span>FCF</span><b>${money(d.fcf)}</b></div>
        <div><span>P/E</span><b>${d.trailing_pe != null ? d.trailing_pe.toFixed(1) : '—'}</b></div>
        <div><span>時価総額</span><b>${money(d.market_cap)}</b></div>
      </div>
    </div>`;
}

// ── Quadrant map ─────────────────────────
function coordsFor(c) {
  const f = fPillars(c) || {};
  return {
    x: (f.operating_leverage || 0),                   // 営業レバレッジ（利益の爆発力）
    y: foresightCompositeFrom(f, state.foresightWeights),
    risk: 100 - (f.survival_dd || 50),                // 距離デフォルトが低い=倒産リスク高
  };
}

function renderQuadrant() {
  const W = 640, H = 420, pad = 46;
  const all = activeUniverse().map((c) => ({ ...c, ...coordsFor(c) }))
    .filter((a) => a.y != null && !isNaN(a.y));
  if (!all.length) { document.getElementById('quadrant').innerHTML = ''; return; }

  const xs = all.map((a) => a.x), ys = all.map((a) => a.y);
  const xMin = Math.min(...xs) - 4, xMax = Math.max(...xs) + 4;
  const yMin = Math.min(...ys) - 4, yMax = Math.max(...ys) + 4;
  const sx = (v) => pad + ((v - xMin) / (xMax - xMin)) * (W - pad * 1.4);
  const sy = (v) => H - pad - ((v - yMin) / (yMax - yMin)) * (H - pad * 1.6);
  const midX = (xMin + xMax) / 2, midY = (yMin + yMax) / 2;

  const dots = all.map((a) => {
    const rColor = scoreColor(100 - a.risk);
    const rad = 6 + (a.y - 50) / 12;
    const sel = state.selected === a.ticker;
    return `
      <g class="quad-dot" data-ticker="${a.ticker}">
        <circle cx="${sx(a.x)}" cy="${sy(a.y)}" r="${Math.max(4, rad)}"
          fill="${rColor}" fill-opacity="${sel ? 0.95 : 0.65}"
          stroke="${sel ? 'var(--accent)' : rColor}" stroke-width="${sel ? 2.5 : 1}"/>
        <text x="${sx(a.x)}" y="${sy(a.y) - Math.max(4, rad) - 3}" text-anchor="middle" class="quad-label"
          style="${sel ? 'fill:var(--accent);font-weight:700' : ''}">${a.ticker.replace(/\..*/, '')}</text>
      </g>`;
  }).join('');

  const svg = `
  <svg viewBox="0 0 ${W} ${H}" class="quad-svg">
    <line x1="${sx(midX)}" y1="${pad - 10}" x2="${sx(midX)}" y2="${H - pad + 6}" stroke="var(--border-bright)" stroke-dasharray="4,4"/>
    <line x1="${pad - 10}" y1="${sy(midY)}" x2="${W - pad + 10}" y2="${sy(midY)}" stroke="var(--border-bright)" stroke-dasharray="4,4"/>
    <text x="${W - pad + 4}" y="${sy(midY) + 20}" text-anchor="end" class="quad-quadrant-label" fill="var(--accent)">◤ 本命：高営業レバレッジ×高客観スコア</text>
    <text x="${pad}" y="${pad - 2}" class="quad-quadrant-label" fill="var(--warn)">守勢：レバレッジ低だがスコア高</text>
    <text x="${pad}" y="${H - pad + 20}" class="quad-quadrant-label" fill="var(--danger)">要警戒：客観スコア低</text>
    <text x="${W / 2}" y="${H - 8}" text-anchor="middle" class="quad-axis-label">→ 営業レバレッジ DOL（利益の爆発力）</text>
    <text x="14" y="${H / 2}" transform="rotate(-90 14 ${H / 2})" text-anchor="middle" class="quad-axis-label">→ 客観スコア（9ファクター合成）</text>
    ${dots}
  </svg>`;

  const el = document.getElementById('quadrant');
  el.innerHTML = svg;
  el.querySelectorAll('.quad-dot').forEach((d) => {
    d.addEventListener('click', () => selectCompany(d.dataset.ticker, true));
  });
}

// ── Orchestration ────────────────────────
function rerender() {
  activePreset = detectPreset();
  renderPresets();
  renderRanking();
  renderDetail();
  renderQuadrant();
}

async function init() {
  renderFramework();
  renderControls();
  renderPresets();

  // ボトムタブ（モバイル）: 初期タブ=今日。リサイズで表示制御を再適用
  document.querySelectorAll('.tab-btn').forEach((b) => {
    b.addEventListener('click', () => setTab(b.dataset.tabgo));
  });
  applyTabs();
  window.addEventListener('resize', applyTabs);

  // 詳細シート内の左右スワイプ = 前後銘柄（縦スクロールは妨げない）
  const dpEl = document.querySelector('.detail-panel');
  if (dpEl) {
    let sx0 = 0, sy0 = 0;
    dpEl.addEventListener('touchstart', (e) => {
      sx0 = e.touches[0].clientX; sy0 = e.touches[0].clientY;
    }, { passive: true });
    dpEl.addEventListener('touchend', (e) => {
      const dx = e.changedTouches[0].clientX - sx0;
      const dy = e.changedTouches[0].clientY - sy0;
      if (Math.abs(dx) > 70 && Math.abs(dx) > 2.2 * Math.abs(dy)) navDetail(dx < 0 ? 1 : -1);
    }, { passive: true });
  }

  // 詳細シートの閉じる操作（✕ / 背景タップ / Escキー）
  const dc = document.getElementById('detail-close');
  if (dc) dc.addEventListener('click', closeDetailSheet);
  const bd = document.getElementById('sheet-backdrop');
  if (bd) bd.addEventListener('click', closeDetailSheet);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetailSheet(); });

  // カラーテーマ切替（コバルト×黄×白 / 緑×白）— localStorageで永続化
  const tb = document.getElementById('theme-toggle');
  const applyTheme = (g) => {
    document.body.classList.toggle('theme-green', g);
    if (tb) tb.textContent = g ? '🎨 コバルト×黄テーマ' : '🎨 緑×白テーマ';
  };
  applyTheme(localStorage.getItem('ngs-theme') === 'green');
  if (tb) tb.addEventListener('click', () => {
    const g = !document.body.classList.contains('theme-green');
    localStorage.setItem('ngs-theme', g ? 'green' : 'cobalt');
    applyTheme(g);
  });

  // ライブデータ読み込み → 客観ファクター適用 → 各種描画
  await loadLiveData();
  LIVE_UNIVERSE = LIVE.loaded ? liveUniverseCompanies() : [];
  const uc = document.getElementById('universe-count');
  if (uc && LIVE_UNIVERSE.length) uc.textContent = LIVE_UNIVERSE.length;
  // 学習済み重みを初期スライダー値に反映（ユーザーは以後自由に調整可）
  if (LIVE.foresight && LIVE.foresight.weights) {
    state.foresightWeights = { ...LIVE.foresight.weights };
    renderControls();
  }
  renderLiveStatus();
  renderIndicators();
  renderLearning();
  renderWatch();
  renderToday();

  renderRanking();
  renderDetail();
  renderQuadrant();
  // 初期選択：トップ銘柄
  const top = rankActive(activeUniverse())[0];
  if (top) selectCompany(top.ticker);
}

document.addEventListener('DOMContentLoaded', init);
