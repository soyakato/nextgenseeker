"""任意の高度化レイヤー: 市場環境（地合い＋セクター温度）を『読み筋』に合成する.

ANTHROPIC_API_KEY があれば Claude Messages API で自然言語コメントを生成。
無ければ決定論的なルールベース要約に自動フォールバック（キー無しでも完全動作）。
半導体固定の旧版から、ユニバース自動導出のセクター温度＋地合いレジームに刷新。
"""
import json
import requests
from config import ANTHROPIC_API_KEY, NGS_MODEL, REQUEST_TIMEOUT


def _rule_based(financials, indicators):
    lines = []
    reg = indicators.get("regime")
    if reg:
        lines.append(f"【地合い】{reg['label']} — {reg['desc']}"
                     + (f"（ベンチ {reg['bench']} / 50日線 {reg['ma50']}"
                        + (f" / VIX {reg['vix']}" if reg.get('vix') is not None else "") + "）"))
    st = indicators.get("sector_temp") or []
    if st:
        hot = st[0]
        cold = st[-1]
        lines.append(f"【セクター温度・最高】{hot['sector']}（平均{hot['avg']}・{hot['n']}銘柄・筆頭 {hot['top']}）"
                     " — 現ユニバースで最も客観スコアが高い領域。")
        if len(st) >= 3:
            mid = ", ".join(f"{x['sector']}{x['avg']}" for x in st[1:4])
            lines.append(f"【セクター温度・分布】{mid} …（ユニバース構成から自動導出。テーマ偏重の有無を示す）")
        lines.append(f"【セクター温度・最低】{cold['sector']}（平均{cold['avg']}）"
                     " — スコア下位。避けられている領域。")
    if not lines:
        lines.append("市場環境データを取得中。")
    return "\n".join(lines)


def _claude(financials, indicators):
    reg = indicators.get("regime")
    st = indicators.get("sector_temp") or []
    payload = {
        "model": NGS_MODEL,
        "max_tokens": 600,
        "system": (
            "あなたは市場全体を俯瞰するマクロ・アナリスト。"
            "与えられた実データ（地合いレジームとセクター別の客観スコア温度）だけを根拠に、"
            "いま市場のどこに機会が出ているかを日本語で簡潔に読み解く。"
            "3〜5行の箇条書き＋最後に1行の総括。特定銘柄の売買推奨や投資助言は避け、"
            "セクター・地合いの構造分析に徹する。"),
        "messages": [{
            "role": "user",
            "content": "data=" + json.dumps({
                "regime": reg,
                "sector_temp": st[:8],
            }, ensure_ascii=False),
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
