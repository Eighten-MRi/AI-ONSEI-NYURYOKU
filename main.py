import os
import time
import threading
import sys
import queue
import socket # 多重起動チェック用
import json

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

from ui_widgets import RoundedButton, RoundedEntry



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
    "あなたは超高精度な文字起こしアシスタントです。ユーザーの録音音声を聞き取り、以下のルールに従って**最終的に言いたかったことだけ**をテキスト化してください。\n"
    "【最重要指示】ユーザーとの対話（「了解しました」等の返答、挨拶、説明）は一切禁止です。文字起こししたテキストのみを出力してください。\n"
    "1. 【徹底したクレンジング】\n"
    "   - 「あー」「えー」「あの」「その」等のフィラー（言い淀み）は全て削除してください。\n"
    "   - 噛んだ言葉、どもり（音の重複）、言い直し、不明瞭なムニャムニャとした音は、書き起こさずに破棄してください。\n"
    "   - 最終的に成立している文章・単語のみを採用してください。\n"
    "2. 【自己訂正の処理】\n"
    "   - 文中で「あ、違う」「あ、間違えた」「訂正」等の自己訂正が入った場合、その発言自体と、**その直前の誤った箇所（数単語〜一文）を遡って削除**し、その後に続く正しい言い直し部分のみを採用してください。\n"
    "3. 【表記ルール】\n"
    "   - 方言は維持し、標準語への変換は行わず、聞こえたまま忠実に書き起こしてください。\n"
    "   - 文脈から明らかな誤変換（漢字のミス等）は修正してください。\n"
    "4. 【操作コマンド（文脈判断）】\n"
    "   - 「まる」→「。」、「てん」→「、」に変換してください。\n"
    "   - 「改行（かいぎょう）」という言葉について：\n"
    "     - 段落を変える指示としての「改行」と言った場合は、特殊な文字列 `[NEWLINE]` をその位置に必ず出力してください。実際の改行コード（\\n）は出力しないでください。\n"
    "     - 例: 「テストです まる 改行 よろしくお願いします」 → 「テストです。[NEWLINE]よろしくお願いします」\n"
    "     - ユーザーが「改行」という単語だけを発している場合は、前後に文字がなくても `[NEWLINE]` を出力してください。\n"
    "     - 文章の中でただの言葉として使われている場合（例：「改行がおかしい」など）は、そのまま文字で「改行」と出力し、`[NEWLINE]` には変換しないでください。\n"
    "5. 【不要な句読点・スペースの排除】\n"
    "   - 入力の最後（文末）には、絶対に「。」（まる）を付けないでください。\n"
    "   - 回答の末尾には絶対に改行コード（\\n）を付けないでください。\n"
    "   - 明示的な「てん」「まる」がない限り、句読点は最小限に留めてください。\n"
    "   - 日本語の文章内にスペース（半角・全角）を絶対に含めないでください。単語間の区切りも不要です。\n"
    "6. 【ノイズ対策】\n"
    "   - 音声が聞き取れない場合や、意味のないノイズのみの場合は、何も出力しないでください。\n"
    "出力は、整形後のテキストのみで行ってください。"
)
# 可能な限りユーザーが発言したそのままのニュアンスを保つことが最優先です。


class SettingsManager:
    """設定をメモリ上でキャッシュし、ファイルI/Oを最小化する。
    ファイルの読み書きは起動時と保存時の1回ずつのみ。"""
    _DEFAULTS = {
        "personas": [{"name": "標準", "instruction": ""}],
        "active_index": 0,
        "energy_threshold": 300,
        "theme": "Relax Navy",
    }

    def __init__(self, path: str):
        self._path = path
        self._data = {}
        self.load()

    def load(self):
        """ファイルから設定を読み込む（起動時のみ呼ぶ）"""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 旧フォーマット移行
                    if "personas" not in data:
                        old_instr = data.get("custom_instruction", "")
                        data["personas"] = [{"name": "標準 (旧設定)", "instruction": old_instr}]
                        data["active_index"] = 0
                    self._data = {**self._DEFAULTS, **data}
                    return
            except Exception as e:
                print(f"[設定読み込みエラー]: {e}")
        self._data = {**self._DEFAULTS, "personas": [{"name": "標準", "instruction": ""}]}

    def save(self):
        """変更時だけ呼ぶ（ファイルへ書き込み）"""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[設定保存エラー]: {e}")

    @property
    def data(self):
        """設定 dict への参照（直接変更可能）"""
        return self._data

    @property
    def energy_threshold(self):
        return self._data.get("energy_threshold", 300)

    @property
    def active_persona_instruction(self):
        idx = self._data.get("active_index", 0)
        personas = self._data.get("personas", [])
        if 0 <= idx < len(personas):
            return personas[idx].get("instruction", "")
        return ""


