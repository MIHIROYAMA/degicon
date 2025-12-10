"""
起動スクリプト

機能:
 - `movies/sandstorm.mp4` をループ再生（ビデオウィンドウ表示）
 - `sounds/sandstorm.mp3` をループ再生（バックグラウンド）
 - マイク入力を監視し、音声（大きさが閾値を超える）を検知したらループを止め、実際のアプリケーションに移行する

依存:
 - Python 3.8+
 - VLC がシステムにインストールされていること（python-vlc はシステムの VLC を利用します）
 - requirements.txt のパッケージをインストールしてください

使い方:
 1. `pip install -r requirements.txt`
 2. `python application/launching.py`

注意: Windows 環境では `python-vlc` がシステムの VLC を利用します。VLC を先にインストールしてください。
"""

import os
import sys
import time
import threading
import vlc
import subprocess
import shutil
import sounddevice as sd
import numpy as np


def resource_path(*parts):
	# launching.py は `application/` にある。プロジェクトルートを1つ上にとる
	base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	return os.path.join(base, *parts)


VIDEO_PATH = resource_path('movies', 'sandstorm.mp4')
AUDIO_PATH = resource_path('sounds', 'sandstorm.mp3')


def file_check():
	missing = []
	if not os.path.isfile(VIDEO_PATH):
		missing.append(VIDEO_PATH)
	if not os.path.isfile(AUDIO_PATH):
		missing.append(AUDIO_PATH)
	if missing:
		print('以下のファイルが見つかりません:')
		for p in missing:
			print(' -', p)
		sys.exit(1)


def loop_player(instance, media_path, stop_event, voice_event, is_video=False, external_players=None):
	try:
		media = instance.media_new(media_path) if instance is not None else None
		player = instance.media_player_new() if instance is not None else None
		if player and media:
			player.set_media(media)
			# メディア情報を解析して長さなどを取得（非同期なので少し待つ）
			try:
				media.parse()
			except Exception as e:
				print(f'[VLC][MEDIA] parse() エラー: {e}')
			# duration が取得できるまで最大3秒待つ
			dur = None
			for _ in range(30):
				dur = media.get_duration()
				if dur and dur > 0:
					break
				time.sleep(0.1)
			try:
				mrl = media.get_mrl()
			except Exception:
				mrl = 'unknown'
			print(f'[VLC][MEDIA] {media_path} mrl={mrl} duration_ms={dur}')
	except Exception as e:
		print(f'[VLC] メディア/プレイヤ作成エラー: {e}')
		media = None
		player = None

	print(f'[VLC] loop_player start: {media_path} (is_video={is_video})')

	prev_state = None

	while not stop_event.is_set() and not voice_event.is_set():
		# play
		if player is None:
			print(f'[VLC] プレイヤが利用できません: {media_path} — 再試行まで待機します')
			time.sleep(1.0)
			continue

		try:
			ret = player.play()
			print(f'[VLC] player.play() returned: {ret}')
		except Exception as e:
			print(f'[VLC] player.play() エラー: {e}')
			time.sleep(1.0)
			continue

		# wait until playback finishes or voice detected or stop requested
		while True:
			if stop_event.is_set() or voice_event.is_set():
				break
			state = player.get_state()
			if state != prev_state:
				print(f'[VLC] {media_path} state -> {state}')
				prev_state = state
			# When playing or buffering, just wait
			if state in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening):
				time.sleep(0.2)
				continue
			# If ended or stopped, break to restart (loop)
			if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error, vlc.State.NothingSpecial):
				break
			time.sleep(0.1)
		try:
			player.stop()
		except Exception:
			pass
		time.sleep(0.1)

		# フォールバック: 短時間のうちに再生状態が変わらなければ外部VLCで開く
		# ここでは直後に State.NothingSpecial または State.Stopped が続く場合をトリガとする
		# （既にループで何度も再試行しているため、簡易的な判定として直後の状態をチェック）
		# If external vlc exists, open and let it play separately
		try:
			s = player.get_state()
		except Exception:
			s = None
		if s in (vlc.State.NothingSpecial, vlc.State.Stopped):
			# check if vlc executable exists
			vlc_exe = shutil.which('vlc') or r"C:\Program Files\VideoLAN\VLC\vlc.exe"
			if os.path.isfile(vlc_exe):
				try:
					print(f'[VLC-FALLBACK] libVLC playback unstable for {media_path}, launching external VLC: {vlc_exe}')
					p = subprocess.Popen([vlc_exe, media_path])
					if external_players is not None:
						external_players.append(p)
					# give external player time to start and then break loop to avoid repeated launches
					time.sleep(1.0)
					break
				except Exception as e:
					print(f'[VLC-FALLBACK] 外部VLC起動に失敗: {e}')
			else:
				print(f'[VLC-FALLBACK] external vlc not found at {vlc_exe}')

	try:
		if player is not None:
			player.stop()
	except Exception:
		pass


