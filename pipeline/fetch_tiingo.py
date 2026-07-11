"""Tiingo EOD取得（保有期間トレンド・A/D蓄積の主データ源。失敗時はyfinanceへフォールバック）.

無料枠: 約1000req/日・月間ユニーク銘柄制限あり。1銘柄1リクエスト(2年分)に抑え、
429/エラー時はNoneを返して呼び出し側がyfinance履歴で代替する。
"""
import datetime as dt
import requests
from config import TIINGO_API_KEY, REQUEST_TIMEOUT


def eod(symbol, years=2):
    """調整済みOHLCV日次系列（古い順）を返す。使えない場合はNone."""
    if not TIINGO_API_KEY:
        return None
    start = (dt.date.today() - dt.timedelta(days=int(365 * years))).isoformat()
    try:
        r = requests.get(
            f"https://api.tiingo.com/tiingo/daily/{symbol}/prices",
            params={"startDate": start, "resampleFreq": "daily",
                    "columns": "date,adjClose,adjHigh,adjLow,adjVolume"},
            headers={"Content-Type": "application/json",
                     "Authorization": f"Token {TIINGO_API_KEY}"},
            timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list) or len(rows) < 60:
            return None
        return {
            "close": [x.get("adjClose") for x in rows],
            "high": [x.get("adjHigh") for x in rows],
            "low": [x.get("adjLow") for x in rows],
            "volume": [x.get("adjVolume") for x in rows],
        }
    except Exception:
        return None
