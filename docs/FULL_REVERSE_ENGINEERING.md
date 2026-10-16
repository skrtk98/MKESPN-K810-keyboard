# 元ソフト全体の解析台帳

開始・更新：2026-10-16。既知SHA256のメーカー配布EXEを対象とする。
今回の追加解析では実機への通信も元ソフトのネイティブ実行も行っていない。
完了した範囲と未解明部分を分け、全体の解析完了とはまだ扱わない。

## 範囲と調査単位

K810の機能、GUIイベント、PC側保存形式、本体側保存形式、USBコマンドを対応付ける。
静的リンクされたMFCの汎用メニューと、K810で使う処理は分ける。
共通バイナリに分岐があるだけの機能を、K810が実装しているとは見なさない。
本体ファームウェアは配布EXEとは別の解析対象で、現在イメージを同定していない。
チップメーカーの参照ソフト2種・仕様書の追加比較は[CHIP_REFERENCE.md](CHIP_REFERENCE.md)に記録する。
マクロ表の使用数境界と追加フラグは[MACRO_DEEP_ANALYSIS.md](MACRO_DEEP_ANALYSIS.md)に追記した。

`catalog_vendor_surface.py` で英語スキンを棚卸しした。
コメント行と単なる名称対訳表を除き、座標を持つ定義は151個だった。
これは実行時に全てが有効という意味ではない。

| ファイル | 座標付き定義 |
| --- | ---: |
| KB.ini | 18 |
| skin_main.ini | 13 |
| skin_kbset.ini | 15 |
| skin_mac.ini | 15 |
| skin_color.ini | 41 |
| skin_sound.ini | 43 |
| skin_modkey.ini | 4 |
| LBWarning.ini | 2 |

ネイティブメニューは5資源、コマンド項目は言語重複を含め52個。
英語のアプリ用はマクロ編集メニュー200の20項目とトレイ201の2項目。
137/138は別言語の同等メニュー、16102はMFC汎用カスタマイズメニュー。
各コマンドIDをMFCメッセージ表の候補ハンドラへ結び付けた。

## 新たに検証した名前→コード変換

変換関数内のリテラル文字列分岐を検出し、各分岐をUnicornで実行した。
以下は行列キー用の独自コード。マクロ命令のF6等とは名前空間が異なる。

| 名前 | 値 |
| --- | --- |
| R-Win | E7 |
| Wakeup | B2 |
| BOSS | B3 |
| € | B4 |
| ¥ | B5 |
| 000 | B6 |
| 00 | B7 |
| Record | DB |
| Rewind | DC |
| Eject | DD |
| Min | DE |
| Screen Save | DF |
| Exchange 4Keys | EE |
| Led Config | EF |
| Mode | F2 |
| KBD Mode | F4 |
| KBD Mode Reset | F5 |
| User Define | FE |
| WINLOCK | F6 |
| NO FUNCTION | FF |

20分岐のコード変換を確認したが、この全項目のK810での実動作は未検証。
破壊的なリセット等を含むため、名前だけで実機へ一括設定していない。
別途、グローバルの翻訳文字列を参照する変換分岐の網羅が必要。

その後、英語KbIndexText.iniのBUTTONPOS・UniqueNameと、合成した20マクロ名を
実際の文字列テーブルへ配置し、408520..40AB93の変換本体を216入力で検証した。
Fn→F1、Full-key Locked→F3、Backlight On/Off→F0、20番目のマクロ→C0を確認。
表示用文字列等、キー変換の対象ではない入力も含むため、216個の割り当て機能があるという意味ではない。
名称からコードを得る部分は、部分分岐の推測だけでなく関数全体でも確認した。

### Fn用の変換と保存領域

Fn用名称変換4080E0..4084E9は通常行列の408520とは別。
同じ英語216入力を、入力文字列ポインターの上位バイトを1/2に変えた2条件で実行した。
一定の値を返すのは26名称で、メディア18項目、Full-key Locked、照明操作7項目だった。
それぞれ通常行列の同名操作と同じコードになる。
このほか関数内に中国語固定文字列の分岐も存在するが、この26件の件数には含めない。

未対応名の経路4084DBは[ebp+0B]（入力ポインター上位バイト）を結果へ取り込む。
無効値FFを必ず返す安全なAPIではないため、この挙動を互換パーサーの許容条件にしてはいけない。
`verify_key_converter.py --fn`に2ポインター条件の観測結果を記録する。

