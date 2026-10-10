# -*- coding: utf-8 -*-
"""逐句配音（千问 qwen3-tts-flash 版），代替他的 scripts/tts_shots.py（那个只认豆包）。

产出和他的一模一样，后面 tag_subcy、insert_hook、build、render 都不用改：
    tts_<stem>/shot_NN.mp3
    <stem>_manifest.json   （{"voice_type", "speed_ratio", "shots": [{...原句字段, "idx", "audio_path", "duration_ms"}]}）

用法：
    python tts_shots_qwen.py <narration.json>              整条配
    python tts_shots_qwen.py <narration.json> --试一句      只配第一句，看能不能通（产物放 tts_<stem>_试一句\\，不写清单）
    python tts_shots_qwen.py <narration.json> --音色 Ryan   换音色（默认取 narration.json 的 voice_type；那里写的是豆包音色就用 Ethan）

要：
    环境变量 DASHSCOPE_API_KEY（阿里云百炼北京地域的 key；万川用 setx 设，别写进文件、别打印出来）；
    ffmpeg、ffprobe（环境变量 FFMPEG、FFPROBE，或者 PATH 里有）。
和他原版的两处不同（试跑记录里要写上）：
    1. 千问接口没有语速参数：先按正常语速合成，再用 ffmpeg atempo 加到 speed_ratio（默认 1.2），音调不变；
    2. 音色是千问的（默认 Ethan 晨煦，男声标准普通话），和他的豆包音色不一样。
接口照官方文档：https://help.aliyun.com/zh/model-studio/qwen-tts-api （一次最多 600 字，返回的音频地址 24 小时内有效）。
已经配好、文字没变的句子会跳过，断了重跑接着配。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
MODEL = "qwen3-tts-flash"
DEFAULT_VOICE = "Ethan"


def tool(name):
    p = os.environ.get(name.upper()) or shutil.which(name)
    if not p:
        sys.exit(f"找不到 {name}：把 ffmpeg 的 bin 文件夹加进 PATH，或设环境变量 {name.upper()}")
    return p


def synth(text, voice, key):
    body = json.dumps({"model": MODEL, "input": {"text": text, "voice": voice, "language_type": "Chinese"}},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    last = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read().decode("utf-8"))
            audio = (resp.get("output") or {}).get("audio") or {}
            if not audio.get("url"):
                raise RuntimeError(f"返回里没有音频地址：code={resp.get('code')} message={resp.get('message')}")
            with urllib.request.urlopen(audio["url"], timeout=120) as r:
                wav = r.read()
            chars = int(((resp.get("usage") or {}).get("characters")) or len(text))
            return wav, chars
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = RuntimeError(f"HTTP {e.code}：{detail}")
            if e.code in (400, 401, 403):
                break  # key 不对、音色不对、文字超长：重试也没用
        except Exception as e:
            last = e
        time.sleep(attempt * 2)
    raise last


def to_mp3(wav_path, mp3_path, speed, ffmpeg):
    af = f"atempo={speed}" if abs(speed - 1.0) > 1e-6 else "anull"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(wav_path), "-filter:a", af,
                    "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-q:a", "2", str(mp3_path)], check=True)


def duration_ms(path, ffprobe):
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return int(round(float(out.stdout.strip()) * 1000))


def main():
    ap = argparse.ArgumentParser(description="逐句配音（千问版）")
    ap.add_argument("narration")
    ap.add_argument("--音色", dest="voice", default="")
    ap.add_argument("--试一句", dest="one", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        sys.exit("没有环境变量 DASHSCOPE_API_KEY：请万川在 PowerShell 里跑 setx DASHSCOPE_API_KEY \"他的key\"，再重开千问")
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")

    narr = Path(args.narration).resolve()
    spec = json.loads(narr.read_text(encoding="utf-8"))
    voice = args.voice or str(spec.get("voice_type") or "")
    if not voice or voice.startswith(("zh_", "BV", "en_")):  # 豆包音色的样子
        voice = DEFAULT_VOICE
    speed = float(spec.get("speed_ratio") or 1.2)
    shots = spec["shots"][:1] if args.one else spec["shots"]
    for i, sh in enumerate(shots):
        if len(sh["text"]) > 600:
            sys.exit(f"第 {i} 句超过 600 字，千问一次合成不了，先把这句拆短")

    shot_dir = narr.parent / (f"tts_{narr.stem}_试一句" if args.one else f"tts_{narr.stem}")
    shot_dir.mkdir(parents=True, exist_ok=True)
    out, total_ms, total_chars, skipped = [], 0, 0, 0
    print(f"千问 {MODEL}，音色 {voice}，合成后加速 {speed} 倍（音调不变），共 {len(shots)} 句")
    for i, sh in enumerate(shots):
        mp3 = shot_dir / f"shot_{i:02d}.mp3"
        txt = shot_dir / f"shot_{i:02d}.txt"
        if mp3.exists() and txt.exists() and txt.read_text(encoding="utf-8") == f"{voice}|{speed}|{sh['text']}":
            skipped += 1
        else:
            wav_bytes, chars = synth(sh["text"], voice, key)
            total_chars += chars
            wav = shot_dir / f"shot_{i:02d}.wav"
            wav.write_bytes(wav_bytes)
            to_mp3(wav, mp3, speed, ffmpeg)
            wav.unlink()
            txt.write_text(f"{voice}|{speed}|{sh['text']}", encoding="utf-8")
        dur = duration_ms(mp3, ffprobe)
        out.append({**sh, "idx": i, "audio_path": str(mp3), "duration_ms": dur})
        total_ms += dur
        print(f"{i:02d} {dur/1000:5.2f}s  {sh['text'][:22]}")

    if args.one:
        print(f"\n试一句通了：{out[0]['audio_path']}（{out[0]['duration_ms']/1000:.2f} 秒）。听一下没问题，再去掉 --试一句 整条配。")
        print(f"这次用了 {total_chars} 个字符（qwen3-tts-flash 约 0.8 元/万字符，以控制台账单为准）")
        return
    manifest = narr.parent / f"{narr.stem}_manifest.json"
    manifest.write_text(json.dumps({"voice_type": voice, "speed_ratio": speed, "tts": f"千问 {MODEL}",
                                    "shots": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTOTAL {total_ms/1000:.1f}s | {len(out)} shots | manifest -> {manifest}")
    print(f"这次新合成用了 {total_chars} 个字符（跳过已配好的 {skipped} 句）；qwen3-tts-flash 约 0.8 元/万字符，以控制台账单为准")


if __name__ == "__main__":
    main()
