# Linear デザインシステム適用によるUI刷新プラン

## Context

音声認識βアプリ（tkinter製）のUIを、Linearのダークモードネイティブ・インディゴバイオレットアクセントのデザインシステムに沿って刷新する。現在4つのテーマ（Relax Navy, Cafe Mocha, Gruvbox, Cyberpunk）があるが、新たに「Linear」テーマを追加しデフォルトにする。既存テーマは引き続き選択可能。

## 対象ファイル

- `main.py` — テーマ辞書、SettingsManager、SettingsWindow、RecordingIndicator
- `ui_widgets.py` — RoundedButton、RoundedEntry

---

## Phase 1: Linearテーマトークン追加（main.py）

### 1-1. `THEMES` 辞書にLinearエントリ追加（197行目付近）

辞書の**先頭**に追加:

```python
"Linear": {
    "bg": "#0f1011",              # Panel Dark
    "fg_primary": "#d0d6e0",      # Secondary Text（本文）
    "fg_header": "#f7f8f8",       # Primary Text（見出し）
    "fg_danger": "#e5484d",       # クールな赤（Radix Red 9）
    "input_bg": "#191a1b",        # Level 3 Surface
    "input_fg": "#d0d6e0",        # Secondary Text
    "btn_bg": "#191a1b",          # Level 3 Surface
    "btn_fg": "#d0d6e0",          # Secondary Text
    "btn_danger_bg": "#1a1011",   # ダーク赤背景
    "btn_danger_fg": "#e5484d",   # クール赤
    "select_bg": "#5e6ad2",       # Brand Indigo
    "select_fg": "#f7f8f8",       # Primary Text
    "border": "#23252a",          # Border Primary
    "active_bg": "#5e6ad2",       # Brand Indigo
    "active_fg": "#f7f8f8",       # Primary Text
    "font": "Segoe UI"            # Windows上のInter代替
},
```

### 1-2. デフォルトテーマ変更

- `SettingsManager._DEFAULTS`（106行目）: `"theme": "Relax Navy"` → `"theme": "Linear"`
- `SettingsWindow.__init__`（247行目）: フォールバック `"Relax Navy"` → `"Linear"`
- `SettingsWindow.__init__`（249行目）: フォールバック `"Relax Navy"` → `"Linear"`

### 1-3. フォントサイズ調整（252-257行目）

```python
base_font = self.colors.get("font", "Segoe UI")
self.font_main   = (base_font, 10)
self.font_bold   = (base_font, 10, "bold")
self.font_header = (base_font, 12, "bold")   # 11→12
self.font_small  = (base_font, 9)             # 8→9
```

---

## Phase 2: RecordingIndicatorカラー更新（main.py）

### 2-1. カラー定義変更（919-925行目）

```python
self.color_idle          = "#8a8f98"         # 緑→クール灰（Tertiary Text）
self.color_recording     = "#7170ff"         # シアン→アクセントバイオレット
self.color_process_start = (94, 106, 210)    # オレンジ→Brand Indigo RGB
self.color_process_end   = (113, 112, 255)   # 赤→Accent Violet RGB
self.color_error         = "#e5484d"         # 紫→クール赤
self.color_grid          = "#23252a"         # ダークシアン→Border Primary
```

### 2-2. グローカラー変更（update_wave内）

| 状態 | 現在 | 変更後 |
|------|------|--------|
| Processing glow start（1055行目） | `(100,50,0)` | `(30,33,66)` |
| Processing glow end（1055行目） | `(100,0,0)` | `(35,35,80)` |
| Error glow（1068行目） | `"#4b0082"` | `"#3d1517"` |
| Recording glow（1080行目） | `"#008080"` | `"#3b3b7a"` |
| Idle glow（1091行目） | `"#003300"` | `"#1a1b1e"` |

---

## Phase 3: ウィジェット改善（ui_widgets.py）

### 3-1. デフォルトフォント変更

- `RoundedButton.__init__`（33行目）: `"Verdana"` → `"Segoe UI"`
- `RoundedEntry.__init__`（186行目）: `"Verdana"` → `"Segoe UI"`

### 3-2. RoundedEntryのフォーカスリング実装（211-215行目）

```python
def __init__(self, ...):
    ...
    self._original_border_color = border_color  # 追加
    self.focus_color = kwargs.pop('focus_color', "#5e6ad2")  # 追加
    ...

def _on_focus_in(self, event):
    self.border_color = self.focus_color
    self.draw()

def _on_focus_out(self, event):
    self.border_color = self._original_border_color
    self.draw()
```

SettingsWindow側でRoundedEntry生成時に `focus_color=self.colors["active_bg"]` を渡す。

---

## Phase 4: レイアウト微調整（main.py）

### 4-1. メインフレームのボーダー

- 274行目: `highlightthickness=2` → `highlightthickness=1`

### 4-2. タブ下セパレーター追加

`tab_frame.pack(...)` の直後にセパレーターラインを挿入:
```python
separator = tk.Frame(self.main_frame, bg=self.colors["border"], height=1)
separator.pack(fill=tk.X, padx=10)
```

### 4-3. Text widgetのセレクション色追加

Text widget生成箇所に `selectbackground=self.colors["select_bg"]`, `selectforeground=self.colors["select_fg"]` を追加。

### 4-4. パディング調整

- content_container（307行目）: `padx=15, pady=10` → `padx=20, pady=12`
- footer_frame（320行目）: `padx=15, pady=(0, 10)` → `padx=20, pady=(0, 12)`

---

## 検証手順

1. アプリ起動 → Linearテーマがデフォルトで適用されることを確認
2. 設定ウィンドウの全4タブ（ペルソナ、音声設定、モデル、外観）を巡回し、配色・フォントを目視確認
3. 外観タブで他テーマ（Relax Navy等）に切り替えて正常動作を確認
4. RecordingIndicatorの各状態を確認:
   - 待機中: 灰色の心拍パターン
   - 録音中: バイオレット色の音量連動波形
   - 処理中: インディゴ↔バイオレットのグリッチアニメーション
   - エラー: 赤のスパイクパターン
5. RoundedEntryにフォーカスした際、インディゴのフォーカスリングが表示されることを確認
