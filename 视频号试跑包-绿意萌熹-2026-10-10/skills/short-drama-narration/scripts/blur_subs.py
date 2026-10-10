"""
对解说用到的集做字幕区局部模糊(烧进视频),输出 <asr_work父目录>/blurred/。
扫描 narration 目录下所有 *.json 收集引用到的 episode,union 后逐集处理,已存在跳过。

用法:
  python blur_subs.py <asr_work目录> <原片全集目录> [字幕区y] [字幕区高h] [crop宽w]

字幕区坐标需按目标剧像素量过再传(不同剧/分辨率不通用)。
默认 y=1795 h=155 w=1440 是「母亲的沉默」量出来的值。
"""
import json, subprocess, sys, glob
from pathlib import Path

wd = Path(sys.argv[1])                       # asr_work
src_dir = Path(sys.argv[2])                  # 原片全集目录
Y = int(sys.argv[3]) if len(sys.argv) > 3 else 1795
H = int(sys.argv[4]) if len(sys.argv) > 4 else 155
W = int(sys.argv[5]) if len(sys.argv) > 5 else 1440

# 收集 narration 目录下所有 json 引用的 episode
eps = set()
for jf in glob.glob(str(wd / "narration" / "*.json")):
    try:
        spec = json.loads(Path(jf).read_text(encoding="utf-8"))
    except Exception:
        continue
    for s in spec.get("shots", []):
        if isinstance(s, dict) and "pic" in s and "episode" in s["pic"]:
            eps.add(int(s["pic"]["episode"]))
eps = sorted(eps)

blur_dir = wd.parent / "blurred"
blur_dir.mkdir(parents=True, exist_ok=True)
flt = f"[0]split[a][b];[b]crop={W}:{H}:0:{Y},boxblur=28:3,eq=brightness=-0.15[bl];[a][bl]overlay=0:{Y}"

# 兼容两种命名:精确匹配 "* - 第{ep}集.mp4" 或含 "第{ep}集"
def find_src(ep):
    cands = list(src_dir.glob(f"*第{ep}集*.mp4"))
    return cands[0] if cands else None

done = 0
for ep in eps:
    src = find_src(ep)
    if not src:
        print("missing src ep", ep); continue
    out = blur_dir / src.name
    if out.exists():
        print("skip ep", ep); continue
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-filter_complex", flt, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-c:a", "copy", "-y", str(out)], check=True)
    print("blurred ep", ep); done += 1
print(f"done: {done} new / {len(eps)} referenced -> {blur_dir}")
