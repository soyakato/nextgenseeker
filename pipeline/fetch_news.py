"""ウォッチ銘柄のニュース取得（yfinance news API・直近NEWS_LOOKBACK_DAYS日）."""
import time
import datetime as dt
import yfinance as yf
from config import NEWS_LOOKBACK_DAYS, NEWS_MAX_PER_TICKER


def _norm(item):
    """新旧フォーマットを吸収してニュース1件を正規化."""
    c = item.get("content", item) or {}
    title = c.get("title") or ""
    pub = c.get("pubDate") or c.get("displayTime") or ""
    provider = ((c.get("provider") or {}).get("displayName")
                if isinstance(c.get("provider"), dict) else c.get("publisher")) or ""
    url = ""
    cu = c.get("canonicalUrl") or c.get("clickThroughUrl")
    if isinstance(cu, dict):
        url = cu.get("url", "")
    return {"title": title.strip(), "summary": (c.get("summary") or "")[:300].strip(),
            "pub": pub[:16], "provider": provider, "url": url}


def fetch_for(tickers):
    """{ticker: [news...]} を返す。重複タイトル・期限切れは除外."""
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
    out = {}
    for t in tickers:
        items, seen = [], set()
        try:
            for raw in (yf.Ticker(t).news or [])[:NEWS_MAX_PER_TICKER * 2]:
                n = _norm(raw)
                if not n["title"] or n["title"].lower() in seen:
                    continue
                if n["pub"] and n["pub"] < cutoff[:16]:
                    continue
                seen.add(n["title"].lower())
                items.append(n)
                if len(items) >= NEWS_MAX_PER_TICKER:
                    break
        except Exception as e:
            print(f"  [news] {t} 取得失敗: {repr(e)[:60]}")
        out[t] = items
        print(f"  [news] {t:6s} {len(items)}件")
        time.sleep(0.4)
    return out
