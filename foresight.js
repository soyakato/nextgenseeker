/*
 * foresight.js — 客観ファクター・レンズ（実データのみ・主観/事前分布なし）
 *
 * 手書きの後知恵アーキタイプ（旧KIOXIA/NVDA基準）と静的サブスコアは全廃。
 * スコアはすべて pipeline/factors.py が実データから算出した客観ファクターの
 * 横断パーセンタイル（live/foresight.json）に由来する。
 */

// ── 6つの客観ファクター（学術レポート準拠） ────────────────
const FORESIGHT_PILLARS = [
  { key: 'operating_leverage', label: '営業レバレッジ', short: 'DOL', color: 'var(--warn)',
    desc: 'Δ営業利益% / Δ売上%（Novy-Marx 2011）。需要回復時の利益の非線形な爆発力' },
  { key: 'cost_stickiness', label: 'コスト硬直性', short: 'STICKY', color: '#f0abfc',
    desc: 'Weiss(2010)。売上減でも費用を落とさない＝将来の稼働に備えた戦略的固定費' },
  { key: 'survival_dd', label: '距離デフォルト', short: 'MERTON', color: 'var(--accent-3)',
    desc: 'Bharath-Shumway(2008) naive Merton。市場ベースの生存力（高いほど倒産から遠い）' },
  { key: 'rnd_intensity', label: 'R&D強度', short: 'R&D', color: 'var(--accent-2)',
    desc: 'Chan-Lakonishok-Sougiannis(2001)。R&D費/売上。財務諸表から機械的に算出（人手のキーワード不要）' },
  { key: 'contrarian_inflection', label: '逆張り変曲', short: 'CONTRA', color: 'var(--danger)',
    desc: '52週高値からのドローダウン×前向きな成長。総悲観だが変曲している乖離' },
  { key: 'capital_momentum', label: '資金の勢い', short: 'FLOW', color: 'var(--accent)',
    desc: '機関保有＋52週位置＋時変ベータの上昇（Kalman近似）。静かな資金流入' },
];

// 既定ウェイト（learning.DEFAULT_WEIGHTS と一致。採点実績で自己調整される）
const FORESIGHT_DEFAULT_WEIGHTS = {
  operating_leverage: 20, cost_stickiness: 12, survival_dd: 20,
  rnd_intensity: 18, contrarian_inflection: 15, capital_momentum: 15,
};

// 任意のファクターオブジェクトから合成スコアを算出
function foresightCompositeFrom(factors, weights) {
  if (!factors) return 0;
  const W = weights || FORESIGHT_DEFAULT_WEIGHTS;
  const tot = Object.values(W).reduce((a, b) => a + b, 0) || 1;
  const s = FORESIGHT_PILLARS.reduce((acc, p) => acc + (factors[p.key] || 0) * (W[p.key] || 0), 0) / tot;
  return Math.max(0, Math.min(100, s));
}

function computeForesight(company, weights) {
  return { composite: foresightCompositeFrom(company.foresight, weights) };
}

// 後方互換: 旧コードが呼ぶが、客観モデルでは静的付与は行わない（liveのみ）
function attachForesight() { /* no-op: 先見スコアは live/foresight.json のみに由来 */ }
