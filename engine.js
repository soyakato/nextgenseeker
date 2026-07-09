/*
 * NextGenSeeker — スコアリング・エンジン
 * 5つの評価軸の加重平均から総合スコアを算出し、
 * コモディティ化リスクを減点として反映する。
 */

// 加重総合スコア（0-100）。riskは減点係数として作用。
function computeComposite(company, weights, riskSensitivity) {
  const s = company.scores;
  const totalW = weights.moat + weights.choke + weights.capital + weights.demand + weights.execution;
  const w = totalW > 0 ? totalW : 1;

  const weighted =
    (s.moat * weights.moat +
     s.choke * weights.choke +
     s.capital * weights.capital +
     s.demand * weights.demand +
     s.execution * weights.execution) / w;

  // riskSensitivity(0-1): リスクをどれだけ総合スコアから差し引くか。
  // risk=50を中立点とし、それより高ければ減点、低ければ加点。
  const riskAdj = (company.risk - 50) * 0.4 * riskSensitivity;
  const composite = Math.max(0, Math.min(100, weighted - riskAdj));

  return { weighted, composite, riskAdj };
}

// 「必然性」対「コモディティ化リスク」の2軸マッピング用の座標
function quadrantCoords(company, weights, riskSensitivity) {
  const { composite } = computeComposite(company, weights, riskSensitivity);
  // x軸 = 構造的な質（堀＋チョークポイント＋実行）
  const structural = (company.scores.moat + company.scores.choke + company.scores.execution) / 3;
  return { x: structural, y: composite, risk: company.risk };
}

// ランキング生成
function rankCompanies(companies, weights, riskSensitivity) {
  return companies
    .map((c) => {
      const r = computeComposite(c, weights, riskSensitivity);
      return { ...c, ...r };
    })
    .sort((a, b) => b.composite - a.composite);
}

// スコア→文字グレード
function grade(score) {
  if (score >= 90) return 'S';
  if (score >= 82) return 'A+';
  if (score >= 75) return 'A';
  if (score >= 68) return 'B+';
  if (score >= 60) return 'B';
  if (score >= 50) return 'C';
  return 'D';
}

// スコア→色（緑=高、赤=低）。ライトテーマ向けに彩度高め・明度低めで白背景に映える。
function scoreColor(score) {
  // 0-100 を hue 0(赤)→145(緑) にマップ
  const hue = Math.max(0, Math.min(145, (score / 100) * 145));
  return `hsl(${hue}, 78%, 40%)`;
}
