# Gemini Live API 移行計画 — リアルタイムストリーミング文字起こし

## Context

現在は「録音→一括送信→結果貼り付け」のバッチ処理方式。キーを離してから貼り付けまで 1〜3 秒の遅延がある。
Gemini Live API（リアルタイム音声ストリーミング対応）に移行することで、話しながらアクティブウィンドウに文字が出てくる体験を実現する。

**ユーザーが求めていること:**
- 話しながらテキストフィールドに文字が逐次出る（ストリーミング）
- 途中の誤認識は Backspace で消して書き直す方式
- 文脈補正（発音が悪くても Gemini が文脈から修正）
- キーを離してからの遅延ゼロ
- ペルソナ・カスタム指示はそのまま Live API に引き継ぐ
- テール録音時間を設定画面から変更できる
- エラー時はインジケータ表示のみ（フォールバックなし）

---

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `main.py` | 主要リファクタ（API・スレッド構成・テキスト貼り付け） |
| `requirements.txt` | `google-generativeai` → `google-genai` |
| `settings.json` | `tail_duration` フィールド追加（デフォルト 0.6） |

---

## 実装計画

### Step 1: requirements.txt 更新

```
# 削除
google-generativeai

# 追加
google-genai
```

### Step 2: main.py — import と初期化の変更

**import 変更（行1〜16付近）:**
```python
# 削除
import queue
import speech_recognition as sr
import google.generativeai as genai

# 追加
from google import genai
from google.genai import types
import asyncio
import contextlib
# audioop・pyaudio・pyperclip・pyautogui はそのまま維持
```

**グローバル初期化（行39〜45付近）:**
```python
# Before
genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = "gemini-2.5-flash-lite"
model = genai.GenerativeModel(MODEL_NAME, generation_config=...)

# After
LIVE_MODEL = "gemini-2.0-flash-live-001"
client = genai.Client(api_key=GOOGLE_API_KEY)
```

### Step 3: SettingsManager に tail_duration を追加

`_DEFAULTS` dict（行99付近）に `"tail_duration": 0.6` を追加。

既存の `energy_threshold` と同じ `@property` パターンで実装:
```python
@property
def tail_duration(self):
    return self._data.get("tail_duration", 0.6)
```

※ `save_setting()` というメソッドは存在しない。`tail_duration` の保存は既存の `save()` + `settings_manager.data` 直接書き換えで対応（`energy_threshold` と同じ方式）。

### Step 4: SettingsWindow に tail_duration スライダー追加

**`__init__` に追加（`var_sense_val` の直後）:**
```python
self.var_tail_val = tk.DoubleVar()
self.var_tail_val.set(self.settings.get("tail_duration", 0.6))
```

**`draw_audio_tab()` のヘルプボックス直後に追加:**
```python
# テール録音時間
tk.Label(container, text="テール録音時間（キーを離した後の追加録音）", ...).pack(...)
tail_val_frame = tk.Frame(container, bg=...)
tail_val_frame.pack(...)
tk.Label(tail_val_frame, text="現在の値:", ...).pack(side=tk.LEFT)
tk.Label(tail_val_frame, textvariable=self.var_tail_val, ...).pack(side=tk.LEFT, ...)
tk.Label(tail_val_frame, text="秒", ...).pack(side=tk.LEFT)
self.scale_tail = tk.Scale(container, from_=0.0, to=2.0, resolution=0.1,
                           orient=tk.HORIZONTAL, showvalue=False, ...)
self.scale_tail.set(self.settings.get("tail_duration", 0.6))
self.scale_tail.pack(fill=tk.X, ...)
```

**`on_tail_change()` ハンドラ追加（`on_sense_change` と同じパターン）:**
```python
def on_tail_change(self):
    val = round(self.scale_tail.get(), 1)
    self.settings["tail_duration"] = val
    self.var_tail_val.set(val)
    self.save_settings()
```

### Step 5: VoiceInputApp.__init__ の書き換え

`sr.Recognizer`・`sr.Microphone`・`audio_queue`・`use_ai`・`energy_threshold` を削除。
asyncio ループ・`_last_pasted_len`・`_session_running` を追加。
※ `_live_audio_queue` は不要（`_send_audio_chunks` は PyAudio から直接読むため）。

