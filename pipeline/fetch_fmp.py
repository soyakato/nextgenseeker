"""FMP (stable API) 取得 — PEAD用の決算サプライズ＋アナリスト格付イベント.

無料枠250req/日の予算管理:
  - 日次キャッシュ(live/fmp_cache.json, gitコミットでクラウド実行間も持続)
  - 実行内カウンタで上限FMP_BUDGET_PER_RUNを強制
  - 403/402/404は当該銘柄をNoneとし静かにフォールバック
実測済み無料枠: earnings(limit<=5)✅ / grades✅ / grades-consensus✅ / insider・v3系❌
"""
import os
import json
import datetime as dt
import requests
from config import LIVE_DIR, REQUEST_TIMEOUT

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
BASE = "https://financialmodelingprep.com/stable/"
CACHE_PATH = os.path.join(LIVE_DIR, "fmp_cache.json")
FMP_BUDGET_PER_RUN = 150   # 250/日の余裕を残す実行内上限

_calls = 0
_cache = None


def _load_cache():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
        today = dt.date.today().isoformat()
        if _cache.get("date") != today:      # 日替わりでキャッシュ破棄（日次鮮度）
            _cache = {"date": today, "earnings": {}, "grades": {}, "consensus": {}}
    return _cache


def save_cache():
    if _cache is not None:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)


def _get(path):
    global _calls
    if not FMP_API_KEY or _calls >= FMP_BUDGET_PER_RUN:
        return None
    _calls += 1
    try:
        sep = "&" if "?" in path else "?"
        r = requests.get(BASE + path + sep + "apikey=" + FMP_API_KEY,
                         timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def latest_surprise(symbol):
    """直近の報告済み決算 {date, act, est, next_date} を返す（日次キャッシュ）."""
    c = _load_cache()
    if symbol in c["earnings"]:
        return c["earnings"][symbol]
    rows = _get(f"earnings?symbol={symbol}&limit=5")
    out = None
    if isinstance(rows, list):
        today = dt.date.today().isoformat()
        next_date = None
        for x in rows:                       # 新しい順
            d = (x.get("date") or "")[:10]
            if x.get("epsActual") is None:
                if d >= today:
                    next_date = d
                continue
            out = {"date": d, "act": x.get("epsActual"), "est": x.get("epsEstimated"),
                   "rev_act": x.get("revenueActual"), "rev_est": x.get("revenueEstimated"),
                   "next_date": next_date}
            break
    c["earnings"][symbol] = out
    return out


def recent_grades(symbol, days=30):
    """直近days日のアナリスト格付イベント（日次キャッシュ）."""
    c = _load_cache()
    if symbol in c["grades"]:
        return c["grades"][symbol]
    rows = _get(f"grades?symbol={symbol}&limit=10")
    out = []
    if isinstance(rows, list):
        cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        for x in rows:
            d = (x.get("date") or "")[:10]
            if d >= cutoff:
                out.append({"date": d, "firm": x.get("gradingCompany"),
                            "action": (x.get("action") or "").lower(),
                            "from": x.get("previousGrade"), "to": x.get("newGrade")})
    c["grades"][symbol] = out
    return out


def consensus(symbol):
    """アナリスト・コンセンサス {buy, hold, sell, consensus}（日次キャッシュ）."""
    c = _load_cache()
    if symbol in c["consensus"]:
        return c["consensus"][symbol]
    rows = _get(f"grades-consensus?symbol={symbol}")
    out = None
    if isinstance(rows, list) and rows:
        x = rows[0]
        out = {"buy": (x.get("strongBuy") or 0) + (x.get("buy") or 0),
               "hold": x.get("hold") or 0,
               "sell": (x.get("sell") or 0) + (x.get("strongSell") or 0),
               "consensus": x.get("consensus")}
    c["consensus"][symbol] = out
    return out


def calls_used():
    return _calls
