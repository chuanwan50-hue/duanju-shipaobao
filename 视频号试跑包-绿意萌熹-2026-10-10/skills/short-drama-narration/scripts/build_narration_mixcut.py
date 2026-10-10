"""
纯解说快剪草稿生成器(第三人称解说混剪)。
每个 shot = 一个原片画面(静音) + 一句解说音频 + 逐句短字幕(按标点拆短句、逐句弹出+向上滑动入场),画面逐句快切。

用法:
  python build_narration_mixcut.py <asr_work目录> <manifest.json路径> <剪映草稿名> [BGM路径]

设计约定(本版,2026-06 改造规格):
- 无调色/氛围特效(暗角/电影感/颗粒已移除)。
- 引流钩子「点击左下角  观看全集」底部居中、全程显示。
- BGM 铺底(默认 0.30,响而不压解说);解说音量提升到「飙黄不飙红」(默认 1.4)。
- 顶部合规声明全程。
"""
import os, re, sys, json, time, uuid, shutil
from pathlib import Path

WD = Path(sys.argv[1])
MANIFEST = Path(sys.argv[2])
DRAFT_NAME = sys.argv[3]
BGM_PATH = sys.argv[4] if len(sys.argv) > 4 else r"E:\背景音乐和音效素材库\音频\背景音乐\by_type\伤感\伤感_005_136.13s.mp3"
GLOBAL_SPEED = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0   # 整体变速(1.0=不变;1.1=全片快10%,音调不变。注:抖音版此参为 arg6,因其 arg5=is_ai)

# 可调音量(飙黄不飙红:解说响而不爆,BGM 压得很低)
NARRATION_VOLUME = 1.4
BGM_VOLUME = 0.30
BGM_SWELL = 0.48   # 情绪峰值处 BGM 推顶(shot 标 "bgm_swell":true 触发;默认无标记=全程 0.30 不变)
# 画面变速(>1 画面更紧凑,显示时长仍=解说,不改时间轴)与放大(轻微裁边)
VIDEO_SPEED = 1.15
VIDEO_SCALE = 1.07

# 剪映草稿库(pyJianYingDraft): 优先本 skill 内置的 _vendor, 再兼容旧的 product-hook-mixcut 位置
_here = os.path.dirname(os.path.abspath(__file__))
_pjy_cand = [os.path.join(_here, "_vendor"),
             os.path.join(_here, "..", "..", "product-hook-mixcut", "scripts", "_vendor")]
PYJYDRAFT_SRC = next((p for p in _pjy_cand if os.path.isdir(p)), _pjy_cand[0])
JIANYING_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
DRAFT_MAPPING_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "JianyingPro", "User Data", "Config", "LocalDraftFolder", "draft_folder_mappings.json")
CANVAS_W, CANVAS_H = 1080, 1920
CTA_TEXT = "点击左下角  观看全集"

# 文字位置(transform_y: +1顶 / 0中 / -1底)
SUBTITLE_TY = -0.50   # 解说词压在原片字幕位置上(源字幕中心≈0.73高,叠1.07放大后≈-0.50)
CTA_TY = -0.80        # 引流钩子(底部,给剧名让位)
TITLE_TY = -0.91      # 《剧名》在 CTA 正下方
TITLE_SIZE = 8.5      # 剧名字号与解说一致
# 剧名:取草稿名 "剧名_SLx_角度" 的第一段
DRAMA_NAME = DRAFT_NAME.split("_")[0]

sys.path.insert(0, PYJYDRAFT_SRC)
import pyJianYingDraft as draft
US = 1_000_000
def us(s): return int(round(float(s) * US))

merged = json.loads((WD / "merged_data.json").read_text(encoding="utf-8"))
ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}
shots = json.loads(MANIFEST.read_text(encoding="utf-8"))["shots"]

# 解说字幕逐镜落到该镜原字幕中心(tag_subcy.py 写入 shot['sub_cy_frac']=占高比例);无则回退 SUBTITLE_TY
def subtitle_ty_for_shot(sh):
    frac = sh.get("sub_cy_frac")
    if frac is None and sh.get("sub_cy"):
        frac = float(sh["sub_cy"]) / CANVAS_H
    if frac is None:
        return SUBTITLE_TY
    canvas_cy = frac * CANVAS_H
    zy = (CANVAS_H/2) + (canvas_cy - CANVAS_H/2) * VIDEO_SCALE
    return round(-(zy - CANVAS_H/2) / (CANVAS_H/2), 4)

safe = re.sub(r'[\\/:*?"<>|]', "_", DRAFT_NAME)
old_dir = os.path.join(JIANYING_DIR, safe)
if os.path.exists(old_dir):
    try: shutil.rmtree(old_dir)
    except Exception as e: print("rmtree warn:", e)

