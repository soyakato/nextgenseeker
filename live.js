/*
 * live.js — パイプライン生成の live/*.json を読み込み、
 * CAPITALスコアを実データ化＋先行指標トラッカーを描画する。
 */
const LIVE = { financials: null, indicators: null, analyst: null, meta: null, history: null, foresight: null, learning: null, watch: null, ownership: null, loaded: false };

async function loadLiveData() {
  const bust = '?t=' + Date.now();
  const files = ['financials', 'indicators', 'analyst', 'meta', 'history', 'foresight', 'learning', 'watch', 'ownership'];
  await Promise.all(files.map(async (f) => {
    try {
      const r = await fetch(`live/${f}.json${bust}`);
      if (r.ok) LIVE[f] = await r.json();
    } catch (e) { /* ライブデータ未生成でも静的スコアで動作 */ }
  }));
  LIVE.loaded = !!(LIVE.financials && LIVE.financials.data);
  return LIVE.loaded;
}

// 実データのCAPITALスコアをCOMPANIES/BENCHMARKに適用（元値は _capital_static に退避）
function applyLiveCapital(useLive) {
  const fin = LIVE.financials && LIVE.financials.data;
  const patch = (c) => {
    if (c._capital_static === undefined) c._capital_static = c.scores.capital;
    const d = fin && fin[c.ticker];
    c.live = d || null;
    if (useLive && d && d.capital_score != null) {
      c.scores.capital = d.capital_score;
      c.capitalIsLive = true;
    } else {
      c.scores.capital = c._capital_static;
      c.capitalIsLive = false;
    }
  };
  COMPANIES.forEach(patch);
  patch(BENCHMARK);
}

// 客観ファクター（live/foresight.json の factors）を curated 銘柄にも適用（質レンズのライブ表示用）
function applyLiveForesight() {
  const fd = LIVE.foresight && LIVE.foresight.data;
  const patch = (c) => {
    const d = fd && fd[c.ticker];
    if (d && d.factors) {
      c.foresight = { ...d.factors };
      c.foresightRaw = d.raw || null;
      c.foresightDiag = d.diag || null;
      c.own = d.own || null;
      c.foresightLive = true;
      c.sector = d.sector || c.sector;
    } else {
      c.foresight = null;
      c.foresightLive = false;
    }
  };
  COMPANIES.forEach(patch);
}

// 機関保有の変遷: 自前時系列(ownership.json)から最古スナップショットとの差分を返す
function ownershipDelta(ticker) {
  const pts = LIVE.ownership && LIVE.ownership.points;
  if (!pts || pts.length < 2) return null;
  const first = pts[0].data && pts[0].data[ticker];
  const last = pts[pts.length - 1].data && pts[pts.length - 1].data[ticker];
  if (!first || !last || first.pct == null || last.pct == null) return null;
  return {
    dPct: (last.pct - first.pct) * 100,
    dCnt: (last.cnt != null && first.cnt != null) ? last.cnt - first.cnt : null,
    days: Math.round((new Date(pts[pts.length - 1].t) - new Date(pts[0].t)) / 86400000),
  };
}

// 客観ユニバース: live/foresight.json の全銘柄を軽量オブジェクトとして返す（客観レンズの母集団）
// 固定リストは使わない。私が選んだ銘柄という概念そのものを排除する。
function liveUniverseCompanies() {
  const fd = LIVE.foresight && LIVE.foresight.data;
  if (!fd) return [];
  const finAll = (LIVE.financials && LIVE.financials.data) || {};
  const out = [];
  for (const [t, d] of Object.entries(fd)) {
    if (!d.factors) continue;
    out.push({
      ticker: t, name: (finAll[t] && finAll[t].name) || t, sector: d.sector || '—',
      layer: d.sector || '客観ユニバース', chokepoint: '',
      scores: {}, risk: null, metrics: {}, thesis: '', risk_note: '',
      foresight: { ...d.factors }, foresightRaw: d.raw || null, foresightDiag: d.diag || null,
      own: d.own || null,
      live: finAll[t] || null, foresightLive: true, isObjective: true,
    });
  }
  return out;
}

