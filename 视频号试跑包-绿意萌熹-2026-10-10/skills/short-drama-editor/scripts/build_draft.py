"""Export a drama edit plan part into a Jianying (CapCut) draft folder."""

import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from time import time
from typing import Any

APP_PROFILES: dict[str, dict[str, Any]] = {
    "jianying": {
        "app_id": 3704,
        "app_source": "lv",
        "app_version": "5.9.0",
        "display_name": "剪映专业版",
        "draft_root": Path.home() / "AppData" / "Local" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
    },
    "capcut": {
        "app_id": 359289,
        "app_source": "cc",
        "app_version": "6.4.0",
        "display_name": "CapCut",
        "draft_root": Path.home() / "AppData" / "Local" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
    },
}


def norm_path(p: str | Path) -> str:
    return str(Path(p).resolve()).replace("\\", "/")


def probe_media(video_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=index,codec_type,width,height",
         "-of", "json", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def pick_video_stream(info: dict) -> dict | None:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


def seconds_to_us(value: float) -> int:
    return int(round(float(value) * 1_000_000))


def new_uuid() -> str:
    return str(uuid.uuid4()).upper()


def build_video_material(video_path: Path, info: dict) -> dict:
    stream = pick_video_stream(info) or {}
    duration_s = float(info.get("format", {}).get("duration", 0))
    return {
        "audio_fade": None,
        "cartoon_path": "",
        "category_id": "",
        "category_name": "",
        "check_flag": 63487,
        "crop": {
            "upper_left_x": 0, "upper_left_y": 0,
            "upper_right_x": 1, "upper_right_y": 0,
            "lower_left_x": 0, "lower_left_y": 1,
            "lower_right_x": 1, "lower_right_y": 1,
        },
        "crop_ratio": "free",
        "crop_scale": 1,
        "duration": seconds_to_us(duration_s),
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": True,
        "has_sound_separated": False,
        "height": int(stream.get("height", 0) or 0),
        "id": new_uuid(),
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "local_id": "",
        "local_material_from": "",
        "local_material_id": "",
        "material_id": "",
        "material_name": video_path.name,
        "material_url": "",
        "matting": {
            "custom_matting_id": "", "enable_matting_stroke": False,
            "expansion": 0, "feather": 0, "flag": 0,
            "has_use_quick_brush": False, "has_use_quick_eraser": False,
            "interactiveTime": [], "path": "", "reverse": False, "strokes": [],
        },
        "media_path": "",
        "multi_camera_info": None,
        "object_locked": None,
        "origin_material_id": "",
        "path": norm_path(video_path),
        "source_platform": 0,
        "team_id": "",
        "type": "video",
        "video_algorithm": {"algorithms": []},
        "width": int(stream.get("width", 0) or 0),
    }


def build_speed_material() -> dict:
    return {
        "curve_speed": None,
        "id": new_uuid(),
        "mode": 0,
        "speed": 1.0,
        "type": "speed",
    }


def build_video_segment(seg: dict, material_id: str, render_index: int, speed_id: str) -> dict:
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0,
            "scale": {"x": 1, "y": 1},
            "transform": {"x": 0, "y": 0},
        },
        "common_keyframes": [],
        "enable_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_hsl": False,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "enable_video_mask": True,
        "extra_material_refs": [speed_id],
        "group_id": "",
        "hdr_settings": {"intensity": 1, "mode": 1, "nits": 1000},
        "id": new_uuid(),
        "intensifies_audio": False,
        "is_loop": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "keyframe_refs": [],
        "last_nonzero_volume": seg["audio_volume"],
        "lyric_keyframes": None,
        "material_id": material_id,
        "raw_segment_id": "",
        "render_index": render_index,
        "render_timerange": {"duration": 0, "start": 0},
        "responsive_layout": {
            "enable": False, "horizontal_pos_layout": 0,
            "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0,
        },
        "reverse": False,
        "source": "segmentsourcenormal",
        "source_timerange": {"duration": seg["source_duration_us"], "start": seg["source_start_us"]},
        "speed": 1,
        "state": 0,
        "target_timerange": {"duration": seg["timeline_duration_us"], "start": seg["timeline_start_us"]},
        "template_id": "",
        "template_scene": "default",
        "track_attribute": 0,
        "track_render_index": render_index,
        "uniform_scale": {"on": True, "value": 1},
        "visible": True,
        "volume": seg["audio_volume"],
    }


