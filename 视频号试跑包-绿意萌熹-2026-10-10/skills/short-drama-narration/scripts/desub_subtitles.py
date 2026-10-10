# -*- coding: utf-8 -*-
"""逐帧字幕检测 + 只对文字框做精准模糊(去硬字幕)。
彻底治「码乱飞」: 过去逐帧独立检测 + 最近3帧求并集, 会把背景里的亮字/招牌/
白车/黄背心当字幕糊掉, 且框逐帧抖动 → 满屏乱飞。本版三道闸:
  ① 逐集自动锁定字幕带: 先采样全片, 取「居中检测框」y中心主峰 = 真实字幕行,
     之后检测ROI只看这条带 ± 余量, 根本不扫人物区(无需手动探测换剧像素)。
  ② 水平居中约束 + 单框对称收敛: 短剧硬字幕一定居中, 偏心框=背景垃圾直接弃;
     每帧把带内居中候选合成「关于画面中线对称的一个框」, 干掉横向抖动。
  ③ 时间去抖: 连续≥2帧命中才开模糊 + 几何EMA平滑 + 命中消失后短暂保持,
     替代旧的「3帧并集」(那是乱飞的直接来源)。

用法:
  python desub_subtitles.py <asr_work目录> [y0=0.45] [y1=0.95] [white=225] [dark=70]
  y0/y1 = 字幕「搜索」带(占画面高比例), 自动锁定会在此范围内找真实带;
  无字幕/检测不到带的片段不糊。
产物: <asr_work父目录>/blurred/<原集名>.mp4 (已存在跳过)
换剧不必再手动量像素; 想确认锁定带是否正确, 看脚本打印的 "lock cy=.. half=.." 行。
"""
import cv2, numpy as np, json, glob, sys, io, collections
from pathlib import Path

CENTER_TOL = 0.14   # |框中心x - 0.5| 超过即判背景垃圾
BAND_MARGIN = 30    # 锁定带上下额外扫描余量(px)
EMA = 0.4           # 框几何平滑系数
ON_NEED = 2         # 最近3帧里命中≥此数才开模糊(去单帧误检)
HOLD = 3            # 命中消失后保持帧数(桥接字幕字间空隙, 防闪)