// ── トレンド矢印（履歴から） ──
function trendArrow(key, ticker) {
  const pts = LIVE.history && LIVE.history.points;
  if (!pts || pts.length < 2) return { sym: '—', cls: 'flat' };
  const last = pts[pts.length - 1], prev = pts[pts.length - 2];
  const gv = (p) => ticker ? (p.capital && p.capital[ticker]) : p[key];
  const a = gv(prev), b = gv(last);
  if (a == null || b == null) return { sym: '—', cls: 'flat' };
  const d = b - a;
  if (d > 0.5) return { sym: '▲ +' + d.toFixed(1), cls: 'up' };
  if (d < -0.5) return { sym: '▼ ' + d.toFixed(1), cls: 'down' };
  return { sym: '→ 0.0', cls: 'flat' };
}

function heatColor(v) {
  if (v == null) return 'var(--text-faint)';
  const hue = Math.max(0, Math.min(145, (v / 100) * 145));
  return `hsl(${hue},78%,40%)`;
}

// ── 先行指標トラッカーの描画 ──
function renderIndicators() {
  const host = document.getElementById('indicator-body');
  if (!host) return;
  if (!LIVE.indicators || !LIVE.indicators.data) {
    host.innerHTML = `<div class="empty-detail">ライブ先行指標は未生成です。<br>
      <code>python3 pipeline/refresh.py</code> を実行するとデータが表示されます。</div>`;
    return;
  }
  const ind = LIVE.indicators.data;
  const moat = ind.moat_erosion, mkt = ind.market;

  const signalCard = (title, sub, heat, trendKey, extra = '') => {
    const tr = trendArrow(trendKey);
    const col = heatColor(heat);
    return `
      <div class="sig-card">
        <div class="sig-top">
          <div><div class="sig-title">${title}</div><div class="sig-sub">${sub}</div></div>
          <div class="sig-heat" style="color:${col}">${heat != null ? heat : 'N/A'}
            <span class="trend ${tr.cls}">${tr.sym}</span></div>
        </div>
        <div class="heat-bar"><i style="width:${heat || 0}%;background:${col}"></i></div>
        ${extra}
      </div>`;
  };

  // CUDA堀侵食: リポジトリ明細
  const repoRows = (moat.repos || []).map((r) => `
    <div class="repo-row">
      <span class="repo-name">${r.repo}</span>
      <span class="repo-stat">★ ${(r.stars || 0).toLocaleString()}</span>
      <span class="repo-stat">commits30d ${r.commits_30d ?? '—'}</span>
    </div>`).join('');
  const scale = moat.scale
    ? `<div class="scale-box hit">◉ SCALE検出: <b>${moat.scale.repo}</b> · ★${moat.scale.stars} — CUDA互換レイヤーの公開活動を監視中</div>`
    : `<div class="scale-box miss">○ SCALE(Spectral Compute)の主要リポジトリは非公開/未検出 — 進展があれば自動で捕捉</div>`;

  const moatExtra = `<div class="repo-list">${repoRows}</div>${scale}`;

  // 市場プロキシの明細
  const proxyDetail = (grp) => (grp.items || []).map((it) =>
    `<span class="proxy-chip">${it.symbol}: 3M ${it.chg_3m != null ? (it.chg_3m > 0 ? '+' : '') + it.chg_3m + '%' : '—'}${it.revenue_growth != null ? ' · revG ' + Math.round(it.revenue_growth * 100) + '%' : ''}</span>`).join('');

  host.innerHTML = `
    <div class="sig-grid">
      ${signalCard('CUDAの堀の侵食', 'GitHub: CUDA代替スタックの直近コミット活動', moat.heat, 'moat_heat', moatExtra)}
      ${signalCard('TSMC 需要ゲージ', 'TSM 四半期成長＋価格モメンタム (プロキシ)', mkt.tsmc_demand.heat, 'tsmc_heat',
        `<div class="proxy-line">${proxyDetail(mkt.tsmc_demand)}</div>`)}
      ${signalCard('光インターコネクト', 'COHR/LITE/FN 受注先行プロキシ', mkt.optical.heat, 'optical_heat',
        `<div class="proxy-line">${proxyDetail(mkt.optical)}</div>`)}
      ${signalCard('電力ボトルネック', 'CEG/VST 電力逼迫の受益 (プロキシ)', mkt.power.heat, 'power_heat',
        `<div class="proxy-line">${proxyDetail(mkt.power)}</div>`)}
      ${signalCard('HBM 供給', 'SK Hynix/Micron モメンタム (プロキシ)', mkt.hbm.heat, 'hbm_heat',
        `<div class="proxy-line">${proxyDetail(mkt.hbm)}</div>`)}
    </div>`;
}

