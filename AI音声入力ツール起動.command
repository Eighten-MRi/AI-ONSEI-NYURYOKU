#!/bin/bash
cd "$(dirname "$0")"

# 依存がインストールされたPythonを探して起動 (Apple純正の python3=3.9 フォールバック回避)
for py in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c "import speech_recognition" 2>/dev/null; then
        exec "$py" main.py
    fi
done

echo "エラー: 必要な依存がインストールされたPythonが見つかりません。"
echo "  pip3 install -r requirements.txt を実行してください。"
read -p "Enterキーで閉じる" dummy
exit 1