```python
def __init__(self):
    self.is_recording = False
    self.recording_key = "right alt"
    self.icon = None
    self.running = True
    self.indicator = RecordingIndicator()
    self._last_pasted_len = 0
    self._session_running = False   # 二重セッション防止フラグ

    # asyncio ループをバックグラウンドスレッドで常時起動
    self._async_loop = asyncio.new_event_loop()
    self._asyncio_thread = threading.Thread(
        target=self._async_loop.run_forever, daemon=True
    )
    self._asyncio_thread.start()
```

### Step 6: 削除するメソッド

- `process_with_gemini_audio()` — バッチ処理不要
- `main_loop()` — Live セッションが代替
- `type_text()` — `_update_pasted_text()` が代替

### Step 7: 新規メソッド群

#### `_postprocess(text)` — 後処理（既存ロジックを独立メソッドに切り出し）
```python
def _postprocess(self, text: str) -> str:
    text = text.strip()
    check_text = text.replace("。","").replace("、","").replace(".","").replace("！","").replace("!","")
    newline_patterns = [
        "改行", "かいぎょう", "カイギョウ", "会場", "了解", "良好", "[NEWLINE]",
        "退場", "開票", "海峡", "解雇", "外教", "大行", "体表", "大京", "会議用",
        "採用", "大会", "対応", "大綱", "開業", "開放", "解像"
    ]
    if check_text in newline_patterns:
        return "\n"
    text = text.replace("。[NEWLINE]", "[NEWLINE]")
    text = text.replace("[NEWLINE]", "\n")
    text = text.replace("。\n", "\n")
    if text.endswith("。"):
        text = text[:-1]
    return text
```

#### `_update_pasted_text(new_text)` — Backspace + 貼り付け（Tkinter スレッドで実行）
```python
def _update_pasted_text(self, new_text):
    if self._last_pasted_len > 0:
        pyautogui.press('backspace', presses=self._last_pasted_len)
        time.sleep(0.03)
    if new_text:
        pyperclip.copy(new_text)
        pyautogui.hotkey('ctrl', 'v')
    self._last_pasted_len = len(new_text)
```

#### `_send_audio_chunks(session)` — 音声送信（asyncio コルーチン）
```python
async def _send_audio_chunks(self, session):
    import pyaudio
    CHUNK = 1600  # 100ms @ 16kHz
    loop = asyncio.get_running_loop()
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    input=True, frames_per_buffer=CHUNK)
    try:
        while self.is_recording and self.running:
            data = await loop.run_in_executor(
                None, lambda: stream.read(CHUNK, exception_on_overflow=False)
            )
            rms = audioop.rms(data, 2)
            self.indicator.set_volume(rms)  # 波形アニメーション維持
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
        # テール録音
        tail = settings_manager.tail_duration
        deadline = time.time() + tail
        while time.time() < deadline and self.running:
            data = await loop.run_in_executor(
                None, lambda: stream.read(CHUNK, exception_on_overflow=False)
            )
            rms = audioop.rms(data, 2)
            self.indicator.set_volume(rms)
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
```

#### `_receive_text(session)` — テキスト受信（asyncio コルーチン）
```python
async def _receive_text(self, session):
    accumulated = ""
    async for response in session.receive():
        if not self.running:
            break
        chunk = getattr(response, "text", None)
        if chunk:
            accumulated += chunk
            display_text = self._postprocess(accumulated)
            self.indicator.root.after(
                0, lambda t=display_text: self._update_pasted_text(t)
            )
```

#### `_live_transcribe_session()` — メインの asyncio コルーチン
```python
async def _live_transcribe_session(self):
    self._last_pasted_len = 0  # 各セッション開始時にリセット
    persona_instruction = settings_manager.active_persona_instruction
    system_prompt = SYSTEM_PROMPT
    if persona_instruction:
        system_prompt += f"\n\n【追加指示（重要）】\n{persona_instruction}"

    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=system_prompt,
    )
    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            send_task = asyncio.ensure_future(self._send_audio_chunks(session))
            recv_task = asyncio.ensure_future(self._receive_text(session))
            await send_task  # 音声送信（テール込み）が終わるまで待つ
            # 最大5秒だけ最終レスポンスを待ち、超えたらキャンセル
            try:
                await asyncio.wait_for(recv_task, timeout=5.0)
            except asyncio.TimeoutError:
                recv_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await recv_task
    except Exception as e:
        print(f"[Live セッションエラー]: {e}")
        self.indicator.root.after(0, lambda: self.indicator.show_error())
    finally:
        self._session_running = False  # セッション終了を通知
```