// ── アナリスト読み筋＋更新ステータス ──
function renderLiveStatus() {
  const el = document.getElementById('live-status');
  if (!el) return;
  if (!LIVE.meta) {
    el.innerHTML = `<span class="live-dot off"></span> ライブデータ未接続 — 静的スコアで表示中`;
    return;
  }
  const upd = new Date(LIVE.meta.updated);
  const ago = Math.round((Date.now() - upd.getTime()) / 60000);
  const agoTxt = ago < 60 ? `${ago}分前` : `${Math.round(ago / 60)}時間前`;
  el.innerHTML = `<span class="live-dot on"></span> LIVE · 最終更新 ${agoTxt}
    <span class="ls-sep">|</span> 実財務 ${LIVE.meta.financials_ok}/${LIVE.meta.financials_total}銘柄
    <span class="ls-sep">|</span> 履歴 ${LIVE.meta.history_points}点
    <span class="ls-sep">|</span> 解析 ${LIVE.meta.analyst_source}`;

  const an = document.getElementById('analyst-body');
  if (an && LIVE.analyst) {
    an.innerHTML = `<div class="analyst-text">${(LIVE.analyst.text || '').replace(/\n/g, '<br>')}</div>
      <div class="analyst-src">出典: ${LIVE.analyst.source}${LIVE.analyst.error ? ' (APIエラーによりフォールバック)' : ''}</div>`;
  }
}

