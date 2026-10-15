# MKESPN K810 Python configurator

**ブラウザ版:** [K810 キーボード設定](https://skrtk98.github.io/MKESPN-K810-keyboard/)

PC版Chrome・Edgeから、専用アプリもPythonも使わず設定できます。キー図から選択して変更し、
変更一覧を確認して本体へ保存します。スマートフォン等のWebHID非対応環境ではデモのみ利用できます。
画面はデジタル庁デザインシステムの公式トークン・ボタン・セレクトCSSを同梱して使用しています。

ブラウザ内でUSB通信が完結し、設定データをサーバーへ送信しません。アクセス解析やCDNへの依存はありません。
Web版では12キーとスティック4方向のみ変更・復元し、ホイールや他のマトリクス行は読み取った値を保持します。
書き込み前に復元用データをローカルストレージへ保存し、本体を再読して他のアプリによる変更がないか確認します。
書き込み後は248バイト全体を照合します。復元用データの保存に失敗したときは書き込みません。

```powershell
# Web版のローカル起動。http://localhost:8765/ を開く
uv run python -m http.server 8765 --bind 127.0.0.1 --directory web

# Web版のテスト（Node.js 22以上）
node --test tests/web-protocol.test.mjs
```

公開は [.github/workflows/pages.yml](.github/workflows/pages.yml) が行います。
GitHubのSettings → Pages → SourceをGitHub Actionsに設定すると、`main` へのWeb版変更のpushで
テスト後に `web/` だけが公開されます。メーカー配布物・機器バックアップ・Python環境は公開対象に含みません。

Web版の設計と検証範囲は [WEBHID.md](docs/WEBHID.md) を参照してください。

メーカーの設定アプリをインストールせず、PythonからK810本体のキー割り当てを変更します。
Windows上の実機 `30FA:2350` で、1キーを `Q → F13 → Q` と変更し、読み戻しと復元を確認済みです。
元アプリ・インストーラは実行していません。解析には展開した実行ファイルを使っています。

## できること

- 12キーとスティック4方向を、通常キー・F1〜F24などの単一キーへ変更
- 現在の割り当ての表示
- 設定領域248バイトのJSONバックアップ
- バックアップからキー割り当てを復元
- 書き込み前のパケットプレビュー、書き込み前の自動バックアップ、書き込み後の全領域照合

**未実装:** キーの組み合わせ（Ctrl+C等）、連続マクロ、RGB、ホイール、プロファイル切替。
今回の実機確認はEEPROMの読み戻しまでです。実際のキー入力イベントと、USB抜き差し後の保持はまだ確認していません。
macOS/Linuxへの対応は実機未検証です。通常はOS標準HIDドライバを使用します。

## 起動

Python 3.12以上と [uv](https://docs.astral.sh/uv/) がある環境で、K810をUSB接続して実行します。

```powershell
uv run mkespn-k810-keyboard list
uv run mkespn-k810-keyboard info
uv run mkespn-k810-keyboard show
uv run mkespn-k810-keyboard backup
```

uvを使わない場合は `python -m pip install -e .` でインストールし、
`python -m mkespn_k810_keyboard show` のようにも起動できます。
メーカーアプリは必要ありません。管理者権限・ドライバ置き換えも、このWindows実機では不要でした。

## キーの変更

例えば `kp1` と呼ぶ位置をF13へ変更する場合:

```powershell
# 送信予定の書き込みパケットを表示。設定を読み取るがEEPROMへは書き込まない
uv run mkespn-k810-keyboard set-key kp1 f13

# 実際に書き込む。元の設定をbackups/へ自動保存し、読み戻して照合する
uv run mkespn-k810-keyboard set-key kp1 f13 --apply

# スティック上方向にWを割り当てる
uv run mkespn-k810-keyboard set-key up w --apply
```

`--apply` がない場合はプレビューです。プレビューと `show` も読み取り用のFeature Reportを送りますが、
EEPROMへの書き込み確定コマンドは送りません。`list` は機器の列挙だけを行います。

設定用コレクションが複数見つかった場合は、`list` に表示される `path` を指定します。

```powershell
uv run mkespn-k810-keyboard --path 'listで表示されたパス' show
```

### 位置の名前

`kp1` などは**メーカー設定ファイル内の工場出荷時の機能名**です。キーキャップの刻印や現在出力されるキーを表す名前ではありません。
この実機では `kp1` がQを出力する位置でした。
次の配置は付属UIの座標から読み取ったものです（K810を通常の向きで見た位置）。

```text
┌──────┬──────┬──────┬──────┬──────┐
│ kp1  │ kp2  │ kp3  │ kp4  │ kp5  │
├──────┼──────┼──────┼──────┼──────┤
│ kp6  │ kp7  │ kp8  │     enter    │
├──────┴──────┼──────┼──────┤       │
│    tab     │ kp9  │ kp0  │       │
└────────────┴──────┴──────┴───────┘
                          スティック: up / down / left / right
```

指定できる出力キー: `a`〜`z`、`0`〜`9`、`f1`〜`f24`、`kp0`〜`kp9`、
`enter`、`kp_enter`、`tab`、`escape`、`space`、`backspace`、`delete`、
`left/right/up/down`、`left_ctrl` 等、`none`。
USB HID Keyboard Usage IDを `0x68` のように指定することもできます。
文字列やショートカット記法は受け付けません。JIS固有キーなどの挙動は未確認です。

### 復元

```powershell
# ファイル名はbackupコマンドで表示されたものに置き換える
uv run mkespn-k810-keyboard restore backups/initial.json
uv run mkespn-k810-keyboard restore backups/initial.json --apply
```

復元対象はキー割り当てテーブル160バイトです。RGB等の領域には書き込みません。
バックアップはEEPROM全体やファームウェアのイメージではなく、設定領域248バイトのスナップショットです。
別個体を識別するシリアル番号はこの実機から取得できないため、バックアップは同じ個体に使用してください。
書き込みの途中で失敗した場合は表示されたバックアップから復元できます。途中失敗時の自動ロールバックはありません。

## 解析と検証

[解析記録](docs/PROTOCOL.md) に入手先、SHA-256、解析アドレス、パケット形式、検証範囲を記載しています。
メーカーアプリの通信処理だけをUnicorn内でエミュレートし、HID/Sleep呼び出しを置き換えて取得した
参照パケットとPython実装を比較しています。通常の利用時に解析ツールや元アプリは不要です。

```powershell
uv run python -m unittest discover -s tests -v

# 解析再現用。既知ハッシュの展開済みファイルが必要
uv run --group research python tools/verify_vendor.py 'research/extracted/app/Gaming Keyboard.exe'
```

参考: [kuriharaさんの分解記事](https://kurihara.hatenadiary.jp/entry/MKESPN_K810_keyboard)。
メーカー配布物とバックアップはローカルの `research/`、`backups/` に保存し、Git管理から除外しています。
