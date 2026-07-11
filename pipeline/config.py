"""NextGenSeeker データパイプライン設定."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_DIR = os.path.join(ROOT, "live")

# 内部ティッカーID → Yahoo Financeシンボル
YAHOO_SYMBOLS = {
    "ASML": "ASML", "TSMC": "TSM", "SNPS": "SNPS", "CDNS": "CDNS",
    "AVGO": "AVGO", "ADTEST": "6857.T", "KLAC": "KLAC", "LRCX": "LRCX",
    "AMAT": "AMAT", "VRT": "VRT", "ANET": "ANET", "ALAB": "ALAB",
    "MRVL": "MRVL", "MPWR": "MPWR", "COHR": "COHR", "CEG": "CEG",
    "VST": "VST", "PLTR": "PLTR", "TEL": "8035.T", "CAMT": "CAMT",
    "HYNIX": "000660.KS", "CRWV": "CRWV", "NVDA": "NVDA",
    "MU": "MU", "SNDK": "SNDK", "KIOX": "285A.T",
}

# ── 先行指標: CUDAの堀の侵食を測るGitHubリポジトリ群 ──────────────
# CUDA代替・ポータビリティ層のモメンタム = NVIDIAソフト独占の亀裂シグナル
MOAT_EROSION_REPOS = [
    ("ROCm/ROCm", "AMD ROCm (CUDA対抗スタック)"),
    ("triton-lang/triton", "Triton (ハード非依存カーネル言語)"),
    ("tinygrad/tinygrad", "tinygrad (マルチバックエンド)"),
    ("ggml-org/llama.cpp", "llama.cpp (多バックエンド推論)"),
    ("vllm-project/vllm", "vLLM (推論サービング)"),
]
# SCALE(Spectral Compute)は候補として試行。存在しなければ自動でスキップ。
SCALE_REPO_CANDIDATES = [
    "spectral-compute/scale-validation-suite",
    "spectral-compute/scale-docs",
]

# 先行指標プロキシとして観測する銘柄群
TSMC_PROXY = "TSM"                       # CoWoS/先端製造の需要ゲージ
OPTICAL_PROXIES = ["COHR", "LITE", "FN"] # 光インターコネクト受注の先行プロキシ
POWER_PROXIES = ["CEG", "VST"]           # 電力ボトルネックの受益
HBM_PROXIES = ["000660.KS", "MU"]        # HBM供給

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # 任意。あればレート制限緩和
TIINGO_API_KEY = os.environ.get("TIINGO_API_KEY", "")  # Tiingo EOD（保有期間トレンド等）

# ── 原理④「専門家の先行足跡」: 各社の技術キーワード（arXiv実測用） ──
# キオクシアのCBA/AiSAQが論文に先行出現したように、研究の勢いを暗黒期シグナルとする
# 短い実在フレーズのOR（arXivのフレーズ検索でヒットするよう2語前後に）
TECH_KEYWORDS = {
    "ASML": ["EUV lithography", "high-NA EUV"],
    "TSMC": ["chiplet", "advanced packaging", "interposer"],
    "SNPS": ["design automation", "logic synthesis"],
    "CDNS": ["design verification", "analog design automation"],
    "AVGO": ["AI accelerator", "network-on-chip"],
    "ADTEST": ["known good die", "wafer test"],
    "KLAC": ["defect inspection", "optical metrology"],
    "LRCX": ["3D NAND", "atomic layer etching"],
    "AMAT": ["thin film deposition", "atomic layer deposition"],
    "VRT": ["liquid cooling", "immersion cooling", "data center cooling"],
    "ANET": ["RDMA", "datacenter network", "congestion control"],
    "ALAB": ["CXL memory", "PCIe retimer", "chip interconnect"],
    "MRVL": ["silicon photonics", "coherent DSP"],
    "MPWR": ["voltage regulator", "power delivery network"],
    "COHR": ["silicon photonics", "optical transceiver"],
    "CEG": ["small modular reactor", "nuclear power"],
    "VST": ["grid demand response", "datacenter power"],
    "PLTR": ["retrieval augmented generation", "LLM agent"],
    "TEL": ["photoresist", "plasma etching"],
    "CAMT": ["3D packaging", "wafer inspection"],
    "HYNIX": ["high bandwidth memory", "HBM", "3D DRAM"],
    "CRWV": ["GPU scheduling", "inference serving"],
    "NVDA": ["GPU kernel", "LLM inference"],
    "MU": ["high bandwidth memory", "HBM", "NAND flash"],
    "SNDK": ["NAND flash", "solid state drive"],
    "KIOXIA": ["approximate nearest neighbor", "vector search", "NAND flash"],
    "KIOX": ["NAND flash", "vector search", "approximate nearest neighbor"],
}

# ── 自己改善・ガラパゴス化防止パラメータ ──────────────────────
# データ信頼度α（原理ごと。プライヤ=事前分布への縮小率。α=0で完全に静的、1で完全にデータ）
DATA_TRUST = {
    "despair": 0.55, "convexity": 0.55, "vacuum": 0.28,
    "expert": 0.60, "backstop": 0.45, "accumulation": 0.45,
}
EWMA_LEARN_RATE = 0.35      # 履歴からの学習速度（小さいほど緩慢＝ノイズ耐性）
MAX_DELTA_PER_RUN = 8.0     # 1回で動かせるスコアの上限（乱高下防止）

# 遅延採点による重み学習
GRADE_HORIZONS = [20, 60]   # 営業日。選定からこの日数後に市場比で採点
FORGET_DAYS = 180           # これより古い採点は忘却（同じトレンドは繰り返さない）
MIN_GRADED_SAMPLES = 12     # これ未満なら重みは一切動かさない（結果が出るまで不動）
WEIGHT_MULT_MIN = 0.5       # 事前分布からの下限倍率
WEIGHT_MULT_MAX = 1.6       # 事前分布からの上限倍率
LEARN_STEP = 0.15           # IC→倍率の反映速度（緩やか）
BENCHMARK_SYMBOL = "SPY"    # 採点のベンチマーク（市場超過リターンで評価）

# 集中(ガラパゴス)警告のしきい値
CONCENTRATION_TOP_N = 8
CONCENTRATION_THRESHOLD = 0.5   # 上位N銘柄中、単一セクター比率がこれ以上で警告

# ── ウォッチ＆兆候レーダー（継続選出→触媒ニュース→価格確認） ──────
WATCH_STREAK_DAYS = 2       # 確定ウォッチ: この日数以上連続でユニバース選出
WATCH_APPEAR_MIN = 3        # または直近WATCH_WINDOW日間にこの回数以上出現
WATCH_WINDOW_DAYS = 14
WATCH_PROVISIONAL_RANK = 10 # 仮ウォッチ: 当日ランキング上位この順位以内（初日から機能させる）
WATCH_MAX = 15              # ニュース取得の対象上限（API予算）
NEWS_LOOKBACK_DAYS = 7      # 直近この日数のニュースのみ判定
NEWS_MAX_PER_TICKER = 8
ALERT_THRESHOLD = 65        # 兆候スコアがこの値以上でアラート記録（遅延採点対象）

# ── 客観ユニバース（固定リスト＝主観を全廃。スクリーナー和集合で自動構築） ──
UNIVERSE_SCREENERS = ["day_gainers", "most_actives", "growth_technology_stocks",
                      "undervalued_large_caps", "aggressive_small_caps",
                      "undervalued_growth_stocks"]
UNIVERSE_MAX = 60           # 1回で採点する客観ユニバースの上限（計算予算）

# ── Claude API (任意の高度化レイヤー) ─────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NGS_MODEL = os.environ.get("NGS_MODEL", "claude-haiku-4-5-20251001")

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (NextGenSeeker/1.0)"}
REQUEST_TIMEOUT = 15