// ── ウォッチ＆兆候レーダー ──────────────────
function renderWatch() {
  const el = document.getElementById('watch-body');
  if (!el) return;
  const W = LIVE.watch;
  if (!W || !W.signals) {
    el.innerHTML = `<div class="empty-detail">ウォッチデータは未生成です。<br><code>python3 pipeline/refresh.py</code> 実行後に表示されます。</div>`;
    return;
  }

  // アラート的中率サマリ（採点済みがあれば）
  const as = W.alert_summary || {};
  const sumTxt = Object.keys(as).length
    ? Object.entries(as).map(([h, s]) =>
        `${h}営業日: 的中${Math.round(s.hit_rate * 100)}% (n=${s.n}, 平均超過${(s.avg_excess * 100).toFixed(1)}%)`).join(' ｜ ')
    : 'アラート採点は満期待ち（5/20営業日後にSPY超過で自動採点）';

  const dirChip = (j) => {
    const d = j.dir || 0;
    const cls = d > 0.15 ? 'up' : (d < -0.15 ? 'down' : 'flat');
    const sym = d > 0.15 ? '▲' : (d < -0.15 ? '▼' : '→');
    return `<span class="news-dir ${cls}${j.is_edgar ? ' edgar' : ''}">${j.is_edgar ? '📜 ' : ''}${sym} ${j.type || ''}</span>`;
  };

  const rows = W.signals.map((s) => {
    const col = heatColor(s.signal);
    const alerted = s.signal >= (W.criteria ? W.criteria.threshold : 65);
    const heads = (s.headlines || []).map((h) => `
      <div class="news-row">
        ${dirChip(h)}
        <a class="news-title" href="${h.url || '#'}" target="_blank" rel="noopener">${h.title}</a>
        <span class="news-meta">${h.provider || ''} ${h.pub ? '· ' + h.pub.slice(5, 16).replace('T', ' ') : ''}${h.why ? ' · ' + h.why : ''}</span>
      </div>`).join('') || '<div class="news-row"><span class="news-meta">直近7日の関連ニュースなし</span></div>';
    const mom = s.mom || {};
    const momTxt = `${mom.ret5 != null ? '5日 ' + (mom.ret5 >= 0 ? '+' : '') + (mom.ret5 * 100).toFixed(1) + '%' : ''}${mom.vol_surge != null ? ' · 出来高 ' + mom.vol_surge + 'x' : ''}`;
    const earnChip = (s.earn_days != null)
      ? `<span class="earn-chip" title="触媒ウィンドウの表示のみ（スコアには不使用）。決算跨ぎは統計的にコイントス">📅 決算${s.earn_days === 0 ? '本日' : s.earn_days + '日後'}</span>` : '';
    return `
    <div class="watch-card ${alerted ? 'alerted' : ''}" data-ticker="${s.ticker}">
      <div class="watch-head">
        <span class="watch-tier ${s.tier === '確定' ? 'firm' : 'prov'}">${s.tier}</span>
        <div class="watch-id"><b>${s.ticker}</b><span>${s.name} · ${s.sector || '—'}</span></div>
        <div class="watch-sub">連続${s.streak}日 · 出現${s.appearances}回 · 本日#${s.today_rank || '—'} ${momTxt ? '· ' + momTxt : ''} ${s.consensus ? `· 評価 Buy${s.consensus.buy}/Hold${s.consensus.hold}/Sell${s.consensus.sell}` : ''} ${earnChip}</div>
        <div class="watch-sig" style="color:${col}">${s.signal}${alerted ? ' ⚡' : ''}</div>
      </div>
      <div class="watch-bars">
        <span>継続 <b>${s.persist}</b></span><span>ニュース <b style="color:${heatColor(s.news)}">${s.news}</b></span><span>確認 <b>${s.confirm}</b></span>
      </div>
      ${heads}
    </div>`;
  }).join('');

  // ⚡アラート履歴（発火記録と採点結果）
  const alertLog = (W.alerts_recent && W.alerts_recent.length) ? `
    <div class="alert-log">
      <span class="alert-log-title">⚡ アラート履歴</span>
      ${W.alerts_recent.slice(0, 8).map((a) => {
        const g5 = a.grades && a.grades['5'];
        const g20 = a.grades && a.grades['20'];
        const gTxt = (h, g) => g == null ? `${h}日:待` : `<b class="${g > 0 ? 'pos-t' : 'neg-t'}">${h}日:${(g * 100).toFixed(1)}%</b>`;
        return `<span class="alert-item">${a.date.slice(5)} <b>${a.ticker}</b> ${a.signal} → ${gTxt(5, g5)} ${gTxt(20, g20)}</span>`;
      }).join('')}
    </div>` : '';

  el.innerHTML = `
    <div class="watch-summary">
      <span class="learn-chip ${Object.keys(as).length ? 'on' : 'off'}">アラート検証</span> ${sumTxt}
      <span class="ls-sep">|</span> 判定: ${W.judge_source}
    </div>
    ${alertLog}
    ${rows || '<div class="empty-detail">ウォッチ対象なし（継続選出の蓄積待ち）</div>'}
    ${(() => {
      const cl = W.composition;
      if (!cl) return '';
      const c = cl.composition || {};
      const pct = (v) => Math.round((v || 0) * 100) + '%';
      const icTxt = cl.ic ? Object.entries({ persist: '継続', news: 'ニュース', confirm: '確認' })
        .map(([k, jp]) => `${jp} ${cl.ic[k] == null ? '—' : (cl.ic[k] >= 0 ? '+' : '') + cl.ic[k]}`).join(' / ') : '';
      return `<div class="learn-status" style="margin-top:10px">
        <span class="learn-chip ${cl.active ? 'on' : 'off'}">${cl.active ? '構成比学習 作動中' : '構成比学習 結果待ち'}</span>
        現在の構成: 継続${pct(c.persist)}・ニュース${pct(c.news)}・確認${pct(c.confirm)}
        <span class="ls-sep">|</span> 採点 ${cl.graded_samples}/${cl.min_samples}
        ${cl.active ? `<span class="ls-sep">|</span> IC: ${icTxt}` : ''}
      </div>`;
    })()}
    <div class="learn-note">兆候スコア＝継続＋ニュース＋価格/出来高確認の加重合成（基準30/40/30、ウォッチ全銘柄の遅延採点ICで構成比を自己調整・×0.5〜1.6クランプ）。📅=決算接近（表示のみ・スコア不使用）。ウォッチ選定も機械的（連続${(W.criteria || {}).streak_days}日以上=確定、当日上位=仮）。📜=SEC EDGAR 8-K（一次情報・Item番号の機械判定・集約2倍重み — 報道より早い触媒）。ニュース判定はLLM使用時も企業名を匿名化し見出し内容のみで判定（ブランド事前知識の遮断）。⚡=兆候スコア${(W.criteria || {}).threshold}以上のアラート（macOS通知＋遅延採点で的中率を自己検証）。</div>`;

  el.querySelectorAll('.watch-card').forEach((c) => {
    c.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      if (typeof selectCompany === 'function') selectCompany(c.dataset.ticker, true);
    });
  });
}

