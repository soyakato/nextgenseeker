"""自己改善ループ（trend_radar の設計思想を先見フレームワークに移植）.

  1. 記録: 実行ごと（日次で重複排除）に各銘柄の6原理スコア＋株価＋ベンチ価格を台帳に残す
  2. 採点: GRADE_HORIZONS(営業日)が経過したコホートを、市場(SPY)超過リターンで機械採点
  3. IC:  原理別に「スコア → その後の超過リターン」の順位相関(Spearman)を測る
  4. 調整: ICに応じて原理の重みを事前分布から0.5〜1.6倍の範囲で緩やかに更新

ガラパゴス化防止:
  - MIN_GRADED_SAMPLES 未満なら一切動かさない（結果が出るまで不動）
  - FORGET_DAYS より古い採点は忘却（同じトレンドは繰り返さない）
  - 倍率は WEIGHT_MULT_MIN..MAX にクランプ（事前分布を錨に）
"""
import os
import json
import datetime as dt
import numpy as np

from config import (GRADE_HORIZONS, FORGET_DAYS, MIN_GRADED_SAMPLES,
                    WEIGHT_MULT_MIN, WEIGHT_MULT_MAX, LEARN_STEP, LIVE_DIR)
from factors import FACTORS

LEDGER_PATH = os.path.join(LIVE_DIR, "learning_ledger.json")

# 客観ファクターの既定ウェイト（学術的な頑健性を反映した中立初期値・計100）
DEFAULT_WEIGHTS = {"operating_leverage": 18, "cost_stickiness": 10, "survival_dd": 18,
                   "rnd_intensity": 14, "contrarian_inflection": 14, "capital_momentum": 13,
                   "holding_trend": 13}

# fp.PILLARS の後方互換
class _FP:
    PILLARS = FACTORS
fp = _FP()


def load_ledger():
    if os.path.exists(LEDGER_PATH):
        try:
            with open(LEDGER_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"cohorts": []}


def save_ledger(led):
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=2)


def pending_tickers(led):
    """未採点horizonが残る全コホートのティッカー集合（ユニバース離脱後も追跡採点するため）."""
    out = set()
    for c in led["cohorts"]:
        if any(str(H) not in c["grades"] for H in GRADE_HORIZONS):
            out.update(c["picks"].keys())
    return out


def _busdays(d0, d1):
    try:
        return int(np.busday_count(d0.isoformat(), d1.isoformat()))
    except Exception:
        return (d1 - d0).days * 5 // 7


def record_cohort(led, today_iso, picks, bench_price):
    """今日のコホートを記録（同日に既にあればスキップ）. picks: {t:{composite,pillars,price}}."""
    today = today_iso[:10]
    if any(c["date"] == today for c in led["cohorts"]):
        return False
    led["cohorts"].append({
        "date": today, "bench_price": bench_price,
        "picks": picks, "grades": {},   # grades[str(horizon)] = {ticker: excess}
    })
    # 忘却: FORGET_DAYS より古いコホートは捨てる
    cutoff = (dt.date.today() - dt.timedelta(days=FORGET_DAYS)).isoformat()
    led["cohorts"] = [c for c in led["cohorts"] if c["date"] >= cutoff]
    return True


def grade(led, price_now, bench_now):
    """満期を迎えたコホートを市場超過リターンで採点."""
    today = dt.date.today()
    graded_events = 0
    for c in led["cohorts"]:
        d0 = dt.date.fromisoformat(c["date"])
        elapsed = _busdays(d0, today)
        b0 = c.get("bench_price")
        for H in GRADE_HORIZONS:
            key = str(H)
            if key in c["grades"]:
                continue
            if elapsed < H:
                continue
            if not b0 or not bench_now:
                continue
            bench_ret = bench_now / b0 - 1
            g = {}
            for t, pk in c["picks"].items():
                p0 = pk.get("price")
                pn = price_now.get(t)
                if p0 and pn:
                    g[t] = round((pn / p0 - 1) - bench_ret, 4)   # 市場超過リターン
            if g:
                c["grades"][key] = g
                graded_events += 1
    return graded_events


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
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def compute_learning(led):
    """原理別ICと、事前分布から0.5〜1.6倍にクランプした学習済み重みを返す."""
    cutoff = (dt.date.today() - dt.timedelta(days=FORGET_DAYS)).isoformat()
    # 原理ごとに (スコア, 超過リターン) を全採点済みコホートから収集
    pairs = {p: {"x": [], "y": []} for p in fp.PILLARS}
    comp_pairs = {"x": [], "y": []}
    graded_samples = 0
    for c in led["cohorts"]:
        if c["date"] < cutoff:
            continue
        for H, g in c["grades"].items():
            for t, excess in g.items():
                pk = c["picks"].get(t)
                if not pk:
                    continue
                graded_samples += 1
                pil = pk.get("pillars", {})
                for p in fp.PILLARS:
                    if p in pil:
                        pairs[p]["x"].append(pil[p])
                        pairs[p]["y"].append(excess)
                if pk.get("composite") is not None:
                    comp_pairs["x"].append(pk["composite"])
                    comp_pairs["y"].append(excess)

    ic = {p: _spearman(pairs[p]["x"], pairs[p]["y"]) for p in fp.PILLARS}
    comp_ic = _spearman(comp_pairs["x"], comp_pairs["y"])

    active = graded_samples >= MIN_GRADED_SAMPLES
    weights, mults = {}, {}
    for p in fp.PILLARS:
        base = DEFAULT_WEIGHTS[p]
        if active and ic[p] is not None:
            # IC 0.1 で約 +0.15 倍。緩やかに、範囲は事前分布の0.5〜1.6倍
            mult = 1 + LEARN_STEP * (ic[p] / 0.1)
            mult = max(WEIGHT_MULT_MIN, min(WEIGHT_MULT_MAX, mult))
        else:
            mult = 1.0
        mults[p] = round(mult, 3)
        weights[p] = round(base * mult, 2)

    return {
        "weights": weights,
        "default_weights": DEFAULT_WEIGHTS,
        "multipliers": mults,
        "ic": {p: (round(v, 3) if v is not None else None) for p, v in ic.items()},
        "composite_ic": (round(comp_ic, 3) if comp_ic is not None else None),
        "graded_samples": graded_samples,
        "active": active,
        "min_samples": MIN_GRADED_SAMPLES,
        "horizons": GRADE_HORIZONS,
        "forget_days": FORGET_DAYS,
        "cohorts_tracked": len(led["cohorts"]),
        "note": ("学習作動中（採点結果で重みを調整）" if active
                 else f"結果待ち: 採点サンプル {graded_samples}/{MIN_GRADED_SAMPLES} — "
                      f"貯まるまで重みは事前分布のまま動かさない"),
    }
