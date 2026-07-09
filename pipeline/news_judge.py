"""ニュース判定層 — Claude API（キー設定時）＋ルールベース（常時動作）.

先読み/ブランドバイアス対策（クオンツレポートの教訓）:
  LLMに渡す前に企業名・ティッカーを「X社」にマスキングする（ディストラクション効果の遮断）。
  LLMは「この見出しの内容そのもの」だけで方向と強さを判定する。

出力（1見出しあたり）: {dir: -1..+1, conf: 0..1, type: イベント種別, why: 一言}
銘柄集約: news_score 0-100（方向×確信度の新しさ加重平均を50中心にスケール）
"""
import re
import json
import requests
from config import ANTHROPIC_API_KEY, NGS_MODEL, REQUEST_TIMEOUT

# ── ルールベース辞書（英語ニュース向け・機械的） ──
_POS = {
    r"\bbeat(s|ing)?\b|\btops? estimates\b|\babove (estimates|expectations)\b": (0.8, "決算ビート"),
    r"\braise[sd]? (guidance|outlook|forecast)\b|\bhike[sd]? (guidance|outlook)\b": (0.9, "ガイダンス引上げ"),
    r"\bcontract\b|\bdeal\b|\bpartnership\b|\bcollaborat|\bagreement\b": (0.6, "契約・提携"),
    r"\bupgrade[sd]?\b|\bprice target (raise|hike|boost)\b|\boverweight\b|\bbuy rating\b": (0.6, "格上げ"),
    r"\bbuyback\b|\brepurchase\b|\bdividend (increase|hike)\b": (0.5, "株主還元"),
    r"\brecord (revenue|profit|sales|quarter)\b|\ball-time high\b": (0.7, "記録更新"),
    r"\bapproval\b|\bapproved\b|\bclearance\b|\bgreen ?light\b": (0.7, "承認"),
    r"\bwins?\b|\bawarded\b|\bsecures?\b": (0.5, "受注"),
    r"\bexpand(s|ing)?\b|\bnew (product|chip|platform|factory|fab)\b|\blaunch(es|ed)?\b": (0.4, "拡大・新製品"),
    r"\bsurge[sd]?\b|\bsoar(s|ed)?\b|\brall(y|ies|ied)\b|\bjump(s|ed)?\b": (0.3, "急騰報道"),
}
_NEG = {
    r"\bmiss(es|ed)?\b|\bbelow (estimates|expectations)\b|\bfalls? short\b": (0.8, "決算ミス"),
    r"\bcut[s]? (guidance|outlook|forecast)\b|\blower(s|ed)? (guidance|outlook)\b": (0.9, "ガイダンス引下げ"),
    r"\blawsuit\b|\bsued?\b|\bprobe\b|\binvestigat|\bsubpoena\b|\bfraud\b": (0.8, "訴訟・調査"),
    r"\bdowngrade[sd]?\b|\bunderweight\b|\bsell rating\b|\bprice target cut\b": (0.6, "格下げ"),
    r"\brecall\b|\bdefect\b|\bhalt(s|ed)?\b|\bsuspend(s|ed)?\b": (0.7, "リコール・停止"),
    r"\blayoffs?\b|\bjob cuts\b|\brestructur": (0.4, "リストラ"),
    r"\bresign(s|ed|ation)\b|\bsteps? down\b|\bdeparture\b": (0.4, "経営陣退任"),
    r"\bplunge[sd]?\b|\btumble[sd]?\b|\bsink(s|ing)?\b|\bcrash(es|ed)?\b|\bsell-?off\b": (0.4, "急落報道"),
    r"\bshort(s|ed| seller| report)\b|\bovervalued\b|\bbubble\b": (0.4, "空売り・過大評価"),
    r"\btariffs?\b|\bexport (ban|control|restriction)\b|\bsanction": (0.5, "規制・関税"),
}


