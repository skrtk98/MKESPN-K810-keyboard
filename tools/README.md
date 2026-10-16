# 解析・検証ツール

通常のCLI/Web利用には不要な調査用ツール。メーカーの実行ファイルや生成Cは配布しない。
固定アドレスを使うオフライン解析は既知SHA256を確認し、異なるバイナリを拒否する。
全体の状況・未解明項目は[解析台帳](../docs/FULL_REVERSE_ENGINEERING.md)を参照。

## オフライン解析

下記はメーカーEXEをホスト上で起動せず、HIDへもアクセスしない。
Unicornを使うツールは対象の関数・命令範囲を限定し、OS・ファイル操作を置き換える。

| ツール | 対象 |
| --- | --- |
| `verify_vendor.py` / `trace_vendor_apply.py` | USBパケット、Apply処理の参照値 |
| `verify_extended.py` / `verify_mouse_handlers.py` | 単独操作、キーボード・マウスマクロ、繰り返しUI |
| `verify_lighting.py` / `verify_light_controls.py` / `verify_control_flags.py` | Lightの保存値、クリック条件、制御フラグ |
| `verify_macro_extensions.py` / `verify_macro_flags.py` / `verify_macro_table_layout.py` | 拡張命令、未知フラグ、表と本体の配置 |
| `verify_special_actions.py` / `verify_key_converter.py` / `verify_fn_table.py` / `verify_vk_layouts.py` | 特殊操作、名称変換、Fn、25配列のVK変換 |
| `verify_dat_loader.py` / `verify_dat_export.py` / `verify_dat_roundtrip.py` / `decode_vendor_dat.py` | メーカーDATの配置、書き出し、往復、研究用JSONへの読み出し |
| `verify_profile_dispatch.py` / `audit_profile_fields.py` | プロファイル管理分岐、INI項目の参照 |
| `verify_stick_press.py` | 非表示列とKBD Modeのコード変換 |
| `audit_vendor_input.py` / `audit_vendor_ui_input.py` / `verify_vendor_connection.py` | 入力API、画面表示経路、模擬接続・初期化 |
| `catalog_vendor_surface.py` / `compare_vendor_interfaces.py` | 画面・メニュー資源、メーカー参照ソフトとの比較 |
| `ExportVendorAnalysis.java` | Ghidraの関数一覧、呼び出し参照、指定範囲の生成C |

Pythonの実行例（リポジトリのルートで実行）:

```powershell
uv run --group research python tools/verify_macro_table_layout.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_macro_flags.py "research/official/app/Gaming Keyboard.exe"
uv run --group research python tools/verify_dat_roundtrip.py "research/official/app/Gaming Keyboard.exe"
```

多くのツールはJSONを標準出力へ出す。`verify_vendor.py`等の従来ツールには
`tests/vendor*_vectors.json`を更新するものもあるため、生成後は差分を確認する。
DAT往復ツールは合成データだけを`research/dat-roundtrip/`へ書く。
その他の結果・メーカー配布物もGit対象外の`research/`へ保存する。

GhidraはJava 21と12.1.4で確認した。出力先は事前に作成し、例えば次のように実行する。
この処理もPEの静的解析であり、対象EXEの起動ではない。

```powershell
# GHIDRA_HOME / JAVA_HOMEには利用環境の展開先を指定する
New-Item -ItemType Directory -Force research/ghidra-project,research/ghidra-export
& "$env:GHIDRA_HOME/support/analyzeHeadless.bat" research/ghidra-project K810 `
  -import "research/official/app/Gaming Keyboard.exe" -analysisTimeoutPerFile 300 `
  -max-cpu 2 -scriptPath tools -postScript ExportVendorAnalysis.java `
  (Resolve-Path research/ghidra-export).Path
```

## 実機へアクセスする調査

以下はオフライン解析と別に扱う。通常の検証として一括実行しない。
Windowsの機器別入力監視は対象VID/PIDの入力に限定する。

| ツール | 操作 |
| --- | --- |
| `inspect_hid_collections.py` | Windows HID能力情報を読む。HIDレポート送信なし |
| `watch_vendor_input.py` | FF00/1の入力レポートを監視・記録。コマンド送信なし |
| `watch_k810_input.py` | K810のWindows Raw Inputを監視・記録 |
| `probe_vendor_modes.py` | 既知の初期化・捕捉コマンドを送る。バックアップ・終了処理・設定照合あり |
| `probe_stick_press.py` | 押し込みキーを一時変更して検証・復元する。実行前に各引数とソースを確認 |

ローカルの監視ログ・機器パス・バックアップはコミットしない。
実機の確認結果は[機能別台帳](../docs/FEATURE_AUDIT.md)、
[押し込み調査](../docs/STICK_PRESS.md)、[RAW HID調査](../docs/RAW_HID.md)に記録する。