def build_subtitle_material(text: str) -> dict:
    content_payload = {
        "styles": [{
            "fill": {
                "alpha": 1.0,
                "content": {
                    "render_type": "solid",
                    "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]},
                },
            },
            "range": [0, len(text.encode("utf-16-le")) // 2],
            "size": 8.0,
            "bold": False,
            "italic": False,
            "underline": False,
            "strokes": [{
                "content": {"solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}},
                "width": 0.08,
            }],
        }],
        "text": text,
    }
    return {
        "id": new_uuid(),
        "content": json.dumps(content_payload, ensure_ascii=False),
        "typesetting": 0,
        "alignment": 1,
        "letter_spacing": 0.0,
        "line_spacing": 0.02,
        "line_feed": 1,
        "line_max_width": 0.82,
        "force_apply_line_max_width": False,
        "check_flag": 15,
        "type": "subtitle",
        "global_alpha": 1.0,
    }


def build_subtitle_segment(cue: dict, material_id: str, render_index: int) -> dict:
    return {
        "enable_adjust": True,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "last_nonzero_volume": 1.0,
        "reverse": False,
        "track_attribute": 0,
        "track_render_index": render_index,
        "visible": True,
        "id": new_uuid(),
        "material_id": material_id,
        "target_timerange": {"duration": cue["duration_us"], "start": cue["start_us"]},
        "common_keyframes": [],
        "keyframe_refs": [],
        "source_timerange": None,
        "speed": 1,
        "volume": 1.0,
        "extra_material_refs": [],
        "is_tone_modify": False,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": -0.68},
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "hdr_settings": None,
        "render_index": 0,
    }


def build_draft_content(part: dict, generate_subtitles: bool, app_name: str) -> dict:
    profile = APP_PROFILES[app_name]
    materials_videos: list[dict] = []
    speed_materials: list[dict] = []
    track_segments: list[dict] = []

    # Deduplicate materials by video path
    video_material_cache: dict[str, str] = {}  # path -> material_id

    for render_index, seg in enumerate(part["segments"]):
        vpath = norm_path(seg["video_path"])
        if vpath not in video_material_cache:
            info = probe_media(Path(seg["video_path"]))
            mat = build_video_material(Path(seg["video_path"]), info)
            materials_videos.append(mat)
            video_material_cache[vpath] = mat["id"]
        else:
            info = probe_media(Path(seg["video_path"]))
            mat = build_video_material(Path(seg["video_path"]), info)
            materials_videos.append(mat)
            video_material_cache[vpath] = mat["id"]

        speed = build_speed_material()
        speed_materials.append(speed)
        track_segments.append(
            build_video_segment(seg, video_material_cache[vpath], render_index, speed["id"])
        )

    # Subtitle track
    materials_texts: list[dict] = []
    subtitle_segments: list[dict] = []
    if generate_subtitles and part.get("subtitles"):
        for idx, cue in enumerate(part["subtitles"]):
            text = str(cue.get("text", "")).strip()
            if not text:
                continue
            sub_mat = build_subtitle_material(text)
            materials_texts.append(sub_mat)
            # Build cue in the format SubtitleSegment expects
            subtitle_segments.append(
                build_subtitle_segment(
                    {"start_us": cue["start_us"], "duration_us": cue["duration_us"]},
                    sub_mat["id"], idx,
                )
            )

    duration_us = part.get("total_duration_us", 0)
    draft_id = new_uuid()

    tracks = [{
        "attribute": 0,
        "flag": 0,
        "id": new_uuid(),
        "is_default_name": True,
        "name": "",
        "segments": track_segments,
        "type": "video",
    }]

    if subtitle_segments:
        tracks.append({
            "attribute": 0,
            "flag": 0,
            "id": new_uuid(),
            "is_default_name": False,
            "name": "subtitles",
            "segments": subtitle_segments,
            "type": "text",
        })

    return {
        "canvas_config": {"width": 1080, "height": 1920, "ratio": "9:16"},
        "color_space": 0,
        "config": {
            "adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1,
            "export_range": None, "extract_audio_last_index": 1,
            "lyrics_recognition_id": "", "lyrics_sync": True, "lyrics_taskinfo": [],
            "maintrack_adsorb": True, "material_save_mode": 0,
            "multi_language_current": "none", "multi_language_list": [],
            "multi_language_main": "none", "multi_language_mode": "none",
            "original_sound_last_index": 1, "record_audio_last_index": 1,
            "sticker_max_index": 1, "subtitle_keywords_config": None,
            "subtitle_recognition_id": "", "subtitle_sync": True,
            "subtitle_taskinfo": [], "system_font_list": [],
            "use_float_render": False, "video_mute": False, "zoom_info_params": None,
        },
        "cover": None,
        "create_time": 0,
        "duration": duration_us,
        "extra_info": None,
        "fps": 30,
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": draft_id,
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [], "audios": [], "effects": [], "filters": [],
            "handwrites": [], "stickers": [], "texts": [], "videos": [],
        },
        "last_modified_platform": {
            "app_id": profile["app_id"], "app_source": profile["app_source"],
            "app_version": profile["app_version"], "os": "windows",
        },
        "materials": {
            "ai_translates": [], "audio_balances": [], "audio_effects": [],
            "audio_fades": [], "audio_track_indexes": [], "audios": [],
            "beats": [], "canvases": [], "chromas": [], "color_curves": [],
            "digital_humans": [], "drafts": [], "effects": [], "flowers": [],
            "green_screens": [], "handwrites": [], "hsl": [], "images": [],
            "log_color_wheels": [], "loudnesses": [], "manual_deformations": [],
            "masks": [], "material_animations": [], "material_colors": [],
            "multi_language_refs": [], "placeholders": [], "plugin_effects": [],
            "primary_color_wheels": [], "realtime_denoises": [], "shapes": [],
            "smart_crops": [], "smart_relights": [], "sound_channel_mappings": [],
            "speeds": speed_materials, "stickers": [], "tail_leaders": [],
            "text_templates": [], "texts": materials_texts, "time_marks": [],
            "transitions": [], "video_effects": [], "video_trackings": [],
            "videos": materials_videos, "vocal_beautifys": [], "vocal_separations": [],
        },
        "mutable_config": None,
        "name": "",
        "new_version": "164.0.0",
        "platform": {
            "app_id": profile["app_id"], "app_source": profile["app_source"],
            "app_version": profile["app_version"], "os": "windows",
        },
        "relationships": [],
        "render_index_track_mode_on": False,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": tracks,
        "update_time": 0,
        "version": 360000,
    }


def build_draft_meta_info(draft_name: str, draft_root: Path, project_dir: Path, draft_id: str, duration_us: int, materials_size: int) -> dict:
    now_us = int(time() * 1_000_000)
    return {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": norm_path(project_dir / "draft_cover.jpg"),
        "draft_deeplink_url": "",
        "draft_enterprise_info": {
            "draft_enterprise_extra": "", "draft_enterprise_id": "",
            "draft_enterprise_name": "", "enterprise_material": [],
        },
        "draft_fold_path": norm_path(project_dir),
        "draft_id": draft_id,
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_materials": [
            {"type": 0, "value": []}, {"type": 1, "value": []},
            {"type": 2, "value": []}, {"type": 3, "value": []},
            {"type": 6, "value": []}, {"type": 7, "value": []},
            {"type": 8, "value": []},
        ],
        "draft_materials_copied_info": [],
        "draft_name": draft_name,
        "draft_need_rename_folder": False,
        "draft_new_version": "164.0.0",
        "draft_json_file": norm_path(project_dir / "draft_content.json"),
        "draft_removable_storage_device": "",
        "draft_root_path": norm_path(draft_root),
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size": materials_size,
        "draft_timeline_materials_size_": materials_size,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
    }


