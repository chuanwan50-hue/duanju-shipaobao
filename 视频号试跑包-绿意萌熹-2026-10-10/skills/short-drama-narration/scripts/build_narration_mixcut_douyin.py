"""
抖音版 纯解说快剪草稿生成器(基于视频号版改造)。
与视频号版区别:
- 顶部 AI 标注(AI剧) / 右上角竖排「剧情演绎 无不良引导」(真人剧)
- 剧名《剧名》加在 AI 标注下面(顶部)
- 引流 CTA「点击左下角观看全集」**竖排**,放左侧中下,末字「集」对齐抖音评论按钮高度
- 解说字幕 ty 适配 1080×1920 原片(SUBTITLE_TY=-0.63)

用法:
  python build_narration_mixcut_douyin.py <asr_work> <manifest.json> <草稿名> <BGM路径> [is_ai=1/0]
"""
import os, re, sys, json, time, uuid, shutil
from pathlib import Path

WD = Path(sys.argv[1])
MANIFEST = Path(sys.argv[2])
DRAFT_NAME = sys.argv[3]
BGM_PATH = sys.argv[4] if len(sys.argv) > 4 else r"E:\背景音乐和音效素材库\音频\背景音乐\by_type\伤感\伤感_005_136.13s.mp3"
IS_AI = (len(sys.argv) <= 5) or (str(sys.argv[5]).strip() not in ("0", "real", "false", "no"))
GLOBAL_SPEED = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0   # 整体变速(1.0=不变;1.1=全片快10%,音调不变)
MUSE_TOP = sys.argv[7] if len(sys.argv) > 7 else ""   # 暮色版式:传第一人称话题→顶部全程话题 banner+底字幕,无CTA/无声明/无剧名(对标暮色解说)

NARRATION_VOLUME = 1.4
BGM_VOLUME = 0.30
BGM_SWELL = 0.48   # 情绪峰值处 BGM 推顶(shot 标 "bgm_swell":true 触发;默认无标记=全程 0.30 不变)
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

# 文字位置(transform_y: +1顶 / 0中 / -1底;transform_x: -1左 / +1右)
SUBTITLE_TY = -0.24   # 解说词压在原片字幕位(此剧原字幕逐场在 y≈1045-1300 大范围跳,单条 blur 1040-1315 全覆盖,解说压其中心)
DECL_TY = 0.90        # 顶部 AI 声明
TITLE_TY = 0.82       # 剧名《》在 AI 声明正下方
# 竖排 CTA(贴左侧边缘、中下,末字「集」对齐抖音评论按钮)
CTA_TX = -0.82
CTA_TY = -0.14
CTA_SIZE = 6.0
# 真人剧 右上角竖排声明(贴右侧边缘,别跑到画面中间;对称于左侧CTA -0.82)
REAL_DECL_TX = 0.85
REAL_DECL_TY = 0.55

DRAMA_NAME = DRAFT_NAME.split("_")[0]
CTA_TEXT_V = "点击左下角观看全集"   # 竖排不用空格

sys.path.insert(0, PYJYDRAFT_SRC)
import pyJianYingDraft as draft
US = 1_000_000
def us(s): return int(round(float(s) * US))

merged = json.loads((WD / "merged_data.json").read_text(encoding="utf-8"))
ep_path = {e["index"]: e["video_path"] for e in merged["episodes"]}
shots = json.loads(MANIFEST.read_text(encoding="utf-8"))["shots"]

# 解说字幕逐镜落到该镜原字幕中心(tag_subcy.py 写入 shot['sub_cy_frac']=占高比例;兼容旧 sub_cy绝对px)
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

def text_seg(text, start_us, dur_us, ty=-0.45, tx=0.0, size=8.5, color=(1.0, 1.0, 1.0), vertical=False):
    return draft.TextSegment(
        text, draft.Timerange(start_us, dur_us),
        font=draft.FontType.新青年体,
        style=draft.TextStyle(size=size, bold=True, color=color, align=1,
                              auto_wrapping=True, max_line_width=0.82, vertical=vertical),
        border=draft.TextBorder(color=(0.0, 0.0, 0.0), width=45.0),
        clip_settings=draft.ClipSettings(transform_x=tx, transform_y=ty))

