# キーボード以外の操作とマクロ

通常の12キー・スティック4方向には、キーボード入力に加えてメディア・アプリ操作18項目、照明操作7項目を指定できます。
メーカーの共通ソフトにある選択肢の保存値を再現しています。実際の反応はファームウェア・OS・対象アプリに依存します。
この個体では音量アップと照明モード切り替えが動作し、照明オン／オフは反応しませんでした。

```powershell
uv run mkespn-k810-keyboard actions
uv run mkespn-k810-keyboard set-key kp1 volume-up --apply
uv run mkespn-k810-keyboard set-key kp1 play-pause --apply
uv run mkespn-k810-keyboard set-key kp1 led-mode --apply
```

キーの組み合わせ・マウス操作は、本体のEEPROMにマクロを保存して割り当てます。常駐アプリやPC側のキー変換は使いません。

```powershell
uv run mkespn-k810-keyboard shortcut kp1 left_ctrl c --apply
uv run mkespn-k810-keyboard mouse kp2 left --apply
uv run mkespn-k810-keyboard mouse kp3 scroll-up --apply
uv run mkespn-k810-keyboard set-macro kp4 my-macro.json --apply
```

`--apply` を外すとプレビューです。マクロのプレビューも空き領域確認のためEEPROMを読み取ります。
マクロは最大20枠、編集するイベント列は最大275行です。待機時間は8〜10,000ms、8ms単位に切り捨てます。
全キー・マウスボタンを離すイベントを含めてください。

`my-macro.json` の例：Ctrl+A → 100ms待機 → 左クリック。

```json
{
  "mode": "repeat",
  "repeat": 1,
  "events": [
    {"type": "key-down", "key": "left_ctrl", "delay": 8},
    {"type": "key-down", "key": "a", "delay": 8},
    {"type": "key-up", "key": "a", "delay": 8},
    {"type": "key-up", "key": "left_ctrl", "delay": 8},
    {"type": "delay", "delay": 100},
    {"type": "mouse-down", "button": "left", "delay": 8},
    {"type": "mouse-up", "button": "left", "delay": 8}
  ]
}
```

イベントは `key-down` / `key-up`、`mouse-down` / `mouse-up`（`left/right/middle`）、
`scroll`（`steps` = -127〜127、正が上）、`move`（`x/y` = -32767〜32767、正が右／下）、`delay`、`led`（照明シーケンス）。
各イベントの `delay` はその操作を実行した**後**の待機時間です。
繰り返し方法は `repeat`（1〜65535回）、`while-held`（押している間）、`until-click`（次のキー操作まで）です。
Web版ではキーの組み合わせ欄、マウス操作欄、行を追加・並べ替えできるマクロ編集画面から設定できます。

## バックアップと復元

マクロ保存前はEEPROM全8,192バイトを読み取り、SHA-256付きバックアップを保存します。
割り当てが参照しているマクロの領域を避け、未使用の消去済み領域へ新規保存します。
書き込む領域を再確認し、保存後は全8,192バイトを照合します。通信には時間がかかります。
空き領域がなければ保存しません。未参照の古いマクロを自動的に消去・圧縮する処理はありません。

```powershell
uv run mkespn-k810-keyboard backup backups/full.json --full
uv run mkespn-k810-keyboard restore backups/full.json --include-macros --apply
```

復元対象はキー表・ホイール・マクロ領域です。RGB設定、モード・ロック設定、EEPROMの予約領域は現在値を保持します。
旧形式の248バイトバックアップにはマクロ本体がないため、新しいマクロ割り当ての復元には使えません。
Web版の「現在の設定を保存」も完全バックアップを取得し、インポートすると同じ範囲を復元します。

LED挿入は点灯パターン・色番号・持続時間のシーケンスとして実装しています（実機検証中）。既存LED参照の領域も保護します。GPIO命令は未対応で、参照中のGPIOデータがあれば新規保存を中止します。

## 解析の根拠

