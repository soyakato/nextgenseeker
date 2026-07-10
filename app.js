/*
 * NextGenSeeker — UIレンダリング
 */

const state = {
  lens: 'discovery',               // 既定は客観ファクター・レンズ / 'quality' = 主観フレーム(参考)
  weights: { ...DEFAULT_WEIGHTS },
  foresightWeights: { ...FORESIGHT_DEFAULT_WEIGHTS },
  riskSensitivity: 0.6,
  showBenchmark: false,
  useLiveCapital: true,
  selected: null,
};

// 先見レンズの採点は live の客観ファクターのみ（静的スコアは使わない）
function fPillars(c) { return c.foresight || null; }

// ── レンズ切替の共通ヘルパー ──────────────────
const isDiscovery = () => state.lens === 'discovery';
const activePillars = () => (isDiscovery() ? FORESIGHT_PILLARS : PILLARS);
// 先見(客観)レンズにベンチマークは無い。質(主観)レンズのみ NVDA を参考表示可
const activeBench = () => (isDiscovery() ? null : BENCHMARK);
const benchLabel = () => 'NVDA(参考)';
const benchTicker = () => 'NVDA';

function compositeOf(c) {
  if (!isDiscovery()) return computeComposite(c, state.weights, state.riskSensitivity).composite;
  const p = fPillars(c);
  return p ? foresightCompositeFrom(p, foresightWeightsActive()) : 0;
}
let LIVE_UNIVERSE = [];   // 客観ユニバース（liveの全銘柄、固定リストなし）

// 現在のレンズで採点対象にする母集団
function activeUniverse() {
  // 客観レンズ: liveの客観ユニバース（私の選定は一切入らない）。質(主観)レンズのみ curated。
  if (isDiscovery()) return LIVE_UNIVERSE.length ? LIVE_UNIVERSE : [];
  return [...COMPANIES];
}
// 先見合成の重み: ユーザー調整値（初期値は学習済み重み）
function foresightWeightsActive() {
  return state.foresightWeights;
}
function rankActive(list) {
  if (!isDiscovery()) return rankCompanies(list, state.weights, state.riskSensitivity);
  const w = foresightWeightsActive();
  return list
    .map((c) => ({ c, p: fPillars(c) }))
    .filter((x) => x.p)                              // 客観モードでは実データ導出が無いものを除外
    .map(({ c, p }) => {
      const comp = foresightCompositeFrom(p, w);
      return { ...c, foresightComposite: comp, composite: comp };
    })
    .sort((a, b) => b.composite - a.composite);
}
// 銘柄オブジェクト取得（参考ベンチマーク・客観ユニバース含む）
function lookupCompany(ticker) {
  if (isDiscovery()) return LIVE_UNIVERSE.find((x) => x.ticker === ticker) || COMPANIES.find((x) => x.ticker === ticker);
  if (ticker === 'NVDA') return BENCHMARK;
  return COMPANIES.find((x) => x.ticker === ticker) || LIVE_UNIVERSE.find((x) => x.ticker === ticker);
}

// ── Framework legend ──────────────────────
function renderFramework() {
  const qualityColors = {
    moat: 'var(--accent)', choke: 'var(--accent-2)', capital: 'var(--warn)',
    demand: 'var(--accent-3)', execution: 'var(--danger)',
  };
  const el = document.getElementById('framework');
  const pillars = activePillars();
  el.innerHTML = pillars.map((p) => {
    const col = isDiscovery() ? p.color : qualityColors[p.key];
    return `
    <div class="pillar-card" style="--pc:${col}">
      <div class="pk">${p.short}</div>
      <div class="pl">${p.label}</div>
      <div class="pd">${p.desc}</div>
    </div>`;
  }).join('');
  el.classList.toggle('six', isDiscovery());
}

