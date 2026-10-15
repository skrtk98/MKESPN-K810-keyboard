# MKESPN K810 / Instant K201 protocol notes

解析日: 2026-10-15。静的解析と、ユーザーが接続した実機での読み書き確認。

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
Pythonもこれを踏襲するが、アプリが毎回行う全設定の再書き込みは行わず、変更したブロックだけを書き込む。

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
`base + 0x20` へのホイール用ニブル設定書き込みも `0x410FF7..0x41101C` にあるが未実装。
RGBのパック処理は他のオフセットにある。現時点ではキー割り当てのみ書き換える。

## Verification

`tools/verify_vendor.py` は既知ハッシュのPEをUnicornの仮想メモリに置き、上記3つの狭い処理範囲だけをエミュレートする。
HIDとSleepはPythonのフックで置き換え、範囲外への実行は拒否する。
出力した `tests/vendor_vectors.json` は元アプリの命令列から得た参照値。
ユニットテストでPythonの読み出しシーケンス、書き込みパケット、表の配置を照合する。

2026-10-15 の実機検証:

- `info`, `backup`, `show`, `set-key` プレビューが成功。
- `kp1` ブロックの先頭 `14` (Q) を `68` (F13) に一時変更。
- 設定領域248バイトを読み戻し、変更対象の1バイトだけが変わったことを確認。
- 元ブロックへ復元し、248バイト全体が初回のバックアップと一致。
- 操作前バックアップ: ローカル `backups/initial.json`。検証ログ: ローカル `research/hardware-test.json`。

入力イベント・USB抜き差し後の保持・マクロとの併用・別ファームウェアは未確認。
これは不揮発メモリへの書き込み処理とその読み戻しを確認したもので、全機能の互換性試験ではない。
