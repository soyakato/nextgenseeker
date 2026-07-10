"""客観ファクター計算（学術レポート準拠・実データのみ、主観/事前分布なし）.

  1. operating_leverage  営業レバレッジ(DOL)          Novy-Marx(2011): ΔOpInc%/ΔRev%
  2. cost_stickiness     コスト硬直性                 Weiss(2010): 費用の下方硬直性
  3. survival_dd         距離デフォルト(Merton naive)  Bharath-Shumway(2008): 市場ベース生存
  4. rnd_intensity       R&D強度                      Chan-Lakonishok-Sougiannis(2001): R&D/売上
  5. contrarian_inflection 逆張り変曲                  ドローダウン×前向き成長
  6. capital_momentum    時変ベータ/資金勢い           回転ベータ+機関保有+52週位置

全ファクターは財務諸表・株価から機械的に算出し、横断パーセンタイル正規化(0-100)する。
人手のキーワードや銘柄選定は一切用いない。値が取れない銘柄は中立50。
※ CDS乖離・特許全文LLM・完全なPiT遡及修正は無料データ範囲外のため未実装（UIで明示）。
"""
import math
import time
import numpy as np
import yfinance as yf
from config import BENCHMARK_SYMBOL

FACTORS = ["operating_leverage", "cost_stickiness", "survival_dd",
           "rnd_intensity", "contrarian_inflection", "capital_momentum"]