- 単独機能の文字列→コード変換：`0x4080E0..0x4084E9`。`UniqueName` の0〜25番と対応。
- マクロのスロットコード：`A5..AF`, `B8..C0`。キー表から参照する20枠。
- マクロ表：設定先頭の `+0x1E` のLEポインタ。この個体は `0x01D8`。1枠5バイト。
- 表のシリアライズ：`0x411615..0x411690`。データのシリアライズ：`0x411790..0x41248B`。
- 表：`07, countLo7 | whileHeld<<7, addressLo, addressHi6 | untilClick<<7 | releaseFlag<<6, countHi`。
- データ：繰り返し回数LE16に続くイベント列、8バイト境界へゼロ埋め。
- 通常キー／マウスボタン：待機8ms単位の7bit値（押す場合bit7）＋コード。左／右／中ボタンは `F1/F3/F2`。メニューのコマンドIDと挿入ハンドラー、実機Raw Inputを照合した。初期実装の `F0/F1/F2` は表示変換用コードとの取り違えだった。
- 移動：`delay,F6,xLo,xHi,yLo,yHi`。スクロール：`delay,F7,steps,00`。
- 長い待機は元ソフトと同じ余りイベント＋`7F 00` の追加レコードへ変換。

`tools/verify_extended.py` は既知ハッシュのPE内の変換処理とApplyシリアライザをUnicornで実行し、
ホストのHID・ファイル・GUIへアクセスしないフックに置き換えます。
`tests/vendor_extended_vectors.json` とPython／JavaScript実装の出力を比較しています。

```powershell
uv run --group research python tools/verify_extended.py 'research/official/app/Gaming Keyboard.exe'
```

CLIで作成したCtrl+F13は、ブラウザの入力テスト欄で修飾キーを含む押下・解放を実機確認済みです。
全選択肢の実動作、繰り返し動作の長期実行、他OS・別ファームウェアは未検証です。

## LightタブとLED挿入

Light設定は本体へ保存します。CLIの `light` で読み取り、`set-light FILE --apply` で指定フィールドを変更できます。
色は7枠、各RGBは4bit精度です。消灯・赤の常時点灯・青の呼吸は実機確認済み。その他の効果と方向・対称・反応方式は調査中です。

```json
{"mode":"constant","brightness":6,"speed":3,"color_selection":1,
 "colors":[[255,15,15],[15,255,15],[15,15,255],[255,255,15],[15,255,255],[255,15,255],[255,255,255]]}
```

マクロの照明イベント例（色はLightタブのパレット番号）：

```json
{"events":[{"type":"led","sequence":[
 {"mode":"off","color":1,"duration_ms":1000},
 {"mode":"constant","color":1,"duration_ms":1000}
]}]}
```

1イベントあたり1〜16段階、持続時間100〜25500ms（100ms単位）、1マクロに5件まで挿入できます。
命令は `delay,F9,ptrLo,ptrHi6|behavior<<6`、参照先は `段階数-1,0,0,0` と `[モード,色,持続時間/100,1]` の列です。
`behavior` は0を既定とし、1・2の実動作は未確認です。Webの新規編集は0を使い、既存値1・2は保持します。

## PC側のライブラリと記録

実行に必要な命令列はキーボード本体のEEPROMへ保存します。マクロ名・グループ名・編集用データは元ソフトでもPC側の `macroGrp.ini` / `.dat` に別途保存します。
Webではこの編集用ライブラリをLocalStorageへ保存し、独自形式JSONで出し入れします。メーカー `.dat` との互換性はありません。
LocalStorageの内容はブラウザ・サイトのオリジンごとに分かれ、自動同期されません。JSONをエクスポートして別端末へ移せます。
ライブラリに保存するだけでは本体を変更しません。編集画面へ読み込み、キーへ割り当ててから本体へ保存します。

入力の記録はWebの記録欄にフォーカスしている間だけです。キー・マウスボタン・スクロールを記録し、停止時に押下中の入力を離す行を補います。
OS全体の操作、OS予約ショートカット、ポインター軌跡の自動記録は行いません。移動量は行編集で指定できます。

Webの「選択したキーのマクロを本体から読む」は、対応する命令列を編集画面へ読み込みます。未知命令や追加フラグは変換を中止し、元データを保持します。
