# -*- coding: utf-8 -*-
"""不经剪映,直接用 ffmpeg 把短剧解说 manifest 渲染成成品 MP4。
复刻 build_narration_mixcut_douyin.py 的版面:画面1.07放大+1.15加速+静音、解说1.4音量、
BGM 0.30、逐句字幕(向上滑入)落在原字幕位、竖排CTA(左中下)、真人声明竖排(右上)、剧名(顶部居中)。
说明:为保音画严丝合缝,镜头间用硬切(不做剪映里的200ms叠化);BGM用恒定0.30(不做swell推顶)。

用法: python render_narration_mp4.py <manifest.json> <剧名> <输出mp4> <merged_data所在asr_work> [is_ai=0/1] [bgm]
"""
import os, re, sys, json, subprocess, tempfile, shutil
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or r"C:\Users\Win10\ffmpeg\ffmpeg.exe"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or r"C:\Users\Win10\ffmpeg\ffprobe.exe"

MANIFEST = Path(sys.argv[1])
DRAMA = sys.argv[2]
OUT = Path(sys.argv[3])
WD = Path(sys.argv[4])                          # asr_work (含 merged_data.json, ../blurred)
IS_AI = len(sys.argv) > 5 and str(sys.argv[5]).strip() not in ("0", "real", "false", "no")
BGM = sys.argv[6] if len(sys.argv) > 6 else r"E:\背景音乐和音效素材库\音频\背景音乐\by_type\伤感\伤感_005_136.13s.mp3"

CANVAS_W, CANVAS_H = 1080, 1920
VIDEO_SPEED = 1.15
VIDEO_SCALE = 1.07
NARR_VOL = 1.4
BGM_VOL = 0.30
BGM_SWELL = 0.48          # bgm_swell 镜头处 BGM 推顶峰值
XF = 0.2                  # 镜头间叠化(crossfade)时长 s
FONT = "Microsoft YaHei"

merged = json.loads((WD / "merged_data.json").read_text(encoding="utf-8"))
ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}
shots = json.loads(MANIFEST.read_text(encoding="utf-8"))["shots"]