// ── 今日のダイジェスト（モバイルのホーム。3秒で要点） ──
function renderToday() {
  const el = document.getElementById('today-body');
  if (!el) return;
  const W = LIVE.watch || {};
  const sigs = W.signals || [];
  const card = (t, name, sub, val, valColor, cls) => `
    <div class="today-card ${cls || ''}" data-ticker="${t}">
      <span class="tc-tk">${t}</span>
      <span class="tc-mid"><span class="tc-name">${name || ''}</span><br><span class="tc-sub">${sub || ''}</span></span>
      <span class="tc-val" style="color:${valColor || 'var(--text)'}">${val}</span>
    </div>`;

  // 1) ⚡アラート（最新3件・採点結果つき）
  const alerts = (W.alerts_recent || []).slice(0, 3);
  const alertHtml = alerts.length
    ? alerts.map((a) => {
        const g5 = a.grades && a.grades['5'];
        const sub = g5 != null ? `5日採点 ${(g5 * 100).toFixed(1)}% (対SPY)` : `${a.date} 発火 · 採点待ち`;
        return card(a.ticker, '', sub, a.signal, heatColor(a.signal), 'alert');
      }).join('')
    : '<div class="today-empty">現在アラートなし（兆候スコア65以上で発火・スマホ通知）</div>';

  // 2) 兆候上位3
  const topSigs = sigs.slice(0, 3).map((s) => {
    const h = (s.headlines || [])[0];
    return card(s.ticker, s.name, h ? h.title.slice(0, 42) : `連続${s.streak}日選出`, s.signal, heatColor(s.signal));
  }).join('') || '<div class="today-empty">ウォッチ蓄積中</div>';

  // 3) スコア急変（直近2スナップショットの客観スコア差・上位3）
  let movers = '<div class="today-empty">履歴蓄積中（次回実行から表示）</div>';
  const pts = (LIVE.history && LIVE.history.points || []).filter((p) => p.foresight);
  if (pts.length >= 2) {
    const a = pts[pts.length - 2].foresight, b = pts[pts.length - 1].foresight;
    const ds = Object.keys(b).filter((t) => a[t] != null)
      .map((t) => ({ t, d: b[t] - a[t], now: b[t] }))
      .sort((x, y) => Math.abs(y.d) - Math.abs(x.d)).slice(0, 3);
    if (ds.length && Math.abs(ds[0].d) > 0.05) {
      movers = ds.map((m) => card(m.t, '', `客観スコア ${m.d >= 0 ? '+' : ''}${m.d.toFixed(1)} → ${m.now.toFixed(1)}`,
        (m.d >= 0 ? '▲' : '▼'), m.d >= 0 ? 'var(--good)' : 'var(--danger)')).join('');
    }
  }

  // 4) 決算接近（7日以内）
  const earnSoon = sigs.filter((s) => s.earn_days != null && s.earn_days <= 7)
    .sort((x, y) => x.earn_days - y.earn_days).slice(0, 3);
  const earnHtml = earnSoon.length
    ? earnSoon.map((s) => card(s.ticker, s.name, '決算跨ぎは統計的にコイントス', s.earn_days === 0 ? '本日' : `${s.earn_days}日後`, 'var(--warn)')).join('')
    : '<div class="today-empty">7日以内の決算なし</div>';

  // 5) システム1行
  const L = LIVE.learning || {};
  const upd = LIVE.meta ? Math.round((Date.now() - new Date(LIVE.meta.updated)) / 60000) : null;
  const sys = `更新 ${upd != null ? (upd < 60 ? upd + '分前' : Math.round(upd / 60) + '時間前') : '—'} · ユニバース ${Object.keys((LIVE.foresight || {}).data || {}).length}銘柄 · ファクター採点 ${L.graded_samples ?? 0}/${L.min_samples ?? 12}${(W.alert_summary && Object.keys(W.alert_summary).length) ? ' · アラート的中率あり→ウォッチ参照' : ''}`;

  el.innerHTML = `
    <div class="today-sec"><h3>⚡ アラート</h3>${alertHtml}</div>
    <div class="today-sec"><h3>📈 兆候 上位3</h3>${topSigs}</div>
    <div class="today-sec"><h3>🔥 スコア急変</h3>${movers}</div>
    <div class="today-sec"><h3>📅 決算接近（7日以内）</h3>${earnHtml}</div>
    <div class="today-line">${sys}</div>`;

  el.querySelectorAll('.today-card').forEach((c) => {
    c.addEventListener('click', () => {
      if (typeof selectCompany === 'function') selectCompany(c.dataset.ticker, true);
    });
  });
}

