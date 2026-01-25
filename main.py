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
    "あなたは高精度な文字起こしアシスタントです。ユーザーの音声認識テキストを受け取り、以下の処理のみを行ってください。"
    "文章の要約や意図的なリライト、標準語への変換は【厳禁】です。\n"
    "1. 文脈から誤変換と思われる漢字のみを修正する。\n"
    "2. フィラー（『えー』『あー』など）は削除しますが、感情や強調を伴う感嘆詞（『お、』『えっ』『あ』など）はフレーズの一部として【必ず維持】してください。\n"
    "3. 「あ、違うわ」「あ、間違えた」などの言い直しを検知した場合、それより前の不要な発言を削除し、最新の正しい意図のみを抽出してください。\n"
    "4. 方言（例：〜やねん、〜やん、〜しとって）や語尾、口調、疑問符（？）は【絶対に一言一句削らず、そのまま維持】してください。\n"
    "5. 文末が明らかに疑問文である場合のみ「？」を付けてください。断定や通常の独り言に「？」を付与しないでください。\n"
    "6. 必要に応じて読点を補う。\n"
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
        
        # マウスイベント貫通 (Windows)
        # マウスイベント貫通設定を削除（右クリックメニュー有効化のため）
        # 元の透過設定は -transparentcolor で機能する


        # キャンバス設定
        self.canvas = tk.Canvas(self.root, width=width, height=height, bg="black", highlightthickness=0)
        self.canvas.pack()
        
        self.width = width
        self.height = height
        self.points = []
        self.is_recording = False
        self.is_processing = False
        self.pqrst_queue = []
        self.alpha_idle = 0.2
        self.alpha_active = 0.9
        
        # ネオンカラー定義
        self.color_cyan = "#00FFFF"   # ネオンシアン
        self.color_orange = "#FFA500" # ネオンオレンジ (処理中)
        self.color_glow = "#008080"    # グロー用
        self.color_grid = "#003333"    # グリッド用（暗い）
        
        # 初期描画
        self.root.attributes("-alpha", self.alpha_idle)
        self.update_wave()


    def setup_context_menu(self, on_quit_callback):
        """右クリックメニューの設定"""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="終了", command=on_quit_callback)
        
        def show_menu(event):
            self.context_menu.post(event.x_root, event.y_root)
            
        self.root.bind("<Button-3>", show_menu)

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
        if recording or self.is_processing:
            self.root.attributes("-alpha", self.alpha_active)
        else:
            self.root.attributes("-alpha", self.alpha_idle)

    def set_processing(self, processing):
        self.is_processing = processing
        if processing or self.is_recording:
            self.root.attributes("-alpha", self.alpha_active)
        else:
            self.root.attributes("-alpha", self.alpha_idle)


    def update_wave(self):
        """ガチ医療モニタ風の心電図アニメーション"""
        self.canvas.delete("all")
        
        # 波形データの生成
        if not self.points:
            self.points = [self.height // 2] * (self.width // 4)
            
        self.points.pop(0)
        
        if self.is_recording:
            # 録音中は動く
            if random.random() > 0.92:
                self.points.append(random.randint(2, 12))
            elif random.random() > 0.85:
                self.points.append(random.randint(28, 38))
            else:
                self.points.append(self.height // 2 + random.randint(-3, 3))
            
            main_color = self.color_cyan
            glow_color = self.color_glow
            main_width = 2.0

        elif self.is_processing:
            # 処理中はPQRST波形 (心電図) をオレンジで表示
            if not self.pqrst_queue:
                # PQRST波形の生成 (標準的な鼓動パターン)
                # フラット -> P -> フラット -> Q -> R -> S -> フラット -> T -> フラット
                base = self.height // 2
                # スケール調整
                h_scale = 0.5 
                
                # シーケンス定義 (相対Y座標)
                sequence = [0]*10 + \
                           [3]*2 + [0]*2 + \
                           [-2] + [25] + [-8] + [0]*2 + \
                           [5]*3 + [0]*15
                           
                for y_offset in sequence:
                   # Y座標は上に行くほど小さいので、マイナスする
                   self.points.append(base - int(y_offset * h_scale))
                   # キューにダミーを入れて制御してもいいが、ここではpointsに直接追加せず
                   # 毎回1つずつpointsに追加するロジックにするため、pqrst_queueを使う
                   
                self.pqrst_queue = sequence
            
            # キューから次の値を取り出して追加
            base = self.height // 2
            next_val = self.pqrst_queue.pop(0)
            # ノイズを少し乗せる
            self.points.append(base - int(next_val) + random.randint(-1, 1))
            
            # キューが空になったら少し待機（フラット）期間を入れるためにNoneなどを入れる手もあるが
            # 上記 sequence にフラット期間を含めているのでループするだけでOK
            
            main_color = self.color_orange
            glow_color = "#804000" # オレンジのグロー
            main_width = 2.0

        else:
            # 待機中は水平
            self.points.append(self.height // 2)
            main_color = "#006666" 
            glow_color = "black"
            main_width = 2.0
            
        # 2. 線を描画
        coords = []
        for i, y in enumerate(self.points):
            coords.append(i * 4)
            coords.append(y)
            
        if self.is_recording or self.is_processing:
            self.canvas.create_line(coords, fill=glow_color, width=4, smooth=True)
            self.canvas.create_line(coords, fill=main_color, width=main_width, smooth=True)
            self.canvas.create_line(coords, fill="white", width=0.5, smooth=True)
            
            # リード点
            last_x, last_y = coords[-2], coords[-1]
            self.canvas.create_oval(last_x-1.5, last_y-1.5, last_x+1.5, last_y+1.5, fill="white", outline=main_color, width=1)
            self.canvas.create_oval(last_x-3, last_y-3, last_x+3, last_y+3, outline=glow_color, width=1)
        else:
            self.canvas.create_line(coords, fill=main_color, width=main_width, smooth=True)


        # 50ms ごとに更新
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
            return response.text.strip()
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
        
        # コンテキストメニュー設定
        self.indicator.setup_context_menu(self.on_quit)
        
        # Tkinter (インジケータ) をメインスレッドで実行
        self.indicator.run()

if __name__ == "__main__":
    if is_already_running():
        sys.exit(0)

    app = VoiceInputApp()
    app.run()