# グローバルな設定管理インスタンス（起動時に一度だけファイルを読む）
settings_manager = SettingsManager(resource_path("settings.json"))


THEMES = {
    "Relax Navy": {
        "bg": "#1A2332", "fg_primary": "#E5E9F0", "fg_header": "#88C0D0", "fg_danger": "#BF616A",
        "input_bg": "#293245", "input_fg": "#E5E9F0", 
        "btn_bg": "#293245", "btn_fg": "#E5E9F0",
        "btn_danger_bg": "#252020", "btn_danger_fg": "#BF616A",
        "select_bg": "#434C5E", "select_fg": "#E5E9F0", "border": "#3B4252",
        "active_bg": "#88C0D0", "active_fg": "#1A2332", "font": "Verdana"
    },
    "Cafe Mocha": {
        "bg": "#3E3535", "fg_primary": "#E8DDCB", "fg_header": "#D4A373", "fg_danger": "#C2716F",
        "input_bg": "#4E4444", "input_fg": "#E8DDCB", 
        "btn_bg": "#4E4444", "btn_fg": "#E8DDCB",
        "btn_danger_bg": "#352e2e", "btn_danger_fg": "#C2716F",
        "select_bg": "#D4A373", "select_fg": "#3E3535", "border": "#594D4D",
        "active_bg": "#D4A373", "active_fg": "#3E3535", "font": "Verdana"
    },
    "Gruvbox": {
        "bg": "#282828", "fg_primary": "#ebdbb2", "fg_header": "#fabd2f", "fg_danger": "#fb4934",
        "input_bg": "#3c3836", "input_fg": "#ebdbb2", 
        "btn_bg": "#3c3836", "btn_fg": "#ebdbb2",
        "btn_danger_bg": "#202020", "btn_danger_fg": "#fb4934",
        "select_bg": "#d79921", "select_fg": "#282828", "border": "#504945",
        "active_bg": "#b8bb26", "active_fg": "#282828", "font": "Verdana"
    },
    "Cyberpunk": {
        "bg": "#050510", "fg_primary": "#00ffff", "fg_header": "#00ff99", "fg_danger": "#ff0055",
        "input_bg": "#1a1a30", "input_fg": "#ffffff", 
        "btn_bg": "#1a1a30", "btn_fg": "#00ffff",
        "btn_danger_bg": "#100000", "btn_danger_fg": "#ff0055",
        "select_bg": "#00ffff", "select_fg": "#000000", "border": "#00ffff",
        "active_bg": "#00ff99", "active_fg": "#000000", "font": "Consolas"
    }
}

