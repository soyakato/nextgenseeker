# NextGenSeeker — 客観ファクター・スクリーナー

銘柄選定・採点・自己改善まで**人手を排した全自動**の学習用スクリーナー。
「次のNVIDIA/キオクシアを人が語る」のではなく、**実データだけが銘柄を浮かび上がらせる**設計。

## 起動方法

```bash
cd nextgenseeker
python3 -m http.server 4178        # → http://localhost:4178
python3 pipeline/refresh.py        # データ手動更新（自動更新は下記）
```

## アーキテクチャ（v3系）

```
Yahooスクリーナー和集合 ──→ 客観ユニバース（毎回自動構築・固定リストなし）
        │
        ├─ factors.py     6客観ファクター（財務諸表・株価から機械算出）
        │                   DOL(Novy-Marx) / コスト硬直性(Weiss) / Merton距離デフォルト
        │                   (Bharath-Shumway) / R&D強度(Chan et al.) / 逆張り変曲 / 資金勢い
        │                   → 横断パーセンタイル → 合成スコア
        │
        ├─ learning.py    自己改善: 日次コホート記録 → 20/60営業日後にSPY超過で採点
        │                   → ファクター別IC → 重み調整（×0.5〜1.6クランプ・180日忘却・
        │                   12件未満は不動・ユニバース離脱銘柄も価格補完して必ず採点）
        │
        └─ watch.py       ウォッチ＆兆候レーダー（継続選出→触媒→価格確認）
             ├─ fetch_news.py   Yahooニュース（直近7日）
             ├─ fetch_edgar.py  SEC 8-K一次情報（Item番号の機械判定・2倍重み）
             ├─ news_judge.py   Claude API（企業名マスキング）＋ルールベース辞書
             └─ 兆候スコア=継続30%+ニュース40%+確認30% → ⚡アラート
                 → macOS通知 → 5/20営業日後に採点 → 的中率を自己検証
```

## 客観性の設計原則

| 排除したもの | 置き換え |
|---|---|
| 手書きの銘柄リスト（選定バイアス） | スクリーナー和集合の自動ユニバース |
| 手書きのスコア・事前分布・後知恵アーキタイプ | 財務諸表・株価からの機械算出 |
| 手書きの技術キーワード | R&D強度（財務諸表から自動） |
| LLMのブランド事前知識バイアス | 企業名マスキング（X社化） |
| 過剰適応（ガラパゴス化） | IC学習のクランプ・忘却・不動条件、セクター集中HHI警告 |

**残る設計判断（UIにも開示）**: ファクター数式・初期重みは学術文献に依拠した設計値（ICで自動調整）。
ユニバースは米国スクリーナー基盤。先行指標トラッカー・主観フレーム（NVIDIA-DNA）はキュレーション参考であり客観スコアに不使用。

## クラウド完全独立運転（GitHub Actions + Pages）

- **サイト**: https://soyakato.github.io/nextgenseeker/ （スマホからいつでも閲覧可）
- **自動更新**: `.github/workflows/refresh.yml` が6時間ごとにクラウドでパイプラインを実行し、
  `live/*.json` をコミット（Macは不要）。cronは±15〜60分の遅延があり得る。
- **スマホ通知**: ⚡アラート時に ntfy.sh へプッシュ。スマホのntfyアプリ（無料）で
  トピック `ngs-alerts-ce34156e108d` を購読すると届く。
- **状態の永続化**: 採点台帳（learning_ledger / watch_state）はリポジトリにコミットされ引き継がれる。
- **Claude API**: リポジトリSecretsに `ANTHROPIC_API_KEY` を追加すると次回からLLM判定が有効化。

### ローカル実行（任意・開発用）

```bash
bash pipeline/install_scheduler.sh        # macOS launchd（クラウドと併用は非推奨=二重実行）
bash pipeline/install_scheduler.sh --uninstall
```

## Claude API（任意）

```bash
cp pipeline/.env.example pipeline/.env    # ANTHROPIC_API_KEY を記入
```
ニュース判定とアナリスト読み筋がLLM化される（未設定ならルールベースで完全動作）。

## 生成物（live/）

`foresight.json`(ファクター) / `learning.json`(IC・重み) / `watch.json`(兆候・アラート) /
`financials.json` / `indicators.json` / `history.json` / `learning_ledger.json`(採点台帳・**消さないこと**) /
`watch_state.json`(出現履歴・アラート台帳)

## 免責

教育目的であり投資助言ではない。ファクターは代理指標を含む近似。
未実装: CDS乖離(Merton CCA)・特許全文LLM・完全PiTデータ・TVTP-MS・生存者バイアス補正。