folder = draft.DraftFolder(JIANYING_DIR)
script = folder.create_draft(safe, CANVAS_W, CANVAS_H, allow_replace=True)
script.add_track(draft.TrackType.video, "画面")
script.add_track(draft.TrackType.audio, "解说")
# 文本轨各给递增 relative_index,使 render_index 错开(15001/2/3/4),否则剪映里 4 条文本同层、单独调整会全堆一块
script.add_track(draft.TrackType.text, "字幕", relative_index=1)
script.add_track(draft.TrackType.text, "引导", relative_index=2)
script.add_track(draft.TrackType.text, "剧名", relative_index=3)
script.add_track(draft.TrackType.audio, "BGM")
script.add_track(draft.TrackType.text, "声明", relative_index=4)

def text_seg(text, start_us, dur_us, ty=-0.45, tx=0.0, size=8.5, color=(1.0, 1.0, 1.0)):
    return draft.TextSegment(
        text, draft.Timerange(start_us, dur_us),
        font=draft.FontType.新青年体,
        style=draft.TextStyle(size=size, bold=True, color=color, align=1,
                              auto_wrapping=True, max_line_width=0.82),
        border=draft.TextBorder(color=(0.0, 0.0, 0.0), width=45.0),
        clip_settings=draft.ClipSettings(transform_x=tx, transform_y=ty))

# 解说字幕逐句短句化:按标点把一句拆成短句, 逐句弹出, 长句不再一屏放不下被切
def split_phrases(text, min_chars=6):
    raw = re.split(r'(?<=[？！?!])|[，。、；：…,.]+|—{2,}|\s+', text)
    raw = [p.strip(" 　,.，。、；：…—") for p in raw if p and p.strip(" 　,.，。、；：…—")]
    out = []
    for p in raw:
        if out and (len(out[-1]) < min_chars or len(p) < 3):
            out[-1] += p
        else:
            out.append(p)
    return out or [text.strip()]

SUB_ANIM = draft.TextIntro.向上滑动   # 解说字幕逐句入场动画

vmat_cache = {}
cursor = 0
trans = False
swell_windows = []   # 收集标了 bgm_swell 的镜头时间窗(用于 BGM 推顶关键帧)
for sh in shots:
    amat = draft.AudioMaterial(sh["audio_path"])
    dur = amat.duration
    tdur = max(1, round(dur / GLOBAL_SPEED))   # 整体变速:时间轴时长=音频/S(解说按S加速,音调不变)
    if sh.get("bgm_swell"):
        swell_windows.append((cursor, tdur))
    ep = int(sh["pic"]["episode"]); start_us = us(sh["pic"]["start_s"])
    vp = ep_path[ep]
    _blur = WD.parent / "blurred" / Path(vp).name
    if _blur.exists():
        vp = str(_blur)
    if vp not in vmat_cache:
        vmat_cache[vp] = draft.VideoMaterial(vp)
    mat = vmat_cache[vp]
    avail = max(1, mat.duration - start_us)
    # 画面变速:source 取 dur*VIDEO_SPEED(footage 不够则裁到可用),随整体变速一并加速
    src = min(max(1, round(dur * VIDEO_SPEED)), avail)
    vseg = draft.VideoSegment(mat, draft.Timerange(cursor, tdur),
                              source_timerange=draft.Timerange(start_us, src), volume=0.0,
                              clip_settings=draft.ClipSettings(scale_x=VIDEO_SCALE, scale_y=VIDEO_SCALE))
    if trans:
        try: vseg.add_transition(draft.TransitionType.叠化, duration=200000)
        except Exception: pass
    script.add_segment(vseg, "画面")
    trans = True
    script.add_segment(draft.AudioSegment(amat, draft.Timerange(cursor, tdur),
                       source_timerange=draft.Timerange(0, dur), volume=NARRATION_VOLUME), "解说")
    # 解说字幕:拆短句逐句显示(短句弹出+向上滑动入场;依字数分配每句时长)
    _ty = subtitle_ty_for_shot(sh)
    _phr = split_phrases(sh["text"])
    _tot = sum(len(p) for p in _phr) or 1
    _acc = 0
    for _i, _p in enumerate(_phr):
        _d = (tdur - _acc) if _i == len(_phr) - 1 else max(1, round(tdur * len(_p) / _tot))
        _seg = text_seg(_p, cursor + _acc, _d, ty=_ty, size=8.0)
        # 不加入场动画:逐句字幕静态出现, 始终精确压住原字幕位(滑入动画会在移动中瞬间露出原字幕)
        script.add_segment(_seg, "字幕")
        _acc += _d
    cursor += tdur