def run(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg失败({desc}): {(r.stderr or '')[-400:]}")
    return r


def dur_s(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def split_phrases(text, min_chars=6):
    raw = re.split(r'(?<=[？！?!])|[，。、；：…,.]+|—{2,}|\s+', text)
    raw = [p.strip(" 　,.，。、；：…—") for p in raw if p and p.strip(" 　,.，。、；：…—")]
    out = []
    for p in raw:
        if out and (len(out[-1]) < min_chars or len(p) < 3): out[-1] += p
        else: out.append(p)
    return out or [text.strip()]


def sub_cy_px(sh):
    """解说字幕在最终(1.07放大后)画面里的竖直中心px(复刻 subtitle_ty_for_shot)。"""
    frac = sh.get("sub_cy_frac")
    if frac is None and sh.get("sub_cy"): frac = float(sh["sub_cy"]) / CANVAS_H
    if frac is None: frac = 0.79
    canvas_cy = frac * CANVAS_H
    return (CANVAS_H / 2) + (canvas_cy - CANVAS_H / 2) * VIDEO_SCALE


def ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(t):
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "")


def vertical(t):
    """竖排:逐字换行(去标点空格)。"""
    chars = [c for c in t if c.strip() and c not in "，。、；：…,. "]
    return "\\N".join(chars)


TMP = Path(tempfile.mkdtemp(prefix="narr_"))
print(f"临时目录 {TMP}")
try:
    # ---- 1. 逐镜出标准化静音视频片段(每镜多渲 XF 真实内容,留给叠化重叠用) ----
    durs = []
    clip_files = []
    swell_windows = []     # (起s, 止s) 标了 bgm_swell 的镜头时间窗
    cum = 0.0
    for i, sh in enumerate(shots):
        D = dur_s(sh["audio_path"])
        durs.append(D)
        if sh.get("bgm_swell"): swell_windows.append((cum, cum + D))
        cum += D
        ep = int(sh["pic"]["episode"]); start = float(sh["pic"]["start_s"])
        vp = ep_path[ep]
        blur = WD.parent / "blurred" / Path(vp).name
        if blur.exists(): vp = str(blur)
        cf = TMP / f"v{i:02d}.mp4"
        clip_len = D + XF                       # 多 XF 秒供 xfade 重叠,转场偏移正好落原硬切点→零漂移
        span = clip_len * VIDEO_SPEED + 0.3
        vf = (f"scale=ceil(iw*{VIDEO_SCALE}/2)*2:ceil(ih*{VIDEO_SCALE}/2)*2,"
              f"crop={CANVAS_W}:{CANVAS_H},setpts=PTS/{VIDEO_SPEED},fps=30,"
              f"tpad=stop_mode=clone:stop_duration=2,format=yuv420p,setsar=1")
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}",
             "-t", f"{span:.3f}", "-i", vp, "-an", "-vf", vf, "-t", f"{clip_len:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30", str(cf)],
            f"shot{i}")
        clip_files.append(cf)
        print(f"  镜{i:02d} ep{ep}@{start:.1f}s  {D:.2f}s{'  [BGM推顶]' if sh.get('bgm_swell') else ''}")

    total = sum(durs)

    # ---- 2. 叠化拼接(xfade链:每段转场偏移=原硬切累计,解说音轨不交叉故无漂移) ----
    silent = TMP / "silent.mp4"
    vin = []
    for c in clip_files: vin += ["-i", str(c)]
    n = len(clip_files)
    if n == 1:
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip_files[0]),
             "-t", f"{total:.3f}", "-c", "copy", str(silent)], "video-1")
    else:
        parts = []; prev = "[0:v]"; off = durs[0]
        for i in range(1, n):
            out = "[vout]" if i == n - 1 else f"[vx{i}]"
            parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}{out}")
            prev = out; off += durs[i]
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *vin,
             "-filter_complex", ";".join(parts), "-map", "[vout]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
             "-pix_fmt", "yuv420p", str(silent)], "xfade")

    # ---- 3. 解说音轨拼接(volume 1.4) + BGM(0.30)混音 ----
    ain = []
    for sh in shots: ain += ["-i", sh["audio_path"]]
    n = len(shots)
    fc = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[narr]"
    narr = TMP / "narr.wav"
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *ain,
         "-filter_complex", fc, "-map", "[narr]", str(narr)], "narr-concat")
    mixed = TMP / "mixed.m4a"
    if swell_windows:
        # 峰值镜头处 BGM 梯形推顶:前后各 0.3s 斜坡,峰内保持 BGM_SWELL
        terms = [f"clip(min((t-{s-0.3:.3f})/0.3,({e+0.3:.3f}-t)/0.3),0,1)" for (s, e) in swell_windows]
        m = terms[0]
        for tm in terms[1:]: m = f"max({m},{tm})"
        bgm_vol = f"volume='{BGM_VOL}+{BGM_SWELL-BGM_VOL:.3f}*({m})':eval=frame"
        print(f"  BGM 推顶窗口: {[(round(s,1),round(e,1)) for s,e in swell_windows]}")
    else:
        bgm_vol = f"volume={BGM_VOL}"
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(narr),
         "-stream_loop", "-1", "-i", BGM, "-filter_complex",
         f"[0:a]volume={NARR_VOL}[na];[1:a]{bgm_vol}[b];"
         f"[na][b]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "[a]", "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", str(mixed)], "mix")

    # ---- 4. 生成 ASS(字幕+CTA+声明+剧名) ----
    ass = TMP / "sub.ass"
    L = []
    L.append("[Script Info]")
    L.append("ScriptType: v4.00+")
    L.append(f"PlayResX: {CANVAS_W}")
    L.append(f"PlayResY: {CANVAS_H}")
    L.append("WrapStyle: 0")
    L.append("")
    L.append("[V4+ Styles]")
    L.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # 字幕白字黑边
    L.append(f"Style: Sub,{FONT},60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,1,5,0,0,0,1")
    L.append(f"Style: CTA,{FONT},46,&H004DE0FF,&H004DE0FF,&H00000000,&H64000000,1,0,0,0,100,100,2,0,1,3,1,5,0,0,0,1")
    L.append(f"Style: Decl,{FONT},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,2,0,1,3,1,5,0,0,0,1")
    L.append(f"Style: Title,{FONT},52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,1,5,0,0,0,1")
    L.append("")
    L.append("[Events]")
    L.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    # 4a 逐句字幕
    cursor = 0.0
    for sh, D in zip(shots, durs):
        cy = sub_cy_px(sh)
        phr = split_phrases(sh["text"])
        tot = sum(len(p) for p in phr) or 1
        acc = 0.0
        for j, p in enumerate(phr):
            d = (D - acc) if j == len(phr) - 1 else max(0.4, round(D * len(p) / tot, 3))
            st = cursor + acc; en = st + d
            move = f"\\move(540,{cy+25:.0f},540,{cy:.0f},0,250)\\fad(150,0)"
            L.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Sub,,0,0,0,,{{{move}}}{esc(p)}")
            acc += d
        cursor += D

    end = ass_time(total)
    # 4b 竖排导流CTA(左中下) x≈97 y≈1094
    L.append(f"Dialogue: 1,0:00:00.00,{end},CTA,,0,0,0,,{{\\pos(97,1094)}}{vertical('点击左下角观看全集')}")
    # 4c 声明 + 剧名
    if IS_AI:
        L.append(f"Dialogue: 1,0:00:00.00,{end},Title,,0,0,0,,{{\\pos(540,96)}}{esc('本视频由AI生成  仅供娱乐  无不良引导')}")
        L.append(f"Dialogue: 1,0:00:00.00,{end},Title,,0,0,0,,{{\\pos(540,170)}}《{esc(DRAMA)}》")
    else:
        # 真人剧:右上竖排声明 x≈999 y≈432 + 顶部居中剧名
        L.append(f"Dialogue: 1,0:00:00.00,{end},Decl,,0,0,0,,{{\\pos(999,432)}}{vertical('剧情演绎无不良引导')}")
        L.append(f"Dialogue: 1,0:00:00.00,{end},Title,,0,0,0,,{{\\pos(540,96)}}《{esc(DRAMA)}》")
    ass.write_text("\n".join(L), encoding="utf-8")

    # ---- 5. 烧字幕 + 合成 ----
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd(); os.chdir(TMP)
    try:
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i", str(mixed),
             "-vf", "ass=sub.ass", "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
             "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-b:a", "192k", "-shortest", str(OUT)], "burn")
    finally:
        os.chdir(cwd)
    print(f"\n✅ 完成: {OUT}  总时长 {total:.1f}s  镜头 {len(shots)}  平台 {'AI' if IS_AI else '真人'}")
    print(f"   大小 {OUT.stat().st_size/1e6:.1f}MB")
finally:
    shutil.rmtree(TMP, ignore_errors=True)
