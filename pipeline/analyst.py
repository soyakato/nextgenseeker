"""任意の高度化レイヤー: 取得済みシグナルを『アナリスト読み筋』に合成する.

ANTHROPIC_API_KEY があれば Claude Messages API で自然言語コメントを生成。
無ければ決定論的なルールベース要約に自動フォールバックする（キー無しでも完全動作）。
"""
import json
import requests
from config import ANTHROPIC_API_KEY, NGS_MODEL, REQUEST_TIMEOUT


def _rule_based(financials, indicators):
    moat = indicators["moat_erosion"]
    mkt = indicators["market"]
    lines = []

    heat = moat["heat"]
    if heat >= 60:
        lines.append(f"【CUDAの堀】代替スタックのコミット活動が高水準（ヒート{heat}）。"
                     "ソフト独占の侵食シグナルは強め — 中期のコモディティ化リスクに注意。")
    elif heat >= 30:
        lines.append(f"【CUDAの堀】代替スタックの活動は中程度（ヒート{heat}）。"
                     "侵食は進行中だが決定的な水準ではない。")
    else:
        lines.append(f"【CUDAの堀】代替スタックの直近活動は限定的（ヒート{heat}）。堀は当面堅牢。")

    th = mkt["tsmc_demand"]["heat"]
    if th is not None:
        tone = "拡大基調" if th >= 55 else ("減速の兆し" if th < 45 else "横ばい")
        lines.append(f"【TSMC需要ゲージ】プロキシ・ヒート{th}（{tone}）。"
                     "CoWoS/先端製造の需要が上流の律速。")

    oh = mkt["optical"]["heat"]
    if oh is not None:
        lines.append(f"【光インターコネクト】受注先行プロキシ・ヒート{oh}。"
                     "ラックスケール化に伴う光モジュール需要の温度感。")

    # 財務ハイライト: CAPITALスコア上位/下位
    scored = [(t, d.get("capital_score")) for t, d in financials.items()
              if d.get("capital_score") is not None]
    scored.sort(key=lambda x: x[1], reverse=True)
    if scored:
        top = ", ".join(f"{t}({s})" for t, s in scored[:3])
        bot = ", ".join(f"{t}({s})" for t, s in scored[-2:])
        lines.append(f"【利益の質・実データ】上位: {top} / 下位: {bot}。"
                     "高粗利×高FCF変換の上流が引き続き構造的に優位。")

    return "\n".join(lines)


def _claude(financials, indicators):
    # 送信用に軽量サマリを作る
    fin_summary = {t: {"cap": d.get("capital_score"),
                       "gm": d.get("gross_margin"),
                       "revG": d.get("revenue_growth"),
                       "fcfConv": d.get("fcf_conversion")}
                   for t, d in financials.items() if d.get("capital_score")}
    payload = {
        "model": NGS_MODEL,
        "max_tokens": 700,
        "system": (
            "あなたはAIバリューチェーンを専門とする半導体アナリスト。"
            "与えられた実データ（財務スコアとGitHub/市場の先行シグナル）だけを根拠に、"
            "『次のNVIDIA候補』の構造を日本語で簡潔に読み解く。"
            "CUDAの堀の侵食・チョークポイント・利益の質・必然の需要の観点で、"
            "4〜6行の箇条書き＋最後に1行の総括。投資助言は避け、構造分析に徹する。"),
        "messages": [{
            "role": "user",
            "content": ("financials=" + json.dumps(fin_summary, ensure_ascii=False)
                        + "\nindicators=" + json.dumps({
                            "moat_heat": indicators["moat_erosion"]["heat"],
                            "moat_commits30d": indicators["moat_erosion"]["total_commits_30d"],
                            "tsmc_heat": indicators["market"]["tsmc_demand"]["heat"],
                            "optical_heat": indicators["market"]["optical"]["heat"],
                            "power_heat": indicators["market"]["power"]["heat"],
                            "hbm_heat": indicators["market"]["hbm"]["heat"],
                        }, ensure_ascii=False))
        }],
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        data=json.dumps(payload), timeout=REQUEST_TIMEOUT * 3)
    r.raise_for_status()
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []))


def synthesize(financials, indicators):
    if ANTHROPIC_API_KEY:
        try:
            text = _claude(financials, indicators)
            return {"source": f"claude:{NGS_MODEL}", "text": text}
        except Exception as e:
            return {"source": "rule-based (claude-fallback)",
                    "text": _rule_based(financials, indicators),
                    "error": repr(e)[:160]}
    return {"source": "rule-based", "text": _rule_based(financials, indicators)}
