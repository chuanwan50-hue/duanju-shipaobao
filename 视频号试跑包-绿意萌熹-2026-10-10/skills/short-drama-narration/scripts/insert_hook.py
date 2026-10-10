# -*- coding: utf-8 -*-
"""往 manifest 头部插一个'原声开场'shot(audio=原片抽出的原声,非TTS)。
用法: python insert_hook.py <manifest.json> <hook.mp3> <ep> <start_s> <dur_ms> <caption> [sub_cy_frac]
⚠️ <caption> **必须 = 原声实际说的那句台词(原声字幕)**,不要写编辑化的钩子句——否则字幕和原声对不上、出戏。
   这些原声台词本身就是钩子(打脸/狠话/尖叫),原样上字幕即可。
[sub_cy_frac] 钩子字幕的原字幕位(占高比例);**必须传该剧实测值**(tag_subcy 结果,如玉米地0.586/蛊镯0.683),不传默认 0.683。"""
import json, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
mp = Path(sys.argv[1]); hook = sys.argv[2]; ep = int(sys.argv[3])
start_s = float(sys.argv[4]); dur_ms = int(sys.argv[5]); caption = sys.argv[6]
sub_cy = float(sys.argv[7]) if len(sys.argv) > 7 else 0.683
d = json.loads(mp.read_text(encoding="utf-8"))
# 已插过就不重复
if d["shots"] and d["shots"][0].get("is_hook"):
    print("already has hook, skip"); sys.exit(0)
hook_shot = {
    "text": caption,
    "pic": {"episode": ep, "start_s": start_s},
    "idx": 0,
    "audio_path": hook,
    "duration_ms": dur_ms,
    "sub_cy_frac": sub_cy,
    "is_hook": True,
}
d["shots"].insert(0, hook_shot)
for i, sh in enumerate(d["shots"]):
    sh["idx"] = i
mp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
print(f"inserted hook -> {mp.name}, total shots={len(d['shots'])}")
