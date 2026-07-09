"""原理④「専門家の先行足跡」を各社レベルで実測する.

キオクシアのCBA/AiSAQが市場に先行して論文・GitHubに現れたように、
各社の技術キーワードに対する研究の"勢い"を暗黒期シグナルとして拾う。
  - arXiv API: 直近の関連論文数（研究の先行注目）
  - GitHub検索: 関連リポジトリ数（実装の先行注目, best-effort）
両者を宇宙内パーセンタイルで0-100に正規化して返す。
"""
import time
import datetime as dt
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from config import TECH_KEYWORDS, GITHUB_TOKEN, HTTP_HEADERS, REQUEST_TIMEOUT

ARXIV_API = "http://export.arxiv.org/api/query"
EXPERT_WINDOW_DAYS = 365  # 直近この期間の論文を"先行の勢い"としてカウント


def _arxiv_recent_count(keywords):
    """キーワード群(OR)で直近EXPERT_WINDOW_DAYS日の論文数と最新投稿日を返す."""
    terms = " OR ".join(f'all:"{k}"' for k in keywords)
    q = urllib.parse.urlencode({
        "search_query": terms, "start": 0, "max_results": 60,
        "sortBy": "submittedDate", "sortOrder": "descending",
    })
    try:
        r = requests.get(f"{ARXIV_API}?{q}", headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None, None
        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=EXPERT_WINDOW_DAYS)
        recent = 0
        latest = None
        for entry in root.findall("a:entry", ns):
            pub = entry.find("a:published", ns)
            if pub is None:
                continue
            try:
                d = dt.datetime.fromisoformat(pub.text.replace("Z", "+00:00"))
            except Exception:
                continue
            if latest is None or d > latest:
                latest = d
            if d >= cutoff:
                recent += 1
        return recent, (latest.isoformat() if latest else None)
    except Exception:
        return None, None


def _github_repo_count(keyword):
    """GitHub検索でヒットするリポジトリ数（best-effort, レート制限に弱いので任意）."""
    h = {"Accept": "application/vnd.github+json", "User-Agent": "NextGenSeeker"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        r = requests.get("https://api.github.com/search/repositories",
                         headers=h, params={"q": keyword, "per_page": 1},
                         timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("total_count")
    except Exception:
        pass
    return None


def _percentile_rank(values):
    """dict{ticker: raw} を 0-100 パーセンタイルに変換（Noneは中立50）."""
    vs = [(t, v) for t, v in values.items() if v is not None]
    if len(vs) < 2:
        return {t: 50 for t in values}
    ordered = sorted(vs, key=lambda x: x[1])
    n = len(ordered)
    out = {}
    for i, (t, _) in enumerate(ordered):
        out[t] = round(100 * i / (n - 1), 1)
    for t, v in values.items():
        if v is None:
            out[t] = 50
    return out


def fetch_expert(tickers=None):
    """各社の専門家先行シグナル(0-100)を返す. tickers未指定ならTECH_KEYWORDS全社."""
    tickers = tickers or list(TECH_KEYWORDS.keys())
    arxiv_raw, latest_map, gh_raw = {}, {}, {}
    for t in tickers:
        kws = TECH_KEYWORDS.get(t)
        if not kws:
            arxiv_raw[t] = None
            continue
        cnt, latest = _arxiv_recent_count(kws)
        arxiv_raw[t] = cnt
        latest_map[t] = latest
        gh_raw[t] = _github_repo_count(kws[0])
        print(f"  [exp] {t:7s} arxiv_recent={cnt} gh_repos={gh_raw[t]} latest={(latest or '')[:10]}")
        time.sleep(3.1)  # arXivへの礼儀（rate limit回避）

    arxiv_pct = _percentile_rank(arxiv_raw)
    gh_pct = _percentile_rank(gh_raw)
    out = {}
    for t in tickers:
        # 論文の勢いを主(0.7)、実装の勢いを従(0.3)
        expert = round(0.7 * arxiv_pct.get(t, 50) + 0.3 * gh_pct.get(t, 50), 1)
        out[t] = {
            "expert_signal": expert,
            "arxiv_recent": arxiv_raw.get(t),
            "arxiv_latest": latest_map.get(t),
            "github_repos": gh_raw.get(t),
        }
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_expert(), indent=2, ensure_ascii=False))
