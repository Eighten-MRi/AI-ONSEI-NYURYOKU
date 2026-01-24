import os
import time
import threading
import sys
import platform
import queue
import socket # 多重起動チェック用

import speech_recognition as sr
import keyboard
import google.generativeai as genai
import pyperclip
import pyautogui
from dotenv import load_dotenv

# アプリ化のためのライブラリ
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# .envファイルから環境変数を読み込む
load_dotenv()
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
    "文章の要約やリライト（言い回しの変更）は厳禁です。\n"
    "1. 文脈を読み取り、誤った漢字変換や同音異義語を修正する（例: 製作/制作、回答/解答）。\n"
    "2. 『えー』『あー』『そのー』などのフィラー（言い淀み）のみを削除する。\n"
    "3. 必要に応じて句読点を補う。\n"
    "出力は修正後のテキストのみを行ってください。"
)

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

        # 録音の設定（沈黙で勝手に止まらないように調整）
        self.recognizer.pause_threshold = 10.0 # 沈黙を10秒まで許容
        # 認識感度の調整
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def create_icon_image(self, state="normal"):
        """システムトレイ用のアイコン画像を生成"""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        
        try:
            if os.path.exists(icon_path):
                image = Image.open(icon_path).convert("RGBA")
                
                # 録音中はアイコンを少し明るくし、赤いインジケータを表示
                if state == "recording":
                    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
                    draw = ImageDraw.Draw(overlay)
                    # 右上に赤い円を表示
                    draw.ellipse([image.size[0]-20, 4, image.size[0]-4, 20], fill="red", outline="white", width=2)
                    image = Image.alpha_composite(image, overlay)
                
                # AI未使用時は画像を白黒にする
                if not self.use_ai:
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Color(image)
                    image = enhancer.enhance(0.0)
                    
                image = image.resize((64, 64), Image.Resampling.LANCZOS)
                return image
            else:
                # フォールバック
                image = Image.new('RGB', (64, 64), "red" if state == "recording" else ("blue" if self.use_ai else "gray"))
                return image
        except:
            return Image.new('RGB', (64, 64), "yellow")

    def update_icon_state(self, state):
        """アイコンの状態を即座に反映"""
        if self.icon:
            self.icon.icon = self.create_icon_image(state=state)

    def process_with_gemini(self, text):
        """Gemini APIを使用してテキストを成形"""
        if not text or not self.use_ai:
            return text
        try:
            prompt = f"{SYSTEM_PROMPT}\n\n入力テキスト: {text}"
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"AIエラー: {e}")
            return text

    def type_text(self, text):
        """クリップボード経由で貼り付け"""
        if not text: return
        pyperclip.copy(text)
        time.sleep(0.1)
        # 確実に修飾キーが離れたタイミングで行う
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")

    def record_audio(self):
        """録音ループ: PyAudioを使用してキーの状態に完全に同期させる"""
        import pyaudio
        import io
        import wave

        p = pyaudio.PyAudio()
        stream = None
        
        # 音声フォーマット設定
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 1024

        while self.running:
            # 右Altキーの監視 (キーコード165はWindowsのRight Alt)
            is_pressed = keyboard.is_pressed(self.recording_key) or keyboard.is_pressed(165)

            if is_pressed and not self.is_recording:
                # 録音開始
                self.is_recording = True
                self.update_icon_state("recording")
                print("\n[録音開始]")
                
                frames = []
                stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
                
                # キーが離されるまで録音し続ける
                while (keyboard.is_pressed(self.recording_key) or keyboard.is_pressed(165)) and self.running:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)
                
                # 録音停止
                stream.stop_stream()
                stream.close()
                self.is_recording = False
                self.update_icon_state("normal")
                print("[録音終了]")

                if frames:
                    # WAVE形式に変換してSpeechRecognitionに渡す
                    container = io.BytesIO()
                    wf = wave.open(container, 'wb')
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(p.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(frames))
                    wf.close()
                    container.seek(0)
                    
                    with sr.AudioFile(container) as audio_source:
                        audio_data = self.recognizer.record(audio_source)
                        self.audio_queue.put(audio_data)

            time.sleep(0.02)
        p.terminate()

    def main_loop(self):
        """処理ループ"""
        while self.running:
            if not self.audio_queue.empty():
                audio = self.audio_queue.get()
                print("[認識中...]")
                try:
                    raw_text = self.recognizer.recognize_google(audio, language="ja-JP")
                    print(f"認識: {raw_text}")
                    refined_text = self.process_with_gemini(raw_text)
                    print(f"変換: {refined_text}")
                    self.type_text(refined_text)
                except sr.UnknownValueError:
                    print("[!] 聞き取れませんでした")
                except Exception as e:
                    print(f"[!] エラー: {e}")
            time.sleep(0.1)

    def main_loop(self):
        """テキスト処理ループ"""
        while self.running:
            if not self.audio_queue.empty():
                audio = self.audio_queue.get()
                
                print("[音声認識中...]")
                try:
                    raw_text = self.recognizer.recognize_google(audio, language="ja-JP")
                    print(f"認識結果: {raw_text}")
                    
                    if self.use_ai:
                        print("[AIが変換中...]")
                        refined_text = self.process_with_gemini(raw_text)
                        print(f"変換結果: {refined_text}")
                    else:
                        refined_text = raw_text
                    
                    self.type_text(refined_text)
                    
                except sr.UnknownValueError:
                    print("\n[!] 音声が聞き取れませんでした。")
                except sr.RequestError as e:
                    print(f"\n[!] 音声認識サービスのエラー: {e}")
                except Exception as e:
                    print(f"\n[!] 予期せぬエラー: {e}")
            
            time.sleep(0.1)

    def setup_tray(self):
        """システムトレイアイコンのセットアップ"""
        menu = (
            item(f'AI使用を切り替え', self.toggle_ai, checked=lambda item: self.use_ai),
            item('終了', self.on_quit)
        )
        self.icon = pystray.Icon("voice_input_tool", self.create_icon_image(), "AI音声入力ツール", menu)
        
        # 処理ループを別スレッドで開始
        threading.Thread(target=self.record_audio, daemon=True).start()
        threading.Thread(target=self.main_loop, daemon=True).start()
        
        # トレイアイコンをメインスレッドで実行
        self.icon.run()

if __name__ == "__main__":
    # 多重起動のチェック
    if is_already_running():
        # すでに起動している場合は静かに終了する
        sys.exit(0)

    app = VoiceInputApp()
    app.setup_tray()
