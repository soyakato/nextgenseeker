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
import datetime as dt
import numpy as np
import yfinance as yf
import fetch_tiingo
import fetch_fmp
from config import BENCHMARK_SYMBOL

FACTORS = ["operating_leverage", "cost_stickiness", "survival_dd",
           "rnd_intensity", "contrarian_inflection", "capital_momentum",
           "holding_trend", "earnings_drift"]


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


def _holding_trend(volume):
    """保有期間トレンド = 推定保有期間(発行株数/平均出来高)の前年比変化%.
    HP比では発行株数が相殺されるため ADV20(1年前)/ADV20(現在) で計算できる。
    正=保有期間が延伸（回転低下=長期保有者の買い集め・安定化）、負=回転上昇（投機化）.
    Tiingo 2年系列が主・yfinance 1年系列は最古20日窓で代替（240営業日以上必要）."""
    v = [x for x in volume if x]
    if len(v) < 240:
        return None
    adv_now = float(np.mean(v[-20:]))
    adv_prev = float(np.mean(v[-260:-240])) if len(v) >= 260 else float(np.mean(v[:20]))
    if adv_now <= 0 or adv_prev <= 0:
        return None
    return max(-80.0, min(300.0, (adv_prev / adv_now - 1) * 100))


def _ad_accum(close, high, low, volume, window=60):
    """Chaikin A/D蓄積比率(-1〜+1): 日中どこで引けたか×出来高の総和/総出来高.
    正=高値圏引け多発（買い集めの足跡）、負=安値圏引け多発（分散）."""
    n = min(len(close), len(high), len(low), len(volume))
    if n < window + 2:
        return None
    mfv = tot = 0.0
    for i in range(n - window, n):
        c, h, l, v = close[i], high[i], low[i], volume[i]
        if None in (c, h, l, v) or not v:
            continue
        rng = h - l
        mult = ((c - l) - (h - c)) / rng if rng > 0 else 0.0
        mfv += mult * v
        tot += v
    return (mfv / tot) if tot > 0 else None


def _earnings_drift_yf(tk):
    """PEAD主データ源: yfinance earnings_dates（全銘柄カバー・Surprise(%)算出済み）.
    返り値 (drift, {date,pct,next})。データ自体が無い場合のみ (None, None)."""
    try:
        ed = tk.earnings_dates
    except Exception:
        return None, None
    if ed is None or ed.empty or "Reported EPS" not in ed.columns:
        return None, None
    today = dt.date.today()
    next_date, latest = None, None
    for idx, row in ed.iterrows():
        d = idx.date() if hasattr(idx, "date") else None
        if d is None:
            continue
        rep = row.get("Reported EPS")
        if rep is None or rep != rep:            # NaN=未報告（将来分）
            if d >= today and (next_date is None or d < next_date):
                next_date = d
            continue
        sp = row.get("Surprise(%)")
        if sp is None or sp != sp:
            continue
        if d <= today and (latest is None or d > latest[0]):
            latest = (d, float(sp))
    nxt = next_date.isoformat() if next_date else None
    if latest is None:
        return None, {"date": None, "pct": None, "next": nxt}
    surp = {"date": latest[0].isoformat(), "pct": round(latest[1], 1), "next": nxt}
    days = (today - latest[0]).days
    if days > 100:
        return 0.0, surp                          # ドリフト消滅（真の状態）
    frac = max(-1.0, min(1.0, latest[1] / 100.0))
    decay = max(0.0, 1.0 - days / 90.0)
    return round(frac * decay * 100, 2), surp


def _earnings_drift(symbol):
    """PEAD（決算後ドリフト, Bernard & Thomas 1989）:
    直近決算のEPSサプライズ% × 時間減衰(報告後90日で消滅)。
    ドリフトは数週間スケールで最も頑健なアノマリー。
    報告後100日超=ドリフト消滅で0（真の状態）、FMPデータ欠損のみNone（中立）."""
    s = fetch_fmp.latest_surprise(symbol)
    if s is None:
        return None, None
    act, est = s.get("act"), s.get("est")
    if act is None or est is None:
        return None, s
    try:
        days = (dt.date.today() - dt.date.fromisoformat(s["date"])).days
    except Exception:
        return None, s
    if days > 100:
        return 0.0, s
    surprise = max(-1.0, min(1.0, (act - est) / max(abs(est), 0.1)))
    decay = max(0.0, 1.0 - days / 90.0)
    return round(surprise * decay * 100, 2), s


