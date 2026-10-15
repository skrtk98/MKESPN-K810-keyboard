# MKESPN K810 / Instant K201 protocol notes

解析日: 2026-10-15。静的解析と、ユーザーが接続した実機での読み書き確認。

メディア・照明操作と、キーボード／マウスマクロの保存形式・追加検証は [MACROS.md](MACROS.md) を参照。
通常設定の248バイトバックアップに加え、マクロ操作ではEEPROM全8,192バイトをバックアップ・照合する。

## Sources and reproducibility

- [参考分解記事](https://kurihara.hatenadiary.jp/entry/MKESPN_K810_keyboard): Instant K201とAT24C64Nの記載。
- [メーカーDriver Download](http://www.mkespnhk.com/Download.aspx?ClassID=37&page=3)
- メーカー掲載の [20250625094337.zip](http://www.mkespnhk.com/upload/20250625094337.zip)
  - ZIP SHA-256: `7a1dfd08d2bad897323beba37a06d903a12119230a4fc171b11e4a94bac08b8c`
  - `MKESPN-K810.[20250610].exe` SHA-256: `b27beac5b0447a55201af747803a85dd002fde74782421f1a785a57ef9163f39`
- [販売店の旧配布ZIP](https://hysc.com.tw/mkespn%20drivers/K810_keyboard_driver.zip)
  - ZIP SHA-256: `f9f9d0e78ca3b89cefef57097cbecbe07cbf41698b1648ac4ead8a326204ca51`
  - `MKESPN-K810.[20240628].exe` SHA-256: `c38c9bd50bc0500dafc576cf1b341a0e8ae506d2e283846d0acc0b4ba2df7827`

両インストーラはInno Setup。公式 [innoextract 1.9](https://constexpr.org/innoextract/) で展開。
両方の `app/Gaming Keyboard.exe` は同一:

```text
SHA-256 ef79b5e0ad1786dd682bc8ed1dad4626627c0518639ec67a702088d6322b8e36
Size    4087792 bytes
PE32 x86 / ImageBase 0x400000
```

インストーラも設定アプリもホスト上では実行していない。USB制御にメーカーDLLは使っていない。
解析対象の安全性を監査・保証したものではない。配布物の再配布は行わない。

## Device selection

アプリのデータにあるVID/PIDペアは `30FA:2350` と `2130:30FA`。
後者は未検証。接続した実機は次のとおり:

```text
VID 30FA / PID 2350 / release 0100
manufacturer INSTANT / product USB Keyboard
interface 1 / collection 7 / UsagePage FF01 / Usage 0001
HidP_GetCaps: FeatureReportByteLength = 8
```

`FF00:0001` は別の入力用コレクション。キーボード入力のコレクションには設定パケットを送らない。
選択処理は元アプリ `0x407852..0x407A06` を参照。

## Feature reports

Report IDは7。SET_FEATUREは8バイト。通常パケット:

| Offset | Meaning |
| --- | --- |
| 0 | `07` report ID |
| 1 | `18` command family |
| 2 | operation |
| 3 | byte index within staged block |
| 4..5 | EEPROM address, little endian |
| 6 | staged byte value |
| 7 | block length minus one |

バイナリにはBSS変数 `0x63DDA8` が非ゼロなら末尾へ0x60を加算する別分岐もある。
調べたアプリではこの変数への直接書き込み参照は見つからず、今回の実機は通常分岐で動作した。
Python実装は通常分岐のみ。別モデルへの汎用USBライタではない。

### Metadata

`HidD_GetFeature(report 7, length 16)`。末尾2バイト `[14:16]` は設定領域先頭。
元アプリ `0x410336..0x41035B`。今回の応答:

```text
07 00 41 40 43 01 02 01 01 02 64 02 28 01 e0 00
configuration base = 0x00E0
```

同じreport IDでも要求長で読み出し内容が変わる。21バイト読み出しは他の機器状態を含む。
メタデータ各フィールドの意味は先頭アドレス以外未確定。

### Block read (`0x406FD0..0x4071C8`)

1. 各バイトについて `op=03, index=i, address=A, value=0, last=N-1` を送る。
2. 1ms待機、`op=00, address=A, index/value/last=0`。
3. 1ms待機。各バイトについて `op=05, index=i, address=A, value=0, last=N-1`。
4. 1ms待機してGET_FEATURE 8バイト。応答 `[1]` がそのバイト。
5. 最後に1ms待機して `07 18 01 00 00 00 00 00`。

`op=03` はステージング。読み取り手順では `op=09` を送らず、EEPROMの更新を確定しない。
元アプリもこの一見書き込みに似た手順で読み出す。

### Block write (`0x4071D0..0x407331`)

1. 各バイトについて `op=03, index=i, address=A, value=data[i], last=N-1`。
2. 2ms待機、`op=09, address=A, index/value=0, last=N-1` で確定。
3. 10ms待機、`op=01, address=A, index/value/last=0`。

アプリのApply処理は先に `07 09 41 00 00 00 00 00` を送って200ms待つ (`0x410239..0x410276`)。
最後に `07 18 11 00 00 00 00 00`、10ms、`07 18 00 00 00 00 00 00` (`0x4124B5..0x412523`)。
Pythonもこれを踏襲する。全設定を再書き込みせず、現在の先頭制御ブロック8バイトと変更したブロックを書き込む。
読み取りを含む設定通信の終了時には上記の全体終了処理に続けて
`07 20 00 00 00 00 00 00` と10ms待機を行う（元アプリ終了処理 `0x412800` / `0x414A1B`）。
ブロック単位の `18 01`、または `07 20` 単独では実機入力が再開しない場面があった。
全体終了処理の送信と診断用入力監視の終了後、USBを抜き差しせずキーとホイールが再び動作した。
修正済みCLIでの復元後にも、ユーザーが音量変化を確認した。

## Configuration region

キー表は `base + 0x48` から160バイト（8行×20列）。
元アプリのメモリ内表はrow-majorだが、EEPROMはcolumn-major。
シリアライザ `0x411021..0x411134` は毎回8バイトを作り20ブロック送る。

```text
EEPROM offset = 0x48 + column * 8 + row
```

`config/KBconfig.ini` の `[KBconfig] 0_0..0_15` が、12キーと4方向の工場出荷時HID Usage IDを示す。
K810では該当コントロールはすべてrow=0。
row=1..7は今回の実機ではFF。これらは8バイト書き込み時も読み出した値をそのまま維持する。

| Control | Column | Default usage | 実機の当初割り当て |
| --- | ---: | ---: | --- |
| kp1 | 0 | 59 | Q |
| kp2 | 1 | 5A | W |
| kp3 | 2 | 5B | E |
| kp4 | 3 | 5C | R |
| kp5 | 4 | 5D | Escape |
| kp6 | 5 | 5E | A |
| kp7 | 6 | 5F | S |
| kp8 | 7 | 60 | D |
| enter | 8 | 28 | Enter |
| tab | 9 | 2B | Tab |
| kp9 | 10 | 61 | Space |
| kp0 | 11 | 62 | C |
| left | 12 | 50 | Left |
| right | 13 | 4F | Right |
| down | 14 | 51 | Down |
| up | 15 | 52 | Up |

表の値は16進数。16/17列はホイール関連で、単純なKeyboard Usage IDとしては公開していない。
`base + 0xE8..0xF3` はFn設定らしき12バイト。マクロ本体はバックアップ範囲外にある。
RGBのパック処理は他のオフセットにある。

### Wheel assignments

`base + 0x20` の1バイトに上方向を上位4ビット、下方向を下位4ビットとして格納する。
方向名はメーカー表記 `Roll Up` / `Roll Down`。メニュー処理 `0x420D00` は
選択インデックス124/125に対し、8項目を次の値へ変換する。

| Value | CLI action |
| ---: | --- |
| 0 | volume-up |
| 1 | volume-down |
| 2 | scroll-up |
| 3 | scroll-down |
| 7 | led-speed-up |
| 8 | led-speed-down |
| 9 | led-brightness-up |
| 10 | led-brightness-down |

`KbIndexText.ini` の98..105番の表示ラベルとも一致する。
パック処理 `0x410FF7..0x411021` は `(up << 4) | (down & 15)` を作り、
`0x4071D0` へ長さ1で渡す。隣接バイトやマトリクスの16/17列には書き込まない。
予約値4/5/6/11..15は選択肢として公開しない。任意キー・マクロの割り当てではない。
実機の当初値は `10`。前回、スティック押し込みを必要な操作と案内したが、元アプリの仕様としての確認が不足していた。
LEDの4項目は設定値のみ解析済みで、物理的なLED変化は未検証。

## Verification

`tools/verify_vendor.py` は既知ハッシュのPEをUnicornの仮想メモリに置き、通信・表配置・ホイールメニューとパックの狭い処理範囲だけをエミュレートする。
HIDとSleepはPythonのフックで置き換え、範囲外への実行は拒否する。
出力した `tests/vendor_vectors.json` は元アプリの命令列から得た参照値。
ユニットテストでPythonの読み出しシーケンス、書き込みパケット、表の配置を照合する。

2026-10-15 の実機検証:

- `info`, `backup`, `show`, `set-key` プレビューが成功。
- `kp1` ブロックの先頭 `14` (Q) を `68` (F13) に一時変更。
- 設定領域248バイトを読み戻し、変更対象の1バイトだけが変わったことを確認。
- 元ブロックへ復元し、248バイト全体が初回のバックアップと一致。
- 操作前バックアップ: ローカル `backups/initial.json`。検証ログ: ローカル `research/hardware-test.json`。

追加のホイール検証では `10 → 20 → 23` と各1バイトを書き換え、各操作で248バイトを照合した。
USB再接続後、ユーザーが音量モードとスティック押し込み後のスクロールを確認した。
全体終了処理を修正したCLIで `10` へ復元し、USB再接続なしで音量操作できることも確認した。
キー割り当てとホイール設定は復元済み。実機のモード操作等でヘッダーやLED状態の一部が変化したため、
この追加検証後の全248バイトが当初バックアップと同一とは主張しない。

キーの各割り当ての入力イベント・マクロとの併用・別ファームウェアは未確認。
全機能の互換性試験ではない。

### 再調査：保存値と実動作の不一致

ユーザーからWeb版で反映されないとの報告を受け、メーカー配布ZIPを再取得した。
2026-10-15時点の掲載先は同じで、ZIP SHA-256も上記と一致した。
`tools/trace_vendor_apply.py` で `0x410239..0x412528` のマクロなしApply経路を
通してエミュレートし、通信API・Sleep・ブロック読み書きをフックした。
これは合成状態からの命令実行トレースであり、実機USBキャプチャではない。

元アプリの順序は、`07 09 41` → メタデータ取得 → `D0` ヘッダー →
`base + 0` 制御ブロック8バイト → 他設定 → `base + 0x20` ホイール → キー表 → 全体終了。
`0x41084F..0x410982` は先頭バイトのbit7にINIの `KEYSMODE` (`0x61F104`) を格納する。
bit6は `BALTF4` (`0x63DDD8`) に由来し、ホイール専用フラグではない。
元アプリは設定UIの初期化後に `KEYSMODE=1` を設定する (`0x41492A`)。

初期実装は値が変わるブロックだけを送ったため、先頭ブロックが抜けていた。
現在値 `C0 F0 1F 0F 1F FF 00 F0` をそのまま8バイト再送し、ホイールを `01 → 23` としたところ、
248バイトの照合が一致し、ユーザーがスティック押し込み・USB再接続なしのスクロールを確認した。
この差分と実機観測から、先頭ブロック再送の省略が今回の反映不良の原因と判断した。
ファームウェア内部の正確なラッチ動作は未解析であり、全ビットの意味を確定したわけではない。

修正では先頭8バイトを読み取ったまま再送する。インポートからのモード・ロック・LED等の変更は許可しない。
スティック押し込みを必須手順とする案内は撤回した。
修正版Web UIでも `01 → 23` の保存・248バイト照合後、ユーザーがそのままスクロールできると確認した。
調査終了時は今回の開始時点のホイール値 `01` へ戻し、キー割り当て・制御ブロックは保持した。
Web切断後にPythonで独立して読み直し、設定領域248バイト全体が今回の調査開始時と一致することも確認した。

再現コマンド（元アプリのネイティブ実行は不要）:

```powershell
uv run --group research python tools/trace_vendor_apply.py 'research/official/app/Gaming Keyboard.exe' tests/vendor_apply_vectors.json
```
