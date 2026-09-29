# 地球と月の公転軌道

太陽のまわりを回る地球と月を、北黄極の側から見下ろして示す理科（天文）教材です。
完成品は 1 つの HTML ファイル（`earth-moon-orbits.html`）で、ダブルクリックで開けます。
12 言語で表示でき、言語ファイルを 1 つ足せば新しい言語を追加できます。

## フォルダ構成

```
src/
  app.html          ページ本体（HTML・CSS・JavaScript）。訳文は含まない
  locales/
    ja.json         基準の言語（原文）。訳者向けの注記（notes）もここに書く
    en.json など     言語ごとに 1 ファイル
tools/
  build.py              src から earth-moon-orbits.html を組み立てる
  check_translations.py 訳文のチェック（機械的なチェックと、Claude による内容の確認）
  snapshot.py           全言語の画面を撮影して、変更の前後を比べる
earth-moon-orbits.html  組み立て後の完成品。公開するのはこのファイル
```

`earth-moon-orbits.html` は直接編集しないでください。組み立てるたびに上書きされます。

## ふだんの作業の流れ

コマンドはプロジェクトのフォルダで実行します（Windows の例）。

1. `src/app.html` や `src/locales/*.json` を編集する
2. 組み立てる: `.venv\Scripts\python tools\build.py`
3. 訳文を機械的にチェックする: `.venv\Scripts\python tools\check_translations.py --dry-run`
4. 画面を確かめる（必要に応じて）: 下の「画面の比較」を参照

日本語（原文）を変えたときは、ほかの言語の訳も直し、3 のチェックで漏れがないか確かめます。

## 言語ファイルの書き方

言語ファイルは次の 4 つの部分からなります。

```json
{
  "meta":       { … その言語の設定 … },
  "strings":    { "title": "地球と月の公転軌道", … },
  "places":     { "tokyo": "東京", … },
  "solarTerms": [ "春分", "清明", … ]
}
```

### meta（言語の設定）

| 項目 | 内容 | 例 |
|---|---|---|
| `name` | 言語メニューに出す、その言語自身での名前（必須） | `"日本語"` |
| `locale` | 数や日付の書式に使うロケール（必須） | `"ja-JP"`、`"ar-u-nu-latn"` |
| `order` | 言語メニューでの順番。無い言語は最後に並ぶ | `2` |
| `dir` | 書く向き。右から左の言語だけ `"rtl"` | `"rtl"` |
| `googleFonts` | 追加で読み込む Google Fonts の指定。ラテン文字・キリル文字は不要 | `"BIZ+UDPGothic:wght@400;700"` |
| `fontUI`、`fontTitle` | 本文と題名の書体（CSS の font-family） | `"\"BIZ UDPGothic\", Meiryo, sans-serif"` |
| `titleLetterSpacing` | 題名の字間 | `".06em"` |
| `joinedScript` | 文字がつながる文字体系（アラビア文字など）なら `true`。字間を空けない | `true` |
| `largeNumbers` | 大きな距離の書き方。`myriad` は万・億の単位、`indian` はラーク・クロール。無ければ百万単位（`strings.kmMillion`） | `{"style": "myriad", "units": ["億", "万"], "separator": ""}` |
| `shortDate` | 図の中の短い日付。`"month/day"` なら 5/6 の形。無ければその言語の標準の短い形 | `"month/day"` |

### strings（訳文）

- キーは基準の `ja.json` と同じにします。値は訳文です。
- `{n}`、`{place}` などの波かっこは、実行時に数や地名が入る場所です。そのまま残し、語順に合わせて位置は動かしてかまいません。
- 数（`{n}`）によって語の形が変わる言語は、1 つの文字列の代わりに形ごとに書きます。

  ```json
  "daysUnit": { "one": "day", "other": "days" }
  ```

  使える形は `zero`・`one`・`two`・`few`・`many`・`other` で、`other` は必須です。どの数がどの形になるかは言語ごとに決まっていて（Unicode の CLDR の規則）、ブラウザが選びます。
- 配列の値（月相の名前、方位など）は、要素の数と順番を日本語と同じにします。

### places と solarTerms

- `places` は観測地の名前です。キー（`tokyo` など）は変えずに、名前だけを訳します。
- `solarTerms` は二十四節気の名前（春分から順に 24 個）です。二十四節気を使う言語だけに書きます。書いた言語では、二十四節気の表示が自動で有効になります。

