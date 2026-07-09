"""集中(ガラパゴス)ガード. 銘柄発見は universe.py に統合済み。"""


def concentration_guard(ranked_with_sector, top_n, threshold):
    """上位N銘柄のセクター集中(HHI的)を測り、ガラパゴス化を警告."""
    top = ranked_with_sector[:top_n]
    if len(top) < max(5, top_n // 2):
        return {"warn": False, "note": "サンプル不足"}
    counts = {}
    for _, sector in top:
        s = sector or "不明"
        counts[s] = counts.get(s, 0) + 1
    sec, n = max(counts.items(), key=lambda kv: kv[1])
    ratio = n / len(top)
    hhi = sum((v / len(top)) ** 2 for v in counts.values())
    warn = ratio >= threshold and n >= 3
    return {
        "warn": warn, "dominant_sector": sec, "dominant_ratio": round(ratio, 2),
        "hhi": round(hhi, 3), "top_n": len(top),
        "note": (f"⚠ 上位{len(top)}銘柄中{n}が「{sec}」に集中（{ratio:.0%}）— 過剰適応/テーマ偏りの兆候。"
                 "一緒に上げ下げする点に注意。" if warn
                 else f"分散は健全（最大セクター{sec} {ratio:.0%}, HHI {hhi:.2f}）"),
    }
