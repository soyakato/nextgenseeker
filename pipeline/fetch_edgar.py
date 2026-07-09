"""SEC EDGAR 8-K 取得 — 報道より早い一次情報の触媒検出.

8-KのItem番号はSECが定める標準タクソノミーであり、キーワード辞書より客観的:
  https://www.sec.gov/fast-answers/answersform8khtm.html
判定はItem番号→方向の機械的マップ（開示済み・主観の入り込む余地が最小）。
data.sec.gov はUser-Agent必須・レート制限(10req/s)あり。
"""
import os
import json
import time
import datetime as dt
import requests
from config import LIVE_DIR, REQUEST_TIMEOUT

UA = {"User-Agent": "NextGenSeeker research tool (contact: soyaelephant@gmail.com)"}
CIK_CACHE = os.path.join(LIVE_DIR, "cik_map.json")
EDGAR_LOOKBACK_DAYS = 14

# 8-K Item番号 → (方向 -1..+1, 確信度, 日本語ラベル)。SEC標準タクソノミーの機械的マップ。
ITEM_MAP = {
    "1.01": (+0.6, 0.7, "重要契約の締結"),
    "1.02": (-0.6, 0.7, "重要契約の終了"),
    "1.03": (-0.9, 0.9, "破産・管財"),
    "2.01": (+0.3, 0.5, "資産取得・売却完了"),
    "2.02": (0.0, 0.3, "決算発表"),            # 中立: 内容はニュース判定側が拾う
    "2.03": (-0.2, 0.4, "債務・オフバランス義務"),
    "2.04": (-0.5, 0.6, "債務加速のトリガー"),
    "2.05": (-0.4, 0.5, "リストラ費用"),
    "2.06": (-0.5, 0.6, "減損"),
    "3.01": (-0.8, 0.8, "上場基準不適合通知"),
    "3.02": (-0.3, 0.5, "未登録株式の売出"),
    "4.01": (-0.4, 0.6, "監査人の交代"),
    "4.02": (-0.9, 0.9, "過年度財務諸表の非依拠"),
    "5.02": (-0.3, 0.5, "役員の退任・選任"),
    "5.03": (0.0, 0.2, "定款変更"),
    "5.07": (0.0, 0.2, "株主総会結果"),
    "7.01": (0.0, 0.2, "Reg FD開示"),
    "8.01": (+0.1, 0.3, "その他の重要イベント"),
    "9.01": (0.0, 0.1, "添付書類"),
}


def _load_cik_map():
    """ticker→CIK マップ（7日キャッシュ）."""
    if os.path.exists(CIK_CACHE):
        try:
            st = os.stat(CIK_CACHE)
            if (time.time() - st.st_mtime) < 7 * 86400:
                with open(CIK_CACHE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=UA, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        m = {v["ticker"].upper(): v["cik_str"] for v in r.json().values()}
        with open(CIK_CACHE, "w", encoding="utf-8") as f:
            json.dump(m, f)
        return m
    except Exception as e:
        print(f"  [edgar] CIKマップ取得失敗: {repr(e)[:60]}")
        return {}


def fetch_8k(tickers):
    """{ticker: [{date, items:[{code,dir,conf,label}], url}...]} を返す（直近14日）."""
    cik_map = _load_cik_map()
    cutoff = (dt.date.today() - dt.timedelta(days=EDGAR_LOOKBACK_DAYS)).isoformat()
    out = {}
    for t in tickers:
        cik = cik_map.get(t.upper())
        events = []
        if cik:
            try:
                r = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                                 headers=UA, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                rec = r.json().get("filings", {}).get("recent", {})
                forms = rec.get("form", [])
                dates = rec.get("filingDate", [])
                items_l = rec.get("items", [])
                accs = rec.get("accessionNumber", [])
                n = min(len(forms), len(dates), len(accs))
                for i in range(n):
                    if forms[i] not in ("8-K", "8-K/A") or dates[i] < cutoff:
                        continue
                    raw_items = items_l[i] if i < len(items_l) else ""
                    codes = [c.strip() for c in (raw_items or "").split(",") if c.strip()]
                    parsed = []
                    for c in codes:
                        d, conf, label = ITEM_MAP.get(c, (0.0, 0.2, f"Item {c}"))
                        parsed.append({"code": c, "dir": d, "conf": conf, "label": label})
                    if parsed:
                        acc = accs[i].replace("-", "")
                        events.append({
                            "date": dates[i], "items": parsed,
                            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}",
                        })
            except Exception as e:
                print(f"  [edgar] {t} 失敗: {repr(e)[:60]}")
        out[t] = events
        if events:
            codes = ", ".join(i["code"] for e in events for i in e["items"])
            print(f"  [edgar] {t:6s} 8-K {len(events)}件 ({codes})")
        time.sleep(0.15)   # レート制限への礼儀
    return out


def to_judged_items(events):
    """8-Kイベントをニュース判定形式に変換（同じ集約器に流すため）."""
    out = []
    for e in events:
        # 1提出内の最重要Item（|dir|×conf最大）を代表にする
        best = max(e["items"], key=lambda i: abs(i["dir"]) * i["conf"])
        labels = "・".join(i["label"] for i in e["items"] if i["code"] != "9.01") or best["label"]
        out.append({
            "title": f"SEC 8-K提出: {labels}",
            "summary": "", "pub": e["date"], "provider": "SEC EDGAR", "url": e["url"],
            "dir": best["dir"], "conf": best["conf"],
            "type": f"8-K {best['code']}", "why": best["label"] + "（一次情報・機械判定）",
            "is_edgar": True,
        })
    return out
