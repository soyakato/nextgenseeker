/*
 * NextGenSeeker — 評価フレームワークと候補企業データセット
 *
 * NVIDIAディープ・リサーチレポートの分析構造を、そのまま
 * スクリーニング用の定量スコアリング・モデルに変換したもの。
 *
 * 免責: 各社のスコアと数値は「NVIDIAフレームワーク」に基づく
 * 構造分析のための概算・定性評価であり、投資助言ではない。
 * 数値は公開情報を基にした概算・イメージ値を含む。
 */

// ── 5つの評価軸（"NVIDIA DNA"） ─────────────────────────────
// レポートの各章に対応:
//   moat      = 2. 定性ファンダメンタルズ（CUDAのようなロックイン）
//   choke     = 3. バリューチェーンと物理的制約（チョークポイント支配）
//   capital   = 1. 定量ファンダメンタルズ（利益の質・資本効率）
//   demand    = 5. 必然のシナリオ（構造的・不可避な需要）
//   execution = 経営陣の Skin in the Game / 実行力
// risk        = クリティカル・リスク（コモディティ化 / 顧客の反乱 / 地政学）。
//               高いほど危険。総合スコアに対する減点として作用。

const PILLARS = [
  { key: 'moat',      label: '独占的な堀',       short: 'MOAT',  desc: 'CUDAのようなエコシステム・ロックイン、標準の所有、スイッチングコスト' },
  { key: 'choke',     label: 'チョークポイント支配', short: 'CHOKE', desc: 'バリューチェーン上の物理的・構造的なボトルネックを握っているか' },
  { key: 'capital',   label: '利益の質・資本効率',  short: 'CAPITAL', desc: '高粗利・FCF変換効率・アセットライト・プライシングパワー' },
  { key: 'demand',    label: '必然の需要',        short: 'DEMAND', desc: '不可避なメガトレンドに乗り「スキップされない」構造的需要' },
  { key: 'execution', label: '実行力・経営',      short: 'EXEC',  desc: '創業者/ビジョナリー、Skin in the Game、ロードマップ実行力' },
];

const DEFAULT_WEIGHTS = { moat: 25, choke: 25, capital: 15, demand: 20, execution: 15 };

