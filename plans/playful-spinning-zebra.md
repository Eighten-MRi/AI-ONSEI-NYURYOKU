# 4テーマ追加プラン（Spotify / Raycast / Claude / ElevenLabs）

## Context

LinearとRelax Navyの2テーマに加え、Spotify・Raycast・Claude・ElevenLabsの4テーマを追加する。Claude・ElevenLabsはライトテーマで、ダーク系2つと合わせてバリエーション豊富な選択肢になる。

## 対象ファイル

- `main.py` — THEMES辞書に4エントリ追加（波形カラー含む）

## 追加テーマ定義

### Spotify（ダーク / グリーンアクセント）
```python
"Spotify": {
    "bg": "#121212", "fg_primary": "#b3b3b3", "fg_header": "#ffffff", "fg_danger": "#f3727f",
    "input_bg": "#1f1f1f", "input_fg": "#ffffff",
    "btn_bg": "#1f1f1f", "btn_fg": "#ffffff",
    "btn_danger_bg": "#1a0a0a", "btn_danger_fg": "#f3727f",
    "select_bg": "#1ed760", "select_fg": "#121212", "border": "#282828",
    "active_bg": "#1ed760", "active_fg": "#121212", "font": "Segoe UI",
    "wave_idle": "#1ed760", "wave_rec": "#539df5",
    "wave_proc_start": "#ffa42b", "wave_proc_end": "#f3727f",
},
```

### Raycast（ダーク / 赤アクセント）
```python
"Raycast": {
    "bg": "#07080a", "fg_primary": "#cecece", "fg_header": "#f9f9f9", "fg_danger": "#FF6363",
    "input_bg": "#101111", "input_fg": "#f9f9f9",
    "btn_bg": "#101111", "btn_fg": "#cecece",
    "btn_danger_bg": "#1a0808", "btn_danger_fg": "#FF6363",
    "select_bg": "#FF6363", "select_fg": "#ffffff", "border": "#252829",
    "active_bg": "#FF6363", "active_fg": "#ffffff", "font": "Segoe UI",
    "wave_idle": "#9c9c9d", "wave_rec": "#FF6363",
    "wave_proc_start": "#ffbc33", "wave_proc_end": "#FF6363",
},
```

### Claude（ライト / テラコッタアクセント）
```python
"Claude": {
    "bg": "#f5f4ed", "fg_primary": "#5e5d59", "fg_header": "#141413", "fg_danger": "#b53333",
    "input_bg": "#ffffff", "input_fg": "#141413",
    "btn_bg": "#e8e6dc", "btn_fg": "#4d4c48",
    "btn_danger_bg": "#f0e0e0", "btn_danger_fg": "#b53333",
    "select_bg": "#c96442", "select_fg": "#ffffff", "border": "#e8e6dc",
    "active_bg": "#c96442", "active_fg": "#ffffff", "font": "Georgia",
    "wave_idle": "#c96442", "wave_rec": "#d97757",
    "wave_proc_start": "#d4a373", "wave_proc_end": "#b53333",
},
```

### ElevenLabs（ライト / モノクロ＋ストーン）
```python
"ElevenLabs": {
    "bg": "#f5f5f5", "fg_primary": "#4e4e4e", "fg_header": "#000000", "fg_danger": "#cc3333",
    "input_bg": "#ffffff", "input_fg": "#000000",
    "btn_bg": "#f5f2ef", "btn_fg": "#000000",
    "btn_danger_bg": "#f5e0e0", "btn_danger_fg": "#cc3333",
    "select_bg": "#000000", "select_fg": "#ffffff", "border": "#e5e5e5",
    "active_bg": "#000000", "active_fg": "#ffffff", "font": "Segoe UI",
    "wave_idle": "#b0aea5", "wave_rec": "#777169",
    "wave_proc_start": "#c9a06a", "wave_proc_end": "#cc3333",
},
```

## 配置順序

THEMES辞書内の順序（外観タブのリスト順）:
1. Linear（デフォルト）
2. Relax Navy
3. Spotify
4. Raycast
5. Claude
6. ElevenLabs

## 検証

1. アプリ起動後、外観タブで6テーマ全て切り替え確認
2. 各テーマでインジケーター波形の色が連動することを確認
3. ライトテーマ（Claude/ElevenLabs）で文字が読めることを確認
