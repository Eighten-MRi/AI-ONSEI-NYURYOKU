# Live API一本化 — バッチAPI廃止 & リアルタイム字幕 + 整形テキストペースト

## Context

現在のアプリは2つのAPI呼び出しが共存:
- **Live API** (`LiveTranscriber`): リアルタイム字幕用 → モデル名 `gemini-live-2.5-flash-preview` がシャットダウン済み（2025/12/9）でエラー
- **バッチAPI** (`process_with_gemini_audio`): 整形テキストのペースト用 → 正常動作中

**目標**: Live API一本に統一し、コスト増なしでリアルタイム字幕 + 整形済みペーストを実現する。

**エラー**: `models/gemini-live-2.5-flash-preview is not found for API version v1beta`

---

## 修正方針

### Step 1: モデル名を最新に更新

**ファイル**: [main.py:670](main.py#L670)

```python
# 変更前
model="gemini-live-2.5-flash-preview"

# 変更後
model="gemini-3.1-flash-live-preview"
```

**選定理由**: 音声入力コストは2.5と同額($3.00/1M tokens)、レイテンシ改善、system_instruction遵守率が大幅向上、2.5はdeprecated。

### Step 2: `system_instruction` を Live API config に追加

**ファイル**: [main.py:659-667](main.py#L659-L667) — `LiveTranscriber._session_loop()`

`LiveConnectConfig` に `system_instruction` を追加して、フィラー除去・整形ルールをLive APIに適用する。

```python
config = genai_live_types.LiveConnectConfig(
    response_modalities=["TEXT"],
    system_instruction=system_prompt,  # ← 追加
    input_audio_transcription=genai_live_types.AudioTranscriptionConfig(),
    realtime_input_config=genai_live_types.RealtimeInputConfig(
        automatic_activity_detection=genai_live_types.AutomaticActivityDetection(
            disabled=True
        ),
    ),
)
```

`LiveTranscriber.__init__` に `system_prompt` パラメータを追加。呼び出し元で `SYSTEM_PROMPT` + ペルソナ指示を渡す。

### Step 3: `_receive_transcription` で `model_turn` テキストを取得

**ファイル**: [main.py:715-734](main.py#L715-L734) — `LiveTranscriber._receive_transcription()`

現状は `input_transcription` のみ処理。`model_turn` のテキスト応答も取得して `on_final` コールバックで返す。

```python
async def _receive_transcription(self, session):
    try:
        async for msg in session.receive():
            sc = msg.server_content
            if sc is None:
                continue

            # リアルタイム字幕（生の書き起こし）
            if sc.input_transcription and sc.input_transcription.text:
                self.on_partial(sc.input_transcription.text)

            # 整形済みテキスト（model_turnのテキスト応答）
            if sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    if hasattr(part, 'text') and part.text:
                        self.on_final(part.text)

            if sc.turn_complete:
                break
    except Exception as e:
        if self._running:
            print(f"[LiveTranscriber] 受信エラー: {e}")
```

### Step 4: `on_final` コールバックでペーストを実行

**ファイル**: [main.py:1219-1227](main.py#L1219-L1227) — `record_audio()` 内のコールバック設定

```python
# 変更前
on_final=lambda t: print(f"[LiveTranscription 確定] {t}")

# 変更後: 整形済みテキストをペーストする
on_final=lambda t: self._handle_live_result(t)
```

新メソッド `_handle_live_result(text)` を追加:
- `_post_process_text()` を適用
- `type_text()` でペースト実行

### Step 5: バッチAPI処理を除去（Live APIが成功した場合はスキップ）

**ファイル**: [main.py:1260-1295](main.py#L1260-L1295) — 録音後のWAV作成 & キュー投入

Live APIから `on_final` で結果が返ってきた場合、バッチAPIへの送信をスキップする。フラグで管理:
- `self._live_result_received = False` → 録音開始時にリセット
- `on_final` で `True` に設定
- 録音後、`True` ならバッチ送信をスキップ、`False`（Live APIエラー等）ならフォールバックとしてバッチ送信

### Step 6: エラーハンドリング改善

**ファイル**: [main.py:681-685](main.py#L681-L685)

`Task was destroyed but it is pending!` 警告を解消:
- `finally` ブロックで `await client.aio.aclose()` を確実に実行（既に実装済み、動作確認）
- セッション切断時の例外を適切にキャッチ

---

## 修正対象ファイル

- [main.py](main.py) のみ

## 主な変更箇所

| 行番号 | 内容 |
|--------|------|
| L616-624 | `LiveTranscriber.__init__` に `system_prompt` パラメータ追加 |
| L656-685 | `_session_loop`: モデル名更新 + system_instruction追加 |
| L715-734 | `_receive_transcription`: model_turnテキスト取得追加 |
| L1219-1227 | コールバック設定: on_final → ペースト実行 |
| L1260-1295 | Live API成功時はバッチ送信スキップ |

## 既存再利用コード

- `_post_process_text()` ([main.py:1116-1142](main.py#L1116-L1142)) — 整形処理はそのまま再利用
- `type_text()` ([main.py:1166-1184](main.py#L1166-L1184)) — ペースト処理はそのまま再利用
- `SYSTEM_PROMPT` ([main.py:67-95](main.py#L67-L95)) — Live APIのsystem_instructionに渡す

## 検証方法

1. アプリ起動 → コンソールに `[LiveTranscriber]` エラーが出ないことを確認
2. 右Alt長押し → 喋る → **字幕オーバーレイにリアルタイムで文字が出る**
3. 右Alt離す → **整形済みテキストがペーストされる**（バッチAPIではなくLive API経由）
4. 短い発話（1-2秒）で動作確認
5. 長い発話（10秒以上）で安定性確認
6. Live APIエラー時 → バッチAPIへフォールバック → 従来通りペーストされる
7. `Task was destroyed` 警告が出ないこと
