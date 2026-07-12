/*
 * engine.js — 共通ユーティリティ（グレード・色）
 * v4.1: 主観フレーム（quality合成・リスク調整）は完全削除。採点は foresight.js に一本化。
 */

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
