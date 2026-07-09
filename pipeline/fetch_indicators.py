"""レポート第4章の『源流シグナル』を自動取得する.

  1. CUDAの堀の侵食  … GitHub上のCUDA代替スタックのモメンタム（実データ）
  2. TSMC需要ゲージ  … TSM 四半期売上成長＋価格モメンタム（プロキシ）
  3. 光インターコネクト … COHR/LITE/FN のモメンタム（受注先行のプロキシ）
  4. 電力ボトルネック  … CEG/VST（プロキシ）
  5. HBM供給        … SK Hynix/Micron（プロキシ）
"""
import time
import datetime as dt
import requests
import yfinance as yf
from config import (MOAT_EROSION_REPOS, SCALE_REPO_CANDIDATES, OPTICAL_PROXIES,
                    POWER_PROXIES, HBM_PROXIES, GITHUB_TOKEN, HTTP_HEADERS,
                    REQUEST_TIMEOUT)


def _gh_headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "NextGenSeeker"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def gh_repo(full):
    """リポジトリのスター/フォーク/更新日と直近30日コミット数を取得."""
    r = requests.get(f"https://api.github.com/repos/{full}",
                     headers=_gh_headers(), timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        return None
    d = r.json()
    since = (dt.datetime.utcnow() - dt.timedelta(days=30)).isoformat() + "Z"
    commits30 = None
    try:
        cr = requests.get(
            f"https://api.github.com/repos/{full}/commits",
            headers=_gh_headers(), params={"since": since, "per_page": 100},
            timeout=REQUEST_TIMEOUT)
        if cr.status_code == 200:
            commits30 = len(cr.json())
    except Exception:
        pass
    return {
        "repo": full,
        "stars": d.get("stargazers_count"),
        "forks": d.get("forks_count"),
        "open_issues": d.get("open_issues_count"),
        "pushed_at": d.get("pushed_at"),
        "commits_30d": commits30,
    }


def fetch_moat_erosion():
    repos = []
    for full, label in MOAT_EROSION_REPOS:
        d = gh_repo(full)
        if d:
            d["label"] = label
            repos.append(d)
            print(f"  [gh] {full:26s} stars={d['stars']} commits30d={d['commits_30d']}")
        time.sleep(0.3)

    # SCALE (Spectral Compute) を探索。無ければ N/A。
    scale = None
    for cand in SCALE_REPO_CANDIDATES:
        d = gh_repo(cand)
        if d:
            d["label"] = "SCALE (Spectral Compute / CUDAバイナリ互換)"
            scale = d
            print(f"  [gh] SCALE found: {cand} stars={d['stars']}")
            break
    if not scale:
        print("  [gh] SCALE repo 非公開/未検出 -> N/A")

    total_stars = sum(r["stars"] or 0 for r in repos)
    total_commits = sum(r["commits_30d"] or 0 for r in repos)
    # ヒート: 直近コミット活動を0-100に。代替スタックが活発なほど堀は侵食。
    heat = _clamp(round(total_commits / 500 * 100, 1), 0, 100)
    return {
        "repos": repos,
        "scale": scale,
        "total_stars": total_stars,
        "total_commits_30d": total_commits,
        "heat": heat,
    }


def _momentum(symbol):
    """価格モメンタム(3M/6M %)と四半期売上成長を取得."""
    t = yf.Ticker(symbol)
    out = {"symbol": symbol}
    try:
        h = t.history(period="6mo", interval="1d")
        if len(h) > 5:
            close = h["Close"].dropna()
            last = float(close.iloc[-1])
            out["price"] = round(last, 2)
            def chg(days):
                if len(close) > days:
                    p0 = float(close.iloc[-days])
                    return round((last / p0 - 1) * 100, 1)
                return None
            out["chg_3m"] = chg(63)
            out["chg_6m"] = chg(126)
    except Exception as e:
        out["price_err"] = repr(e)[:80]
    try:
        info = t.info
        out["revenue_growth"] = info.get("revenueGrowth")
        out["gross_margin"] = info.get("grossMargins")
    except Exception:
        pass
    return out


def _heat_from_momentum(items):
    """複数銘柄の3Mモメンタムと売上成長を0-100ヒートに合成."""
    vals = []
    for it in items:
        c = it.get("chg_3m")
        g = it.get("revenue_growth")
        s = 50
        if c is not None:
            s = 50 + _clamp(c, -40, 60)          # 3M価格変化
        if g is not None:
            s = 0.6 * s + 0.4 * (50 + _clamp(g * 100, -30, 50))
        vals.append(_clamp(s, 0, 100))
    return round(sum(vals) / len(vals), 1) if vals else None


def fetch_market_signals():
    def basket(symbols):
        items = []
        for s in symbols:
            items.append(_momentum(s))
            time.sleep(0.3)
        return items

    tsmc = _momentum("TSM"); time.sleep(0.3)
    optical = basket(OPTICAL_PROXIES)
    power = basket(POWER_PROXIES)
    hbm = basket(HBM_PROXIES)

    for name, it in [("TSMC", [tsmc]), ("OPTICAL", optical),
                     ("POWER", power), ("HBM", hbm)]:
        print(f"  [mkt] {name:8s} heat={_heat_from_momentum(it)}")

    return {
        "tsmc_demand": {"items": [tsmc], "heat": _heat_from_momentum([tsmc])},
        "optical": {"items": optical, "heat": _heat_from_momentum(optical)},
        "power": {"items": power, "heat": _heat_from_momentum(power)},
        "hbm": {"items": hbm, "heat": _heat_from_momentum(hbm)},
    }


def fetch_all():
    print(" -- moat erosion (GitHub) --")
    moat = fetch_moat_erosion()
    print(" -- market proxies --")
    market = fetch_market_signals()
    return {"moat_erosion": moat, "market": market}


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all(), indent=2, ensure_ascii=False))