def _inst_flow_13f(tk):
    """13F上位機関の保有変化(前四半期比)の加重平均。正=機関の買い越し.
    新規建て等の極端値は±50%にクランプ（四半期・確報データ）."""
    try:
        ih = tk.institutional_holders
        if ih is None or ih.empty or "pctChange" not in ih.columns:
            return None, None
        rows = ih.dropna(subset=["pctChange"]).head(10)
        if rows.empty:
            return None, None
        w = rows["pctHeld"].fillna(0).clip(lower=0.001)
        chg = rows["pctChange"].clip(-0.5, 0.5)
        flow = float((chg * w).sum() / w.sum())
        date = str(rows["Date Reported"].iloc[0])[:10] if "Date Reported" in rows.columns else None
        return flow, date
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

            # ── Tiingo 2年OHLCV（主）/ yfinance 1年（代替）の統一系列 ──
            tio = fetch_tiingo.eod(sym)
            if tio:
                closes, highs, lows, vols = tio["close"], tio["high"], tio["low"], tio["volume"]
            else:
                closes = [float(x) for x in hist["Close"].fillna(0)] if len(hist) else []
                highs = [float(x) for x in hist["High"].fillna(0)] if len(hist) else []
                lows = [float(x) for x in hist["Low"].fillna(0)] if len(hist) else []
                vols = [float(x) for x in hist["Volume"].fillna(0)] if len(hist) else []

            # 保有期間トレンド（第7ファクター・Tiingo出来高由来）
            raw[tid]["holding_trend"] = _holding_trend(vols)
            # A/D蓄積60日（機関の足跡・日次代理）
            ad60 = _ad_accum(closes, highs, lows, vols, window=60)
            # 13F機関フロー（四半期・確報）
            flow13f, flow_date = _inst_flow_13f(tk)
            inst_count = None
            try:
                mh = tk.major_holders
                if mh is not None and "institutionsCount" in mh.index:
                    inst_count = int(mh.loc["institutionsCount"].iloc[0])
            except Exception:
                pass

            # 資金勢い: 日次鮮度の成分のみ（52週位置＋時変ベータ＋A/D蓄積60日）。
            # 13Fフロー・機関保有率は四半期＋45日遅延の遅効データであり、
            # さらに保有率の「水準」は高い＝発見済みを意味し早期発見と逆行するため
            # スコアから除外し、参考表示（own）に降格した。
            inst = info.get("heldPercentInstitutions")
            lo = info.get("fiftyTwoWeekLow")
            pos = ((price - lo) / (dd - lo)) if (price and dd and lo and dd > lo) else None
            comps = [x for x in [
                (pos * 100 if pos is not None else None),
                (50 + b_trend * 100) if b_trend is not None else None,
                (50 + ad60 * 100) if ad60 is not None else None,
            ] if x is not None]
            raw[tid]["capital_momentum"] = (sum(comps) / len(comps)) if comps else None

            # PEAD: yfinance earnings_dates主（全銘柄）、FMPは補完
            # （FMP無料枠は銘柄ユニバース制限があり10/60しか取れない＝横断比較を壊すため主にできない）
            drift, surp = _earnings_drift_yf(tk)
            if drift is None and surp is None:
                drift, s = _earnings_drift(sym)
                surp = ({"date": s.get("date"),
                         "pct": (round((s["act"] - s["est"]) / max(abs(s["est"]), 0.1) * 100, 1)
                                 if (s.get("act") is not None and s.get("est") is not None) else None),
                         "next": s.get("next_date")} if s else None)
            raw[tid]["earnings_drift"] = drift

            shares = info.get("sharesOutstanding")
            adv20 = float(np.mean([x for x in vols[-20:] if x])) if len(vols) >= 20 else None
            hp_days = round(shares / adv20, 1) if (shares and adv20) else None
            raw[tid]["_own"] = {
                "surprise": surp,
                "inst_pct": inst, "inst_count": inst_count,
                "flow_13f": (round(flow13f, 4) if flow13f is not None else None),
                "flow_date": flow_date,
                "ad60": (round(ad60, 3) if ad60 is not None else None),
                "hp_days": hp_days,
                "src": "tiingo" if tio else "yfinance",
            }
            raw[tid]["_diag"] = {"beta": round(b_now, 2) if b_now else None,
                                 "beta_trend": round(b_trend, 3) if b_trend is not None else None,
                                 "vol": round(vol, 2) if vol else None,
                                 "debt": total_debt}
            print(f"  [fac] {tid:7s} DOL={_fmt(raw[tid]['operating_leverage'])} "
                  f"hold={_fmt(raw[tid]['holding_trend'])} flow13F={_fmt(flow13f)} "
                  f"ad={_fmt(ad60)} hp={_fmt(hp_days)}d src={'T' if tio else 'Y'}")
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
