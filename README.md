# Tokyo Map Cool Route

暑い日に「今、出かけていいのか」「どの道を歩くべきか」に答える東京の暑さ対策マップ。

都知事杯オープンデータ・ハッカソン2026 応募作品。

A heat-safety map for Tokyo that answers two questions: *should I go out
now,* and *which way should I walk.*

<!-- TODO: デモURL / Demo URL -->
<!-- TODO: スクリーンショット1枚。READMEで一番効く。 -->

---

## 課題 / The problem

東京の夏は年々厳しくなっている。涼める場所も緑地も公開データとして存在するが、
「今この瞬間、この道を歩いて大丈夫か」という判断には結びついていない。

Tokyo publishes cooling shelters, green space, and real-time heat index
data — but none of it is connected to the decision a person actually
makes on a hot street: go now, or wait, and which way.

## やること / What it does

- **今の危険度** — 環境省のWBGT（暑さ指数）実況・予測から、公式の警戒レベルを表示
- **涼めるルート** — 緑地・水系・街路樹に近い経路を優先し、距離と暑さのトレードオフを提示
- **休憩場所** — クーリングシェルターとコンビニを経路上に表示
- **気候変動の可視化** — 過去のWBGTデータから危険日数の推移を提示

<!-- TODO: 実装できた範囲に合わせて削る。できていないものは書かない。 -->

## データ出典 / Data sources

東京都オープンデータカタログサイト、環境省、国土数値情報、OpenStreetMap。
取得日・ライセンスの詳細は **[SOURCES.md](SOURCES.md)** を参照。

Full provenance, retrieval dates and licences: **[SOURCES.md](SOURCES.md)**.

© OpenStreetMap contributors (ODbL)

---

## 開発 / Development

### 前提 / Requirements

- Python 3.11+
- Node.js 20+
- R2の認証情報（チーム内で共有）

### セットアップ / Setup

```bash
git clone <repo-url>
cd Tokyo_Map_Cool_Route

# Python
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 認証情報 / Credentials
cp .env.example .env            # 値を記入。.env は絶対にコミットしない

# 生データ取得 / Fetch raw data
python scripts/fetch_raw.py --list      # バケットの中身を確認
python scripts/fetch_raw.py

# フロントエンド / Frontend
cd web
npm install
npm run dev
```

### パイプライン / Pipeline

```
csv/  ──(scripts)──▶  cleaned_data/  ──(clip & simplify)──▶  web/public/data/
```

<!-- TODO: 実行順を確定して記載。例:
1. fetch_raw.py       R2から生データ取得
2. wbgt.py            WBGT履歴の集計とグラフ生成
3. ...
-->

**原則:** `csv/` の生データは絶対に直接編集しない。
`cleaned_data/` は削除してもスクリプト再実行で復元できる状態を保つ。

**Rule:** raw data in `csv/` is never edited in place. Everything in
`cleaned_data/` must be reproducible by re-running the scripts.

### ディレクトリ / Layout

```
*.py                 パイプライン / pipeline scripts
csv/                 生データ（gitignored, R2から取得）
<GIS folders>/       緑地・水系のシェープファイル
cleaned_data/        中間生成物（gitignored, 再生成可能）
outputs/             ピッチ用のグラフ・図
web/                 フロントエンド（React + Vite）
web/public/data/     アプリが読む軽量GeoJSON（コミットする）
```

### デプロイ / Deploy

Cloudflare Pages。ルートディレクトリは `web/`、ビルドは `npm run build`、
出力は `dist`。

---

## 注意 / Important

**健康に関する判断は行わない。** 警戒レベルと対処の指針は環境省の公式基準を
そのまま表示する。年齢・体調の入力は「何を表示するか」「いつ休憩を促すか」を
変えるだけで、独自のリスクスコアは算出しない。

**This app does not make health judgements.** Risk levels and guidance
come from 環境省's published thresholds. Age and condition inputs change
what is *shown* and when a break is *suggested* — they never feed an
invented risk score.

**個人情報は収集しない。** アカウント登録なし、年齢・体調の保存なし。

**ルート重み付けはヒューリスティック。** 暑さのペナルティ係数は独自の推定値で
あり、科学的根拠に基づくものではない。

## チーム / Team

<!-- TODO -->

## ライセンス / Licence

<!-- TODO: コード側のライセンスを決める。データのライセンスとは別。 -->