// ── 候補企業データセット ──────────────────────────────────────
// layer: AIバリューチェーン上のレイヤー
const COMPANIES = [
  {
    ticker: 'ASML', name: 'ASML Holding', sector: '半導体製造装置',
    layer: '最上流：露光装置',
    chokepoint: 'EUV露光装置の完全独占（世界で唯一の供給者）',
    scores: { moat: 98, choke: 99, capital: 85, demand: 92, execution: 82 }, risk: 32,
    metrics: { '粗利益率': '≈51%', '市場シェア(EUV)': '100%', 'リードタイム': '12〜18ヶ月', '受注残': '巨大' },
    thesis: '先端半導体はEUVなしに製造不可能。NVIDIAのCUDA以上に代替不能な物理的独占で、AIチップ・HBM・ASICのすべてがASMLの装置を通過する。「誰が勝っても勝つ」究極のツルハシ。',
    risk_note: '装置サイクルの波が大きく需要は塊状。中国向け輸出規制と、次世代High-NAの立ち上がり速度が鍵。',
  },
  {
    ticker: 'TSMC', name: 'Taiwan Semiconductor', sector: 'ファウンドリ',
    layer: '製造：前工程＋CoWoS',
    chokepoint: '先端ロジック製造とCoWoS先端パッケージングの実質独占',
    scores: { moat: 88, choke: 96, capital: 78, demand: 95, execution: 90 }, risk: 44,
    metrics: { '粗利益率': '≈59%', 'CoWoS能力': '月13万枚(26末)', 'CapEx(26E)': '$52-56B', '先端シェア': '>90%' },
    thesis: 'AIチップの物理的な製造を握る最狭チョークポイント。NVIDIAがCoWoS枠の6割を買い占めても、その供給者はTSMC。ASIC・GPUの覇権争いに関わらず売上を回収する「胴元」。',
    risk_note: '台湾地政学リスクが最大のアキレス腱。アリゾナ先端パッケージング本格稼働は2028年以降で代替が効かない。資本集約度も高い。',
  },
  {
    ticker: 'SNPS', name: 'Synopsys', sector: 'EDA / 設計IP',
    layer: '最上流：設計ツール',
    chokepoint: 'EDA（電子設計自動化）の実質デュオポリー＋設計IP',
    scores: { moat: 92, choke: 88, capital: 80, demand: 85, execution: 78 }, risk: 33,
    metrics: { '粗利益率': '≈80%', 'EDAシェア': '2社寡占', '解約率': '極小', '収益': 'サブスク型' },
    thesis: 'あらゆるチップ（GPUもASICもASML装置も）はEDA上で設計される。NVIDIA vs ASICの戦争がどちらに転んでも、両陣営が使うツールを売る。深いロックインとサブスク収益はCUDAの経済性に近い。',
    risk_note: '中国市場アクセスの規制リスク。Ansys統合の実行と、AI設計自動化による競争環境変化。',
  },
  {
    ticker: 'CDNS', name: 'Cadence Design', sector: 'EDA / 設計IP',
    layer: '最上流：設計ツール',
    chokepoint: 'EDAデュオポリーの一角＋設計・検証IP',
    scores: { moat: 91, choke: 87, capital: 82, demand: 85, execution: 80 }, risk: 34,
    metrics: { '粗利益率': '≈88%', 'EDAシェア': '2社寡占', '営業利益率': '高位', '収益': 'サブスク型' },
    thesis: 'Synopsysと共にチップ設計の「言語」を握る。ハイパースケーラーのカスタムASIC急増はEDA需要をむしろ増幅する。設計の複雑化がそのまま堀の深化になる稀有な構造。',
    risk_note: 'Synopsysとの二強競争の均衡、地政学リスク、AIネイティブ設計ツールの新規参入。',
  },
  {
    ticker: 'AVGO', name: 'Broadcom', sector: 'カスタムASIC / ネットワーク',
    layer: 'アクセラレータ＋接続',
    chokepoint: 'ハイパースケーラー向けカスタムASIC設計＋AIネットワーキング',
    scores: { moat: 82, choke: 80, capital: 88, demand: 88, execution: 90 }, risk: 40,
    metrics: { 'AIバックログ': '≈$73B', '粗利益率': '≈75%', '主要顧客': 'Google/Meta等', 'FCF': '極めて高い' },
    thesis: 'NVIDIA最大の対抗軸。Google TPU・Meta MTIAの共同設計者として「顧客の反乱（脱NVIDIA）」を直接マネタイズ。ASIC市場が44.6%成長する構造の最大受益者で、Hock Tanの規律ある資本配分も強力。',
    risk_note: 'ASIC需要の顧客集中（少数のCSP依存）。CoWoS枠でNVIDIAに供給を絞られる構造的ハンデ。',
  },
  {
    ticker: 'ADTEST', name: 'Advantest (6857.T)', sector: '半導体テスト装置',
    layer: '後工程：テスト',
    chokepoint: 'AIチップ／HBM向けSoCテスタの実質独占',
    scores: { moat: 78, choke: 82, capital: 72, demand: 85, execution: 74 }, risk: 42,
    metrics: { 'SoCテストシェア': '首位独走', '粗利益率': '高位', '需要': 'HBM連動', '受注': '急拡大' },
    thesis: 'AIチップとHBMは複雑さゆえテスト工程が急増。GPUでもASICでも、高性能チップは必ずテスタを通る隠れたチョークポイント。生成AIの物量増がそのままテスタ需要になる「静かな独占」。',
    risk_note: 'テラダインとの競争、半導体サイクル連動、単一工程依存。',
  },
  {
    ticker: 'KLAC', name: 'KLA Corporation', sector: '検査・計測装置',
    layer: '製造：プロセス制御',
    chokepoint: 'プロセス制御（検査・計測）装置の圧倒的シェア',
    scores: { moat: 86, choke: 84, capital: 82, demand: 84, execution: 80 }, risk: 40,
    metrics: { '粗利益率': '≈60%', 'シェア': '>50%', '営業利益率': '高位', '需要': '微細化連動' },
    thesis: '微細化と先端パッケージングが進むほど欠陥検査の価値が上がる。歩留まりの守護神として、あらゆるファブが依存。ASMLに次ぐ装置分野の「準独占」。',
    risk_note: '装置サイクル、中国売上比率、微細化ペース鈍化リスク。',
  },
  {
    ticker: 'LRCX', name: 'Lam Research', sector: 'エッチング・成膜装置',
    layer: '製造：前工程',
    chokepoint: '3D構造・HBM積層に不可欠なエッチング／成膜',
    scores: { moat: 80, choke: 83, capital: 78, demand: 85, execution: 80 }, risk: 45,
    metrics: { '粗利益率': '≈48%', 'HBM露出': '高い', 'シェア': '上位寡占', '需要': '積層化連動' },
    thesis: 'HBMの多層スタックと3D NANDの高積層化はエッチング技術に直結。AIメモリ需要の爆発がそのまま装置需要に。TSV（シリコン貫通電極）加工の要。',
    risk_note: 'メモリサイクルへの感応度が高い。中国比率と装置需要の塊状性。',
  },
  {
    ticker: 'AMAT', name: 'Applied Materials', sector: '半導体製造装置（総合）',
    layer: '製造：前工程',
    chokepoint: '成膜・イオン注入など幅広い前工程装置の最大手',
    scores: { moat: 80, choke: 82, capital: 78, demand: 85, execution: 80 }, risk: 45,
    metrics: { '粗利益率': '≈48%', '製品幅': '最広', 'シェア': '首位級', '需要': '設備投資連動' },
    thesis: '装置分野で最も幅広いポートフォリオ。先端ロジック・HBM・先端パッケージングのどこが伸びても恩恵。材料工学の総合力が堀。',
    risk_note: '装置サイクル、中国売上、コモディティ工程の価格競争。',
  },
  {
    ticker: 'VRT', name: 'Vertiv Holdings', sector: 'データセンター電力・冷却',
    layer: 'インフラ：熱・電力',
    chokepoint: 'AIラックの液冷・電力供給インフラの主要サプライヤー',
    scores: { moat: 68, choke: 78, capital: 62, demand: 90, execution: 80 }, risk: 45,
    metrics: { '受注残': '急拡大', '液冷': '中核製品', '成長': '高い', '提携': 'NVIDIA連携' },
    thesis: 'Vera Rubin世代は100%液冷が必須。「電力と排熱の限界」がAI配備の律速になる中、冷却と電力供給は不可避の必然需要。チップの外側で確実に稼ぐインフラ層。',
    risk_note: '競合参入が比較的容易（堀は装置ほど深くない）。景気・建設サイクル感応度。',
  },
  {
    ticker: 'ANET', name: 'Arista Networks', sector: 'AIネットワーキング',
    layer: 'インフラ：ネットワーク',
    chokepoint: 'ハイパースケーラー向け高速イーサネットスイッチ',
    scores: { moat: 74, choke: 70, capital: 82, demand: 84, execution: 85 }, risk: 42,
    metrics: { '粗利益率': '≈64%', '主要顧客': 'Meta/MS等', '営業利益率': '高位', 'EOS': 'SW差別化' },
    thesis: 'GPUクラスタの規模拡大はネットワーク帯域の指数的需要を生む。EOSソフトウェアによる差別化と、NVIDIA InfiniBandに対するイーサネット陣営の旗手。Jayshree Ullalの実行力。',
    risk_note: '顧客集中（少数CSP依存）、NVIDIA(Mellanox)との直接競合、ホワイトボックス化圧力。',
  },
  {
    ticker: 'ALAB', name: 'Astera Labs', sector: '接続半導体',
    layer: 'アクセラレータ接続',
    chokepoint: 'PCIe/CXLリタイマ・接続ソリューション',
    scores: { moat: 66, choke: 72, capital: 70, demand: 82, execution: 74 }, risk: 58,
    metrics: { '成長率': '超高成長', '粗利益率': '高位', '規模': '小型', '需要': 'ラック大型化連動' },
    thesis: 'ラックスケール化でGPU/CPU/メモリ間の高速接続がボトルネックに。信号劣化を救うリタイマは物量増の隠れた勝者。小さいが構造的に不可欠な部品。',
    risk_note: '小型で単一領域依存、大手（Broadcom/Marvell）の参入、高いバリュエーション。',
  },
  {
    ticker: 'MRVL', name: 'Marvell Technology', sector: 'カスタムASIC / 光DSP',
    layer: 'アクセラレータ＋接続',
    chokepoint: 'カスタムASIC（Trainium/Maia）＋光通信DSP',
    scores: { moat: 72, choke: 72, capital: 78, demand: 82, execution: 78 }, risk: 48,
    metrics: { '主要顧客': 'AWS/MS', '光DSP': '首位級', '粗利益率': '高位', '成長': 'AI牽引' },
    thesis: 'AWS Trainium・Microsoft MaiaのASICを支える第2の対抗軸。加えて光通信DSPで1.6T時代の先行者。ハイパースケーラーの自給自足を直接マネタイズ。',
    risk_note: 'Broadcomとの競争、顧客集中、ASIC受注の変動。',
  },
  {
    ticker: 'MPWR', name: 'Monolithic Power', sector: '電源半導体',
    layer: 'アクセラレータ電源',
    chokepoint: 'GPU/AIチップ向け高効率パワーマネジメント',
    scores: { moat: 70, choke: 68, capital: 80, demand: 80, execution: 78 }, risk: 50,
    metrics: { '粗利益率': '≈55%', 'NVIDIA採用': 'あり', '成長': '高い', '効率': '技術優位' },
    thesis: 'GPUの消費電力急増は電源設計を極限まで要求する。高密度・高効率のパワーICは性能を左右する隠れたキーコンポーネント。AIチップの電力密度危機が追い風。',
    risk_note: 'アナログ競合の追随、NVIDIAの調達多様化、バリュエーション。',
  },
  {
    ticker: 'COHR', name: 'Coherent Corp', sector: '光通信部品',
    layer: 'インフラ：光インターコネクト',
    chokepoint: '光トランシーバ／レーザーの主要サプライヤー',
    scores: { moat: 62, choke: 68, capital: 55, demand: 82, execution: 68 }, risk: 55,
    metrics: { '光モジュール': '主要供給', '需要': '800G/1.6T', '負債': '要注視', '成長': '高い' },
    thesis: 'ラックスケール化とスケールアウトは光インターコネクトの需要を先行して生む。シリコンフォトニクスと1.6T光モジュールの本命。データセンター光化の必然。',
    risk_note: '負債水準、価格競争が激しい部品領域、中国サプライヤーとの競合。',
  },
  {
    ticker: 'CEG', name: 'Constellation Energy', sector: '電力（原子力）',
    layer: 'インフラ：電源（発電）',
    chokepoint: 'AIデータセンター向けの安定・脱炭素ベースロード電力',
    scores: { moat: 72, choke: 80, capital: 55, demand: 88, execution: 76 }, risk: 48,
    metrics: { '電源': '米最大級原子力', '契約': 'CSP直接供給', '希少性': '高い', '需要': '電力逼迫' },
    thesis: '「電力こそ次のボトルネック」。AIファクトリーはメガワット級の安定電源を要求し、24/7脱炭素電力を供給できる原子力は極めて希少。計算資源の律速が半導体から電力に移る構造の中核。',
    risk_note: '規制・政治リスク、電力価格変動、新設のリードタイムの長さ。',
  },
  {
    ticker: 'VST', name: 'Vistra Corp', sector: '電力（発電）',
    layer: 'インフラ：電源（発電）',
    chokepoint: 'AI需要地に近い発電容量（原子力含む）',
    scores: { moat: 60, choke: 72, capital: 55, demand: 85, execution: 72 }, risk: 55,
    metrics: { '発電容量': '大規模', '電源': '原子力＋ガス', '需要': '電力逼迫', '立地': '需要地近接' },
    thesis: 'データセンター向け電力逼迫の直接受益者。原子力とガスの発電容量で急増するAI負荷を吸収。電力が希少資源化するテーマの純粋なプレイ。',
    risk_note: '電力市場のボラティリティ、規制、燃料コスト、資本構成。',
  },
  {
    ticker: 'PLTR', name: 'Palantir', sector: 'AIソフトウェア',
    layer: 'アプリケーション層',
    chokepoint: 'オントロジーによる企業/政府データの深いロックイン',
    scores: { moat: 80, choke: 55, capital: 78, demand: 80, execution: 88 }, risk: 60,
    metrics: { '粗利益率': '≈80%', '解約率': '低い', 'AIP': '急拡大', '創業者': 'Karp' },
    thesis: 'ハードのコモディティ化が進んでも、価値はソフトとデータに移る。オントロジーは業務にAIを埋め込み剥がれにくいCUDA的ロックインを形成。推論需要の最終出口を握るアプリ層の候補。',
    risk_note: '極めて高いバリュエーション、政府売上依存、汎用LLM/エージェントによる代替可能性。',
  },
  {
    ticker: 'TEL', name: 'Tokyo Electron (8035.T)', sector: '半導体製造装置',
    layer: '製造：前工程＋パッケージ',
    chokepoint: 'コータ/デベロッパ・エッチング・先端パッケージ装置',
    scores: { moat: 78, choke: 80, capital: 76, demand: 84, execution: 78 }, risk: 44,
    metrics: { '粗利益率': '高位', 'コータシェア': '首位', 'HBM露出': '高い', '需要': '微細化連動' },
    thesis: 'EUV露光の前後工程（塗布現像）で圧倒的シェア。ASMLと補完関係にあり、先端ノードとHBMが伸びれば必ず恩恵。日本の装置チョークポイント。',
    risk_note: '装置サイクル、中国売上比率、地政学。',
  },
  {
    ticker: 'CAMT', name: 'Camtek (CAMT)', sector: 'パッケージ検査装置',
    layer: '後工程：先端パッケージ検査',
    chokepoint: 'CoWoS/HBM向け先端パッケージング検査の専業',
    scores: { moat: 68, choke: 76, capital: 70, demand: 84, execution: 72 }, risk: 55,
    metrics: { 'HBM/CoWoS': '直接露出', '成長': '高い', '規模': '小型', '専業性': '高い' },
    thesis: 'CoWoSとHBMの物量拡大の最も純粋なピュアプレイ。先端パッケージが最狭ボトルネックである以上、その検査装置は構造的な追い風を受ける小型の勝者。',
    risk_note: '小型で単一テーマ依存、大手装置メーカーの参入、パッケージ需要の変動。',
  },
  {
    ticker: 'HYNIX', name: 'SK Hynix (000660.KS)', sector: 'メモリ（HBM）',
    layer: 'メモリ製造',
    chokepoint: 'HBM（広帯域メモリ）の最先端リーダー',
    scores: { moat: 70, choke: 85, capital: 68, demand: 90, execution: 72 }, risk: 55,
    metrics: { 'HBMシェア': '首位', 'B200原価': 'HBMが最大', '26年枠': '完売', '需要': '爆発的' },
    thesis: 'B200の製造原価で最大要因はシリコンではなくHBM。AIチップの性能を決めるのはメモリ帯域であり、HBMの供給がGPU出荷の律速。NVIDIAの利益の一部を上流で回収する構造的勝者。',
    risk_note: 'メモリ市況の激しいサイクル性、Samsung/Micronの追い上げ、設備投資負担。',
  },
  {
    ticker: 'CRWV', name: 'CoreWeave', sector: 'ネオクラウド（GPUaaS）',
    layer: 'クラウド：GPUレンタル',
    chokepoint: 'GPU大量調達によるAI特化クラウド容量',
    scores: { moat: 45, choke: 50, capital: 40, demand: 82, execution: 70 }, risk: 78,
    metrics: { 'GPU保有': '大規模', '負債': '非常に高い', '成長': '爆発的', '顧客': '集中' },
    thesis: 'GPU供給制約下で「容量そのもの」を売る。需要が供給を上回る局面では高成長。ただしこれは堀ではなく調達力とレバレッジの勝負で、ハイリスク・ハイリターンの純粋な需要プレイ。',
    risk_note: '巨額の負債とGPU減価償却、顧客集中、GPU供給緩和・値下がりで一気に脆弱化。「次のNVIDIA」ではなく「NVIDIA依存」の典型。',
  },
  {
    ticker: 'MU', name: 'Micron Technology', sector: 'メモリ（HBM/NAND）',
    layer: 'メモリ製造',
    chokepoint: 'HBM/DRAM/NANDの三領域を持つ唯一の米国メモリ大手',
    scores: { moat: 62, choke: 78, capital: 62, demand: 88, execution: 74 }, risk: 55,
    metrics: { 'HBM': '第3極', 'CHIPS法': '巨額補助', '市況': 'シクリカル', '需要': 'AI牽引' },
    thesis: 'キオクシア型の凸性を体現するシクリカル・メモリ。市況反転＋HBM参入＋米政府のCHIPS法補助という「利益レバレッジ×生存保証」の組合せ。発見前フェーズでは総悲観に沈みやすい。',
    risk_note: 'メモリ市況の激しい変動、価格下落局面での急激な赤字化、HBMでの3番手ハンデ。',
  },
  {
    ticker: 'KIOX', name: 'キオクシア (285A.T・実データ)', sector: 'メモリ（NAND専業）',
    layer: 'メモリ製造',
    chokepoint: 'BiCS(CBA)＋AiSAQ。ただし本エントリは後知恵を排し実データで客観採点',
    scores: { moat: 68, choke: 76, capital: 62, demand: 88, execution: 74 }, risk: 58,
    metrics: { '上場': '2024/12', '市況': 'シクリカル', '真空': 'エンプラSSD', '需要': 'AI牽引' },
    thesis: '本物のキオクシア株（東証285A）。「暗黒期の型」アーキタイプ（後知恵）とは別に、他社と同じエンジンで実データ採点した客観エントリ。既に発見・再評価が進んだ現在の姿が出る。',
    risk_note: 'メモリ市況の激しい変動、上場後の需給、単一事業依存。',
  },
  {
    ticker: 'SNDK', name: 'Sandisk (WD分離)', sector: 'メモリ（NAND専業）',
    layer: 'メモリ製造',
    chokepoint: 'キオクシアと共同のNAND製造基盤を持つ純粋NANDプレイ',
    scores: { moat: 55, choke: 72, capital: 55, demand: 82, execution: 66 }, risk: 62,
    metrics: { 'NAND': '純粋プレイ', '提携': 'キオクシア共同', '市況': 'シクリカル', '需要': 'エンプラSSD' },
    thesis: 'キオクシアの「双子」。同じBiCS製造基盤を共有するNAND純粋プレイで、まさに需給の真空（エンプラSSD）の直接受益者。分離直後の低い注目度＝逆張り度が高い典型例。',
    risk_note: '分離直後の不安定さ、NAND市況の変動、単一事業依存、キオクシアとの提携依存。',
  },
];

// NVIDIA自身をベンチマーク（比較基準）として保持
const BENCHMARK = {
  ticker: 'NVDA', name: 'NVIDIA (現王者・基準)', sector: 'AIアクセラレータ',
  layer: 'アクセラレータ＋CUDA',
  chokepoint: 'CUDAエコシステム＋CoWoS枠買い占め＋ラックスケール統合',
  scores: { moat: 97, choke: 92, capital: 95, demand: 96, execution: 95 }, risk: 50,
  metrics: { '粗利益率': '≈75%', 'AIシェア': '75-87%', 'FCF(1Q)': '$49B', 'CoWoS枠': '≈60%' },
  thesis: '基準点。CUDAロックイン・チョークポイント買い占め・ラックスケール統合の三位一体。ただし高すぎる利益率自体が「NVIDIA包囲網」を招く。',
  risk_note: 'SCALE等の互換レイヤーによるコモディティ化、顧客(CSP)のASIC自給自足、TSMC単一依存の地政学。',
};