Fn設定はRAMの63D9A4..63D9AFの12バイト。
元Applyを12ケースで隔離実行し、各1バイトだけをC9（Play/Pause）へ変更した結果、
設定相対+E8..+F3（EEPROM絶対1C8..1D3）だけが変わることを確認した。
INI名UFN_F1..12と対応し、画面ハンドラ4130D0は選択された要素へ変換結果を1バイト保存する。
一部Fn画面定義はコメントアウトされており、実機でのFnとの組み合わせ・物理キー対応は未確認。

## 設定ヘッダーとLight循環の追加解析

INIロードの名前と、Applyシリアライザを照合した。

| INI名 | グローバル | 設定内の変化 |
| --- | --- | --- |
| KEYSMODE | 61F104 | +00 bit7 |
| BALTF4 | 63DDD8 | +00 bit6 |
| BWINLOCK | 63DDE8 | +00 bit2 |
| BALLKEYSLOCK | 63DDF0 | +00 bit0 |
| BMODELED | 63DDF4 | 今回のK810系Apply条件では差分なし |

ここで確認したのは名前と保存ビットの対応であり、ファームウェア内部の意味を証明したものではない。
skin_main.iniでは一部のロック用画面定義がコメントアウトされている。

Lightの内部循環フラグ13枠を各1個だけ有効化する試験に加え、
全有効状態から各1個を無効化する試験も行った。

- EN0..7は+1Bの各bit0..7に差が出る。
- EN9..12は+08の各bit4..7に差が出る。
- EN8は全有効→無効の差分が出なかった。このApply分岐で独立に保存できるとは扱わない。
- +02の上位ニブルにも、現在モードの補正を伴う差分がある。
  これを単純な有効ビットとして扱うと誤るため、追加追跡が必要。

元ソフトと同じ挙動を再現する場合と、元ソフトの不整合を修正する場合を区別する。
現Webの未知ビット保持を、この途中結果だけで変更しない。

追加でINIロード41BD40..41D1CCと保存422430..422CDFを照合した。
文字列キーHR_LED_MODE_ENは0..8のみを参照し、9..12のINIキーは両関数にない。
内部13枠とINIの9項目は一致しない。以前の解析用ラベルで9..12にも付けた
HR_LED_MODE_ENという名前は実在するINIキーと誤解させるため、ツール内では
cycle_internal_slot_9..12へ訂正した。`audit_profile_fields.py`で参照箇所を再現できる。

方向・対称表示のクリック分岐415E63..415EF9は、13モード×5操作を隔離実行した。

| モード | 対称表示・方向0/1 | 方向2 | 方向3 |
| --- | --- | --- | --- |
| 0/1/2/4 | 更新なし | 更新なし | 更新なし |
| 5 | 更新あり | 更新なし | 更新なし |
| 8 | 更新あり | 更新あり | 更新あり |
| 3/6/7/9/10/11/12 | 更新あり | 更新あり | 更新なし |

これはクリック分岐単体の受理条件であり、画面でその部品が実際に表示されるか、
K810のファームウェアが動作させるかの証明とは分ける。描画側は別途マスク処理を持つ。

## メーカーDATの追加解析

メーカーの.datはINIで、[Init] DAT_VER、[Macros] macroNumと数字キーを持つ。
数字キーの値は、各バイトを000..255の3桁十進数として連結したもの。
本体の圧縮マクロ命令列をそのまま格納したファイルではない。

ロード処理は41D710..41DF20、数値の配置分岐は41DB9A..41DEF1。
DAT_VER=3の配置を限定エミュレーションで追った。

| 連結データのバイト位置 | 内容／内部への配置 |
| --- | --- |
| 0..59 | UTF-16LE名、内部0..59 |
| 60 | モード等のフラグ、内部3C |
| 61..72 | 各16bitカウンタ、内部3E..49 |
| 73..80 | 拡張管理値、内部4A..51 |
| 81..2280 | 275イベント×8バイトを種類・コード・XY・待機の並列配列へ分解 |
| 2281..2620 | LEDシーケンス340バイト、内部8EA..A3D |
| 2621以降 | この読み込み分岐では無視される |

