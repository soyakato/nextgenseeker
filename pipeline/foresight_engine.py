"""先見6原理を実データから導出し、事前分布(プライヤ)へ縮小して自己改善する.

ガラパゴス化防止:
  - shrinkage: final = prior*(1-α) + data*α   （αはDATA_TRUSTで上限0.6）
  - EWMA: 前回値から緩やかに更新（EWMA_LEARN_RATE）
  - drift cap: 1回の変動をMAX_DELTA_PER_RUNに制限
データが取れない原理はプライヤのまま（＝静的にフォールバック）。
"""
from config import DATA_TRUST, EWMA_LEARN_RATE, MAX_DELTA_PER_RUN
import foresight_priors as fp


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def _lin(v, x0, y0, x1, y1):
    if v is None:
        return None
    t = (v - x0) / (x1 - x0) if x1 != x0 else 0
    return _clamp(y0 + t * (y1 - y0), min(y0, y1), max(y0, y1))


# ── 各原理のデータ導出（Noneならプライヤにフォールバック） ──
def _despair(fin):
    """逆張り度: 高値からの下落(drawdown)が大きく、かつ前向きに変曲(成長+)しているほど高い."""
    dd = fin.get("drawdown")
    if dd is None:
        return None
    base = _lin(dd, 0.0, 12, 0.6, 92)               # 深く売られるほど高い
    g = fin.get("revenue_growth")
    # 成長が正なら"変曲"としてブースト、深い減収なら"落ちるナイフ"として減衰
    mult = 1.0
    if g is not None:
        mult = _clamp(0.55 + g, 0.45, 1.35) / 1.0
    return _clamp(base * mult)


def _convexity(fin):
    """利益の凸性: 高粗利(operating leverage余地)×高成長×高ベータ(シクリカル)."""
    gm = _lin(fin.get("gross_margin"), 0.2, 35, 0.75, 92)
    g = _lin(fin.get("revenue_growth"), 0.0, 40, 1.0, 96)
    b = _lin(fin.get("beta"), 0.8, 40, 2.2, 92)
    parts = [(gm, 0.4), (g, 0.35), (b, 0.25)]
    num = sum(v * w for v, w in parts if v is not None)
    den = sum(w for v, w in parts if v is not None)
    return _clamp(num / den) if den else None


def _vacuum(fin):
    """需給の真空(弱い代理): 高成長だが巨大ではない銘柄ほど、隠れた需給逼迫の可能性."""
    g = _lin(fin.get("revenue_growth"), 0.0, 40, 0.8, 90)
    if g is None:
        return None
    mc = fin.get("market_cap")
    size_pen = 0
    if mc and mc > 1.5e12:      # 超大型は"隠れた真空"ではない
        size_pen = 15
    return _clamp(g - size_pen)


def _backstop(fin):
    """生存保証: バランスシートの頑健さ(低負債・現金厚・FCF黒字). 政策要因はプライヤ側が担う."""
    de = fin.get("debt_to_equity")
    de_score = _lin(de, 0, 90, 250, 15) if de is not None else None   # 低負債=高得点
    cash, debt = fin.get("total_cash"), fin.get("total_debt")
    cover = None
    if cash is not None and debt is not None:
        cover = _lin(cash / (debt + 1), 0.0, 30, 1.2, 88)
    cr = _lin(fin.get("current_ratio"), 0.8, 35, 2.5, 85) if fin.get("current_ratio") is not None else None
    fcf = fin.get("fcf")
    fcf_score = (82 if (fcf and fcf > 0) else 42) if fcf is not None else None
    parts = [(de_score, 0.35), (cover, 0.3), (cr, 0.15), (fcf_score, 0.2)]
    num = sum(v * w for v, w in parts if v is not None)
    den = sum(w for v, w in parts if v is not None)
    return _clamp(num / den) if den else None


def _accumulation(fin):
    """スマートマネー: 52週レンジ内で高位置(静かに買い上げ)＋機関保有の厚み."""
    pos = _lin(fin.get("pos_52w"), 0.1, 30, 0.95, 88) if fin.get("pos_52w") is not None else None
    inst = _lin(fin.get("held_pct_inst"), 0.3, 40, 0.95, 85) if fin.get("held_pct_inst") is not None else None
    parts = [(pos, 0.55), (inst, 0.45)]
    num = sum(v * w for v, w in parts if v is not None)
    den = sum(w for v, w in parts if v is not None)
    return _clamp(num / den) if den else None


def derive_pillars(fin, expert_signal):
    """1銘柄の6原理データ導出値（取れないものはNone）を返す."""
    return {
        "despair": _despair(fin),
        "convexity": _convexity(fin),
        "vacuum": _vacuum(fin),
        "expert": expert_signal,   # 0-100 or None（arXiv実測）
        "backstop": _backstop(fin),
        "accumulation": _accumulation(fin),
    }


def blend(ticker, data_pillars, prev_final):
    """プライヤへの縮小 → EWMA → drift cap の順に適用し最終スコアを返す."""
    prior = fp.prior_for(ticker)
    out, derived_log = {}, {}
    for p in fp.PILLARS:
        d = data_pillars.get(p)
        pri = prior[p]
        if d is None:
            target = pri                       # データ無し→プライヤ
        else:
            a = DATA_TRUST.get(p, 0.5)
            target = pri * (1 - a) + d * a     # shrinkage（錨を離さない）
        derived_log[p] = None if d is None else round(d, 1)
        prev = prev_final.get(p) if prev_final else None
        if prev is None:
            val = target
        else:
            val = prev * (1 - EWMA_LEARN_RATE) + target * EWMA_LEARN_RATE   # 緩やかに学習
            val = max(prev - MAX_DELTA_PER_RUN, min(prev + MAX_DELTA_PER_RUN, val))  # drift cap
        out[p] = round(_clamp(val), 1)
    return out, derived_log
