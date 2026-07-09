"""客観ユニバース構築（固定リスト＝私の主観を廃止）.

trend_radar思想: 実行のたびにYahoo定義済みスクリーナーの和集合から
「いま市場が客観的に選んでいる銘柄」を取得する。人手の銘柄選定は一切しない。
"""
import re
import yfinance as yf
from config import UNIVERSE_SCREENERS, UNIVERSE_MAX

_SYM = re.compile(r"^[A-Z]{1,5}$")
_EXCLUDE = set("SPY QQQ IWM DIA VOO VTI VT GLD SLV TLT HYG TQQQ SQQQ SOXL SOXS "
               "UVXY VXX UPRO SPXL SPXS TNA TZA".split())


def _valid(sym):
    return bool(_SYM.match(sym)) and sym not in _EXCLUDE


def build():
    """スクリーナー和集合の客観ユニバースを返す。出現スクリーナー数で優先順位付け."""
    counts = {}
    for scr in UNIVERSE_SCREENERS:
        try:
            res = yf.screen(scr, count=25)
            quotes = res.get("quotes", []) if isinstance(res, dict) else []
            for q in quotes:
                s = (q.get("symbol") or "").upper()
                if _valid(s):
                    counts[s] = counts.get(s, 0) + 1
            print(f"  [uni] {scr}: {len(quotes)}")
        except Exception as e:
            print(f"  [uni] {scr} 失敗: {repr(e)[:60]}")
    # 複数スクリーナーに現れる銘柄を優先し、上位UNIVERSE_MAXに絞る（計算予算）
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    syms = [s for s, _ in ranked[:UNIVERSE_MAX]]
    print(f"  [uni] 客観ユニバース {len(syms)}銘柄（和集合{len(counts)}→上位{len(syms)}）")
    return syms
