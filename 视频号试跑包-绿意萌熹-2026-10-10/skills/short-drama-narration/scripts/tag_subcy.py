"""为每条 manifest 的每个 shot 检测原字幕中心(占画面高比例 sub_cy_frac),写回 manifest。
build 据此让解说字幕逐镜精确压在原字幕位置(分辨率无关)。
在 desub 之前对**原片**跑;若该镜检不到字幕则不写(build 回退默认 SUBTITLE_TY)。

用法:
  python tag_subcy.py <asr_work目录> [y0=0.45] [y1=0.95] [white=225] [dark=70]
"""
import cv2, numpy as np, json, glob, sys, statistics
from pathlib import Path

WD = Path(sys.argv[1])
Y0R = float(sys.argv[2]) if len(sys.argv) > 2 else 0.45
Y1R = float(sys.argv[3]) if len(sys.argv) > 3 else 0.95
WHITE = int(sys.argv[4]) if len(sys.argv) > 4 else 225
DARK = int(sys.argv[5]) if len(sys.argv) > 5 else 70
VIDEO_SPEED = 1.15

merged = json.loads((WD/"merged_data.json").read_text(encoding="utf-8"))
ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}

def detect_cy_frac(frame):
    h, w = frame.shape[:2]
    y0, y1 = int(h*Y0R), int(h*Y1R); x0, x1 = int(w*0.05), int(w*0.95)
    roi = frame[y0:y1, x0:x1]; gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    white = (gray >= WHITE).astype(np.uint8)*255
    dark = (gray <= DARK).astype(np.uint8)*255
    dark_d = cv2.dilate(dark, np.ones((7, 7), np.uint8))
    text = cv2.bitwise_and(white, dark_d)
    text = cv2.morphologyEx(text, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (45, 11)))
    cnts, _ = cv2.findContours(text, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None; area = 0
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w*0.10 or bh < 14 or bw/bh < 1.8:
            continue
        if bw*bh > area:
            area = bw*bh; best = (y0+y, bh)
    return (best[0]+best[1]/2.0)/h if best else None

caps = {}
def cap(p):
    if p not in caps:
        caps[p] = cv2.VideoCapture(p)
    return caps[p]

for mp in sorted(glob.glob(str(WD/"narration"/"sl*_manifest.json"))):
    d = json.loads(Path(mp).read_text(encoding="utf-8"))
    fr_list = []
    for sh in d["shots"]:
        ep = int(sh["pic"]["episode"]); start = float(sh["pic"]["start_s"])
        dur = sh.get("duration_ms", 0)/1000.0; src = max(1.0, dur*VIDEO_SPEED)
        c = cap(ep_path[ep]); fracs = []
        t = start
        while t < start+src:
            c.set(cv2.CAP_PROP_POS_MSEC, t*1000); ok, im = c.read()
            if ok:
                f = detect_cy_frac(im)
                if f:
                    fracs.append(f)
            t += 0.3
        if fracs:
            sh["sub_cy_frac"] = round(statistics.median(fracs), 4)
        fr_list.append(sh.get("sub_cy_frac"))
    Path(mp).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(Path(mp).stem, fr_list)
for c in caps.values():
    c.release()
print("done")