// ── Weight sliders ───────────────────────
function renderControls() {
  const el = document.getElementById('weight-group');
  const pillars = activePillars();
  const wobj = isDiscovery() ? state.foresightWeights : state.weights;
  const maxW = 40;
  el.innerHTML = pillars.map((p) => `
    <div class="slider-block">
      <label>${p.label} <span class="val" id="wv-${p.key}">${wobj[p.key]}</span></label>
      <input type="range" min="0" max="${maxW}" value="${wobj[p.key]}" data-key="${p.key}" class="w-slider">
    </div>`).join('');

  el.querySelectorAll('.w-slider').forEach((sl) => {
    sl.addEventListener('input', (e) => {
      const k = e.target.dataset.key;
      wobj[k] = +e.target.value;
      document.getElementById(`wv-${k}`).textContent = e.target.value;
      rerender();
    });
  });

  // リスク減点スライダーとプリセットは quality レンズのみ
  const riskRow = document.getElementById('risk-row');
  if (riskRow) riskRow.style.display = isDiscovery() ? 'none' : '';

  const rs = document.getElementById('risk-slider');
  if (rs && !rs.dataset.bound) {
    rs.dataset.bound = '1';
    rs.value = state.riskSensitivity * 100;
    rs.addEventListener('input', (e) => {
      state.riskSensitivity = +e.target.value / 100;
      document.getElementById('rs-val').textContent = (+e.target.value) + '%';
      rerender();
    });
  }
}

// ── Presets ──────────────────────────────
const PRESETS = {
  balanced: { label: 'バランス型', weights: { moat: 25, choke: 25, capital: 15, demand: 20, execution: 15 }, risk: 0.6 },
  moat:     { label: '堀・独占重視', weights: { moat: 40, choke: 30, capital: 10, demand: 10, execution: 10 }, risk: 0.7 },
  choke:    { label: 'チョークポイント重視', weights: { moat: 15, choke: 40, capital: 10, demand: 25, execution: 10 }, risk: 0.5 },
  quality:  { label: '利益の質重視', weights: { moat: 20, choke: 15, capital: 40, demand: 10, execution: 15 }, risk: 0.8 },
  momentum: { label: '必然の需要重視', weights: { moat: 10, choke: 20, capital: 10, demand: 45, execution: 15 }, risk: 0.3 },
};
// 客観ファクター・レンズ用プリセット
const FORESIGHT_PRESETS = {
  balanced:  { label: '均衡（学術頑健）', weights: { ...FORESIGHT_DEFAULT_WEIGHTS } },
  leverage:  { label: '営業レバレッジ重視', weights: { operating_leverage: 38, cost_stickiness: 20, survival_dd: 14, tech_lead: 10, contrarian_inflection: 10, capital_momentum: 8 } },
  survival:  { label: '生存力（低倒産）', weights: { operating_leverage: 12, cost_stickiness: 8, survival_dd: 40, tech_lead: 12, contrarian_inflection: 12, capital_momentum: 16 } },
  tech:      { label: '技術先行重視', weights: { operating_leverage: 12, cost_stickiness: 8, survival_dd: 16, tech_lead: 40, contrarian_inflection: 12, capital_momentum: 12 } },
  contrarian:{ label: '逆張り変曲', weights: { operating_leverage: 16, cost_stickiness: 10, survival_dd: 16, tech_lead: 10, contrarian_inflection: 38, capital_momentum: 10 } },
};
let activePreset = 'balanced';

function renderPresets() {
  const el = document.getElementById('presets');
  const presets = isDiscovery() ? FORESIGHT_PRESETS : PRESETS;
  el.innerHTML = Object.entries(presets).map(([k, p]) =>
    `<button class="btn preset ${k === activePreset ? 'active' : ''}" data-preset="${k}">${p.label}</button>`).join('');
  el.querySelectorAll('.preset').forEach((b) => {
    b.addEventListener('click', () => {
      const p = presets[b.dataset.preset];
      activePreset = b.dataset.preset;
      if (isDiscovery()) {
        state.foresightWeights = { ...p.weights };
      } else {
        state.weights = { ...p.weights };
        state.riskSensitivity = p.risk;
      }
      renderControls();
      renderPresets();
      rerender();
    });
  });
}

