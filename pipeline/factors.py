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


def _yoy_pairs(series):
    """新しい順の系列から (今期, 前期) のYoYペア列を返す（古い→新しいの変化）."""
    pairs = []
    for i in range(len(series) - 1):
        cur, prev = series[i], series[i + 1]
        pairs.append((cur, prev))
    return pairs


def _dol(rev, opinc):
    """営業レバレッジ = ΔOpInc% / ΔRev% の中央値."""
    if not rev or not opinc:
        return None
    n = min(len(rev), len(opinc))
    rev, opinc = rev[:n], opinc[:n]
    dols = []
    for i in range(n - 1):
        dr = (rev[i] - rev[i + 1]) / abs(rev[i + 1]) if rev[i + 1] else None
        do = (opinc[i] - opinc[i + 1]) / abs(opinc[i + 1]) if opinc[i + 1] else None
        if dr and abs(dr) > 0.02 and do is not None:
            dols.append(do / dr)
    if not dols:
        return None
    return float(np.median([max(-5, min(12, d)) for d in dols]))


def _stickiness(rev, cost):
    """Weiss型コスト硬直性: 売上増時と減時の費用弾力性の差(正=硬直的)."""
    if not rev or not cost:
        return None
    n = min(len(rev), len(cost))
    rev, cost = rev[:n], cost[:n]
    up, down = [], []
    for i in range(n - 1):
        dr = (rev[i] - rev[i + 1]) / abs(rev[i + 1]) if rev[i + 1] else 0
        dc = (cost[i] - cost[i + 1]) / abs(cost[i + 1]) if cost[i + 1] else 0
        if abs(dr) < 0.02:
            continue
        elast = dc / dr
        (up if dr > 0 else down).append(elast)
    if not up or not down:
        return None
    # 売上増時の弾力性 > 売上減時の弾力性 なら硬直的（コストが減りにくい）
    return float(np.mean(up) - np.mean(down))


def _merton_dd(mktcap, total_debt, sigma_e, mu):
    """Bharath-Shumway(2008) naive Merton距離デフォルト. 高いほど安全."""
    if not mktcap or mktcap <= 0:
        return None
    F = total_debt if (total_debt and total_debt > 0) else mktcap * 0.01
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

            rev = _row(inc, "Total Revenue", "Operating Revenue") or _row(qinc, "Total Revenue")
            opinc = (_row(inc, "Total Operating Income As Reported", "Operating Income", "EBIT")
                     or _row(qinc, "Operating Income", "EBIT"))
            cost = (_row(inc, "Total Expenses", "Reconciled Cost Of Revenue", "Cost Of Revenue")
                    or _row(qinc, "Total Expenses"))
            rnd = _row(inc, "Research And Development")
            debt_row = _row(bs, "Total Debt", "Net Debt")
            total_debt = debt_row[0] if debt_row else info.get("totalDebt")

            hist = tk.history(period="1y")
            vol, ret1y = _annualized_vol_and_ret(hist)
            b_now, b_trend = _rolling_beta(hist, spy_hist)

            raw[tid]["operating_leverage"] = _dol(rev, opinc)
            raw[tid]["cost_stickiness"] = _stickiness(rev, cost)
            raw[tid]["survival_dd"] = _merton_dd(info.get("marketCap"), total_debt, vol, ret1y)
            # R&D強度 = R&D費 / 売上（客観・自動。人手のキーワード不要）
            raw[tid]["rnd_intensity"] = (rnd[0] / rev[0] * 100) if (rnd and rev and rev[0]) else None

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
    """各ファクターを横断的に0-100パーセンタイルへ. 欠損は中立50."""
    norm = {tid: {} for tid in raw}
    for f in FACTORS:
        vals = [(tid, raw[tid].get(f)) for tid in raw if raw[tid].get(f) is not None]
        if len(vals) < 2:
            for tid in raw:
                norm[tid][f] = 50.0
            continue
        ordered = sorted(vals, key=lambda x: x[1])
        n = len(ordered)
        rank = {tid: round(100 * i / (n - 1), 1) for i, (tid, _) in enumerate(ordered)}
        for tid in raw:
            norm[tid][f] = rank.get(tid, 50.0)
    return norm
