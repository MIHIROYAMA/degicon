# 起動スクリプト: メディアループとマイク検出

このリポジトリには、起動時に `movies/sandstorm.mp4`（動画） と `sounds/sandstorm.mp3`（音声） を無限ループ再生し、マイク入力を監視して音声を検出したら実アプリケーションに遷移するスクリプトが含まれています。

セットアップ (Windows / PowerShell):

```powershell
# 仮想環境推奨
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

注意:
- `python-vlc` はシステムにインストールされた VLC を利用します。事前に https://www.videolan.org/vlc/ から VLC をインストールしてください。
- `sounddevice` は PortAudio を利用します。Windows の場合 pip インストールで足りることが多いですが、問題が出た場合は PortAudio のセットアップを確認してください。

実行:

```powershell
python application/launching.py
```

動作:
- 動画と音声をループ再生します。
- マイクの音量が閾値を超えると再生を停止して `actual_application()`（プレースホルダ）に遷移します。

カスタマイズ:
- 閾値やサンプリングレートは `application/launching.py` 内の `monitor_mic` の引数で調整できます。