### Step 8: `record_audio` の書き換え

音声収集ロジックを削除し、キー検知 + Live セッション起動のみ。
`_session_running` フラグで二重セッションを防止。

```python
def record_audio(self):
    """キー検知のみ。音声収集は _send_audio_chunks で行う"""
    print("--- 録音待機中 ---")
    while self.running:
        is_pressed = keyboard.is_pressed(165) or keyboard.is_pressed(self.recording_key)
        if is_pressed and not self.is_recording and not self._session_running:
            self.is_recording = True
            self._session_running = True
            self.indicator.set_recording(True)
            keyboard.press('shift')
            keyboard.release('shift')
            try: keyboard.block_key(165)
            except: pass
            asyncio.run_coroutine_threadsafe(
                self._live_transcribe_session(), self._async_loop
            )
        elif not is_pressed and self.is_recording:
            self.is_recording = False
            self.indicator.set_recording(False)
            try: keyboard.unblock_key(165)
            except: pass
        time.sleep(0.01)
```

### Step 9: `run()` の更新

`main_loop` スレッドを削除。`record_audio` スレッドのみ起動。

```python
def run(self):
    threading.Thread(target=self.record_audio, daemon=True).start()
    self.indicator.set_callback(self.on_quit)
    self.indicator.run()
```

---

## テキスト後処理 `_postprocess()`

既存の `process_with_gemini_audio` 内の後処理（`[NEWLINE]` 変換、文末「。」削除、改行パターン）を独立メソッドとして切り出す。

---

## settings.json の変更

```json
{
  "personas": [...],
  "active_index": 0,
  "energy_threshold": 20,
  "tail_duration": 0.6,
  "theme": "Relax Navy"
}
```

---

## 検証方法

1. `pip install google-genai` して起動確認
2. 右 Alt を押しながら短い文を話す → テキストフィールドに文字が逐次出ることを確認
3. 誤認識後に続きを話す → Backspace で書き換えられることを確認
4. キーを離す → テール録音後にセッションが正常終了することを確認
5. ネットワークを切断して録音 → インジケータにエラーが表示されることを確認
6. 設定画面で「テール録音時間」スライダーが動作することを確認
7. ペルソナ変更後に録音 → カスタム指示が反映されることを確認
8. 録音中に素早くキーを離して再度押す → セッションの二重起動が起きないことを確認

---

## 注意点・リスク

| リスク | 対策 |
|--------|------|
| asyncio + PyAudio のスレッド混在 | `run_in_executor` で PyAudio ブロッキング呼び出しをオフロード |
| セッション終了後 `receive()` がハングする可能性 | `asyncio.wait_for(timeout=5.0)` でタイムアウト後キャンセル |
| 二重セッション（キー連打） | `_session_running` フラグで二重起動を防止 |
| Windows フォーカスが変わった時の Backspace 誤爆 | 設計上防げないが稀なケースとして許容 |
| Live API セッション最大時間制限 | 通常の短文入力では問題なし |
| `audioop` モジュール（Python 3.13 で削除予定） | 現時点では影響なし、警告が出たら `numpy` に移行 |

## 修正済み問題点（初版からの変更）

| 問題 | 修正内容 |
|------|---------|
| `get_active_persona()` は存在しない | `settings_manager.active_persona_instruction` を使用 |
| `_live_audio_queue` が未使用のデッドコード | 削除 |
| セッション終了後 `_receive_text` がハング | `wait_for(timeout=5.0)` + キャンセルで対処 |
| `asyncio.get_event_loop()` が非推奨 | `asyncio.get_running_loop()` に変更 |
| `SettingsManager.save_setting()` は存在しない | 既存の `save()` + `data` 直接操作パターンを踏襲 |
| `tail_duration` が `@property` パターン不一致 | `energy_threshold` と同じ `@property` で実装 |
| 二重セッション防止が未記載 | `_session_running` フラグを追加 |
| 波形アニメーションが消える | `_send_audio_chunks` 内で `set_volume(rms)` を呼ぶ |
