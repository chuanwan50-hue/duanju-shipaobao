"""
质量检查:同一故事线内「连着出现相同画面」检测。
对每个 narration json(或 manifest),判断相邻两 shot 是否会显示同一段画面:
  - 完全相同的 (episode, start_s)  -> 重复
  - 同 episode 且源时间窗重叠         -> 重叠(会出现相同帧)
源时间窗 = [start_s, start_s + 显示时长*VIDEO_SPEED];显示时长优先用 manifest 的 duration_ms,
没有就用估算 5.0s。

用法:
  python validate_shots.py <narration目录> [VIDEO_SPEED]
"""
import json, sys, glob
from pathlib import Path

nd = Path(sys.argv[1])
SPEED = float(sys.argv[2]) if len(sys.argv) > 2 else 1.15
EST = 5.0

def win(sh):
    dur = sh.get("duration_ms")
    d = (dur / 1000.0) if dur else EST
    s = float(sh["pic"]["start_s"])
    return s, s + d * SPEED

bad_total = 0
# 优先看 *_manifest.json(带真实时长),否则看 sl*.json
files = sorted(glob.glob(str(nd / "*_manifest.json"))) or sorted(glob.glob(str(nd / "sl*.json")))
for f in files:
    spec = json.loads(Path(f).read_text(encoding="utf-8"))
    shots = spec.get("shots", [])
    name = Path(f).stem
    viol = []
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        ea, eb = int(a["pic"]["episode"]), int(b["pic"]["episode"])
        sa = float(a["pic"]["start_s"]); sb = float(b["pic"]["start_s"])
        if ea != eb:
            continue
        if abs(sa - sb) < 0.05:
            viol.append((i, "重复", f"ep{ea} {sa}"))
            continue
        (a0, a1), (b0, b1) = win(a), win(b)
        if a0 < b1 and b0 < a1:
            viol.append((i, "重叠", f"ep{ea} [{a0:.1f}-{a1:.1f}] x [{b0:.1f}-{b1:.1f}]"))
    if viol:
        bad_total += len(viol)
        print(f"[{name}] {len(viol)} 处:")
        for i, kind, info in viol:
            print(f"   shot{i}->shot{i+1}  {kind}  {info}")
    else:
        print(f"[{name}] OK 无连续相同画面")
print(f"\n合计违规: {bad_total}")