def main():
    parser = argparse.ArgumentParser(description="Export drama edit plan part to Jianying draft.")
    parser.add_argument("--work-dir", required=True, help="ASR work directory containing edit_plan.json.")
    parser.add_argument("--part-id", type=int, required=True, help="Which part to export (1-based).")
    parser.add_argument("--app-target", choices=["jianying", "capcut"], default="jianying")
    parser.add_argument("--generate-subtitles", action="store_true", default=True,
                        help="Include ASR subtitle track (default: on).")
    parser.add_argument("--no-subtitles", dest="generate_subtitles", action="store_false",
                        help="Skip subtitle generation.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing draft folder.")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    plan_path = work_dir / "edit_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"edit_plan.json not found in {work_dir}")

    edit_plan = json.loads(plan_path.read_text(encoding="utf-8"))

    # Find the requested part
    target_part = None
    for p in edit_plan.get("parts", []):
        if p["part_id"] == args.part_id:
            target_part = p
            break
    if target_part is None:
        raise SystemExit(f"Part {args.part_id} not found in edit_plan.json")

    profile = APP_PROFILES[args.app_target]
    draft_root = profile["draft_root"]
    draft_root.mkdir(parents=True, exist_ok=True)

    # Sanitize draft name for filesystem
    draft_name = target_part.get("draft_name", f"Drama_Part{args.part_id}")
    # Remove chars that are problematic in folder names
    import re
    draft_name = re.sub(r'[<>:"/\\|?*]', '_', draft_name)
    draft_name = draft_name.strip()[:100]

    project_dir = draft_root / draft_name
    if project_dir.exists():
        if args.overwrite:
            shutil.rmtree(project_dir)
        else:
            # Append a number to avoid collision
            for n in range(1, 100):
                alt = draft_root / f"{draft_name}_{n}"
                if not alt.exists():
                    project_dir = alt
                    break
    project_dir.mkdir(parents=True, exist_ok=True)

    content = build_draft_content(target_part, args.generate_subtitles, args.app_target)
    draft_id = content["id"]
    duration_us = content["duration"]

    # Write draft_content.json AND draft_info.json (dual-file compatibility)
    content_path = project_dir / "draft_content.json"
    info_path = project_dir / "draft_info.json"
    content_json = json.dumps(content, ensure_ascii=False, indent=2)
    content_path.write_text(content_json, encoding="utf-8", newline="\n")
    info_path.write_text(content_json, encoding="utf-8", newline="\n")

    # Write draft_meta_info.json
    materials_size = len(content_json.encode("utf-8"))
    meta = build_draft_meta_info(draft_name, draft_root, project_dir, draft_id, duration_us, materials_size)
    meta_path = project_dir / "draft_meta_info.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    # Update root_meta_info.json so the draft appears in Jianying's project list
    root_meta_path = draft_root / "root_meta_info.json"
    if root_meta_path.exists():
        try:
            root_meta = json.loads(root_meta_path.read_text(encoding="utf-8"))
            if not isinstance(root_meta, dict):
                root_meta = {}
        except Exception:
            root_meta = {}
    else:
        root_meta = {}

    all_drafts = root_meta.get("all_draft_store", [])
    if not isinstance(all_drafts, list):
        all_drafts = []
    filtered = [d for d in all_drafts if isinstance(d, dict) and d.get("draft_fold_path") != meta["draft_fold_path"]]
    filtered.append(meta)
    root_meta["all_draft_store"] = filtered
    root_meta["draft_ids"] = len(filtered)
    root_meta_path.write_text(json.dumps(root_meta, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print(f"Draft exported: {project_dir}")
    print(f"  Name: {draft_name}")
    print(f"  Duration: {duration_us / 1_000_000:.1f}s")
    print(f"  Segments: {len(target_part.get('segments', []))}")
    subs = len(target_part.get("subtitles", []))
    if args.generate_subtitles and subs:
        print(f"  Subtitles: {subs} cues")


if __name__ == "__main__":
    main()
