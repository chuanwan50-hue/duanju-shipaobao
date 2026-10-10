# -*- coding: utf-8 -*-
"""把我们本机做好的转写，换成他三个 skill 要的格式（代替他调豆包转写那一步）。

在 Windows 测试电脑上跑（他的格式里要写原片的完整路径，所以必须在跑测试的那台电脑上生成）：
    python 我们加的脚本\\转写换成他的格式.py --原片 D:\\sdtest\\原片\\绿意萌熹 --转写 D:\\sdtest\\我们的转写\\绿意萌熹

读：
    原片文件夹里的每集视频（按文件名自然排序，和他的脚本一样）；
    转写文件夹里同名的 .srt（一句一条）和 .json（每个字的时间：tokens、timestamps）。
写：
    1. 每集视频旁边放一份同名 .srt：批量高光看到它就不调豆包（他的规划器 find_sidecar_srt）。
    2. <原片文件夹>_精剪\\asr_work\\：精剪、解说混剪要的东西，格式照他的 asr_transcribe.py：
         NNN_<集名>\\timeline_segments.json、transcript.txt
         batch_summary.json（status 都是 ok，他的 merge_transcripts.py 读它）
         _segments_compact.txt（全剧紧凑台词，解说混剪第 1 步要读；他的包里没有生成它的脚本）
只用 Python 自带的库；要用 ffprobe 量每集时长（环境变量 FFPROBE，或者 PATH 里的 ffprobe）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}
PUNCT = set("，。！？、；：,.!?;:…—-“”\"'‘’（）()《》【】[] ")


def natural_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def srt_time(s):
    h, m, rest = s.strip().split(":")
    sec, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms[:3].ljust(3, "0")) / 1000.0


def parse_srt(path):
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        arrow = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if arrow is None:
            continue
        a, b = lines[arrow].split("-->")
        text = "".join(lines[arrow + 1:]).strip()
        if text:
            cues.append((srt_time(a), srt_time(b), text))
    return cues


def probe_duration(video):
    ffprobe = os.environ.get("FFPROBE") or shutil.which("ffprobe")
    if not ffprobe:
        return None
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(video)], capture_output=True, text=True)
    try:
        return round(float(out.stdout.strip()), 6)
    except ValueError:
        return None


def is_punct(tok):
    return tok.strip() == "" or tok in PUNCT


def build_segments(cues, tokens, stamps):
    """每条字幕一段，标点并到前一个字上（和他的 normalize 一样）。
    字幕和逐字时间出自同一次转写，字的顺序一样：先按文字顺序一个字一个字对；
    这一集对不上（拼起来的文字不一样）就退回按时间分（落在交界上的字可能分到上一句）。"""
    chars = "".join(c for _, _, text in cues for c in text if not is_punct(c))
    toks = "".join(str(t) for t in tokens if not is_punct(str(t)))  # 英文、数字一个 token 可能有好几个字符
    if chars == toks:
        return build_by_text(cues, tokens, stamps), "按文字对"
    return build_by_time(cues, tokens, stamps), "按时间分"


def word_end(stamps, i, cue_end):
    nxt = stamps[i + 1] if i + 1 < len(stamps) else cue_end
    return round(max(stamps[i] + 0.05, min(nxt, cue_end)), 6)


def build_by_text(cues, tokens, stamps):
    segments, ti, n = [], 0, len(tokens)
    for idx, (st, et, text) in enumerate(cues):
        need = sum(1 for c in text if not is_punct(c))
        words, got = [], 0
        while ti < n and got < need:
            tok = str(tokens[ti])
            if is_punct(tok):
                if words:
                    words[-1]["word"] += tok
            else:
                words.append({"word": tok, "start": round(stamps[ti], 6), "end": word_end(stamps, ti, et), "confidence": None})
                got += len(tok)
            ti += 1
        while ti < n and is_punct(str(tokens[ti])):  # 这一句后面的标点
            if words:
                words[-1]["word"] += str(tokens[ti])
            ti += 1
        segments.append({"id": idx, "start": round(st, 6), "end": round(et, 6), "text": text, "words": words})
    return segments


def build_by_time(cues, tokens, stamps):
    segments = []
    ti = 0
    n = len(tokens)
    for idx, (st, et, text) in enumerate(cues):
        words = []
        while ti < n and stamps[ti] < st - 0.05:
            ti += 1
        while ti < n and stamps[ti] < et + 0.05:
            tok = str(tokens[ti])
            if tok.strip() == "" or tok in PUNCT:
                if words:
                    words[-1]["word"] += tok
            else:
                nxt = stamps[ti + 1] if ti + 1 < n else et
                words.append({"word": tok, "start": round(stamps[ti], 6),
                              "end": round(max(stamps[ti] + 0.05, min(nxt, et)), 6), "confidence": None})
            ti += 1
        segments.append({"id": idx, "start": round(st, 6), "end": round(et, 6), "text": text, "words": words})
    return segments


def main():
    ap = argparse.ArgumentParser(description="我们的转写 → 他三个 skill 的格式")
    ap.add_argument("--原片", dest="videos", required=True)
    ap.add_argument("--转写", dest="trans", required=True)
    ap.add_argument("--asr-work", dest="work", default="", help="默认 <原片文件夹>_精剪\\asr_work")
    args = ap.parse_args()

    vdir = Path(args.videos).resolve()
    tdir = Path(args.trans).resolve()
    work = Path(args.work).resolve() if args.work else vdir.parent / f"{vdir.name}_精剪" / "asr_work"
    videos = sorted([p for p in vdir.iterdir() if p.is_file() and p.suffix.lower() in EXTS], key=lambda p: natural_key(p.name))
    if not videos:
        sys.exit(f"原片文件夹里没有视频：{vdir}")
    missing = [v.stem for v in videos if not (tdir / f"{v.stem}.srt").exists() or not (tdir / f"{v.stem}.json").exists()]
    if missing:
        sys.exit("这几集在转写文件夹里找不到同名的 .srt 或 .json：" + "、".join(missing))

    work.mkdir(parents=True, exist_ok=True)
    rows, compact = [], []
    no_dur = []
    for idx, video in enumerate(videos, start=1):
        cues = parse_srt(tdir / f"{video.stem}.srt")
        tj = json.loads((tdir / f"{video.stem}.json").read_text(encoding="utf-8"))
        segments, mode = build_segments(cues, tj.get("tokens", []), [float(x) for x in tj.get("timestamps", [])])
        dur = probe_duration(video)
        if dur is None:
            no_dur.append(video.name)
            dur = segments[-1]["end"] if segments else 0.0
        text = "".join(s["text"] for s in segments)

        item = work / f"{idx:03d}_{video.stem}"
        item.mkdir(parents=True, exist_ok=True)
        (item / "timeline_segments.json").write_text(json.dumps(
            {"text": text, "segments": segments, "language": "zh", "duration": dur,
             "provider": "我们的本机转写（CapsWriter 切段），代替豆包"}, ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
        (item / "transcript.txt").write_text(text, encoding="utf-8", newline="\n")
        rows.append({"index": idx, "video": str(video), "item_dir": str(item), "status": "ok",
                     "http_status": 200, "message": "来自我们的本机转写，没调豆包"})

        shutil.copyfile(tdir / f"{video.stem}.srt", video.with_suffix(".srt"))

        compact.append(f"=== 第{idx}集 {video.name}（{dur:.1f} 秒）===")
        compact += [f"EP{idx:02d} {s['start']:.2f}-{s['end']:.2f} {s['text']}" for s in segments]
        nwords = sum(len(s["words"]) for s in segments)
        print(f"[{idx}/{len(videos)}] {video.name}：{len(segments)} 句、{nwords} 个字带时间（{mode}）、时长 {dur:.1f} 秒")

    (work / "batch_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (work / "_segments_compact.txt").write_text("\n".join(compact) + "\n", encoding="utf-8", newline="\n")
    print(f"\n完成：{len(rows)} 集。")
    print(f"精剪、解说用的 asr_work：{work}")
    print(f"批量高光用的字幕：已放在每集视频旁边（同名 .srt）")
    if no_dur:
        print("注意：没找到 ffprobe，这几集的时长按最后一句台词的结束时间算：" + "、".join(no_dur))


if __name__ == "__main__":
    main()
