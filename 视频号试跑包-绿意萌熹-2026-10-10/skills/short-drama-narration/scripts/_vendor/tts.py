"""
豆包 TTS 2.0 SSE 调用。
输入：纯文本 + 草稿名
输出：narration.mp3 + narration.json（含逐字时间戳）

用法：
  python tts.py <文案.txt> <草稿名>
"""
import os
import sys
import json
import uuid
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    TTS_API_KEY, TTS_URL, TTS_RESOURCE, TTS_DEFAULT_SPEAKER,
    STORYBOARD_ROOT
)


def synthesize(text: str, out_mp3: str, out_json: str,
               speaker: str = TTS_DEFAULT_SPEAKER,
               speed_ratio: float = 1.0) -> dict:
    """调豆包 TTS 2.0 SSE，返回 {duration_ms, words: [...]}"""
    headers = {
        "X-Api-Key": TTS_API_KEY,
        "X-Api-Resource-Id": TTS_RESOURCE,
        "Content-Type": "application/json",
    }
    payload = {
        "user": {"uid": str(uuid.uuid4())},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": int((speed_ratio - 1.0) * 100),  # -50 ~ 50
                "enable_subtitle": True,
            },
        },
    }

    audio_bytes = bytearray()
    words = []
    duration_ms = 0

    with requests.post(TTS_URL, headers=headers, json=payload, stream=True, timeout=120) as r:
        r.raise_for_status()
        # 关键：用字节模式读，自己按 UTF-8 解码，避免 requests 用 latin-1 误解码
        for raw_line in r.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                evt = json.loads(data)
            except json.JSONDecodeError:
                continue

            # 音频块
            audio_b64 = evt.get("data") or evt.get("audio")
            if audio_b64:
                import base64
                try:
                    audio_bytes.extend(base64.b64decode(audio_b64))
                except Exception:
                    pass

            # 字幕事件（豆包 TTS 2.0 SSE 真实结构: sentence.words[] 时间单位为秒）
            sent = evt.get("sentence")
            if isinstance(sent, dict):
                ws = sent.get("words") or []
                for w in ws:
                    if not isinstance(w, dict):
                        continue
                    txt = w.get("word") or w.get("text") or ""
                    st = w.get("startTime", w.get("start_time", 0))
                    et = w.get("endTime", w.get("end_time", st))
                    # 秒 -> 毫秒
                    if isinstance(st, (int, float)) and st < 100:
                        st_ms = int(round(float(st) * 1000))
                        et_ms = int(round(float(et) * 1000))
                    else:
                        st_ms, et_ms = int(st), int(et)
                    words.append({"text": txt, "startTime": st_ms, "endTime": et_ms})
                    duration_ms = max(duration_ms, et_ms)

            # 兼容旧 subtitle.words 路径
            sub = evt.get("subtitle") or evt.get("subtitles")
            if isinstance(sub, dict):
                ws = sub.get("words") or []
                for w in ws:
                    if not isinstance(w, dict):
                        continue
                    txt = w.get("word") or w.get("text") or ""
                    st = w.get("startTime", w.get("start_time", 0))
                    et = w.get("endTime", w.get("end_time", st))
                    if isinstance(st, (int, float)) and st < 100:
                        st_ms = int(round(float(st) * 1000))
                        et_ms = int(round(float(et) * 1000))
                    else:
                        st_ms, et_ms = int(st), int(et)
                    words.append({"text": txt, "startTime": st_ms, "endTime": et_ms})
                    duration_ms = max(duration_ms, et_ms)

    if not audio_bytes:
        raise RuntimeError("TTS 未返回任何音频数据")

    os.makedirs(os.path.dirname(out_mp3), exist_ok=True)
    with open(out_mp3, "wb") as f:
        f.write(audio_bytes)

    # 用 ffprobe 取真实音频时长（覆盖 words 算出的 duration，因为末尾通常有静音 padding）
    probed = _probe_duration_ms(out_mp3)
    if probed > 0:
        duration_ms = max(duration_ms, probed)

    meta = {
        "text": text,
        "speaker": speaker,
        "duration_ms": duration_ms,
        "duration_sec": round(duration_ms / 1000.0, 3),
        "words": words,
        "audio_path": out_mp3,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


def _probe_duration_ms(mp3_path: str) -> int:
    import subprocess
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return int(float(out) * 1000)
    except Exception:
        return 0


def main():
    if len(sys.argv) < 3:
        print("用法: python tts.py <文案.txt> <草稿名> [--speaker <音色>]")
        sys.exit(1)

    txt_path = sys.argv[1]
    draft_name = sys.argv[2]
    speaker = TTS_DEFAULT_SPEAKER
    if "--speaker" in sys.argv:
        i = sys.argv.index("--speaker")
        speaker = sys.argv[i + 1]

    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("文案为空")
        sys.exit(1)

    work_dir = os.path.join(STORYBOARD_ROOT, draft_name)
    os.makedirs(work_dir, exist_ok=True)

    out_mp3 = os.path.join(work_dir, "narration.mp3")
    out_json = os.path.join(work_dir, "narration.json")

    print(f"[TTS] 文案字数: {len(text)}")
    print(f"[TTS] 音色: {speaker}")
    meta = synthesize(text, out_mp3, out_json, speaker=speaker)
    print(f"[TTS] 时长: {meta['duration_sec']}s，字幕点: {len(meta['words'])}")
    print(f"[TTS] 音频: {out_mp3}")
    print(f"[TTS] 元数据: {out_json}")


if __name__ == "__main__":
    main()