イベントコードはWindows VKから変換されるため、ファイルの数値をそのままHID Usageとして使えない。
`decode_vendor_dat.py` は英語レイアウトの元変換関数43B620も実行し、同梱されたv3ファイルの
12マクロを研究用JSONへ読み出した。元ファイルを変更せず、マクロを実行せず、機器へ保存もしない。
日本語その他のレイアウトやファイルへの書き戻しはまだ検証していない。

続けて、元のVK変換ディスパッチ424800と各変換関数を、配列ID0..24×
第2引数0/1×VK0..255の12,800ケースで実行した。合成結果は13種類のテーブルに分かれる。
配列ID12（JP）は、この変換でID1（EN）と同一の結果になった。
これは現在のWindowsの全日本語入力方式の再現を保証するものではなく、元関数の挙動の記録。
DAT読み出しツールにも配列ID指定を追加した。配布パッケージのスキン実体は0/1のみ。

書き出し経路41E510..41F5xx（単一マクロ）と41F5xx..420C6D（グループ）も追跡した。
イベント275枠に続け、内部63E6F2から68バイト×5個のLEDブロックを出力してファイル保存へ進む。
GPIO340バイトはこの書き出し経路に含まれない。現行v3の意味を持つ範囲2621バイトと整合する。
同梱v3ファイルには2621バイトより短い／長い行もあり、DAT_VER=3だけでは完全互換を判定できない。
続けて単一マクロ書き出し41E510..41F594を隔離実行し、2,621バイトの出力を得た。
275枠の種類・XY・待機時間の計1,925バイトとLED末尾340バイトを、
元の内部構造から独立に抽出した値と照合した。キーコードは元のHID→VK変換も実行した。
ヘッダーの連結データ77..80は、内部値によらず0になることも確認した。
INI書き込みは3回捕捉し、実際のファイルI/Oには置き換えていない。
これは任意の入力が完全往復する証明ではない。未対応キーコードの変換損失、
旧版、グループ書き出し本体の独立実行は引き続き確認が必要。

`verify_dat_roundtrip.py` は英語配列の合成キーボードマクロを元エクスポート処理で
DATへ変換し、元インポート処理で読み直す。名前、繰り返し3回、4イベントの
種類・キーコード・待機・パラメーターが一致した。Aと左Ctrlを使用した1ケースであり、
全キー・全配列・マウス等の全イベントの完全互換を示すものではない。

元のローダーはv3で8883回の3桁読み取りを試み、文字バッファにはその3倍の長さを要求する。
これを逆解析側で勝手に2961回へ読み替えない。短い文字列の残りは空文字列の数値変換になる。
オフセット2621以降の配置先は存在せず、内部GPIO領域A3E..B91への書き込みもない。
従って、このv3ロード経路でGPIOデータまで取り込めるとは扱わない。
旧版0では無視開始位置が2615となり、v3とはヘッダーの長さが異なる。
同梱の旧defMacro.datが現在のローダーへ完全互換とはまだ確認していない。

同梱ファイルには、macroNumより大きい番号の古い行や、宣言数に足りない行がある。
数値行の総数をmacroNumとして扱うのは不正確。機器へ適用するパーサーを作る際は
欠損・余剰・未対応イベントを明示的に検証する必要がある。

## プロファイル

config.iniは[Init] CurConfig/ConfgCnt/ConfigName等と、[Config1]..[Config5]、
そのLED用セクションを持つ。選択処理412A40はPC側のCurConfigを更新し、
41BD40で該当設定をRAMへ読み、マクロ参照数を数え直して再描画する。
この選択経路自体にHID送信は見つからない。適用処理とは分ける。
本体へ複数プロファイルを保持する切替命令は、この経路からは発見していない。

Ghidraの関数・呼び出し一覧から管理メニューを追跡し、メインMFCメッセージ表の
83EC→418B50を確認した。カテゴリ9の項目は次のように処理される。

| 項目番号 | 処理 | 根拠 |
| --- | --- | --- |
| 1 | INIを開いて取り込む | 40D980、ファイルダイアログのopen=1、41BD40でロード |
| 2 | INIへ書き出す | 4073A0、saveダイアログ、625278=1として422430を呼ぶ |
| 3 | 既定設定をロードして適用 | 418B94..418C38、既定160キーをコピー、412600をスレッド起動 |
| 4 | 新規プロファイル | 404380、63B9FC<5の場合のみ作成 |
| 5 | プロファイル削除 | 4061B0、63B9FC<2では拒否 |

