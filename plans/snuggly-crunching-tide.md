# モデル選択UIの修正 & リッチ化

## Context

モデル選択ボタン（RoundedButton）がクリックできない不具合がある。RoundedButtonはCanvas描画ベースのカスタムウィジェットで、長いテキストやpack(fill=tk.X)との相性に問題がある可能性。

ユーザー要望：選択UIを表形式にして、各モデルの種別(Live/バッチ)・速度・月額コスト目安を表示し、「1日100回使った場合」の文言も入れたい。

## 修正対象

- [main.py](main.py) の `VOICE_MODELS` 定義と `draw_audio_tab()` のモデル選択セクション（433-448行目付近）

## 修正内容

### 1. VOICE_MODELS に速度情報を追加

```python
VOICE_MODELS = {
    "gemini-3.1-flash-live-preview": {
        "label": "Gemini 3.1 Flash Live",
        "type": "Live API",
        "speed": "爆速（~0.3秒）",
        "cost": "~$6.50/月（~¥1,000）",
    },
    ...
}
```

### 2. RoundedButton → クリック可能なカードUIに変更

RoundedButtonの代わりに、標準 `tk.Frame` + `<Button-1>` バインドでモデルカードを実装。各カードに以下を表示：

```
┌──────────────────────────────────────┐
│ ● Gemini 3.1 Flash Live             │ ← モデル名（選択中は●、色変更）
│   種別: Live API  速度: 爆速(~0.3秒) │ ← 種別 + 速度
│   月額: ~$6.50（~¥1,000）            │ ← コスト目安
└──────────────────────────────────────┘
```

- 選択中カード: `active_bg` 色で背景ハイライト + 左に「●」
- 非選択カード: `input_bg` 色 + 左に「○」
- カード全体（Frame + 全Label）に `<Button-1>` をバインドしてクリック確実にする
- セクション上部に「※ 1日100回・平均10秒の録音を想定した月額目安です」の説明を追加

### 3. on_model_select はそのまま（動作は正しい）

```python
def on_model_select(self, model_id):
    self.settings["live_model"] = model_id
    settings_manager.save()
    self.show_save_indicator()
    self.rebuild_ui()
```

## 変更しないもの

- LiveTranscriber / record_audio() のLive/バッチ分岐ロジック
- SettingsManager のlive_modelプロパティ
- 他のタブ（ペルソナ、外観）

## 検証方法

1. アプリ起動 → 設定画面 → Audioタブ
2. モデルカードが4つ表示され、現在の選択が視覚的にわかる
3. 各カードをクリックして「保存完了」が表示される
4. 種別・速度・コストが各カードに表示されている
5. モデル切替後の録音で選択したモデルが使われる