// ── Ranking table ────────────────────────
function renderRanking() {
  const disc = isDiscovery();
  const ranked = rankActive(activeUniverse());
  const bench = activeBench();

  // 最終列: discovery=距離デフォルト(客観・生存力) / quality=リスク
  const lastCol = (c) => {
    if (!disc) return `<span class="risk-chip" style="color:${scoreColor(100 - c.risk)}">${c.risk}</span>`;
    const dd = c.foresight ? c.foresight.survival_dd : null;
    if (dd == null) return '<span class="risk-chip">—</span>';
    return `<span class="risk-chip" style="color:${scoreColor(dd)}" title="距離デフォルト(客観)">${Math.round(dd)}</span>`;
  };
  document.getElementById('rank-lastcol').textContent = disc ? '生存力(DD)' : 'リスク';
  document.getElementById('rank-scorecol').textContent = disc ? '客観スコア' : '総合スコア';
  const posHdr = document.getElementById('rank-poscol');
  if (posHdr) posHdr.textContent = disc ? 'セクター' : 'バリューチェーン位置';

  const rows = ranked.map((c, i) => {
    const g = grade(c.composite);
    const col = scoreColor(c.composite);
    const sel = state.selected === c.ticker ? 'selected' : '';
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
        <td class="num">${lastCol(c)}</td>
      </tr>`;
  }).join('');

  // 参考ベンチマークは質(主観)レンズのみ・任意表示
  const benchComp = bench ? compositeOf(bench) : 0;
  const benchRow = (bench && state.showBenchmark && !disc) ? `
    <tr class="bench-row company-row" data-ticker="${benchTicker()}">
      <td class="rk">★</td>
      <td><div class="tk" style="color:var(--accent-3)">${benchTicker()}</div><div class="nm">現王者・参考</div></td>
      <td class="nm">${bench.layer}</td>
      <td><span class="grade-badge" style="background:#a78bfa22;color:#a78bfa;border:1px solid #a78bfa55">${grade(benchComp)}</span></td>
      <td class="num"><div class="score-bar-wrap"><div class="mini-bar"><i style="width:${benchComp}%;background:#a78bfa"></i></div><span class="score-num" style="color:#a78bfa">${benchComp.toFixed(1)}</span></div></td>
      <td class="num"><span class="risk-chip">${bench.risk}</span></td>
    </tr>` : '';

  document.getElementById('rank-body').innerHTML = benchRow + rows;

  document.querySelectorAll('.company-row').forEach((r) => {
    r.addEventListener('click', () => selectCompany(r.dataset.ticker, true));
  });
}

// ── Radar chart (SVG) — 両レンズ対応 ──────
function radarSVG(company, size = 240) {
  const disc = isDiscovery();
  const pillars = activePillars();
  const scoreOf = (c) => (disc ? fPillars(c) : c.scores) || {};
  const bench = activeBench();
  const cs = scoreOf(company);
  const bs = bench ? ((disc ? fPillars(bench) : bench.scores) || {}) : null;

  const cx = size / 2, cy = size / 2 + 6, R = size * 0.32;
  const keys = pillars.map((p) => p.key);
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
    labels += `<text x="${lx}" y="${ly + 3}" text-anchor="${anchor}" class="quad-label">${pillars[i].short}</text>`;
  });

  const poly = (obj) => keys.map((k, i) => {
    const v = (obj[k] || 0) / 100;
    return `${cx + R * v * Math.cos(angle(i))},${cy + R * v * Math.sin(angle(i))}`;
  }).join(' ');

  return `
  <svg viewBox="0 0 ${size} ${size + 20}" class="radar" width="${size}" height="${size + 20}">
    ${rings}${spokes}
    ${bs ? `<polygon points="${poly(bs)}" fill="none" stroke="var(--accent-3)" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.6"/>` : ''}
    <polygon points="${poly(cs)}" fill="rgba(11,92,255,0.10)" stroke="var(--accent)" stroke-width="2"/>
    ${keys.map((k, i) => {
      const v = (cs[k] || 0) / 100;
      return `<circle cx="${cx + R * v * Math.cos(angle(i))}" cy="${cy + R * v * Math.sin(angle(i))}" r="2.5" fill="var(--accent)"/>`;
    }).join('')}
    ${labels}
  </svg>`;
}

// ── Detail panel ─────────────────────────
function selectCompany(ticker, userAction) {
  state.selected = ticker;
  renderRanking();
  renderDetail();
  renderQuadrant();
  // モバイル/タブレット（1カラム積み）では、タップ時に詳細パネルへ確実にジャンプ
  // （smoothは環境依存で無効化される事例があるため、明示的にinstantを指定）
  if (userAction && window.innerWidth <= 1080) {
    const panel = document.getElementById('detail-body');
    if (panel) panel.closest('.panel').scrollIntoView({ behavior: 'instant', block: 'start' });
  }
}

function renderDetail() {
  const el = document.getElementById('detail-body');
  if (!state.selected) {
    el.innerHTML = `<div class="empty-detail"><div class="big">◎</div>左のランキングから銘柄を選ぶと、<br>5軸レーダーと「必然の論理／ブラックスワン」を表示します。</div>`;
    return;
  }
  const c = lookupCompany(state.selected);
  if (!c) { el.innerHTML = ''; return; }
  const disc = isDiscovery();
  const comp = compositeOf(c);
  const col = scoreColor(comp);
  const f = fPillars(c);

  // 客観ファクターの内訳バー（生の実測値＝rawを併記）
  const rawFmt = (k) => {
    const r = c.foresightRaw ? c.foresightRaw[k] : null;
    return r == null ? '—' : (typeof r === 'number' ? r.toFixed(2) : r);
  };
  const foresightBreakdown = (disc && f) ? `
    <div class="fbreak">
      <div class="fbreak-head">
        <span class="obj-tag">客観ファクター（実データのみ）</span>
        <span class="fbreak-hint">バー=横断パーセンタイル / 括弧=生の実測値</span>
      </div>
      ${activePillars().map((p) => {
        const v = f[p.key] || 0;
        return `
        <div class="fbreak-row">
          <span class="fbk" title="${p.desc}">${p.label}</span>
          <div class="fbk-bar"><i style="width:${v}%;background:${p.color}"></i></div>
          <span class="fbv" style="color:${p.color}">${Math.round(v)}<em class="fbv-der">(${rawFmt(p.key)})</em></span>
        </div>`;
      }).join('')}
    </div>` : '';

  // 質(主観)レンズのみ論理テキスト。先見(客観)レンズはファクターの学術的根拠を表示。
  const thesisBlocks = disc ? `
    <div class="thesis-block down">
      <h4>▼ 集計方法の明示</h4>
      <p>財務諸表・株価から機械算出した6ファクターの横断パーセンタイル（同値タイは平均ランク）。変化系ファクター（DOL・コスト硬直性）は年次＋四半期の<b>前年同期比</b>エピソードの中央値/平均で季節性を排除。R&D未計上は中立ではなく<b>0として採点</b>（Chan et al.慣行）。Merton距離のデフォルトポイントはKMV慣行（短期負債＋長期負債×0.5）。生値が「—」の項目のみ真の欠損として中立50。</p>
    </div>` : `
    <div class="thesis-block up"><h4>▲ 必然の論理（主観フレーム・参考）</h4><p>${c.thesis || ''}</p></div>
    <div class="thesis-block down"><h4>▼ ブラックスワン（主観フレーム・参考）</h4><p>${c.risk_note || ''}</p></div>`;

  el.innerHTML = `
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
    <div class="detail-layer">${c.layer}</div>

    <div class="radar-wrap">${radarSVG(c)}</div>
    <div style="text-align:center;font-family:var(--mono);font-size:10px;color:var(--text-faint);margin-top:-6px">
      <span style="color:var(--accent)">■</span> ${c.ticker.replace(/\..*/, '')}
      ${!disc ? `&nbsp; <span style="color:var(--accent-3)">┈</span> ${benchLabel()}` : ''}
    </div>

    ${foresightBreakdown}
    ${liveFinancialBlock(c)}

    ${(!disc && c.chokepoint) ? `<div class="detail-choke"><b>CHOKEPOINT / 握っているボトルネック</b>${c.chokepoint}</div>` : ''}
    ${(Object.keys(c.metrics || {}).length) ? `<div class="metrics-grid">${Object.entries(c.metrics).map(([k, v]) => `<div class="metric-box"><div class="mk">${k}</div><div class="mv">${v}</div></div>`).join('')}</div>` : ''}
    ${thesisBlocks}`;
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
  const capTrend = trendArrow(null, c.ticker);
  return `
    <div class="live-fin">
      <div class="live-fin-head">
        <span class="live-tag">LIVE 実財務</span>
        <span class="live-fin-sym">${d.symbol}</span>
        <span class="cap-trend trend ${capTrend.cls}">CAPITAL ${capTrend.sym}</span>
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

// ── Quadrant map — 両レンズ対応 ──────────
function lensCoords(c) {
  if (isDiscovery()) {
    const f = fPillars(c) || {};
    return {
      x: (f.operating_leverage || 0),                   // 営業レバレッジ（利益の爆発力）
      y: foresightCompositeFrom(f, foresightWeightsActive()),
      risk: 100 - (f.survival_dd || 50),                // 距離デフォルトが低い=倒産リスク高
    };
  }
  return quadrantCoords(c, state.weights, state.riskSensitivity);
}

function renderQuadrant() {
  const W = 640, H = 420, pad = 46;
  const all = activeUniverse().map((c) => ({ ...c, ...lensCoords(c) }))
    .filter((a) => a.y != null && !isNaN(a.y));
  const bench = activeBench();
  if (bench && state.showBenchmark && !isDiscovery()) all.push({ ...bench, ...lensCoords(bench), isBench: true });

  const xs = all.map((a) => a.x), ys = all.map((a) => a.y);
  const xMin = Math.min(...xs) - 4, xMax = Math.max(...xs) + 4;
  const yMin = Math.min(...ys) - 4, yMax = Math.max(...ys) + 4;
  const sx = (v) => pad + ((v - xMin) / (xMax - xMin)) * (W - pad * 1.4);
  const sy = (v) => H - pad - ((v - yMin) / (yMax - yMin)) * (H - pad * 1.6);

  const midX = (xMin + xMax) / 2, midY = (yMin + yMax) / 2;

  let dots = all.map((a) => {
    const risk = a.risk;
    const rColor = scoreColor(100 - risk); // 高リスク=赤
    const rad = a.isBench ? 9 : 6 + (a.y - 50) / 12;  // a.y = リスク調整後の総合スコア
    const sel = state.selected === a.ticker;
    return `
      <g class="quad-dot" data-ticker="${a.ticker}">
        <circle cx="${sx(a.x)}" cy="${sy(a.y)}" r="${Math.max(4, rad)}"
          fill="${a.isBench ? 'var(--accent-3)' : rColor}" fill-opacity="${sel ? 0.95 : 0.65}"
          stroke="${sel ? 'var(--accent)' : (a.isBench ? 'var(--accent-3)' : rColor)}" stroke-width="${sel ? 2.5 : 1}"/>
        <text x="${sx(a.x)}" y="${sy(a.y) - Math.max(4, rad) - 3}" text-anchor="middle" class="quad-label"
          style="${sel ? 'fill:var(--accent);font-weight:700' : ''}">${a.ticker.replace(/\..*/, '')}</text>
      </g>`;
  }).join('');

  const disc = isDiscovery();
  const qTopRight = disc ? '◤ 本命：高営業レバレッジ×高客観スコア' : '◤ 本命：構造的な質×総合スコア高';
  const qTopLeft = disc ? '守勢：レバレッジ低だがスコア高' : '投機的：需要は高いが堀が浅い';
  const qBotLeft = disc ? '要警戒：客観スコア低' : '要警戒：質・スコアともに低い';
  const axX = disc ? '→ 営業レバレッジ DOL（利益の爆発力）' : '→ 構造的な質（堀＋チョークポイント＋実行力）';
  const axY = disc ? '→ 客観スコア（6ファクター合成）' : '→ 総合スコア（リスク調整後）';

  const svg = `
  <svg viewBox="0 0 ${W} ${H}" class="quad-svg">
    <line x1="${sx(midX)}" y1="${pad - 10}" x2="${sx(midX)}" y2="${H - pad + 6}" stroke="var(--border-bright)" stroke-dasharray="4,4"/>
    <line x1="${pad - 10}" y1="${sy(midY)}" x2="${W - pad + 10}" y2="${sy(midY)}" stroke="var(--border-bright)" stroke-dasharray="4,4"/>

    <text x="${W - pad + 4}" y="${sy(midY) + 20}" text-anchor="end" class="quad-quadrant-label" fill="var(--accent)">${qTopRight}</text>
    <text x="${pad}" y="${pad - 2}" class="quad-quadrant-label" fill="var(--warn)">${qTopLeft}</text>
    <text x="${pad}" y="${H - pad + 20}" class="quad-quadrant-label" fill="var(--danger)">${qBotLeft}</text>

    <text x="${W / 2}" y="${H - 8}" text-anchor="middle" class="quad-axis-label">${axX}</text>
    <text x="14" y="${H / 2}" transform="rotate(-90 14 ${H / 2})" text-anchor="middle" class="quad-axis-label">${axY}</text>

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

function detectPreset() {
  if (isDiscovery()) {
    for (const [k, p] of Object.entries(FORESIGHT_PRESETS)) {
      if (Object.keys(p.weights).every((key) => p.weights[key] === state.foresightWeights[key])) return k;
    }
    return null;
  }
  for (const [k, p] of Object.entries(PRESETS)) {
    const w = p.weights;
    if (Object.keys(w).every((key) => w[key] === state.weights[key]) && Math.abs(p.risk - state.riskSensitivity) < 0.001) return k;
  }
  return null;
}

// レンズ切替
function setLens(lens) {
  if (state.lens === lens) return;
  state.lens = lens;
  state.selected = null;
  document.querySelectorAll('.lens-btn').forEach((b) => b.classList.toggle('active', b.dataset.lens === lens));
  document.body.classList.toggle('discovery-lens', isDiscovery());
  activePreset = detectPreset();
  renderFramework();
  renderControls();
  renderPresets();
  renderRanking();
  renderQuadrant();
  const top = rankActive(activeUniverse())[0];
  selectCompany(top.ticker);
}

async function init() {
  attachForesight();  // COMPANIES/BENCHMARK に6原理スコアを結合
  renderFramework();
  renderControls();
  renderPresets();
  document.getElementById('rs-val').textContent = Math.round(state.riskSensitivity * 100) + '%';

  document.querySelectorAll('.lens-btn').forEach((b) => {
    b.addEventListener('click', () => setLens(b.dataset.lens));
  });

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

  const bt = document.getElementById('toggle-bench');
  if (bt) {
    bt.classList.toggle('active', state.showBenchmark);
    bt.addEventListener('click', () => {
      state.showBenchmark = !state.showBenchmark;
      bt.classList.toggle('active', state.showBenchmark);
      rerender();
    });
  }

  const lt = document.getElementById('toggle-live');
  lt.addEventListener('click', () => {
    state.useLiveCapital = !state.useLiveCapital;
    lt.classList.toggle('active', state.useLiveCapital);
    applyLiveCapital(state.useLiveCapital && LIVE.loaded);
    rerender();
  });

  // ライブデータ読み込み → 客観ファクター適用 → 各種描画
  await loadLiveData();
  applyLiveCapital(state.useLiveCapital && LIVE.loaded);
  applyLiveForesight();
  LIVE_UNIVERSE = LIVE.loaded ? liveUniverseCompanies() : [];
  // 客観レンズが既定なので、ユニバース数は客観ユニバースを表示
  const uc = document.getElementById('universe-count');
  if (uc && LIVE_UNIVERSE.length) uc.textContent = LIVE_UNIVERSE.length;
  // 学習済み重みを初期スライダー値に反映（ユーザーは以後自由に調整可）
  if (LIVE.foresight && LIVE.foresight.weights) {
    state.foresightWeights = { ...LIVE.foresight.weights };
    renderControls();
  }
  document.body.classList.toggle('discovery-lens', isDiscovery());
  lt.classList.toggle('active', state.useLiveCapital && LIVE.loaded);
  if (!LIVE.loaded) lt.textContent = '実データ未接続';
  renderLiveStatus();
  renderIndicators();
  renderLearning();
  renderWatch();

  renderRanking();
  renderDetail();
  renderQuadrant();
  // 初期選択：トップ銘柄
  const top = rankActive(activeUniverse())[0];
  selectCompany(top.ticker);
}

document.addEventListener('DOMContentLoaded', init);