### 注記（notes、ja.json だけ）

`ja.json` の `notes` には、訳者に伝えたいことをキーごとに書きます。ページには含まれません。

```json
"notes": {
  "vernalDir": { "note": "上の図の右端に右寄せで描く矢印の文字。…", "maxWidth": 56 }
}
```

- `note`: 表示される場所や、訳すときの注意。Claude による確認にも一緒に渡されます。
- `maxWidth`: 表示幅の上限（半角換算。全角文字は 2、結合文字は 0 と数える）。図の中の文字など、長すぎるとはみ出す文字に付けます。超えるとチェックで指摘されます。
- `onlyWithSolarTerms`: 二十四節気を使う言語でだけ表示する文字なら `true`。

## 新しい言語を追加する

ドイツ語（`de`）を例にします。

1. `src/locales/en.json` をコピーして `src/locales/de.json` を作る
2. `meta` を書き換える: `"name": "Deutsch"`、`"locale": "de-DE"`、`"order": 13`。英語用の設定が残っていれば消す
3. `strings` と `places` を訳す（`ja.json` の `notes` も参照）
4. 機械的にチェックする: `.venv\Scripts\python tools\check_translations.py --dry-run de`
   - キーの漏れ、`{n}` などの食い違い、表示幅の超過が指摘されます
5. 必要なら内容も確認する: `.venv\Scripts\python tools\check_translations.py de`
   - Claude が日本語の原文と照らして確認し、結果を `translation-report.md` に書き出します
   - `.env` に `ANTHROPIC_API_KEY` が必要です。1 言語あたり約 0.2 ドルかかります
6. 組み立てる: `.venv\Scripts\python tools\build.py`
7. 画面を確かめる: `.venv\Scripts\python tools\snapshot.py take shots --langs de` で `shots\de.png` を開く

プログラムの変更は要りません。ページは、ブラウザの言語設定が一致すれば、初めて開いたときにその言語で表示されます。

## 画面の比較

変更の前後で全言語の画面を撮影して比べられます（Microsoft Edge が必要です）。

```
.venv\Scripts\python tools\snapshot.py take before    # 変更前に撮影
（変更して build.py を実行）
.venv\Scripts\python tools\snapshot.py take after     # 変更後に撮影
.venv\Scripts\python tools\snapshot.py compare before after
```

- 2027 年 5 月 6 日 11:00（UTC）、東京で一時停止した状態を撮影します。
- 撮影のたびに差が出ないよう、Web フォントは読み込まず、パソコンにある書体で表示します。
- 差が 1 行（1 ピクセル）だけのときは、図の枠の端で起きる描画の揺らぎのことがあります。撮り直して確かめてください。

## 準備（初回だけ）

```
python -m venv .venv
.venv\Scripts\python -m pip install anthropic
```

`build.py` と `snapshot.py` は Python の標準機能だけで動きます。`check_translations.py` は、`--dry-run` で使う場合も `anthropic` パッケージが必要です。
翻訳チェックの結果（`translation-report.md`）は作業用の記録なので、git の記録の対象から外しています。

## ライセンス

MIT License です（[LICENSE](LICENSE)）。Copyright (c) 2026 ok1971

教材の利用・改変・再配布は、商用を含めて自由です。再配布するときは、著作権表示とライセンス文を残してください。
組み立てた `earth-moon-orbits.html` の先頭にも同じ文が入っているので、HTML ファイルだけを配る場合も、そのままで条件を満たします。

## 出典

- 地球の軌道: NASA/JPL（E. M. Standish）"Keplerian Elements for Approximate Positions of the Major Planets" の、地球と月の共通重心（EM Bary）の平均軌道要素 — https://ssd.jpl.nasa.gov/planets/approx_pos.html
- 月の位置: Jean Meeus, *Astronomical Algorithms*（第 2 版, 1998）第 47 章の表 47.A・47.B の主要項（Chapront らの月理論 ELP-2000/82 に基づく係数）
- 書体: IBM Plex、Noto Sans・Noto Serif、BIZ UDPGothic、Shippori Mincho B1 など。いずれも SIL Open Font License 1.1 の書体で、Google Fonts から読み込んでいます（このリポジトリには含みません）
- 翻訳の確認: `tools/check_translations.py` は Anthropic の Claude API（Python パッケージ `anthropic`）を使います。教材そのものは Claude API を使いません
