# -*- coding: utf-8 -*-
"""与 desub_subtitles.py 同款检测/模糊(含自动锁定字幕带 + 去码乱飞), 只处理指定集号(并行分片)。
用法: python desub_eps.py <asr_work> <y0> <y1> <ep1,ep2,...> [white=225] [dark=70]"""
import json, sys, io
from pathlib import Path
from desub_subtitles import process_video   # 复用同一套核心, 避免两条路径不一致

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    WD = Path(sys.argv[1]); y0r = float(sys.argv[2]); y1r = float(sys.argv[3])
    EPS = [int(x) for x in sys.argv[4].split(",") if x.strip()]
    white = int(sys.argv[5]) if len(sys.argv) > 5 else 225
    dark = int(sys.argv[6]) if len(sys.argv) > 6 else 70
    merged = json.loads((WD/"merged_data.json").read_text(encoding="utf-8"))
    ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}
    blur_dir = WD.parent/"blurred"; blur_dir.mkdir(parents=True, exist_ok=True)
    for ep in EPS:
        vp = Path(ep_path[ep]); out = blur_dir/vp.name
        if out.exists():
            print("skip", vp.name); continue
        nf = process_video(vp, out, y0r, y1r, white, dark)
        print(f"desub {vp.name} frames={nf}")
    print("group done")

if __name__ == "__main__":
    main()