def _mask(text, ticker, name):
    """企業名・ティッカーを X社 にマスキング（LLMの事前知識バイアス遮断）."""
    out = text
    if name:
        # 会社名の主要語（Inc等の法人格を除く先頭2語まで）をマスク
        words = [w for w in re.split(r"[,\s]+", name)
                 if w and w.lower() not in ("inc", "inc.", "corp", "corp.", "corporation",
                                            "ltd", "ltd.", "co", "co.", "plc", "the",
                                            "group", "holdings", "technologies", "technology")]
        for w in words[:2]:
            if len(w) >= 3:
                out = re.sub(re.escape(w), "X社", out, flags=re.IGNORECASE)
    out = re.sub(rf"\b{re.escape(ticker)}\b", "X社", out)
    return out


def _rule_judge(title, summary):
    text = f"{title} {summary}".lower()
    score, hits = 0.0, []
    for pat, (w, label) in _POS.items():
        if re.search(pat, text):
            score += w
            hits.append(f"+{label}")
    for pat, (w, label) in _NEG.items():
        if re.search(pat, text):
            score -= w
            hits.append(f"-{label}")
    d = max(-1.0, min(1.0, score))
    return {"dir": round(d, 2), "conf": min(1.0, abs(score)) if hits else 0.15,
            "type": hits[0].lstrip("+-") if hits else "一般",
            "why": " ".join(hits[:3]) if hits else "特定イベント検出なし"}


def _claude_judge(masked_items):
    """匿名化済み見出し群をまとめて1リクエストで判定（JSON配列で返させる）."""
    numbered = "\n".join(f"{i+1}. {it}" for i, it in enumerate(masked_items))
    payload = {
        "model": NGS_MODEL, "max_tokens": 1200,
        "system": ("あなたは株式ニュースの触媒判定器。企業名は匿名化済み(X社)。"
                   "見出し内容だけから各項目を判定し、JSON配列のみを出力せよ。"
                   '各要素: {"i":番号,"dir":-1〜1の方向,"conf":0〜1の確信度,'
                   '"type":"決算/契約/規制/不祥事/製品/格付/株主還元/マクロ/その他","why":"日本語一言"}'),
        "messages": [{"role": "user", "content": numbered}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": ANTHROPIC_API_KEY,
                               "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      data=json.dumps(payload), timeout=REQUEST_TIMEOUT * 3)
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


def judge_all(news_by_ticker, name_map):
    """全ウォッチ銘柄のニュースを判定し、銘柄別スコアと明細を返す."""
    results = {}
    use_claude = bool(ANTHROPIC_API_KEY)
    source = f"claude:{NGS_MODEL}" if use_claude else "rule-based"

    for t, items in news_by_ticker.items():
        judged = []
        if items and use_claude:
            try:
                masked = [_mask(f'{n["title"]}. {n["summary"][:150]}', t, name_map.get(t, "")) for n in items]
                arr = _claude_judge(masked)
                by_i = {a.get("i"): a for a in arr if isinstance(a, dict)}
                for i, n in enumerate(items):
                    a = by_i.get(i + 1)
                    j = ({"dir": max(-1, min(1, float(a.get("dir", 0)))),
                          "conf": max(0, min(1, float(a.get("conf", 0)))),
                          "type": str(a.get("type", "その他"))[:12],
                          "why": str(a.get("why", ""))[:60]} if a
                         else _rule_judge(n["title"], n["summary"]))
                    judged.append({**n, **j})
            except Exception as e:
                print(f"  [judge] {t} Claude失敗→ルールベース: {repr(e)[:60]}")
                source = "rule-based (claude-fallback)"
                judged = [{**n, **_rule_judge(n["title"], n["summary"])} for n in items]
        else:
            judged = [{**n, **_rule_judge(n["title"], n["summary"])} for n in items]

        results[t] = {"score": aggregate_score(judged), "items": judged, "n": len(judged)}
    return results, source


def aggregate_score(items):
    """銘柄集約: 方向×確信度の平均を0-100へ（50=中立）。
    一次情報(EDGAR)は2倍重み。件数が少ないほど中立へ縮小（過信防止）."""
    if not items:
        return 50.0
    num, den = 0.0, 0.0
    for j in items:
        w = 2.0 if j.get("is_edgar") else 1.0
        num += j["dir"] * j["conf"] * w
        den += w
    raw = num / den
    shrink = min(1.0, den / 4)
    return round(max(0, min(100, 50 + raw * 50 * shrink)), 1)