# 引流钩子:底部居中 + 全程显示
script.add_segment(text_seg(CTA_TEXT, 0, cursor,
                            ty=CTA_TY, tx=0.0, size=6.5, color=(1.0, 0.88, 0.3)), "引导")
# 剧名:CTA 正下方,字号与解说一致,全程
script.add_segment(text_seg(f"《{DRAMA_NAME}》", 0, cursor,
                            ty=TITLE_TY, tx=0.0, size=TITLE_SIZE, color=(1.0, 1.0, 1.0)), "剧名")

# 背景音乐(低音量,不压解说)
_bgm = draft.AudioMaterial(BGM_PATH)
_bgm_dur = min(cursor, _bgm.duration)
_bgm_seg = draft.AudioSegment(_bgm, draft.Timerange(0, cursor),
                   source_timerange=draft.Timerange(0, _bgm_dur), volume=BGM_VOLUME)
if swell_windows:
    # 情绪峰值处 BGM 推顶:峰值前 0.3s 起涨→峰值内保持 BGM_SWELL→峰值后 0.3s 回落 0.30
    _bgm_seg.add_keyframe(0, BGM_VOLUME)
    for (ws, wd) in swell_windows:
        pre = max(1, ws - 300000); pin = ws + 200000
        pout = max(pin + 1, ws + wd - 200000); post = ws + wd + 300000
        _bgm_seg.add_keyframe(pre, BGM_VOLUME)
        _bgm_seg.add_keyframe(pin, BGM_SWELL)
        _bgm_seg.add_keyframe(pout, BGM_SWELL)
        _bgm_seg.add_keyframe(min(cursor - 1, post), BGM_VOLUME)
    _bgm_seg.add_keyframe(max(1, cursor - 1), BGM_VOLUME)
script.add_segment(_bgm_seg, "BGM")

# 顶部合规声明(全程):字号放大到清晰可见(原 4.5 太小,平台仍强制加 AI 标注)
script.add_segment(text_seg("本视频由AI生成  仅供娱乐  无不良引导", 0, cursor,
                            ty=0.86, tx=0.0, size=6.5, color=(1.0, 1.0, 1.0)), "声明")

script.save()
out_path = os.path.join(JIANYING_DIR, safe)

# 修复文本联动:vendor 把 auto_wrapping 文本标成 type="subtitle",剪映按"字幕同步"把多条文本当一批联动(动一个→4条全堆画面中间)。
# 改回 "text" + 关 subtitle_sync,让各文本独立可调。auto_wrap 由 line_max_width 字段保留,不受影响。
_dc = os.path.join(out_path, "draft_content.json")
if os.path.exists(_dc):
    _d = json.loads(Path(_dc).read_text(encoding="utf-8"))
    for _m in _d.get("materials", {}).get("texts", []):
        if _m.get("type") == "subtitle":
            _m["type"] = "text"
    _d.setdefault("config", {})["subtitle_sync"] = False
    Path(_dc).write_text(json.dumps(_d, ensure_ascii=False), encoding="utf-8")

# fix meta + register
meta_path = os.path.join(out_path, "draft_meta_info.json")
draft_id = None
if os.path.exists(meta_path):
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    now = int(time.time() * US); draft_id = str(uuid.uuid4()).upper()
    meta.update({"draft_id": draft_id, "draft_fold_path": out_path.replace("\\", "/"),
                 "draft_root_path": JIANYING_DIR.replace("/", "\\"), "draft_name": safe,
                 "tm_draft_create": now, "tm_draft_modified": now,
                 "draft_json_file": os.path.join(out_path, "draft_content.json").replace("\\", "/")})
    Path(meta_path).write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")
registered = False
if draft_id and os.path.exists(DRAFT_MAPPING_PATH):
    from datetime import datetime
    j = json.loads(Path(DRAFT_MAPPING_PATH).read_text(encoding="utf-8"))
    if not isinstance(j.get("mappings"), list): j["mappings"] = []
    j["mappings"] = [m for m in j["mappings"] if isinstance(m, dict) and m.get("draftId") != draft_id]
    j["mappings"].append({"draftId": draft_id, "folderId": "", "mappedTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
    j["timestamp"] = int(time.time() * 1000)
    Path(DRAFT_MAPPING_PATH).write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    registered = True

print(f"draft: {out_path}")
print(f"total: {cursor/US:.1f}s | shots: {len(shots)} | narration_vol: {NARRATION_VOLUME} | bgm_vol: {BGM_VOLUME} | registered: {registered}")