// ── 自己改善ステータス（遅延採点・IC・ガラパゴス化ガード） ──
const FORESIGHT_PILLAR_JP = { operating_leverage: '営業レバレッジ', cost_stickiness: 'コスト硬直性',
  survival_dd: '距離デフォルト', rnd_intensity: 'R&D強度', contrarian_inflection: '逆張り変曲',
  capital_momentum: '資金の勢い', holding_trend: '保有期間トレンド', earnings_drift: '決算ドリフト' };

function renderLearning() {
  const el = document.getElementById('learning-body');
  if (!el) return;
  const L = LIVE.learning;
  if (!L) { el.innerHTML = `<div class="empty-detail">自己改善データは未生成です。</div>`; return; }

  const conc = L.concentration || {};
  const concCls = conc.warn ? 'galapagos-warn' : 'galapagos-ok';

  const icRows = Object.keys(FORESIGHT_PILLAR_JP).map((p) => {
    const ic = L.ic ? L.ic[p] : null;
    const w = L.weights ? L.weights[p] : null;
    const dw = L.default_weights ? L.default_weights[p] : null;
    const mult = L.multipliers ? L.multipliers[p] : 1;
    const icTxt = ic == null ? '—' : (ic >= 0 ? '+' : '') + ic.toFixed(3);
    const icCls = ic == null ? 'flat' : (ic > 0.02 ? 'up' : (ic < -0.02 ? 'down' : 'flat'));
    const moved = Math.abs((mult || 1) - 1) > 0.001;
    return `<tr>
      <td>${FORESIGHT_PILLAR_JP[p]}</td>
      <td class="num trend ${icCls}">${icTxt}</td>
      <td class="num">${dw}</td>
      <td class="num" style="font-weight:700;color:${moved ? 'var(--accent)' : 'var(--text-dim)'}">${w != null ? w.toFixed(1) : '—'}${moved ? ` (×${mult})` : ''}</td>
    </tr>`;
  }).join('');

  const compIc = L.composite_ic;
  el.innerHTML = `
    <div class="galapagos ${concCls}">${conc.note || ''}</div>
    <div class="learn-status">
      <span class="learn-chip ${L.active ? 'on' : 'off'}">${L.active ? '学習作動中' : '結果待ち・重み不動'}</span>
      <span class="ls-sep">|</span> 採点サンプル <b>${L.graded_samples}/${L.min_samples}</b>
      <span class="ls-sep">|</span> 追跡コホート ${L.cohorts_tracked}
      <span class="ls-sep">|</span> 採点horizon ${(L.horizons || []).join('/')}営業日
      <span class="ls-sep">|</span> 忘却 ${L.forget_days}日
      ${compIc != null ? `<span class="ls-sep">|</span> 総合IC ${compIc >= 0 ? '+' : ''}${compIc}` : ''}
    </div>
    <table class="learn-table">
      <thead><tr><th>原理</th><th class="num">IC(予測力)</th><th class="num">既定重み</th><th class="num">現在の重み</th></tr></thead>
      <tbody>${icRows}</tbody>
    </table>
    ${(() => {
      const cov = LIVE.foresight && LIVE.foresight.coverage;
      if (!cov) return '';
      const tot = cov._total || 0;
      return `<div class="discovered-list">📊 データカバレッジ（実データで採点できた銘柄数 / ${tot}）: ${Object.keys(FORESIGHT_PILLAR_JP).map((k) => `${FORESIGHT_PILLAR_JP[k]} ${cov[k] != null ? cov[k] : '—'}`).join(' · ')} — 欠損は中立50（R&D未計上は0扱いでカバレッジに含む）</div>`;
    })()}
    <div class="learn-note">${L.note} — ガラパゴス化防止: 事前分布を錨に×0.5〜1.6の範囲でのみ調整。ICは「原理スコア→その後の市場超過リターン」の順位相関で、+0.05で実用・±0.02は雑音。</div>
    ${(LIVE.foresight && LIVE.foresight.discovered && LIVE.foresight.discovered.length) ? `<div class="discovered-list">🔭 今回の自動発見（固定リスト外）: ${LIVE.foresight.discovered.join(', ')}</div>` : ''}`;
}