class SettingsWindow:
    def __init__(self, parent, on_quit_callback=None):
        self.window = tk.Toplevel(parent)
        self.window.title("SYSTEM CONFIG") # Title update
        self.window.geometry("720x520") 
        self.on_quit_callback = on_quit_callback
        
        self.window.attributes("-alpha", 1.0)
        self.window.attributes("-topmost", True)
        self.window.overrideredirect(False)
        self.parent = parent
        
        self.settings = settings_manager.data
        
        # Theme Setup
        self.current_theme_name = self.settings.get("theme", "Relax Navy")
        if self.current_theme_name not in THEMES:
             self.current_theme_name = "Relax Navy"
        self.colors = THEMES[self.current_theme_name]
        
        # Font Setup
        base_font = self.colors.get("font", "Verdana")
        self.font_main = (base_font, 10)
        self.font_bold = (base_font, 10, "bold")
        self.font_header = (base_font, 11, "bold")
        self.font_small = (base_font, 8)
        
        self.window.config(bg=self.colors["bg"])
        
        # UI Variables
        self.current_index = self.settings.get("active_index", 0)
        if self.current_index >= len(self.settings["personas"]):
            self.current_index = 0
            
        self.var_name = tk.StringVar()
        self.var_sense_val = tk.IntVar()
        self.var_sense_val.set(self.settings.get("energy_threshold", 300))
        self.current_tab = "persona" # persona, audio, appearance

        # === Layout ===
        # Main Container with Border
        self.main_frame = tk.Frame(self.window, bg=self.colors["bg"], 
                              highlightbackground=self.colors["border"], highlightthickness=2)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.rebuild_ui()

    def rebuild_ui(self):
        # Clear existing widgets in main_frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()
            
        # Update Main Frame BG
        self.main_frame.config(bg=self.colors["bg"], highlightbackground=self.colors["border"])
        self.window.config(bg=self.colors["bg"])

        # --- Tab Header ---
        tab_frame = tk.Frame(self.main_frame, bg=self.colors["bg"])
        tab_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        tabs = [
            ("👤 ペルソナ", "persona"),
            ("🎤 音声設定", "audio"),
            ("🎨 外観", "appearance")
        ]

        for text, tab_id in tabs:
            is_active = (self.current_tab == tab_id)
            btn = self.create_flat_btn(tab_frame, text, lambda tid=tab_id: self.switch_tab(tid), 
                                      style="primary" if is_active else "secondary")
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # Content Area
        self.content_container = tk.Frame(self.main_frame, bg=self.colors["bg"])
        self.content_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        if self.current_tab == "persona":
            self.draw_persona_tab()
        elif self.current_tab == "audio":
            self.draw_audio_tab()
        elif self.current_tab == "appearance":
            self.draw_appearance_tab()
            
        # --- Footer ---
        footer_frame = tk.Frame(self.main_frame, bg=self.colors["bg"])
        footer_frame.pack(fill=tk.X, padx=15, pady=(0, 10))

        # Save Indicator (Top Row of Footer)
        save_msg_frame = tk.Frame(footer_frame, bg=self.colors["bg"])
        save_msg_frame.pack(fill=tk.X)
        self.lbl_save_status = tk.Label(save_msg_frame, text="", font=self.font_small, 
                                        bg=self.colors["bg"], fg=self.colors["fg_primary"])
        self.lbl_save_status.pack(side=tk.RIGHT)

        # Bottom Buttons (Bottom Row of Footer)
        btn_frame = tk.Frame(footer_frame, bg=self.colors["bg"])
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.create_flat_btn(btn_frame, "設定を閉じる", self.window.destroy, style="primary").pack(side=tk.LEFT)
        self.create_flat_btn(btn_frame, "アプリを終了する", self.on_shutdown, style="danger").pack(side=tk.RIGHT)

    def switch_tab(self, tab_id):
        self.current_tab = tab_id
        self.rebuild_ui()

    def draw_persona_tab(self):
        # Content Area split for persona
        content_frame = tk.Frame(self.content_container, bg=self.colors["bg"])
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Left Panel (List) ---
        frame_left = tk.Frame(content_frame, bg=self.colors["bg"], width=240)
        frame_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        tk.Label(frame_left, text="ペルソナ一覧", font=self.font_bold, 
                 bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(anchor=tk.W, pady=(0,10))
        
        list_container = tk.Frame(frame_left, bg=self.colors["border"], padx=1, pady=1)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        self.listbox = tk.Listbox(list_container, exportselection=False, 
                                  bg=self.colors["input_bg"], fg=self.colors["input_fg"],
                                  selectbackground=self.colors["select_bg"], selectforeground=self.colors["select_fg"],
                                  highlightthickness=0, borderwidth=0, font=self.font_main)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        
        frame_list_btns = tk.Frame(frame_left, bg=self.colors["bg"])
        frame_list_btns.pack(fill=tk.X, pady=15)
        self.create_flat_btn(frame_list_btns, "新規作成", self.add_persona, style="secondary").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.create_flat_btn(frame_list_btns, "削除", self.delete_persona, style="danger").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # --- Right Panel (Details) ---
        frame_right = tk.Frame(content_frame, bg=self.colors["bg"])
        frame_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        frame_name = tk.Frame(frame_right, bg=self.colors["bg"])
        frame_name.pack(fill=tk.X, pady=(0, 15))
        tk.Label(frame_name, text="識別名 (ID):", font=self.font_bold, bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(side=tk.LEFT, padx=(0,10))
        self.entry_name = RoundedEntry(frame_name, textvariable=self.var_name, 
                                   bg=self.colors["input_bg"], fg=self.colors["input_fg"], 
                                   insertbackground=self.colors["fg_primary"], font=self.font_main, radius=8, height=36)
        self.entry_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry_name.bind_entry("<FocusOut>", self.on_name_change) 
        
        tk.Label(frame_right, text="AI指示プロンプト (書き起こし調整):", font=self.font_bold, bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(anchor=tk.W, pady=(0, 5))
        text_container = tk.Frame(frame_right, bg=self.colors["border"], padx=1, pady=1)
        text_container.pack(fill=tk.BOTH, expand=True)
        self.text_instruction = tk.Text(text_container, height=1, width=40, bg=self.colors["input_bg"], fg=self.colors["input_fg"], 
                                        insertbackground=self.colors["fg_primary"], highlightthickness=0, borderwidth=0, font=self.font_main, padx=10, pady=10)
        self.text_instruction.pack(fill=tk.BOTH, expand=True)
        self.text_instruction.bind("<KeyRelease>", self.on_text_change)

        # Footer Actions for Persona
        frame_persona_actions = tk.Frame(frame_right, bg=self.colors["bg"])
        frame_persona_actions.pack(fill=tk.X, pady=(15, 0))
        self.lbl_active_status = tk.Label(frame_persona_actions, text="", font=self.font_bold, bg=self.colors["bg"])
        self.lbl_active_status.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_activate = self.create_flat_btn(frame_persona_actions, "有効化", self.set_active_persona, style="primary")
        self.btn_activate.pack(side=tk.RIGHT)

        # Init persona tab state
        self.refresh_list()
        self.listbox.selection_set(self.current_index)
        self.load_details(self.current_index)
        self.update_active_display()

    def draw_audio_tab(self):
        container = tk.Frame(self.content_container, bg=self.colors["bg"])
        container.pack(fill=tk.BOTH, expand=True, pady=20)

        tk.Label(container, text="🎤 マイク録音感度の設定", font=self.font_header, 
                 bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(pady=(0, 20))

        # Description
        desc = "Altキーを押したとき、どの程度の音量があれば「喋っている」と判断するかを調整します。"
        tk.Label(container, text=desc, font=self.font_main, bg=self.colors["bg"], fg=self.colors["fg_primary"], wraplength=600).pack(pady=5)

        # Slider Value Display
        val_frame = tk.Frame(container, bg=self.colors["bg"])
        val_frame.pack(pady=10)
        tk.Label(val_frame, text="現在のしきい値:", font=self.font_main, bg=self.colors["bg"], fg=self.colors["fg_primary"]).pack(side=tk.LEFT)
        self.lbl_sense_val = tk.Label(val_frame, textvariable=self.var_sense_val, font=(self.colors["font"], 16, "bold"), 
                                      bg=self.colors["bg"], fg=self.colors["active_bg"])
        self.lbl_sense_val.pack(side=tk.LEFT, padx=10)

        # Slider Frame with Guides
        slider_outer = tk.Frame(container, bg=self.colors["bg"])
        slider_outer.pack(fill=tk.X, padx=50, pady=20)

        # Labels for Slider
        guide_frame = tk.Frame(slider_outer, bg=self.colors["bg"])
        guide_frame.pack(fill=tk.X)
        tk.Label(guide_frame, text="← 高感度 (ボソボソ声用)", font=self.font_small, bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(side=tk.LEFT)
        tk.Label(guide_frame, text="雑音に強い (騒がしい場所) →", font=self.font_small, bg=self.colors["bg"], fg=self.colors["fg_danger"]).pack(side=tk.RIGHT)

        self.scale_sense = tk.Scale(slider_outer, from_=10, to=500, orient=tk.HORIZONTAL, 
                                    showvalue=False, bg=self.colors["bg"], highlightthickness=0,
                                    troughcolor=self.colors["input_bg"], activebackground=self.colors["active_bg"],
                                    command=lambda e: self.on_sense_change())
        self.scale_sense.set(self.settings.get("energy_threshold", 300))
        self.scale_sense.pack(fill=tk.X, pady=5)

        # Help Info
        help_box = tk.Frame(container, bg=self.colors["input_bg"], padx=15, pady=15)
        help_box.pack(fill=tk.X, padx=50, pady=10)
        help_text = "💡 アドバイス:\n・静かな部屋で使う場合は 30〜80 程度がおすすめです。\n・テレビや外の音がうるさい場合は 200〜400 程度に上げてください。\n・バーを動かして「保存完了」が出れば、次の録音から反映されます。"
        tk.Label(help_box, text=help_text, font=self.font_small, bg=self.colors["input_bg"], fg=self.colors["input_fg"], justify=tk.LEFT).pack()

    def draw_appearance_tab(self):
        container = tk.Frame(self.content_container, bg=self.colors["bg"])
        container.pack(fill=tk.BOTH, expand=True, pady=10)

        tk.Label(container, text="🎨 アプリの外観テーマ", font=self.font_header, 
                 bg=self.colors["bg"], fg=self.colors["fg_header"]).pack(pady=(0, 10))

        # List of themes
        list_outer = tk.Frame(container, bg=self.colors["border"], padx=1, pady=1)
        list_outer.pack(fill=tk.BOTH, expand=True, padx=50)

        self.theme_listbox = tk.Listbox(list_outer, exportselection=False, 
                                        bg=self.colors["input_bg"], fg=self.colors["input_fg"],
                                        selectbackground=self.colors["select_bg"], selectforeground=self.colors["select_fg"],
                                        highlightthickness=0, borderwidth=0, font=self.font_main)
        self.theme_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        theme_names = list(THEMES.keys())
        for name in theme_names:
            self.theme_listbox.insert(tk.END, name)
            if name == self.current_theme_name:
                idx = theme_names.index(name)
                self.theme_listbox.selection_set(idx)
        
        self.theme_listbox.bind("<<ListboxSelect>>", self.on_theme_select)

        tk.Label(container, text="※ 一覧から選択すると即座に反映されます", font=self.font_small, 
                 bg=self.colors["bg"], fg=self.colors["fg_primary"]).pack(pady=10)

    def on_theme_select(self, event):
        sel = self.theme_listbox.curselection()
        if sel:
            theme_names = list(THEMES.keys())
            new_theme = theme_names[sel[0]]
            if new_theme != self.current_theme_name:
                self.apply_theme(new_theme)

    def apply_theme(self, theme_name):
        self.current_theme_name = theme_name
        self.colors = THEMES[self.current_theme_name]
        
        # Save theme
        self.settings["theme"] = self.current_theme_name
        self.save_settings()
        
        # Update fonts
        base_font = self.colors.get("font", "Verdana")
        self.font_main = (base_font, 10)
        self.font_bold = (base_font, 10, "bold")
        self.font_header = (base_font, 11, "bold")
        self.font_small = (base_font, 8)
        
        # Rebuild UI
        self.rebuild_ui()

    def cycle_theme(self):
        theme_names = list(THEMES.keys())
        curr_idx = theme_names.index(self.current_theme_name) if self.current_theme_name in theme_names else 0
        next_idx = (curr_idx + 1) % len(theme_names)
        self.apply_theme(theme_names[next_idx])

    def create_flat_btn(self, parent, text, command, style="secondary"):
        """Custom Flat Button with Hierarchy"""
        # Determine colors based on style
        bg_color = self.colors["btn_bg"]
        fg_color = self.colors["btn_fg"]
        
        if style == "primary":
            # Primary: Active Color Background (e.g., Blue/Cyan/Green)
            bg_color = self.colors["active_bg"]
            fg_color = self.colors["active_fg"]
        elif style == "danger":
            # Danger: Dark Red BG or similar
            bg_color = self.colors.get("btn_danger_bg", "#300000")
            fg_color = self.colors.get("btn_danger_fg", "#ff0000")
        else: # secondary
             # Secondary: Default Button BG
             pass
            
        btn = RoundedButton(parent, text=text, command=command,
                        bg=bg_color, fg=fg_color,
                        active_bg=fg_color, active_fg=bg_color,
                        font=self.font_bold,
                        padx=16, pady=8, radius=8)
        return btn

    def show_save_indicator(self):
        """Show a temporary 'SAVED' message"""
        self.lbl_save_status.config(text="[ 保存完了 (SAVED) ]")
        # Remove existing timer if any
        if hasattr(self, "_save_timer") and self._save_timer:
            self.window.after_cancel(self._save_timer)
        self._save_timer = self.window.after(2000, lambda: self.lbl_save_status.config(text=""))

    def save_settings(self):
        settings_manager.save()
        self.show_save_indicator()

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, p in enumerate(self.settings["personas"]):
            name = p["name"]
            # Active indicator
            if i == self.settings["active_index"]:
                name = f"● {name}" 
            self.listbox.insert(tk.END, name)
            
            # ハイライトは選択色と同じだが、一覧でも文字色を変えてわかりやすくする
            if i == self.settings["active_index"]:
                 self.listbox.itemconfig(i, fg=self.colors["fg_header"]) # Yellowish for active item text in list

    def on_select(self, event):
        sel = self.listbox.curselection()
        if sel:
            index = sel[0]
            self.current_index = index 
            self.load_details(index)
            self.update_active_display()

    def load_details(self, index):
        if 0 <= index < len(self.settings["personas"]):
            p = self.settings["personas"][index]
            self.var_name.set(p["name"])
            self.text_instruction.delete("1.0", tk.END)
            self.text_instruction.insert("1.0", p["instruction"])

    def on_name_change(self, event):
        name = self.var_name.get()
        if 0 <= self.current_index < len(self.settings["personas"]):
            self.settings["personas"][self.current_index]["name"] = name
            self.save_settings()
            self.refresh_list()
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.current_index)

    def on_text_change(self, event):
        text = self.text_instruction.get("1.0", tk.END).strip()
        if 0 <= self.current_index < len(self.settings["personas"]):
            self.settings["personas"][self.current_index]["instruction"] = text
            # デバウンス: 500ms入力が止まってから保存（キー入力ごとの連続ディスク書き込みを防ぐ）
            if hasattr(self, "_save_debounce") and self._save_debounce:
                self.window.after_cancel(self._save_debounce)
            self._save_debounce = self.window.after(500, self.save_settings)

    def add_persona(self):
        new_persona = {"name": "新規ペルソナ (NEW)", "instruction": ""}
        self.settings["personas"].append(new_persona)
        self.save_settings()
        self.refresh_list()
        new_idx = len(self.settings["personas"]) - 1
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_idx)
        self.current_index = new_idx
        self.load_details(new_idx)
        self.update_active_display()

    def delete_persona(self):
        if len(self.settings["personas"]) <= 1:
            return 
            
        del self.settings["personas"][self.current_index]
        
        if self.current_index == self.settings["active_index"]:
            self.settings["active_index"] = 0
        elif self.current_index < self.settings["active_index"]:
            self.settings["active_index"] -= 1
            
        if self.current_index >= len(self.settings["personas"]):
            self.current_index = len(self.settings["personas"]) - 1
            
        self.save_settings()
        self.refresh_list()
        self.listbox.selection_set(self.current_index)
        self.load_details(self.current_index)
        self.update_active_display()

    def set_active_persona(self):
        self.settings["active_index"] = self.current_index
        self.save_settings()
        self.refresh_list()
        self.listbox.selection_set(self.current_index) 
        self.update_active_display()

    def on_sense_change(self):
        val = self.scale_sense.get()
        self.settings["energy_threshold"] = val
        self.var_sense_val.set(val)
        self.save_settings()

    def update_active_display(self):
        if self.current_index == self.settings["active_index"]:
            # Active State
            self.lbl_active_status.config(text="[ 稼働中 ]", fg=self.colors["active_bg"])
            self.btn_activate.config(state=tk.DISABLED, text="現在使用中", 
                                     disabled_bg=self.colors["active_bg"], disabled_fg=self.colors["active_fg"])
        else:
            # Idle State
            self.lbl_active_status.config(text="", fg="black")
            self.btn_activate.config(state=tk.NORMAL, text="このペルソナを有効化", 
                                     bg=self.colors["btn_bg"], fg=self.colors["btn_fg"])

    def on_shutdown(self):
        if self.on_quit_callback:
            self.window.destroy()
            self.on_quit_callback()



class RecordingIndicator:
    """画面中央下に表示される心電図風インジケータ"""
    def __init__(self):
        # === Dual Window Strategy ===
        # 1. self.root (Click Layer):
        #    - 背景は黒 (#000000) だが、透過度(alpha)を 0.01 に設定。
        #    - ほぼ完全な透明に見えるが、Windows上で「ウィンドウ」として認識されるためクリックを捕獲できる。
        # 2. self.visual_window (Visual Layer):
        #    - self.root の上に重なる Toplevel ウィンドウ。
        #    - 透過キー (transparentcolor) を黒に設定し、背景を完全に透過させる。
        #    - ここに Canvas を配置し、波形のみを高不透明度 (alpha 0.8-0.9) で描画する。
        
        self.root = tk.Tk()
        self.root.title("Recording Indicator (Click Layer)")
        
        # Click Layer Setup
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.01) # ほぼ透明だがクリック可能
        self.root.config(bg="#000000")
        
        # サイズと位置 (画面中央下)
        width, height = 100, 40 
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = screen_height - height - 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Visual Layer Setup
        self.visual_window = tk.Toplevel(self.root)
        self.visual_window.title("Recording Indicator (Visual Layer)")
        self.visual_window.overrideredirect(True)
        self.visual_window.attributes("-topmost", True)
        self.visual_window.attributes("-transparentcolor", "black")
        self.visual_window.config(bg="black")
        self.visual_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Canvasは Visual Layer に配置 (背景は透過キーの黒)
        self.canvas = tk.Canvas(self.visual_window, width=width, height=height, bg="black", highlightthickness=0)
        self.canvas.pack()
        
        # === イベントバインディング (両方のウィンドウで設定) ===
        # Click Layer: 背景クリック用
        self.root.bind("<Button-3>", self.open_settings_handler)
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)
        
        # Visual Layer: 波形(線)クリック用
        # Canvas自体がイベントを受ける
        self.canvas.bind("<Button-3>", self.open_settings_handler)
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<ButtonRelease-1>", self.stop_move)
        
        self.width = width
        self.height = height
        self.points = []
        
        # 状態フラグ
        self.is_recording = False
        self.is_processing = False
        self.is_error = False 
        self.drag_data = {"x": 0, "y": 0, "moved": False}
        
        # アニメーション用変数
        self.current_volume = 0 
        self.pqrst_queue = []   
        self.processing_frame = 0 
        self.error_frame = 0    
        
        self.alpha_idle = 0.8
        self.alpha_active = 0.9
        
        # カラー定義
        self.color_idle = "#00FF00"    
        self.color_recording = "#00FFFF" 
        self.color_process_start = (255, 165, 0) 
        self.color_process_end = (255, 0, 0)     
        self.color_error = "#800080" 
        self.color_grid = "#003333"
        
        self.on_quit_callback = None
        
        # 初期描画 (Visual Layerの透過度設定)
        self.visual_window.attributes("-alpha", self.alpha_idle)
        self.update_wave()
        
        # 2つのウィンドウを同期させ続けるためのループ
        self.sync_windows()
        
        # 起動時に設定ウィンドウを最小化状態で開く
        self.root.after(500, self.open_settings_minimized)

    def open_settings_minimized(self):
        self.open_settings()
        if hasattr(self, "settings_window") and self.settings_window:
            self.settings_window.iconify()

    def sync_windows(self):
        """Visual WindowをClick Windowに追従させる（念のため）"""
        try:
            self.visual_window.lift()
            self.root.after(100, self.sync_windows)
        except:
            pass

    def set_callback(self, callback):
        self.on_quit_callback = callback

    def start_move(self, event):
        """ドラッグ開始"""
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        self.drag_data["moved"] = False

    def do_move(self, event):
        """ドラッグ中 - 両方のウィンドウを移動"""
        dx = event.x - self.drag_data["x"]
        dy = event.y - self.drag_data["y"]
        
        if abs(dx) > 2 or abs(dy) > 2:
            self.drag_data["moved"] = True
            
        # イベント発生元がどちらでも、基準は self.root の位置
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        
        geom = f"+{x}+{y}"
        self.root.geometry(geom)
        self.visual_window.geometry(geom)

    def stop_move(self, event):
        """ドラッグ終了"""
        if not self.drag_data["moved"]:
            self.on_click(event)
        self.drag_data["moved"] = False

    def open_settings_handler(self, event):
        self.open_settings()

    def open_settings(self):
        if hasattr(self, "settings_window") and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        sw = SettingsWindow(self.root, on_quit_callback=self.on_quit_callback)
        self.settings_window = sw.window


    def set_recording(self, recording):
        self.is_recording = recording
        self._update_alpha()

    def set_processing(self, processing):
        self.is_processing = processing
        self._update_alpha()
        
    def show_error(self):
        self.is_error = True
        self.error_frame = 40 
        self._update_alpha()
        
    def set_volume(self, rms):
        # settings_managerからメモリ上のしきい値を取得（ファイルI/Oなし）
        threshold = settings_manager.energy_threshold
        if rms < threshold:
            vol = 0
        else:
            vol = min((rms - threshold) / 2000, 1.0)
        self.current_volume = vol

    def _update_alpha(self):
        # 変更対象は visual_window のみ (rootは常に0.01)
        if self.is_recording or self.is_processing or self.is_error:
            self.visual_window.attributes("-alpha", self.alpha_active)
        else:
            self.visual_window.attributes("-alpha", self.alpha_idle)

    def interpolate_color(self, start_rgb, end_rgb, progress):
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * progress)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * progress)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * progress)
        return f"#{r:02x}{g:02x}{b:02x}"

    def update_wave(self):
        """アニメーション描画"""
        self.canvas.delete("all")
        
        # Click Shield は不要になったので削除 (rootウィンドウがその役割)
        
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
            swing_progress = (math.sin(self.processing_frame * 0.2) + 1) / 2 
            main_color = self.interpolate_color(self.color_process_start, self.color_process_end, swing_progress)
            glow_color = self.interpolate_color((100,50,0), (100,0,0), swing_progress)

            noise = random.randint(-15, 15)
            self.points.append(base_y + noise)
            
        elif self.is_error:
            # === エラー: 紫色のスパイク ===
            self.error_frame -= 1
            if self.error_frame <= 0:
                self.is_error = False
                self._update_alpha()
            
            main_color = self.color_error
            glow_color = "#4b0082" # Indigo
            
            # ランダムで鋭いスパイク
            if random.random() > 0.7:
                 val = random.randint(-20, 20)
            else:
                 val = random.randint(-2, 2)
            self.points.append(base_y + val)

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
            
        if self.is_processing or self.is_recording or self.is_error:
             # グロー効果あり
             self.canvas.create_line(coords, fill=glow_color, width=4, smooth=True)
        
        self.canvas.create_line(coords, fill=main_color, width=line_width, smooth=True)
        
        # リード点（先頭のドット）
        if len(coords) >= 2:
            lx, ly = coords[-2], coords[-1]
            self.canvas.create_oval(lx-1, ly-1, lx+1, ly+1, fill="white", outline=main_color)



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
        
        self.energy_threshold = settings_manager.energy_threshold

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
            # プロンプト構築
            prompt = SYSTEM_PROMPT
            custom_instruction = settings_manager.active_persona_instruction
            if custom_instruction:
                prompt += f"\n\n【追加指示（重要）】\n{custom_instruction}"
            prompt += "\n\n添付された音声を聴き取り、指示通りに成形したテキストのみを答えてください。"

            response = model.generate_content([
                prompt,
                {"mime_type": "audio/wav", "data": audio_bytes}
            ])
            
            # Geminiが勝手に出力する前後の不要な空白・改行（\\n）を完全に除去する
            # ※これで「勝手に改行される」問題を解決
            text = response.text.strip()
            
            # 短いレスポンスでの改行指示のフォールバック
            # 「了解」「良好」「開票」「海峡」「大会」「採用」「退場」など、「かいぎょう」の誤認パターンを幅広く吸収する
            check_text = text.replace("。", "").replace("、", "").replace(".", "").replace("！", "").replace("!", "")
            newline_patterns = [
                "改行", "かいぎょう", "カイギョウ", "会場", "了解", "良好", "[NEWLINE]",
                "退場", "開票", "海峡", "解雇", "外教", "大行", "体表", "大京", "会議用",
                "採用", "大会", "対応", "大綱", "開業", "開放", "解像"
            ]
            if check_text in newline_patterns:
                return "\n"
                
            # 「。[NEWLINE]」を「[NEWLINE]」に（改行前のまるを消去）
            text = text.replace("。[NEWLINE]", "[NEWLINE]")
            
            # 特殊トークン `[NEWLINE]` を実際の改行コード（\\n）に変換
            # ※これで「改行がされない」問題を解決
            text = text.replace("[NEWLINE]", "\n")
            
            # 「。\\n」を「\\n」に（念のため）
            text = text.replace("。\n", "\n")
            
            # 最後に文末の「。」を削除（ユーザー要望：入力の最後にまるは要らない）
            if text.endswith("。"):
                text = text[:-1]
            
            if not text:
                return None
            
            return text
        except Exception as e:
            print(f"[Gemini直接処理失敗]: {e}")
            # エラー視覚化 (メインスレッドで実行)
            self.indicator.root.after(0, self.indicator.show_error)
            return None


    def type_text(self, text):
        """以前動作していた安定版をベースに、メニュー干渉対策を適用"""
        if not text: return
        try:
            # 1. クリップボードにコピー
            pyperclip.copy(text)
            time.sleep(0.05) 
            
            # 2. フォーカス復帰ハック (中和法と併用し、確実にフォーカスを確保)
            # 既に中和されているはずだが、念のため Ctrl タップでフォーカスを再確認
            pyautogui.press('ctrl')
            time.sleep(0.01)
            
            # 3. 貼り付け実行
            pyautogui.hotkey('ctrl', 'v')
            
            print(f" -> ペースト完了: {len(text)} 文字")
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
        RATE = 16000  # 16kHzで十分（人明の声帯域をカバー）。44100Hz比で生データが素4分の1に削減
        CHUNK = 1024

        print("--- 録音待機中 ---")
        while self.running:
            try:
                # 右Alt (キーコード165) を優先検知
                is_pressed = keyboard.is_pressed(165) or keyboard.is_pressed(self.recording_key)

                if is_pressed and not self.is_recording:
                    self.is_recording = True
                    self.indicator.set_recording(True)

                    # === 【重要】Altキーの中和処理 (Neutralization) ===
                    # Altだけが押されて離されるとWindowsのメニューが反応する。
                    # 録音開始（Alt押下）直後にShiftを空打ちすることで、
                    # Windowsに「Alt単体押しではない」と認識させ、メニュー起動を根絶する。
                    keyboard.press('shift')
                    keyboard.release('shift')

                    # Altキー押下イベントを遮断 (他のアプリへの漏洩防止)
                    try: keyboard.block_key(165)
                    except: pass
                    
                    try:
                        frames = []
                        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
                        
                        while (keyboard.is_pressed(165) or keyboard.is_pressed(self.recording_key)) and self.running:
                            data = stream.read(CHUNK, exception_on_overflow=False)
                            frames.append(data)
                            rms = audioop.rms(data, 2)
                            self.indicator.set_volume(rms)
                        
                        # 末尾の切れ防止 (約0.6秒)
                        for _ in range(10):
                            frames.append(stream.read(CHUNK, exception_on_overflow=False))
                        
                        stream.stop_stream()
                        stream.close()
                    finally:
                        self.indicator.set_recording(False)
                        # 必ずブロックを解除
                        try: keyboard.unblock_key(165)
                        except: pass



                    if frames:
                        # WAVEデータを作成
                        raw_data = b''.join(frames)
                        
                        # 録音終了時に最新のしきい値を再取得 (settings_managerからメモリ内で取得)
                        self.energy_threshold = settings_manager.energy_threshold

                        # 音量のチェック (無音時はスキップ)
                        rms = audioop.rms(raw_data, 2) # 2はpaInt16의バイト数
                        print(f" (入力音量: {rms}, 閾値: {self.energy_threshold})", end="", flush=True)
                        
                        if rms > self.energy_threshold:
                            # === 音声のノーマライズ (増幅) ===
                            # 小さな声でも Gemini が認識しやすいように、最大音量を引き上げる
                            try:
                                max_val = audioop.max(raw_data, 2)
                                if max_val > 0:
                                    # 最大値が 32767 の 80% 以下なら増幅
                                    target = 26214 # 32767 * 0.8
                                    if max_val < target:
                                        factor = target / max_val
                                        # 過度な増幅（ノイズ強調）を防ぐため最大10倍まで
                                        factor = min(factor, 10.0)
                                        raw_data = audioop.mul(raw_data, 2, factor)
                                        print(f" [Boost x{factor:.1f}]", end="")
                            except: pass

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

