import os
import time
import threading
import sys
import platform
import queue

import speech_recognition as sr
import keyboard
import google.generativeai as genai
import pyperclip
import pyautogui
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Geminiの初期化
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# システムプロンプトの設定
SYSTEM_PROMPT = (
    "あなたは高精度な文字起こしアシスタントです。ユーザーの音声認識テキストを受け取り、以下の処理のみを行ってください。"
    "文章の要約やリライト（言い回しの変更）は厳禁です。\n"
    "1. 文脈を読み取り、誤った漢字変換や同音異義語を修正する（例: 製作/制作、回答/解答）。\n"
    "2. 『えー』『あー』『そのー』などのフィラー（言い淀み）のみを削除する。\n"
    "3. 必要に応じて句読点を補う。\n"
    "出力は修正後のテキストのみを行ってください。"
)

class VoiceInputTool:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.recording_key = "right alt"
        
        # 認識感度の調整
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def process_with_gemini(self, text):
        """Gemini APIを使用してテキストを成形する"""
        if not text:
            return ""
        
        try:
            prompt = f"{SYSTEM_PROMPT}\n\n入力テキスト: {text}"
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"\n[Error] Gemini API エラー: {e}")
            return text

    def type_text(self, text):
        """テキストをクリップボードにコピーして貼り付ける"""
        if not text:
            return
            
        pyperclip.copy(text)
        
        # OSに応じた貼り付けショートカット
        if platform.system() == "Darwin":  # Mac
            pyautogui.hotkey("command", "v")
        else:  # Windows/Linux
            pyautogui.hotkey("ctrl", "v")

    def record_audio(self):
        """録音ループ（別スレッドで実行）"""
        with self.microphone as source:
            while True:
                if keyboard.is_pressed(self.recording_key):
                    if not self.is_recording:
                        print("\n[聞き取っています...]")
                        self.is_recording = True
                        
                    # 録音開始
                    audio = self.recognizer.listen(source)
                    self.audio_queue.put(audio)
                else:
                    if self.is_recording:
                        self.is_recording = False
                    time.sleep(0.1)

    def main_loop(self):
        """処理ループ"""
        print(f"--- AI 音声入力ツール 起動中 ---")
        print(f"設定: [{self.recording_key}] キーを押している間だけ録音します。")
        print("終了するには Ctrl+C を押してください。")
        
        # 録音スレッドの開始
        threading.Thread(target=self.record_audio, daemon=True).start()

        try:
            while True:
                if not self.audio_queue.empty():
                    audio = self.audio_queue.get()
                    
                    print("[音声認識中...]")
                    try:
                        # Google Web Speech API でテキスト化
                        raw_text = self.recognizer.recognize_google(audio, language="ja-JP")
                        print(f"認識結果: {raw_text}")
                        
                        print("[AIが変換中...]")
                        refined_text = self.process_with_gemini(raw_text)
                        print(f"変換結果: {refined_text}")
                        
                        # 入力
                        self.type_text(refined_text)
                        
                    except sr.UnknownValueError:
                        print("\n[!] 音声が聞き取れませんでした。")
                    except sr.RequestError as e:
                        print(f"\n[!] 音声認識サービスのエラー: {e}")
                    
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n終了します。")

if __name__ == "__main__":
    tool = VoiceInputTool()
    tool.main_loop()
