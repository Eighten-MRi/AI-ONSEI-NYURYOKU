import os
import time
import threading
import sys
import platform
import queue
import socket # 多重起動チェック用

import speech_recognition as sr
import keyboard
import audioop # 音量解析用
import google.generativeai as genai
import pyperclip
import pyautogui
from dotenv import load_dotenv

# アプリ化のためのライブラリ
def resource_path(relative_path):
    """ PyInstaller の一時フォルダ、または通常のカレントディレクトリから絶対パスを取得する """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


import tkinter as tk
import random
import math



# .envファイルから環境変数を読み込む
load_dotenv(resource_path(".env"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Geminiの初期化
genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

# 多重起動を防ぐためのポート番号
LOCK_PORT = 65432

def is_already_running():
    """ソケットを使用して二重起動をチェックする"""
    try:
        # このポートを占有しようとする
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', LOCK_PORT))
        # 参照を維持するためにグローバル変数に保持（プログラム終了まで閉じない）
        global _lock_socket
        _lock_socket = s
        return False
    except socket.error:
        return True

# システムプロンプトの設定
SYSTEM_PROMPT = (
    "あなたは高精度な文字起こしアシスタントです。ユーザーの音声認識テキストを受け取り、以下の処理のみを行ってください。\n"
    "1. 文脈から誤変換と思われる漢字のみを修正する。\n"
    "2. フィラーは削除するが、感嘆詞は維持する。\n"
    "3. 方言は維持する。標準語への変換を行わず、聞こえたまま忠実に書き起こすこと。\n"
    "4. 【重要】文末に勝手に句点「。」を付けないこと。これは絶対です。\n"
    "5. 認識結果が「まる」のみの場合は「。」を出力する。\n"
    "6. 認識結果が「てん」のみの場合は「、」を出力する。\n"
    "7. 認識結果が「改行」または「かいぎょう」のみの場合は改行コード(\\n)を出力する。\n"
    "出力は修正後のテキストのみを行ってください。"
)
# 可能な限りユーザーが発言したそのままのニュアンスを保つことが最優先です。

class RecordingIndicator:
    """画面中央下に表示される心電図風インジケータ"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Recording Indicator")
        
        # ウィンドウ設定: 枠なし、最前面、背景透過
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "black")
        self.root.config(bg="black")
        
        # サイズと位置 (画面中央下)
        width, height = 100, 40 # 幅を1/3程度に縮小しスリム化
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = screen_height - height - 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # キャンバス設定
        self.canvas = tk.Canvas(self.root, width=width, height=height, bg="black", highlightthickness=0)
        self.canvas.pack()
        
        # キャンバスイベント
        self.canvas.bind("<Button-3>", self.show_shutdown_button) # 右クリック
        self.canvas.bind("<Button-1>", self.on_click)             # 左クリック
        
        self.width = width
        self.height = height
        self.points = []
        
        # 状態フラグ
        self.is_recording = False
        self.is_processing = False
        self.shutdown_visible = False
        
        # アニメーション用変数
        self.current_volume = 0 # 音量 (0.0 - 1.0相当)
        self.pqrst_queue = []   # 心拍波形キュー
        self.processing_frame = 0 # 処理中アニメーション用フレーム
        
        self.alpha_idle = 0.2
        self.alpha_active = 0.9
        
        # カラー定義
        self.color_idle = "#00FF00"    # 待機中（緑）
        self.color_recording = "#00FFFF" # 録音中（シアン）
        self.color_process_start = (255, 165, 0) # オレンジ
        self.color_process_end = (255, 0, 0)     # 赤
        self.color_grid = "#003333"
        
        # アプリ終了コールバック
        self.on_quit_callback = None
        
        # 初期描画
        self.root.attributes("-alpha", self.alpha_idle)
        self.update_wave()

    def set_callback(self, callback):
        self.on_quit_callback = callback

    def set_callback(self, callback):
        self.on_quit_callback = callback

    def show_shutdown_button(self, event):
        """右クリックでSHUTDOWNボタンを表示"""
        # 既に表示中なら何もしない（トグルにすると二重クリックで消えるのが煩わしいかもだが今回はトグル維持か確認。
        # 要望は「出にくい」への対処と「自動で消える」なので、強制表示で良い。
        
        self.shutdown_visible = True
        self.root.attributes("-alpha", self.alpha_active)
        
        # 既存のタイマーがあればキャンセル（連続クリック対策）
        if hasattr(self, "_hide_timer") and self._hide_timer:
            self.root.after_cancel(self._hide_timer)
            
        # 1.5秒後に自動で隠す
        self._hide_timer = self.root.after(1500, self.hide_shutdown_button)

    def hide_shutdown_button(self):
        """SHUTDOWNボタンを隠す"""
        if self.shutdown_visible:
            self.shutdown_visible = False
            if not (self.is_recording or self.is_processing):
                 self.root.attributes("-alpha", self.alpha_idle)

    def on_click(self, event):
        """クリック判定（SHUTDOWNボタンなど）"""
        if self.shutdown_visible:
            # SHUTDOWNボタンのエリア判定（見た目より広く判定して押しやすくする）
            hit_w, hit_h = 100, 50
            cx, cy = self.width // 2, self.height // 2
            x1, y1 = cx - hit_w // 2, cy - hit_h // 2
            x2, y2 = cx + hit_w // 2, cy + hit_h // 2
            
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                # ボタンクリック時 -> 終了
                if self.on_quit_callback:
                    self.on_quit_callback()
            else:
                # エリア外クリック -> 閉じる
                self.shutdown_visible = False
                if not (self.is_recording or self.is_processing):
                     self.root.attributes("-alpha", self.alpha_idle)

    def draw_grid(self):
        """背景の医療用グリッドを描画"""
        # 25pxごとにメイングリッド、5pxごとにサブグリッド
        for x in range(0, self.width, 5):
            width = 1 if x % 25 == 0 else 0.5
            color = self.color_grid if x % 25 == 0 else "#001a1a"
            self.canvas.create_line(x, 0, x, self.height, fill=color, width=width)
        for y in range(0, self.height, 5):
            width = 1 if y % 25 == 0 else 0.5
            color = self.color_grid if y % 25 == 0 else "#001a1a"
            self.canvas.create_line(0, y, self.width, y, fill=color, width=width)

    def set_recording(self, recording):
        self.is_recording = recording
        self._update_alpha()

    def set_processing(self, processing):
        self.is_processing = processing
        self._update_alpha()
        
    def set_volume(self, rms):
        """音量(RMS)を設定し、0.0-1.0の範囲に正規化して保持"""
        # RMSは静かな部屋で10-100、話し声で300-2000くらい変動する
        # ここでは対数的に扱って感度を調整
        if rms < 300: # 無音閾値を上げてノイズでの誤反応を防ぐ
            vol = 0
        else:
            vol = min((rms - 300) / 2000, 1.0)
        self.current_volume = vol

    def _update_alpha(self):
        if self.is_recording or self.is_processing or self.shutdown_visible:
            self.root.attributes("-alpha", self.alpha_active)
        else:
            self.root.attributes("-alpha", self.alpha_idle)

    def interpolate_color(self, start_rgb, end_rgb, progress):
        """2色間を補間して#RRGGBB文字列を返す"""
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * progress)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * progress)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * progress)
        return f"#{r:02x}{g:02x}{b:02x}"

    def update_wave(self):
        """アニメーション描画"""
        self.canvas.delete("all")
        
        # === クリックシールド (Click Shield) ===
        # 背景全体に「見えないがクリック判定を持つ」矩形を置く。
        # stipple="gray50" で50%の密度で描画（透明ではない扱いになる）。
        # 色は #010101 (ほぼ黒) だが、透過キー bg="black" とは違う色にする。
        self.canvas.create_rectangle(0, 0, self.width, self.height, 
                                     fill="#010101", outline="", stipple="gray50")
        
        # 波形データの生成
        if not self.points:
            self.points = [self.height // 2] * (self.width // 4)
            
        self.points.pop(0)
        
        base_y = self.height // 2
        
        # 状態ごとの描画色と形状ロジック
        main_color = self.color_idle
        glow_color = ""
        line_width = 2.0
        
        if self.is_processing:
            # === 処理中: グリッチ＆カラーシフト ===
            self.processing_frame += 1
            progress = (self.processing_frame % 20) / 20.0 # 20フレームで色が一周...せず赤へ向かう
            
            # 色：オレンジ -> 赤 へランダムに揺らぎながら変化
            # 完全に赤になりきらず、行ったり来たりさせる演出
            swing_progress = (math.sin(self.processing_frame * 0.2) + 1) / 2 # 0.0-1.0
            main_color = self.interpolate_color(self.color_process_start, self.color_process_end, swing_progress)
            glow_color = self.interpolate_color((100,50,0), (100,0,0), swing_progress)

            # 形状：グリッチノイズ
            # 音量に関係なく激しく乱れる
            noise = random.randint(-15, 15)
            self.points.append(base_y + noise)
            
        elif self.is_recording:
            # === 録音中: 音量連動 ===
            main_color = self.color_recording
            glow_color = "#008080"
            
            # 音量に応じて振れ幅を変える
            # 基本ノイズ(1) + 音量ブースト (感度を微調整)
            amp = 1 + int(self.current_volume * 80) # 係数を150->80に下げて抑制
            val = random.randint(-amp, amp)
            self.points.append(base_y + val)
            
        else:
            # === 待機中: PQRST心拍 ===
            main_color = self.color_idle
            glow_color = "#003300"
            
            if not self.pqrst_queue:
                # ランダムな間隔で鼓動を入れる
                # 頻度を上げる (0.96 -> 0.90)
                if random.random() > 0.90:
                     # PQRSTシーケンス生成
                     # フラット -> P -> Q -> R -> S -> T
                     h = 15 # 基準高さ
                     seq = [0, 0, -3, -4, -2, 0, 0, 2, 40, -10, -5, 0, 0, -6, -8, -4, 0, 0] 
                     # Y座標は画面座標系なので、上(マイナス)がプラス波、下(プラス)がマイナス波
                     # 修正: 上向き(R波のピーク)はYを減らす
                     
                     # 修正seq: P(小上), Q(小下), R(大上), S(大下), T(中上)
                     # 画面Y座標: 上(-), 下(+)
                     seq = [0]*2 + \
                           [-3, -4, -2] + [0]*2 + \
                           [2, 3] + [-25, -30] + [8, 10] + [0]*2 + \
                           [-5, -7, -4] + [0]*2
                     self.pqrst_queue = seq
                else:
                    self.points.append(base_y)
            
            if self.pqrst_queue:
                 self.points.append(base_y + self.pqrst_queue.pop(0))

        # --- 波形の描画 ---
        coords = []
        for i, y in enumerate(self.points):
            coords.append(i * 4)
            coords.append(y)
            
        if self.is_processing or self.is_recording:
             # グロー効果あり
             self.canvas.create_line(coords, fill=glow_color, width=4, smooth=True)
        
        self.canvas.create_line(coords, fill=main_color, width=line_width, smooth=True)
        
        # リード点（先頭のドット）
        if len(coords) >= 2:
            lx, ly = coords[-2], coords[-1]
            self.canvas.create_oval(lx-1, ly-1, lx+1, ly+1, fill="white", outline=main_color)

        # --- SHUTDOWNボタン描画 ---
        if self.shutdown_visible:
            # 見た目は元のサイズに戻す
            btn_w, btn_h = 70, 24
            cx, cy = self.width // 2, self.height // 2
            x1, y1 = cx - btn_w // 2, cy - btn_h // 2
            x2, y2 = cx + btn_w // 2, cy + btn_h // 2
            
            # SF風枠
            self.canvas.create_rectangle(x1, y1, x2, y2, fill="black", outline="red", width=2)
            self.canvas.create_line(x1, y1, x1+5, y1, fill="white", width=2) # 角の飾り
            self.canvas.create_line(x1, y1, x1, y1+5, fill="white", width=2)
            self.canvas.create_line(x2-5, y2, x2, y2, fill="white", width=2)
            self.canvas.create_line(x2, y2-5, x2, y2, fill="white", width=2)
            
            self.canvas.create_text(cx, cy, text="SHUTDOWN", fill="red", font=("Arial", 8, "bold"))

        # 50ms (20fps) 更新
        self.root.after(50, self.update_wave)

    def run(self):
        self.root.mainloop()

    def stop(self):
        self.root.destroy()


class VoiceInputApp:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_recording = False
        self.use_ai = True  # AI使用フラグ
        self.audio_queue = queue.Queue()
        self.recording_key = "right alt"
        self.icon = None
        self.running = True
        self.indicator = RecordingIndicator()
        self.energy_threshold = 300 # 無音判定のしきい値 (RMS)

        # 録音の設定
        self.recognizer.pause_threshold = 10.0
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def on_quit(self):
        """アプリ終了処理"""
        self.running = False
        self.indicator.stop()
        sys.exit(0)


    def process_with_gemini_audio(self, audio_bytes):
        """音声データを直接Geminiに送信して、聞き取りと成形を同時に行う"""
        try:
            # プロンプトを音声対応用に調整
            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                "添付された音声を聞き取り、指示通りに成形したテキストのみを答えてください。"
            )
            response = model.generate_content([
                prompt,
                {"mime_type": "audio/wav", "data": audio_bytes}
            ])
            text = response.text.strip()
            
            # クライアント側フォールバック: 「改行」という文字そのものが返ってきたら改行コードにする
            if text in ["改行", "かいぎょう"]:
                return "\n"
                
            return text
        except Exception as e:
            print(f"[Gemini直接処理失敗]: {e}")
            return None

    def type_text(self, text):
        """クリップボード経由で貼り付け"""
        if not text: return
        try:
            pyperclip.copy(text)
            time.sleep(0.1)
            if platform.system() == "Darwin":
                pyautogui.hotkey("command", "v")
            else:
                pyautogui.hotkey("ctrl", "v")
        except Exception as e:
            print(f"[貼り付けエラー]: {e}")

    def record_audio(self):
        """録音ループ: キーの状態に同期"""
        import pyaudio
        import io
        import wave

        p = pyaudio.PyAudio()
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 1024

        print("--- 録音待機中 ---")
        while self.running:
            try:
                # 右Altの検知 (キーコード165)
                is_pressed = keyboard.is_pressed(self.recording_key) or keyboard.is_pressed(165)

                if is_pressed and not self.is_recording:
                    self.is_recording = True
                    # インジケータを更新
                    self.indicator.set_recording(True)

                    
                    frames = []
                    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
                    
                    while (keyboard.is_pressed(self.recording_key) or keyboard.is_pressed(165)) and self.running:
                        data = stream.read(CHUNK, exception_on_overflow=False)
                        frames.append(data)
                        
                        # リアルタイム波形更新
                        try:
                            rms = audioop.rms(data, 2)
                            self.indicator.set_volume(rms)
                        except:
                            pass
                    
                    # 末尾の切れを防ぐため、キーを離した直後の音をわずかに（約0.3秒）追加録音
                    for _ in range(5):
                        data = stream.read(CHUNK, exception_on_overflow=False)
                        frames.append(data)
                    
                    stream.stop_stream()
                    stream.close()
                    self.indicator.set_recording(False)



                    if frames:
                        # WAVEデータを作成
                        raw_data = b''.join(frames)
                        
                        # 音量のチェック (無音時はスキップ)
                        rms = audioop.rms(raw_data, 2) # 2はpaInt16のバイト数
                        print(f" (入力音量: {rms})", end="", flush=True)
                        # self.indicator.set_volume(rms) # ここでの更新は遅いので削除（ループ内で実施済み）

                        
                        if rms > self.energy_threshold:
                            container = io.BytesIO()
                            wf = wave.open(container, 'wb')
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(p.get_sample_size(FORMAT))
                            wf.setframerate(RATE)
                            wf.writeframes(raw_data)
                            wf.close()
                            # 音声バイト列をキューに入れる
                            self.audio_queue.put(container.getvalue())
                        else:
                            print(" -> 無音のためスキップ")
                    
                    self.is_recording = False
            except Exception as e:
                print(f"[録音エラー]: {e}")
                self.is_recording = False
                self.indicator.set_recording(False)


                time.sleep(1)

            time.sleep(0.01)
        p.terminate()

    def main_loop(self):
        """処理ループ"""
        while self.running:
            if not self.audio_queue.empty():
                audio_bytes = self.audio_queue.get()
                
                try:
                    self.indicator.set_processing(True) # 処理中開始
                    if self.use_ai:
                        # AIがONなら直接Geminiで処理（爆速）
                        print("[Geminiで直接処理中...]", end="", flush=True)
                        refined_text = self.process_with_gemini_audio(audio_bytes)
                        if refined_text:
                            print(f" -> {refined_text}")
                            self.type_text(refined_text)
                    else:
                        # AIがOFFなら従来のGoogle音声認識
                        print("[Google音声認識中...]", end="", flush=True)
                        import io
                        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
                            audio_data = self.recognizer.record(source)
                            raw_text = self.recognizer.recognize_google(audio_data, language="ja-JP")
                            print(f" -> {raw_text}")
                            self.type_text(raw_text)

                except Exception as e:
                    print(f" -> [!] 処理失敗: {e}")
                finally:
                    self.indicator.set_processing(False) # 処理中終了


            
            time.sleep(0.1)

    def run(self):
        """アプリ開始"""
        # 処理ループを別スレッドで開始
        threading.Thread(target=self.record_audio, daemon=True).start()
        threading.Thread(target=self.main_loop, daemon=True).start()
        
        # コンテキストメニュー設定（不要になったので削除）
        # self.indicator.setup_context_menu(self.on_quit)
        
        # コールバック設定
        self.indicator.set_callback(self.on_quit)

        
        # Tkinter (インジケータ) をメインスレッドで実行
        self.indicator.run()

if __name__ == "__main__":
    if is_already_running():
        sys.exit(0)

    app = VoiceInputApp()
    app.run()

