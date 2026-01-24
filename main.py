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

    def create_icon_image(self):
        """システムトレイ用のアイコン画像を生成（ナノバナナ画像を使用）"""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        
        try:
            if os.path.exists(icon_path):
                image = Image.open(icon_path).convert("RGBA")
                
                # AI未使用時は画像を白黒（グレースケール）にする
                if not self.use_ai:
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Color(image)
                    image = enhancer.enhance(0.0) # 彩度を0にして白黒化
                    
                # アイコンサイズに最適化してリサイズ
                image = image.resize((64, 64), Image.Resampling.LANCZOS)
                return image
            else:
                # 画像がない場合のフォールバック（シンプルな円を表示）
                width, height = 64, 64
                color = "#4285F4" if self.use_ai else "#757575"
                image = Image.new('RGB', (width, height), color)
                dc = ImageDraw.Draw(image)
                dc.ellipse([width//4, height//4, width*3//4, height*3//4], fill="white")
                return image
        except Exception as e:
            print(f"アイコン生成エラー: {e}")
            return Image.new('RGB', (64, 64), "yellow")

    def toggle_ai(self, icon, item):
        """AI使用のON/OFFを切り替え"""
        self.use_ai = not self.use_ai
        print(f"AI使用: {'ON' if self.use_ai else 'OFF'}")
        if self.icon:
            self.icon.icon = self.create_icon_image()

    def on_quit(self, icon, item):
        """アプリ終了処理"""
        self.running = False
        if self.icon:
            self.icon.stop()

    def process_with_gemini(self, text):
        """Gemini APIを使用してテキストを成形する"""
        if not text or not self.use_ai:
            return text
        
        try:
            prompt = f"{SYSTEM_PROMPT}\n\n入力テキスト: {text}"
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"\n[Error] AI変換エラー: {e}")
            return text

    def type_text(self, text):
        """テキストをクリップボードにコピーして貼り付ける"""
        if not text:
            return
            
        pyperclip.copy(text)
        time.sleep(0.1)
        
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")

    def record_audio(self):
        """録音ループ: キーが押されている間だけ確実に録音する"""
        with self.microphone as source:
            while self.running:
                # キーが押された瞬間を検知
                if keyboard.is_pressed(self.recording_key):
                    if not self.is_recording:
                        print("\n[聞き取っています... 長押し中]")
                        self.is_recording = True
                        
                        try:
                            # キーが離されるまで、または長時間（例: 60秒）まで録音し続ける
                            # phrase_time_limitを大きく設定し、沈黙で途切れないようにする
                            audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=120)
                            if self.is_recording: # まだキーが押し続けられていた、あるいは録音が完了した
                                self.audio_queue.put(audio)
                        except sr.WaitTimeoutError:
                            self.is_recording = False
                        except Exception as e:
                            print(f"録音エラー: {e}")
                            self.is_recording = False
                else:
                    if self.is_recording:
                        # キーが離された
                        self.is_recording = False
                    time.sleep(0.05)

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
