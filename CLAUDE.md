# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Windows向け日本語音声入力ツール。右Altキーで録音し、Google Gemini APIで文字起こしして、アクティブなテキストフィールドにCtrl+Vで貼り付ける。

## コマンド

```bash
# 実行
python main.py

# ビルド（PyInstallerで単一.exe生成）
pyinstaller "AI音声入力ツール.spec"
```

テストフレームワークは未導入。動作確認はアプリ起動後、右Altキーで録音テストを行う。

## 技術スタック

- **GUI**: Tkinter（カスタムCanvas描画ウィジェット）
- **音声取得**: PyAudio + speech_recognition（16kHz, mono, 16bit PCM）
- **AI**: Google Gemini API（google-generativeai）— モデルは `main.py` 冒頭で定義
- **テキスト入力**: pyperclip + pyautogui（クリップボード経由のCtrl+V）
- **キー監視**: keyboard（右Alt = keycode 165）

## アーキテクチャ

### main.py（全体の約95%）

3つのスレッドで構成:
1. **メインスレッド**: Tkinter UIイベントループ（`RecordingIndicator`の描画）
2. **録音スレッド** (`record_audio`): 右Altキー検知 → マイク入力キャプチャ → キューに投入
3. **処理スレッド** (`main_loop`): キューから音声取得 → 音量正規化 → Gemini API送信 → 後処理 → テキスト入力

主要クラス:
- **`VoiceInputApp`**: アプリ本体。スレッド管理、音声処理パイプライン
- **`RecordingIndicator`**: 透明オーバーレイUI。2層ウィンドウ（クリック層+描画層）で心電図風アニメーション
- **`SettingsWindow`**: 3タブ設定画面（ペルソナ/音声/外観）
- **`SettingsManager`**: JSON設定のメモリキャッシュ管理

### ui_widgets.py

`RoundedButton`と`RoundedEntry` — Canvas上に角丸矩形を描画するカスタムウィジェット。

## 重要な設計判断

- **Alt キーの中和処理**: 録音後にShiftを押し離しすることで、Alt単押しによるWindowsメニュー発動を防止
- **テール録音**: キーリリース後0.6秒の追加録音で発話末尾の切れを防止
- **音量ブースト**: 小声の音声を最大10倍に増幅してからGeminiに送信
- **`[NEWLINE]`トークン**: システムプロンプトで改行コマンドを`[NEWLINE]`文字列として出力させ、後処理で実際の改行に変換
- **二重起動防止**: ポート65432のソケットバインドで排他制御
- **デバウンス**: 設定テキスト変更は500ms遅延で保存（I/O削減）

## 設定

- `.env`: `GOOGLE_API_KEY` を格納（git管理外）
- `settings.json`: ペルソナ、音声感度（energy_threshold）、テーマ設定
