"""ウォッチ＆兆候レーダー — 継続選出の機械的検出とアラートの遅延採点.

ウォッチ選定は完全に機械的（私が銘柄を選ばない）:
  確定ウォッチ: 連続WATCH_STREAK_DAYS日以上選出 or 直近WATCH_WINDOW日でWATCH_APPEAR_MIN回出現
  仮ウォッチ:   当日ランキング上位WATCH_PROVISIONAL_RANK位以内（履歴が浅い初期でも機能）

兆候スコア = 継続性(30%) + ニュース触媒(40%) + 価格/出来高確認(30%) の機械的合成。
ALERT_THRESHOLD以上のアラートは価格つきで台帳に記録し、5/20営業日後にSPY超過で採点、
的中率をUIに表示する（アラート層それ自体も自己検証される）。
"""
import os
import json
import datetime as dt
import numpy as np

from config import (LIVE_DIR, WATCH_STREAK_DAYS, WATCH_APPEAR_MIN, WATCH_WINDOW_DAYS,
                    WATCH_PROVISIONAL_RANK, WATCH_MAX, ALERT_THRESHOLD)

STATE_PATH = os.path.join(LIVE_DIR, "watch_state.json")
ALERT_HORIZONS = [5, 20]   # 営業日


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tickers": {}, "alerts": []}


def save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def _busdays(d0, d1):
    try:
        return int(np.busday_count(d0, d1))
    except Exception:
        return 0


def update_appearances(st, today, ranked_tickers):
    """今日のランキング（順位順のticker列）を出現履歴に記録."""
    for rank, t in enumerate(ranked_tickers, 1):
        e = st["tickers"].setdefault(t, {"dates": {}, "first_seen": today})
        e["dates"][today] = min(rank, e["dates"].get(today, 999))
    # 古い履歴の掃除（WATCH_WINDOW_DAYSの3倍で忘却）
    cutoff = (dt.date.today() - dt.timedelta(days=WATCH_WINDOW_DAYS * 3)).isoformat()
    for t in list(st["tickers"]):
        e = st["tickers"][t]
        e["dates"] = {d: r for d, r in e["dates"].items() if d >= cutoff}
        if not e["dates"]:
            del st["tickers"][t]


def _streak(dates_sorted, today):
    """今日から遡る連続選出日数（暦日ベース、土日ギャップは許容）."""
    if today not in dates_sorted:
        return 0
    streak, cur = 1, dt.date.fromisoformat(today)
    ds = set(dates_sorted)
    while True:
        prev = cur - dt.timedelta(days=1)
        # 土日を跨いで最大3日まで遡って探す（週末に選出は起きないため）
        found = None
        for back in range(1, 4):
            cand = cur - dt.timedelta(days=back)
            if cand.isoformat() in ds:
                found = cand
                break
        if found is None:
            break
        streak += 1
        cur = found
    return streak


def select_watchlist(st, today, today_ranks):
    """機械的基準でウォッチ対象を選ぶ. today_ranks: {ticker: 今日の順位}."""
    window_cut = (dt.date.today() - dt.timedelta(days=WATCH_WINDOW_DAYS)).isoformat()
    out = []
    for t, e in st["tickers"].items():
        dates = sorted(e["dates"].keys())
        recent = [d for d in dates if d >= window_cut]
        streak = _streak(dates, today)
        best_rank = min(e["dates"].values()) if e["dates"] else None
        tier = None
        if streak >= WATCH_STREAK_DAYS or len(recent) >= WATCH_APPEAR_MIN:
            tier = "確定"
        elif today_ranks.get(t) and today_ranks[t] <= WATCH_PROVISIONAL_RANK:
            tier = "仮"
        if tier:
            out.append({
                "ticker": t, "tier": tier, "streak": streak,
                "appearances": len(recent), "best_rank": best_rank,
                "today_rank": today_ranks.get(t), "first_seen": e.get("first_seen"),
            })
    # 確定優先→連続日数→当日順位 で並べ、上限まで
    out.sort(key=lambda x: (x["tier"] != "確定", -x["streak"], x["today_rank"] or 999))
    return out[:WATCH_MAX]


def persistence_score(w):
    """継続性 0-100（機械式・開示）: 連続日数と出現回数を線形加点."""
    s = min(60, w["streak"] * 20) + min(40, w["appearances"] * 10)
    return min(100, s)


def confirmation_score(mom):
    """価格/出来高確認 0-100: 5日リターンと出来高サージから（momはfactors診断由来）."""
    if not mom:
        return 50.0
    s = 50.0
    r5 = mom.get("ret5")
    vs = mom.get("vol_surge")
    if r5 is not None:
        s += max(-30, min(30, r5 * 300))          # +10%で+30
    if vs is not None and vs > 0:
        s += max(-10, min(20, (vs - 1) * 15))     # 出来高2倍で+15
    return max(0, min(100, s))


COMPOSITION_BASE = {"persist": 0.30, "news": 0.40, "confirm": 0.30}
COMP_MIN_SAMPLES = 10       # ウォッチ採点がこの件数未満なら構成比は不動
COMP_MULT_MIN, COMP_MULT_MAX = 0.5, 1.6


def composite_signal(persist, news, confirm, comp=None):
    """兆候スコア = 継続/ニュース/確認の加重合成。compは学習済み構成比（無ければ基準値）."""
    c = comp or COMPOSITION_BASE
    return round(persist * c["persist"] + news * c["news"] + confirm * c["confirm"], 1)


# ── ウォッチ・コホート: 全ウォッチ銘柄を毎日記録→採点→構成比を学習 ──
# （アラートのみの採点は選択バイアスがかかるため、母集団全体で学習する）

