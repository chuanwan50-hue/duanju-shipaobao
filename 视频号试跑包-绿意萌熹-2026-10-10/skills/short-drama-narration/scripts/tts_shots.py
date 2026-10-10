"""
逐句豆包 TTS。读一个 narration json(含 voice_type/speed_ratio/shots[{text,pic}]),
每句合成 mp3 + 写一份 manifest(带逐句真实时长)。

用法:
  python tts_shots.py <narration.json路径>
产出(与 narration.json 同目录):
  tts_<stem>/shot_NN.mp3
  <stem>_manifest.json
"""
import base64, json, sys, uuid, io, os
from pathlib import Path
from urllib.request import Request, urlopen

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
# 凭据从环境变量读取（火山引擎语音合成 TTS）；勿在此硬编码明文
APP_ID = os.environ.get("DOUBAO_APP_ID", ""); TOKEN = os.environ.get("DOUBAO_ACCESS_TOKEN", "")
if not APP_ID or not TOKEN:
    sys.exit("请先设置环境变量 DOUBAO_APP_ID 和 DOUBAO_ACCESS_TOKEN（火山引擎语音合成凭据）")
URL = "https://openspeech.bytedance.com/api/v1/tts"

NARR = Path(sys.argv[1])
spec = json.loads(NARR.read_text(encoding="utf-8"))
voice = spec["voice_type"]; speed = float(spec["speed_ratio"])
stem = NARR.stem
shot_dir = NARR.parent / f"tts_{stem}"; shot_dir.mkdir(parents=True, exist_ok=True)

def synth(text):
    payload = {"app": {"appid": APP_ID, "token": TOKEN, "cluster": "volcano_tts"},
               "user": {"uid": "drama-narr"},
               "audio": {"voice_type": voice, "encoding": "mp3", "rate": 24000,
                         "speed_ratio": speed, "volume_ratio": 1.0, "pitch_ratio": 1.0, "language": "cn"},
               "request": {"reqid": str(uuid.uuid4()), "text": text, "text_type": "plain", "operation": "query"}}
    req = Request(URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer;{TOKEN}"}, method="POST")
    with urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if int(resp.get("code", 0)) != 3000:
        raise RuntimeError(f"code={resp.get('code')} {resp.get('message')}")
    return base64.b64decode(resp["data"]), int(str((resp.get("addition") or {}).get("duration", "0")).strip() or 0)

out, total = [], 0
for i, sh in enumerate(spec["shots"]):
    audio, dur = synth(sh["text"])
    p = shot_dir / f"shot_{i:02d}.mp3"; p.write_bytes(audio)
    out.append({**sh, "idx": i, "audio_path": str(p), "duration_ms": dur})
    total += dur
    print(f"{i:02d} {dur/1000:4.2f}s  {sh['text'][:22]}")
manifest = NARR.parent / f"{stem}_manifest.json"
manifest.write_text(
    json.dumps({"voice_type": voice, "speed_ratio": speed, "shots": out}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nTOTAL {total/1000:.1f}s | {len(out)} shots | manifest -> {manifest}")
