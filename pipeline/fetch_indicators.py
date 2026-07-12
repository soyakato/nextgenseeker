"""市場環境トラッカー — 地合いレジーム（旧・半導体固定プロキシは全廃）.

旧版はCUDA/TSMC/光/HBM等の手選りプロキシ＝テック固定で、バリュー株も扱う現在の
スコープと不整合だった。新版は市場全体の客観指標のみ:
  - 地合いレジーム: ベンチマーク(SPY)の50/200日線と20日リターン＋VIX水準から
    リスクオン/中立/リスクオフを機械判定（trend_radarで実測済みの手法。
    弱気局面ではモメンタム系ICが反転するという10年検証に基づく文脈情報）
セクター温度図はユニバース自体から導出するため refresh.py 側で合成する。
参考表示専用 — 客観スコアには一切使用しない。
"""
import yfinance as yf
from config import BENCHMARK_SYMBOL


def _regime_from(spy_close, vix_last):
    if spy_close is None or len(spy_close) < 60:
        return None
    last = float(spy_close.iloc[-1])
    ma50 = float(spy_close.tail(50).mean())
    ma200 = float(spy_close.tail(200).mean()) if len(spy_close) >= 210 else None
    r20 = last / float(spy_close.iloc[-21]) - 1 if len(spy_close) > 21 else 0.0
    v = vix_last
    uptrend = (last > ma50 > ma200) if ma200 else (last > ma50 and r20 > 0)
    if uptrend and (v is None or v < 20):
        label = "リスクオン"
        desc = "ベンチマークが上昇トレンド・恐怖指数も平静。モメンタム系ファクターが機能しやすい地合い"
    elif last < ma50 and ((v or 0) > 25 or r20 < -0.05):
        label = "リスクオフ"
        desc = "50日線割れ＋変動率上昇。モメンタム系の統計的傾きが反転しやすい局面 — 生存力・バリュー寄りの重みと小さいサイズを検討"
    else:
        label = "中立"
        desc = "強い方向感なし。標準の重み付けで"
    return {"label": label, "desc": desc,
            "bench": round(last, 1), "ma50": round(ma50, 1),
            "ma200": (round(ma200, 1) if ma200 else None),
            "r20": round(r20, 4), "vix": (round(v, 1) if v is not None else None)}


def fetch_all():
    """{regime: {...}} を返す。取得失敗はNone（呼び出し側が前回値を再利用）."""
    spy = yf.Ticker(BENCHMARK_SYMBOL).history(period="1y")["Close"].dropna()
    vix_last = None
    try:
        vh = yf.Ticker("^VIX").history(period="5d")["Close"].dropna()
        if len(vh):
            vix_last = float(vh.iloc[-1])
    except Exception:
        pass
    regime = _regime_from(spy, vix_last)
    if regime:
        print(f"  [env] 地合い: {regime['label']} (bench {regime['bench']} / MA50 {regime['ma50']} / VIX {regime['vix']})")
    return {"regime": regime}
