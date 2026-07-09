"""先見6原理の事前分布（プライヤ／学習の錨）。foresight.js のキュレーション値のスナップショット。
順序: despair, convexity, vacuum, expert, backstop, accumulation
自動発見された未知銘柄は NEUTRAL_PRIOR を使う（純データ駆動になる）。"""

PILLARS = ["despair", "convexity", "vacuum", "expert", "backstop", "accumulation"]

_RAW = {
    "ASML": [20, 45, 25, 82, 72, 42], "TSMC": [26, 55, 30, 84, 88, 46],
    "SNPS": [22, 40, 30, 78, 55, 40], "CDNS": [23, 42, 30, 78, 55, 40],
    "AVGO": [30, 55, 45, 70, 55, 58], "ADTEST": [40, 66, 62, 72, 55, 50],
    "KLAC": [28, 50, 40, 78, 55, 45], "LRCX": [38, 62, 55, 74, 55, 48],
    "AMAT": [40, 58, 45, 76, 55, 46], "VRT": [34, 70, 66, 55, 45, 55],
    "ANET": [30, 62, 48, 62, 50, 52], "ALAB": [42, 70, 60, 60, 40, 55],
    "MRVL": [40, 62, 55, 66, 50, 55], "MPWR": [38, 58, 50, 60, 48, 50],
    "COHR": [48, 62, 56, 60, 45, 50], "CEG": [40, 70, 72, 55, 74, 60],
    "VST": [44, 74, 70, 52, 70, 58], "PLTR": [22, 55, 40, 70, 55, 45],
    "TEL": [42, 60, 55, 76, 55, 46], "CAMT": [46, 66, 68, 62, 42, 52],
    "HYNIX": [45, 80, 60, 76, 76, 62], "CRWV": [62, 72, 40, 45, 38, 55],
    "NVDA": [12, 60, 20, 85, 60, 50], "MU": [55, 82, 62, 72, 78, 62],
    "SNDK": [58, 85, 66, 65, 50, 55], "KIOXIA": [92, 90, 85, 82, 95, 78],
    # 本物のキオクシア(285A.T)は後知恵を避け中立プライヤ＝実データで客観採点
    "KIOX": [50, 50, 50, 50, 50, 50],
}

PRIORS = {t: dict(zip(PILLARS, v)) for t, v in _RAW.items()}
NEUTRAL_PRIOR = {p: 50 for p in PILLARS}


def prior_for(ticker):
    return dict(PRIORS.get(ticker, NEUTRAL_PRIOR))