def detect_raw(frame, y_lo, y_hi, white, dark):
    """在 [y_lo, y_hi] 像素行内找「白字黑边」小框, 返回全帧坐标 (x,y,bw,bh)。"""
    h, w = frame.shape[:2]
    y_lo = max(0, y_lo); y_hi = min(h, y_hi)
    if y_hi - y_lo < 8:
        return []
    x0, x1 = int(w*0.05), int(w*0.95)
    roi = frame[y_lo:y_hi, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    wht = (gray >= white).astype(np.uint8)*255
    drk = (gray <= dark).astype(np.uint8)*255
    drk_d = cv2.dilate(drk, np.ones((7, 7), np.uint8))
    text = cv2.bitwise_and(wht, drk_d)
    text = cv2.morphologyEx(text, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (45, 11)))
    cnts, _ = cv2.findContours(text, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w*0.10 or bh < 14 or bw/bh < 1.8:
            continue
        boxes.append((x0+x, y_lo+y, bw, bh))
    return boxes

def lock_band(cap, W, H, N, y0r, y1r, white, dark):
    """采样全片, 取居中检测框 y中心主峰作为字幕带。返回 (cy_px, half_px) 或 None。"""
    sy0, sy1 = int(H*y0r), int(H*y1r)
    step = max(1, N // 600)
    cys = []; bhs = []
    fi = 0
    while True:
        if not cap.grab():
            break
        if fi % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                for (x, y, bw, bh) in detect_raw(fr, sy0, sy1, white, dark):
                    cx = (x + bw/2) / W
                    if abs(cx - 0.5) <= CENTER_TOL:
                        cys.append(y + bh/2); bhs.append(bh)
        fi += 1
    cap.release()
    if len(cys) < 12:
        return None
    cys = np.array(cys); bhs = np.array(bhs)
    # 8px 一桶取主峰
    binw = 8
    hist = collections.Counter((cys // binw).astype(int))
    peak_bin, peak_cnt = hist.most_common(1)[0]
    if peak_cnt < max(8, len(cys) * 0.18):
        return None
    center = (peak_bin + 0.5) * binw
    near = bhs[np.abs(cys - center) <= 3 * binw]
    typ_h = float(np.percentile(near, 80)) if len(near) else 40.0
    half = max(typ_h / 2 + 14, 26)        # 覆盖单/双行字幕 + 余量
    return float(center), float(half)

def consolidate(boxes, W, cy_px, half_px):
    """带内+居中候选 → 关于画面中线对称的一个框 (cx, top, w, h); 无则 None。"""
    cxf = W / 2.0
    keep = []
    for (x, y, bw, bh) in boxes:
        cy = y + bh/2
        if abs(cy - cy_px) > half_px + 8:
            continue
        if abs((x + bw/2) - cxf) / W > CENTER_TOL:
            continue
        keep.append((x, y, bw, bh))
    if not keep:
        return None
    left = min(b[0] for b in keep)
    right = max(b[0] + b[2] for b in keep)
    top = min(b[1] for b in keep)
    bot = max(b[1] + b[3] for b in keep)
    half_w = max(cxf - left, right - cxf)          # 对称化, 杜绝横向抖动
    return cxf, top, half_w, (bot - top)

def blur_sym(frame, cxf, top, half_w, h, padx=16, pady=10):
    H, W = frame.shape[:2]
    x0 = max(0, int(cxf - half_w - padx)); x1 = min(W, int(cxf + half_w + padx))
    y0 = max(0, int(top - pady)); y1 = min(H, int(top + h + pady))
    if x1 <= x0 or y1 <= y0:
        return
    reg = frame[y0:y1, x0:x1]
    h0, w0 = reg.shape[:2]
    # 马赛克: 强下采样再最近邻放大 → 彻底打散文字笔画(只糊残影读不出原字)
    sw = max(1, w0 // 16); sh = max(1, h0 // 6)
    reg = cv2.resize(cv2.resize(reg, (sw, sh), interpolation=cv2.INTER_LINEAR),
                     (w0, h0), interpolation=cv2.INTER_NEAREST)
    k = max(15, (min(h0, w0) // 2) | 1)
    reg = cv2.GaussianBlur(reg, (k, k), 0)        # 软化马赛克块边
    reg = cv2.convertScaleAbs(reg, alpha=0.62, beta=0)   # 更狠压暗, 残影成暗带
    frame[y0:y1, x0:x1] = reg

def process_video(vp, out, y0r, y1r, white, dark):
    cap = cv2.VideoCapture(str(vp))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    band = lock_band(cap, W, H, N, y0r, y1r, white, dark)   # 释放cap
    if band is None:
        cy_px, half_px = H * (y0r + y1r) / 2, H * (y1r - y0r) / 2  # 退化: 用整搜索带
        print(f"  [{vp.name}] 未锁定字幕带, 回退整带 cy={cy_px:.0f} half={half_px:.0f}")
    else:
        cy_px, half_px = band
        print(f"  [{vp.name}] lock cy={cy_px:.0f}({cy_px/H*100:.1f}%) half={half_px:.0f}")
    det_lo = int(cy_px - half_px - BAND_MARGIN); det_hi = int(cy_px + half_px + BAND_MARGIN)

    cap = cv2.VideoCapture(str(vp))
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    hits = collections.deque(maxlen=3)   # 最近3帧是否命中
    sm = None                            # 平滑后的 (cxf, top, half_w, h)
    hold = 0; nf = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        boxes = detect_raw(fr, det_lo, det_hi, white, dark)
        cur = consolidate(boxes, W, cy_px, half_px)
        hits.append(cur is not None)
        if cur is not None:
            if sm is None:
                sm = cur
            else:
                sm = tuple(EMA * c + (1 - EMA) * s for c, s in zip(cur, sm))
        on = sum(hits) >= ON_NEED
        if on:
            hold = HOLD
        elif hold > 0:
            hold -= 1
        if hold > 0 and sm is not None:
            blur_sym(fr, *sm)
        if cur is None and hold == 0:
            sm = None
        vw.write(fr); nf += 1
    cap.release(); vw.release()
    return nf

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    WD = Path(sys.argv[1])
    y0r = float(sys.argv[2]) if len(sys.argv) > 2 else 0.45
    y1r = float(sys.argv[3]) if len(sys.argv) > 3 else 0.95
    white = int(sys.argv[4]) if len(sys.argv) > 4 else 225
    dark = int(sys.argv[5]) if len(sys.argv) > 5 else 70
    merged = json.loads((WD/"merged_data.json").read_text(encoding="utf-8"))
    ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}
    eps = set()
    for jf in glob.glob(str(WD/"narration"/"sl*.json")):
        spec = json.loads(Path(jf).read_text(encoding="utf-8"))
        for s in spec.get("shots", []):
            eps.add(int(s["pic"]["episode"]))
    eps = sorted(eps)
    blur_dir = WD.parent/"blurred"; blur_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for ep in eps:
        vp = Path(ep_path[ep]); out = blur_dir/vp.name
        if out.exists():
            print("skip", vp.name); continue
        nf = process_video(vp, out, y0r, y1r, white, dark)
        print(f"desub {vp.name} frames={nf}"); done += 1
    print(f"done {done}/{len(eps)} -> {blur_dir}")

if __name__ == "__main__":
    main()
