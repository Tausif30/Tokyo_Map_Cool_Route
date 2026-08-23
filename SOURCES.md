# データ出典 / Data Sources

このプロジェクトで使用しているデータの出典・取得日・ライセンスの一覧。

Provenance for every dataset used in this project. Fill in the TODOs by
checking each source directly — do not guess at licence terms.

**Rule:** if you add a dataset, add a row here in the same commit.

---

## 1. WBGT（暑さ指数）

| | |
|---|---|
| 出典 / Source | 環境省 熱中症予防情報サイト |
| URL | https://www.wbgt.env.go.jp/ |
| 取得日 / Retrieved | TODO |
| ファイル / Files | TODO |
| ライセンス / Licence | TODO — 利用規約を確認すること |
| 備考 / Notes | 提供期間は季節限定（概ね4月下旬〜10月下旬）。実況推定値・予測値・地点マスタあり。 |

## 2. クーリングシェルター / TOKYOクールシェアスポット

| | |
|---|---|
| 出典 / Source | 東京都 熱中症対策ポータル |
| URL | https://wbgt.metro.tokyo.lg.jp/ |
| 取得日 / Retrieved | TODO |
| ファイル / Files | TODO |
| ライセンス / Licence | TODO |
| 備考 / Notes | 住所のみ・座標なし。ジオコーディングが必要。施設により対象年齢・受入人数の制限あり。 |

## 3. 緑地・公園・水系データ

| | |
|---|---|
| 出典 / Source | 東京都オープンデータカタログサイト |
| URL | https://portal.data.metro.tokyo.lg.jp/ |
| 取得日 / Retrieved | TODO |
| データセット名 / Dataset | TODO — 01_公園・緑地等 / 08_水系 など、正式名称を記載 |
| ライセンス / Licence | TODO |
| 備考 / Notes | ポリゴンデータ。デモ対象区域にクリップして使用。 |

## 4. 行政区域データ

| | |
|---|---|
| 出典 / Source | 国土交通省 国土数値情報（N03 行政区域） |
| URL | https://nlftp.mlit.go.jp/ksj/jpgis/datalist/KsjTmplt-N03.html |
| 取得日 / Retrieved | TODO |
| 年度版 / Edition | TODO — 年度により仕様が異なるため必ず記載 |
| ライセンス / Licence | TODO |
| 備考 / Notes | ジオコーディング結果の検証（point-in-polygon）に使用。 |

## 5. コンビニエンスストア

| | |
|---|---|
| 出典 / Source | OpenStreetMap（Overpass API 経由） |
| URL | https://www.openstreetmap.org/ |
| 取得日 / Retrieved | Generated file records the UTC retrieval time |
| クエリ / Query | `nwr["shop"="convenience"]` in area JP-13 — see `scripts/fetch_convenience_stores.py` |
| ライセンス / Licence | ODbL — © OpenStreetMap contributors. 表示義務あり。 |
| 備考 / Notes | 補助データ。有志による整備のため網羅性は保証されない。 |

---

## ジオコーディング / Geocoding

| | |
|---|---|
| サービス / Service | TODO |
| ライセンス・保存可否 / Licence & caching | TODO — 結果の保存が許可されているか必ず確認 |
| 実施日 / Run date | TODO |

### 精度 / Accuracy

<!-- 検証後に記入。ピッチのデータ品質スライドの根拠になる。 -->

| | 件数 / Count |
|---|---|
| 入力レコード数 / Input records | TODO |
| ジオコーディング成功 / Geocoded | TODO |
| 区名が一致 / Ward matched (point-in-polygon) | TODO |
| 不一致・要確認 / Mismatched, inspected | TODO |
| 除外 / Dropped | TODO |

失敗の傾向 / Patterns in the failures:

- TODO

---

## 帰属表示 / Attribution

アプリ内に表示すること / Must appear in the app:

- © OpenStreetMap contributors (ODbL)
- TODO — 各データセットの要求する表示を追記