def _row(df, *names):
    """財務諸表DataFrameから候補名のいずれかの行(新しい順の配列)を返す."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            vals = [float(x) for x in df.loc[n].values if x is not None and not (isinstance(x, float) and math.isnan(x))]
            if len(vals) >= 2:
                return vals   # 新しい順
    return None


def _annual_pairs(series):
    """年次系列(新しい順)から連続ペア=(今期,前期)。年次の連続はYoYそのもの."""
    return [(series[i], series[i + 1]) for i in range(len(series) - 1)]


def _quarterly_yoy_pairs(series):
    """四半期系列(新しい順)から前年同期比ペア=(q[i], q[i+4])。
    前期比(QoQ)は季節性ノイズを注入するため使わない — YoYに統一する."""
    return [(series[i], series[i + 4]) for i in range(len(series) - 4)]


def _change_pairs(annual, quarterly):
    """年次連続＋四半期YoYの合算エピソード（全てYoYで頻度整合）."""
    pairs = []
    if annual and len(annual) >= 2:
        pairs += _annual_pairs(annual)
    if quarterly and len(quarterly) >= 5:
        pairs += _quarterly_yoy_pairs(quarterly)
    return pairs


def _dol_from_pairs(rev_pairs, op_pairs):
    """営業レバレッジ = ΔOpInc% / ΔRev% の中央値（YoYエピソード集合から）."""
    n = min(len(rev_pairs), len(op_pairs))
    dols = []
    for i in range(n):
        rc, rp = rev_pairs[i]
        oc, op_ = op_pairs[i]
        dr = (rc - rp) / abs(rp) if rp else None
        do = (oc - op_) / abs(op_) if op_ else None
        if dr and abs(dr) > 0.02 and do is not None:
            dols.append(max(-5, min(12, do / dr)))
    return float(np.median(dols)) if dols else None


def _stickiness_from_pairs(rev_pairs, cost_pairs):
    """Weiss型コスト硬直性: 売上増時と減時の費用弾力性の差(正=硬直的)。
    YoYエピソード合算で増減両方のサンプルを確保しやすくする."""
    n = min(len(rev_pairs), len(cost_pairs))
    up, down = [], []
    for i in range(n):
        rc, rp = rev_pairs[i]
        cc, cp = cost_pairs[i]
        if not rp or not cp:
            continue
        dr = (rc - rp) / abs(rp)
        dc = (cc - cp) / abs(cp)
        if abs(dr) < 0.02:
            continue
        elast = max(-8, min(8, dc / dr))
        (up if dr > 0 else down).append(elast)
    if not up or not down:
        return None
    return float(np.mean(up) - np.mean(down))


def _merton_dd(mktcap, cur_debt, lt_debt, total_debt, sigma_e, mu):
    """Bharath-Shumway(2008) naive Merton距離デフォルト. 高いほど安全.
    デフォルトポイントFはKMV慣行=短期負債+0.5×長期負債（総負債は過大なため）."""
    if not mktcap or mktcap <= 0:
        return None
    if cur_debt is not None or lt_debt is not None:
        F = (cur_debt or 0) + 0.5 * (lt_debt or 0)
    else:
        F = total_debt
    if not F or F <= 0:
        F = (total_debt if (total_debt and total_debt > 0) else mktcap * 0.01)
    V = mktcap + F
    sigma_e = sigma_e if (sigma_e and sigma_e > 0) else 0.4
    sigma_v = (mktcap / V) * sigma_e + (F / V) * (0.05 + 0.25 * sigma_e)   # naive資産ボラ
    mu = max(-0.5, min(0.8, mu if mu is not None else 0.0))
    try:
        dd = (math.log(V / F) + (mu - 0.5 * sigma_v ** 2)) / (sigma_v)
    except (ValueError, ZeroDivisionError):
        return None
    return max(-3, min(15, dd))


def _annualized_vol_and_ret(hist):
    if hist is None or len(hist) < 30:
        return None, None
    close = hist["Close"].dropna()
    rets = close.pct_change().dropna()
    if len(rets) < 20:
        return None, None
    vol = float(rets.std()) * math.sqrt(252)
    total_ret = float(close.iloc[-1] / close.iloc[0] - 1)
    return vol, total_ret


def _rolling_beta(stock_hist, spy_hist):
    """直近と3ヶ月前のベータを比較し、(現ベータ, ベータ上昇幅)を返す(時変ベータの近似)."""
    try:
        s = stock_hist["Close"].pct_change().dropna()
        m = spy_hist["Close"].pct_change().dropna()
        df = s.to_frame("s").join(m.to_frame("m"), how="inner").dropna()
        if len(df) < 80:
            return None, None
        def beta(win):
            sub = df.iloc[-win:]
            cov = np.cov(sub["s"], sub["m"])[0, 1]
            var = np.var(sub["m"])
            return cov / var if var > 0 else None
        b_now = beta(60)
        b_prev = beta(120)
        trend = (b_now - b_prev) if (b_now is not None and b_prev is not None) else None
        return b_now, trend
    except Exception:
        return None, None


def compute_raw(symbols, spy_hist):
    """各銘柄の生ファクター値(正規化前)を財務諸表・株価から機械的に計算. symbols: {id: yahoo_sym}."""
    raw = {tid: {f: None for f in FACTORS} for tid in symbols}
    for tid, sym in symbols.items():
        try:
            tk = yf.Ticker(sym)
            inc = getattr(tk, "income_stmt", None)
            qinc = getattr(tk, "quarterly_income_stmt", None)
            bs = getattr(tk, "balance_sheet", None)
            info = tk.info

            # 年次＋四半期の両方を取得（変化エピソードは全てYoYで頻度整合）
            rev_a = _row(inc, "Total Revenue", "Operating Revenue")
            rev_q = _row(qinc, "Total Revenue", "Operating Revenue")
            op_a = _row(inc, "Total Operating Income As Reported", "Operating Income", "EBIT")
            op_q = _row(qinc, "Total Operating Income As Reported", "Operating Income", "EBIT")
            cost_a = _row(inc, "Total Expenses", "Reconciled Cost Of Revenue", "Cost Of Revenue")
            cost_q = _row(qinc, "Total Expenses", "Reconciled Cost Of Revenue", "Cost Of Revenue")
            rnd = _row(inc, "Research And Development")
            rev = rev_a or rev_q

            debt_row = _row(bs, "Total Debt", "Net Debt")
            total_debt = debt_row[0] if debt_row else info.get("totalDebt")
            cur_row = _row(bs, "Current Debt", "Current Debt And Capital Lease Obligation")
            lt_row = _row(bs, "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
            cur_debt = cur_row[0] if cur_row else None
            lt_debt = lt_row[0] if lt_row else None

            hist = tk.history(period="1y")
            vol, ret1y = _annualized_vol_and_ret(hist)
            b_now, b_trend = _rolling_beta(hist, spy_hist)

            rev_pairs = _change_pairs(rev_a, rev_q)
            raw[tid]["operating_leverage"] = _dol_from_pairs(rev_pairs, _change_pairs(op_a, op_q))
            raw[tid]["cost_stickiness"] = _stickiness_from_pairs(rev_pairs, _change_pairs(cost_a, cost_q))
            raw[tid]["survival_dd"] = _merton_dd(info.get("marketCap"), cur_debt, lt_debt,
                                                 total_debt, vol, ret1y)
            # R&D強度 = R&D費/売上。損益計算書にR&D行が無い場合は「不明」ではなく
            # 経済的にゼロとして採点する（Chan et al. 系ファクター研究の標準慣行。
            # 中立50に置くと無投資企業が実投資下位企業より上位に来る歪みが生じるため）
            if rev and rev[0]:
                raw[tid]["rnd_intensity"] = (rnd[0] / rev[0] * 100) if rnd else 0.0

            dd = info.get("fiftyTwoWeekHigh")
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            drawdown = (1 - price / dd) if (price and dd and dd > 0) else None
            g = info.get("revenueGrowth")
            if drawdown is not None:
                mult = max(0.4, min(1.4, 0.55 + (g or 0)))
                raw[tid]["contrarian_inflection"] = drawdown * 100 * mult
            # 資金勢い: 機関保有 + 52週位置 + 時変ベータ上昇
            inst = info.get("heldPercentInstitutions")
            lo = info.get("fiftyTwoWeekLow")
            pos = ((price - lo) / (dd - lo)) if (price and dd and lo and dd > lo) else None
            comps = [x for x in [
                (inst * 100 if inst is not None else None),
                (pos * 100 if pos is not None else None),
                (50 + b_trend * 100) if b_trend is not None else None,
            ] if x is not None]
            raw[tid]["capital_momentum"] = (sum(comps) / len(comps)) if comps else None
            raw[tid]["_diag"] = {"beta": round(b_now, 2) if b_now else None,
                                 "beta_trend": round(b_trend, 3) if b_trend is not None else None,
                                 "vol": round(vol, 2) if vol else None,
                                 "debt": total_debt}
            print(f"  [fac] {tid:7s} DOL={_fmt(raw[tid]['operating_leverage'])} "
                  f"stick={_fmt(raw[tid]['cost_stickiness'])} DD={_fmt(raw[tid]['survival_dd'])} "
                  f"contra={_fmt(raw[tid]['contrarian_inflection'])}")
        except Exception as e:
            print(f"  [fac] {tid:7s} ERROR {repr(e)[:80]}")
        time.sleep(0.5)
    return raw


def _fmt(v):
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def percentile_normalize(raw):
    """各ファクターを横断的に0-100パーセンタイルへ.
    同値タイは平均ランク（恣意的な順位差を排除）。真の欠損のみ中立50."""
    norm = {tid: {} for tid in raw}
    for f in FACTORS:
        vals = [(tid, raw[tid].get(f)) for tid in raw if raw[tid].get(f) is not None]
        if len(vals) < 2:
            for tid in raw:
                norm[tid][f] = 50.0
            continue
        ordered = sorted(vals, key=lambda x: x[1])
        n = len(ordered)
        rank = {}
        i = 0
        while i < n:
            j = i
            while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
                j += 1
            pct = round(100 * ((i + j) / 2) / (n - 1), 1)   # タイ区間の平均ランク
            for k in range(i, j + 1):
                rank[ordered[k][0]] = pct
            i = j + 1
        for tid in raw:
            norm[tid][f] = rank.get(tid, 50.0)
    return norm
