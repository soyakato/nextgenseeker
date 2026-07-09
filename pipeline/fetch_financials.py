"""yfinanceで実財務データを取得し、CAPITALスコア（利益の質・資本効率）を実データ化する."""
import time
import yfinance as yf
from config import YAHOO_SYMBOLS


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _lin(v, x0, y0, x1, y1):
    """v を (x0,y0)-(x1,y1) の線形マップに通し、y0..y1 にクランプ."""
    if v is None:
        return None
    t = (v - x0) / (x1 - x0) if x1 != x0 else 0
    y = y0 + t * (y1 - y0)
    return _clamp(y, min(y0, y1), max(y0, y1))


def capital_score(gm, fcf_conv, rev_growth):
    """3要素から利益の質スコア(0-100)を合成.
    - gross margin       45%  … プライシングパワー
    - FCF変換効率(fcf/ocf) 30%  … アセットライトさ
    - 売上成長率          25%  … トラクション
    """
    parts, weights = [], []
    s_gm = _lin(gm, 0.30, 40, 0.80, 96) if gm is not None else None
    s_fc = _lin(fcf_conv, 0.25, 45, 0.95, 96) if fcf_conv is not None else None
    s_gr = _lin(rev_growth, 0.0, 50, 0.60, 95) if rev_growth is not None else None
    for s, w in [(s_gm, 0.45), (s_fc, 0.30), (s_gr, 0.25)]:
        if s is not None:
            parts.append(s * w)
            weights.append(w)
    if not weights:
        return None
    return round(sum(parts) / sum(weights), 1)


def fetch_one(symbol):
    info = yf.Ticker(symbol).info
    gm = info.get("grossMargins")
    ocf = info.get("operatingCashflow")
    fcf = info.get("freeCashflow")
    rev_growth = info.get("revenueGrowth")
    rev = info.get("totalRevenue")
    fcf_conv = None
    if fcf and ocf and ocf > 0:
        fcf_conv = _clamp(fcf / ocf, 0, 1.2)
    fcf_margin = (fcf / rev) if (fcf and rev and rev > 0) else None
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    hi52 = info.get("fiftyTwoWeekHigh")
    lo52 = info.get("fiftyTwoWeekLow")
    # 52週レンジ内の位置（0=安値, 1=高値）とドローダウン（高値からの下落率）
    pos52 = None
    drawdown = None
    if price and hi52 and lo52 and hi52 > lo52:
        pos52 = _clamp((price - lo52) / (hi52 - lo52), 0, 1)
    if price and hi52 and hi52 > 0:
        drawdown = _clamp(1 - price / hi52, 0, 1)
    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "gross_margin": gm,
        "revenue_growth": rev_growth,
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margin": info.get("profitMargins"),
        "fcf": fcf,
        "ocf": ocf,
        "fcf_conversion": fcf_conv,
        "fcf_margin": fcf_margin,
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "price": price,
        "fifty_two_high": hi52,
        "fifty_two_low": lo52,
        "pos_52w": pos52,
        "drawdown": drawdown,
        "beta": info.get("beta"),
        "debt_to_equity": info.get("debtToEquity"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "current_ratio": info.get("currentRatio"),
        "held_pct_inst": info.get("heldPercentInstitutions"),
        "sector": info.get("sector"),
        "capital_score": capital_score(gm, fcf_conv, rev_growth),
    }


def fetch_all():
    out = {}
    for tid, symbol in YAHOO_SYMBOLS.items():
        try:
            d = fetch_one(symbol)
            d["ok"] = d["capital_score"] is not None
            out[tid] = d
            print(f"  [fin] {tid:7s} {symbol:9s} gm={d['gross_margin']} "
                  f"revG={d['revenue_growth']} fcfConv={d['fcf_conversion']} "
                  f"-> CAPITAL={d['capital_score']}")
        except Exception as e:
            out[tid] = {"symbol": symbol, "ok": False, "error": repr(e)[:160]}
            print(f"  [fin] {tid:7s} {symbol:9s} ERROR {repr(e)[:100]}")
        time.sleep(0.4)  # 軽いレート制御
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all(), indent=2, ensure_ascii=False))
