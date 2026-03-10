# 音声認識モデル段階的アップグレード計画

## Context
現在使用中の `gemini-2.0-flash-lite` は **2026年6月1日に廃止予定**。精度向上とコスパを両立するため、まず同価格帯の `gemini-2.5-flash-lite` に移行し、`temperature=0` とプロンプト強化を適用する。これだけでも世代が新しい分、精度向上が見込める。

## 変更内容

### Step 1: モデルを `gemini-2.5-flash-lite` に変更
- **ファイル**: [main.py:41-42](main.py#L41-L42)
- 変更前:
  ```python
  MODEL_NAME = "gemini-2.0-flash-lite"
  model = genai.GenerativeModel(MODEL_NAME)
  ```
- 変更後:
  ```python
  MODEL_NAME = "gemini-2.5-flash-lite"
  model = genai.GenerativeModel(
      MODEL_NAME,
      generation_config=genai.GenerationConfig(temperature=0)
  )
  ```
- **料金**: 変わらない（テキスト $0.10 / 音声 $0.30 / 出力 $0.40 per 1Mトークン）

### Step 2: システムプロンプトに精度重視の指示を追加
- **ファイル**: [main.py:61-88](main.py#L61-L88)
- `SYSTEM_PROMPT` の冒頭に以下を追加:
  ```
  【聞き取り精度最優先】音声から聞こえた言葉を正確に書き起こしてください。聞こえていない言葉を補完したり、推測で言い換えたりすることは禁止です。
  ```

## 変更しないもの
- サンプルレート（16kHz）
- ノイズリダクション（ライブラリ追加なし）
- settings.json の構造（モデル選択UIは今回スコープ外）

## 検証方法
1. アプリを起動し、右Altキーで録音テスト
2. 以下のパターンで精度を確認:
   - 通常の文章（短文・長文）
   - フィラー入りの発話（「えー」「あの」を含む）
   - 小声での発話
   - 「改行」「まる」「てん」コマンド
3. 精度が不十分な場合 → `gemini-2.5-flash` への追加アップグレードを検討