def split_phrases(text, min_chars=6):
    """把一句解说按标点拆成短句(逐句显示用):丢弃 ，。、；：…—— 等分隔标点,? !留在句末;过短的并入前句"""
    raw = re.split(r'(?<=[？！?!])|[，。、；：…,.]+|—{2,}|\s+', text)
    raw = [p.strip(" 　,.，。、；：…—") for p in raw if p and p.strip(" 　,.，。、；：…—")]
    out = []
    for p in raw:
        if out and (len(out[-1]) < min_chars or len(p) < 3):
            out[-1] += p
        else:
            out.append(p)
    return out or [text.strip()]

SUB_ANIM = draft.TextIntro.向上滑动   # 解说字幕逐句入场动画(想换:渐显/向上弹入/居中打字 等)

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
    src = min(max(1, round(dur * VIDEO_SPEED)), avail)   # 画面随之按 VIDEO_SPEED×S 加速
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
    # 解说字幕:拆短句逐句显示(每句短、依字数分配时长、带入场动画;长句不再一屏放不下被切)
    _ty = subtitle_ty_for_shot(sh)
    _phr = split_phrases(sh["text"])
    _tot = sum(len(p) for p in _phr) or 1
    _acc = 0
    for _i, _p in enumerate(_phr):
        _d = (tdur - _acc) if _i == len(_phr) - 1 else max(1, round(tdur * len(_p) / _tot))
        _seg = text_seg(_p, cursor + _acc, _d, ty=_ty, size=8.0)
        try: _seg.add_animation(SUB_ANIM, duration=min(300000, max(1, _d // 2)))
        except Exception: pass
        script.add_segment(_seg, "字幕")
        _acc += _d
    cursor += tdur

if MUSE_TOP:
    # 暮色版式:仅顶部居中第一人称话题(全程),无 CTA/无声明/无剧名(合规靠发布时勾平台 AI 标签)
    _t = MUSE_TOP if MUSE_TOP.startswith("《") else f"《{MUSE_TOP}》"
    script.add_segment(text_seg(_t, 0, cursor,
                                ty=0.90, tx=0.0, size=5.0, color=(0.92, 0.92, 0.92)), "剧名")
else:
    # 引流钩子:竖排,左中下,末字「集」对齐评论按钮
    script.add_segment(text_seg(CTA_TEXT_V, 0, cursor,
                                ty=CTA_TY, tx=CTA_TX, size=CTA_SIZE, color=(1.0, 0.88, 0.3), vertical=True), "引导")
    if IS_AI:
        # AI 剧:顶部 AI 声明 + 剧名在其正下方
        script.add_segment(text_seg("本视频由AI生成  仅供娱乐  无不良引导", 0, cursor,
                                    ty=DECL_TY, tx=0.0, size=6.5, color=(1.0, 1.0, 1.0)), "声明")
        script.add_segment(text_seg(f"《{DRAMA_NAME}》", 0, cursor,
                                    ty=TITLE_TY, tx=0.0, size=7.0, color=(1.0, 1.0, 1.0)), "剧名")
    else:
        # 真人剧:右上角竖排「剧情演绎 无不良引导」+ 剧名在其下
        script.add_segment(text_seg("剧情演绎  无不良引导", 0, cursor,
                                    ty=REAL_DECL_TY, tx=REAL_DECL_TX, size=6.0, color=(1.0, 1.0, 1.0), vertical=True), "声明")
        script.add_segment(text_seg(f"《{DRAMA_NAME}》", 0, cursor,
                                    ty=DECL_TY, tx=0.0, size=7.0, color=(1.0, 1.0, 1.0)), "剧名")

# 背景音乐
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
print(f"total: {cursor/US:.1f}s | shots: {len(shots)} | platform: {'AI' if IS_AI else '真人'} | narration_vol: {NARRATION_VOLUME} | bgm_vol: {BGM_VOLUME} | registered: {registered}")