`verify_profile_dispatch.py` は418B50の分岐を0..6の7ケースで隔離実行した。
呼び先は全てスタブであり、リセット時にも実スレッド・実HID通信は起動しない。
リセット分岐の160キー×4バイトの既定値コピー、変更配列のクリア、適用起動先までを確認。
適用起動先412600は40FD90を呼ぶ。リセットを単なるPC内編集として扱ってはいけない。

新規作成は現在の編集設定をINIへ保存した後、件数と選択番号を増やし、
Profile名を生成、既定INIをロードして新しいConfig番号へ保存する。
削除は最後の1件を残す制約を持つ。中間の削除では名前配列を詰めるが、
この関数内ではConfig番号付きセクションを全て移送する処理は見つからない。
残存するINIセクションの扱いは、互換実装前に独立検証する必要がある。

改名ハンドラ412840は入力の空欄／予約値を補正し、既存名との重複を調べる。
重複しない場合に名前表を更新し、424AD0でCurConfig・ConfgCnt・ConfigName群を保存する。
INI書き出し422430は通常Config番号付き、625278=1では単独のConfigセクションを使う。
キー160個に加え、20件ずつのMACROGRP_MAP/MACRO_MAPを保存する。
マクロ本体DATとは別の参照情報であり、INI単体で全マクログループを移送できるとはまだ確認していない。

## 全体の関数・呼び出し一覧

Ghidra 12.1.4（公式ZIPのSHA256照合済み）でPEを静的解析し、
認識された12,746関数の一覧と、00400000..00444FFFの非サンク382関数の
逆コンパイル結果・呼び出し参照をローカルのresearch/ghidra-exportへ出力した。
382件の逆コンパイルAPI呼び出しは全て完了した。ただし、これは382件の意味を全て
解明したという意味ではない。範囲には共通ヘルパーも含む。
MFC由来の例外処理で解析警告があり、特に呼び出し規約と引数推定は元命令で照合する。
生成Cとメーカー由来データはGitへ含めず、再現用ExportVendorAnalysis.javaのみを管理する。

## 未完了の作業

| 分野 | 残る解析 |
| --- | --- |
| Button/Special | Fnの実動作・物理対応、非公開列17、特殊操作の条件（英語名称変換とFn表の保存位置は検証済み） |
| Light | EN8、現在モード補正、モードごとの方向・対称制約、未検証の実動作 |
| Macro | ファイルの完全な書き出し・旧版互換、追加フラグの実動作、未公開拡張の到達性（フラグ変換・表の境界は追加検証済み） |
| Profiles | 管理操作の骨格は特定。削除後の残存セクション、INI/DAT参照の完全な移送、各保存項目の独立照合 |
| Lifecycle | 起動・終了・言語切替・異常時回復・OS側保存の網羅 |
| Firmware | イメージの所在、取得方法、実装されている処理の同定 |

## 再現用

```powershell
uv run --group research python tools/catalog_vendor_surface.py "research/official/app/Gaming Keyboard.exe" research/official/app/1/skins/1_INI_EN
uv run --group research python tools/verify_special_actions.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_key_converter.py "research/official/app/Gaming Keyboard.exe" research/official/app/1/skins/1_INI_EN/KbIndexText.ini
uv run --group research python tools/verify_key_converter.py "research/official/app/Gaming Keyboard.exe" research/official/app/1/skins/1_INI_EN/KbIndexText.ini --fn
uv run --group research python tools/verify_fn_table.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_vk_layouts.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_control_flags.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_light_controls.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/audit_profile_fields.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_dat_loader.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_dat_export.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_dat_roundtrip.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_profile_dispatch.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/decode_vendor_dat.py "research/official/app/Gaming Keyboard.exe" "PATH_TO_DAT"
```

実機検証状況は[FEATURE_AUDIT.md](FEATURE_AUDIT.md)、独自入力経路は
[VENDOR_INPUT_ANALYSIS.md](VENDOR_INPUT_ANALYSIS.md)と[RAW_HID.md](RAW_HID.md)を参照する。