def monitor_mic(voice_event, stop_event, threshold=0.05, samplerate=44100, blocksize=1024):
	# threshold: 音声のRMS閾値（正規化された -1..1 スケール）
	print(f'[MIC] monitor starting (threshold={threshold})')
	def callback(indata, frames, time_info, status):
		if status:
			return
		# indata は float32 の場合 -1..1
		rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
		# デバッグ出力: 閾値を超えたら詳細を表示
		if rms > threshold:
			print(f'[MIC] rms={rms:.5f} > threshold={threshold}')
			voice_event.set()
		else:
			# 小さな定期的ログ（過度に出力しないよう、閾値の1/2以上のみ表示）
			if rms > (threshold / 2):
				print(f'[MIC] rms={rms:.5f}')

	try:
		with sd.InputStream(channels=1, samplerate=samplerate, blocksize=blocksize, callback=callback):
			while not voice_event.is_set() and not stop_event.is_set():
				time.sleep(0.1)
	except Exception as e:
		print('マイク入力の初期化に失敗しました:', e)
		print('マイク検出は無効になります。')


def actual_application():
	# 実アプリケーションに遷移する箇所のプレースホルダ
	print('\n--- 音声を検出しました。実際のアプリケーションへ遷移します ---\n')
	# ここに本来の処理を呼び出す
	# 例: from application import main; main.run()
	# 今は代わりに簡単なメッセージと終了
	print('アプリケーションが実行されました（プレースホルダ）。')


def main():
	print('起動スクリプトを開始します...')
	file_check()

	# VLC インスタンス（ファイル出力ログは無効化）
	try:
		instance = vlc.Instance()
	except Exception as e:
		print('VLC インスタンスの作成に失敗しました:', e)
		instance = None

	# libVLC バージョン確認
	try:
		ver = vlc.libvlc_get_version()
	except Exception:
		try:
			ver = instance.get_version() if instance is not None else 'unknown'
		except Exception:
			ver = 'unknown'
	print('libVLC version:', ver)


	stop_event = threading.Event()
	voice_event = threading.Event()

	threads = []

	# 外部VLCプロセスを格納するリスト（フォールバック起動時に追加される）
	external_players = []

	# Video thread
	t_video = threading.Thread(
		target=loop_player,
		args=(instance, VIDEO_PATH, stop_event, voice_event, True, external_players),
		daemon=True,
	)
	threads.append(t_video)

	# Audio thread
	t_audio = threading.Thread(
		target=loop_player,
		args=(instance, AUDIO_PATH, stop_event, voice_event, False, external_players),
		daemon=True,
	)
	threads.append(t_audio)

	# Mic monitor
	t_mic = threading.Thread(target=monitor_mic, args=(voice_event, stop_event), daemon=True)
	threads.append(t_mic)

	for t in threads:
		t.start()

	try:
		# メインは voice_event が立つのを待つ
		while not voice_event.is_set():
			time.sleep(0.2)
	except KeyboardInterrupt:
		print('ユーザーによる中断。終了します。')
		voice_event.set()

	# 音声検出または中断による終了処理
	# まず内部プレイヤに停止を通知
	stop_event.set()

	# 外部プレイヤ（vlc.exe）を強制終了
	if external_players:
		print(f'[VLC-FALLBACK] terminating {len(external_players)} external player(s)')
		for p in list(external_players):
			try:
				# terminate -> wait -> kill if necessary
				p.terminate()
				p.wait(timeout=1.0)
			except Exception:
				try:
					p.kill()
				except Exception:
					pass

	# 少し待ってスレッドが停止するのを待つ
	for t in threads:
		t.join(timeout=1.0)

	if voice_event.is_set() or stop_event.is_set():
		actual_application()


if __name__ == '__main__':
	main()