def record_watch_cohort(st, today, signals, price_map, spy_price):
    """今日のウォッチ全銘柄を構成要素つきでコホート記録（同日1回）."""
    cohorts = st.setdefault("watch_cohorts", [])
    if any(c["date"] == today for c in cohorts):
        return False
    entries = {}
    for s in signals:
        p = price_map.get(s["ticker"])
        if p:
            entries[s["ticker"]] = {"persist": s["persist"], "news": s["news"],
                                    "confirm": s["confirm"], "signal": s["signal"], "price": p}
    if not entries:
        return False
    cohorts.append({"date": today, "spy": spy_price, "entries": entries, "grades": {}})
    cutoff = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    st["watch_cohorts"] = [c for c in cohorts if c["date"] >= cutoff]
    return True


def grade_watch_cohorts(st, price_now, spy_now):
    """満期ウォッチ・コホートをSPY超過で採点."""
    today = dt.date.today().isoformat()
    n = 0
    for c in st.get("watch_cohorts", []):
        elapsed = _busdays(c["date"], today)
        for H in ALERT_HORIZONS:
            k = str(H)
            if k in c["grades"] or elapsed < H:
                continue
            if not (c.get("spy") and spy_now):
                continue
            spy_ret = spy_now / c["spy"] - 1
            g = {}
            for t, e in c["entries"].items():
                p = price_now.get(t)
                if p and e.get("price"):
                    g[t] = round((p / e["price"] - 1) - spy_ret, 4)
            if g:
                c["grades"][k] = g
                n += 1
    return n


def pending_watch_tickers(st):
    out = set()
    for c in st.get("watch_cohorts", []):
        if any(str(H) not in c["grades"] for H in ALERT_HORIZONS):
            out.update(c["entries"].keys())
    return out


def _spearman(xs, ys):
    if len(xs) < 5:
        return None
    def rank(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0] * len(a)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def learn_composition(st):
    """構成要素別IC → 兆候スコア構成比を学習（既存と同じガードレール:
    クランプ×0.5〜1.6・120日忘却・COMP_MIN_SAMPLES未満は不動・正規化）."""
    pairs = {k: {"x": [], "y": []} for k in COMPOSITION_BASE}
    graded = 0
    for c in st.get("watch_cohorts", []):
        for H, g in c["grades"].items():
            for t, excess in g.items():
                e = c["entries"].get(t)
                if not e:
                    continue
                graded += 1
                for k in COMPOSITION_BASE:
                    pairs[k]["x"].append(e[k])
                    pairs[k]["y"].append(excess)
    ic = {k: _spearman(pairs[k]["x"], pairs[k]["y"]) for k in COMPOSITION_BASE}
    active = graded >= COMP_MIN_SAMPLES
    comp, mults = {}, {}
    for k, base in COMPOSITION_BASE.items():
        if active and ic[k] is not None:
            m = max(COMP_MULT_MIN, min(COMP_MULT_MAX, 1 + 0.15 * (ic[k] / 0.1)))
        else:
            m = 1.0
        mults[k] = round(m, 3)
        comp[k] = base * m
    tot = sum(comp.values()) or 1
    comp = {k: round(v / tot, 3) for k, v in comp.items()}   # 合計1に正規化
    return {"composition": comp, "ic": {k: (round(v, 3) if v is not None else None) for k, v in ic.items()},
            "multipliers": mults, "graded_samples": graded, "active": active,
            "min_samples": COMP_MIN_SAMPLES}


def record_alerts(st, today, signals, price_map, spy_price):
    """兆候スコアが閾値以上のものをアラート台帳に記録（同銘柄・同日は1回）."""
    existing = {(a["date"], a["ticker"]) for a in st["alerts"]}
    n = 0
    for s in signals:
        if s["signal"] < ALERT_THRESHOLD:
            continue
        key = (today, s["ticker"])
        if key in existing or not price_map.get(s["ticker"]):
            continue
        st["alerts"].append({
            "date": today, "ticker": s["ticker"], "signal": s["signal"],
            "price": price_map[s["ticker"]], "spy": spy_price, "grades": {},
        })
        n += 1
    # 忘却: 120日超のアラートは捨てる
    cutoff = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    st["alerts"] = [a for a in st["alerts"] if a["date"] >= cutoff]
    return n


def grade_alerts(st, price_now, spy_now):
    """満期アラートをSPY超過リターンで採点し、的中率サマリを返す."""
    today = dt.date.today()
    for a in st["alerts"]:
        d0 = dt.date.fromisoformat(a["date"])
        elapsed = _busdays(d0.isoformat(), today.isoformat())
        for H in ALERT_HORIZONS:
            k = str(H)
            if k in a["grades"] or elapsed < H:
                continue
            p_now = price_now.get(a["ticker"])
            if p_now and a.get("price") and a.get("spy") and spy_now:
                excess = (p_now / a["price"] - 1) - (spy_now / a["spy"] - 1)
                a["grades"][k] = round(excess, 4)
    # サマリ
    summary = {}
    for H in ALERT_HORIZONS:
        vals = [a["grades"][str(H)] for a in st["alerts"] if str(H) in a["grades"]]
        if vals:
            summary[str(H)] = {
                "n": len(vals),
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 2),
                "avg_excess": round(float(np.mean(vals)), 4),
            }
    return summary


def pending_alert_tickers(st):
    return {a["ticker"] for a in st["alerts"]
            if any(str(H) not in a["grades"] for H in ALERT_HORIZONS)}
