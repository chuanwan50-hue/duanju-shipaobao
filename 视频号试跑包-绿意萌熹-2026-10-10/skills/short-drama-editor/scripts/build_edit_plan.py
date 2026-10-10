"""Convert AI story analysis into a precise microsecond-level edit plan."""

import argparse
import json
import re
from pathlib import Path


def seconds_to_us(value: float) -> int:
    return int(round(float(value) * 1_000_000))


def normalize_path(value: str) -> str:
    return str(Path(value).resolve())


def find_episode_by_number(episodes: list[dict], ep_num: int) -> dict | None:
    """Find an episode in merged_data by its episode number (1-based)."""
    for ep in episodes:
        if ep["index"] == ep_num:
            return ep
    return None


SNAP_TOLERANCE_S = 0.5  # Max distance to snap to an utterance boundary


def snap_boundary_to_utterance(ep: dict, target_s: float, snap_to: str) -> float:
    """Snap a target time to the nearest ASR utterance boundary.

    Args:
        ep: Episode dict with 'segments' list.
        target_s: Requested time in seconds.
        snap_to: 'start' to snap to utterance start, 'end' to snap to utterance end.

    Returns:
        Snapped time in seconds, or the original target_s if no utterance is within tolerance.
    """
    segments = ep.get("segments", [])
    if not segments:
        return target_s

    best_dist = SNAP_TOLERANCE_S
    best_s = target_s

    for seg in segments:
        boundary = float(seg.get(snap_to, target_s))
        dist = abs(boundary - target_s)
        if dist < best_dist:
            best_dist = dist
            best_s = boundary

    return best_s


def resolve_clip(episodes: list[dict], ep_num: int, start_s: float, end_s: float, role: str, label_prefix: str, order: int) -> dict | None:
    """Build a single segment entry, snapping boundaries to nearest ASR utterance edges."""
    ep = find_episode_by_number(episodes, ep_num)
    if ep is None:
        return None

    # Snap boundaries to ASR utterance edges so cuts never split a sentence
    snapped_start = snap_boundary_to_utterance(ep, start_s, "start")
    snapped_end = snap_boundary_to_utterance(ep, end_s, "end")

    start_us = seconds_to_us(snapped_start)
    end_us = seconds_to_us(snapped_end)
    duration_us = max(end_us - start_us, 1)

    return {
        "timeline_order": order,
        "role": role,
        "video_path": normalize_path(ep["video_path"]),
        "source_start_us": start_us,
        "source_duration_us": duration_us,
        "timeline_start_us": 0,  # filled later
        "timeline_duration_us": duration_us,
        "audio_volume": 1.0,
        "label": f"{label_prefix}{ep_num} [{snapped_start:.1f}s-{snapped_end:.1f}s]",
    }


def resolve_keep_ranges(episodes: list[dict], keep_ranges_by_episode: dict, start_order: int) -> list[dict]:
    """Convert AI keep_ranges into segment entries, preserving AI-specified order.

    The AI writes episodes in chronological story order (not numeric order),
    and ranges within each episode in chronological order. We preserve both.
    No sorting by episode number — that would break chronological flow.
    """
    segments = []
    order = start_order

    for ep_num_str, ranges in keep_ranges_by_episode.items():
        ep_num = int(ep_num_str)
        for r in ranges:
            seg = resolve_clip(
                episodes, ep_num,
                float(r["start_s"]), float(r["end_s"]),
                role="backbone",
                label_prefix=f"主干: {r.get('reason', '')} 第",
                order=order,
            )
            if seg:
                segments.append(seg)
                order += 1

    # Only sort within same episode to preserve AI's cross-episode ordering
    for i, s in enumerate(segments):
        s["timeline_order"] = start_order + i
    return segments


def build_part_edit_plan(part: dict, episodes: list[dict], merged_data: dict) -> dict:
    """Build the edit plan for one part."""
    segments = []
    order = 0

    # 1. Hook (always first)
    hook = part.get("hook", {})
    if hook:
        seg = resolve_clip(episodes, hook["episode"], hook["start_s"], hook["end_s"],
                           "hook", f"钩子: {hook.get('reason', '')} 第", order)
        if seg:
            segments.append(seg)
            order += 1

    # 2. Context clips (Part 2+ only, after hook)
    context_clips = part.get("context_clips", [])
    for clip in context_clips:
        seg = resolve_clip(episodes, clip["episode"], clip["start_s"], clip["end_s"],
                           "context", f"前情: {clip.get('purpose', '')} 第", order)
        if seg:
            segments.append(seg)
            order += 1

    # 3. Backbone (keep_ranges, sorted by episode)
    keep_ranges = part.get("keep_ranges_by_episode", {})
    backbone_segs = resolve_keep_ranges(episodes, keep_ranges, order)
    segments.extend(backbone_segs)
    order += len(backbone_segs)

    # 4. Ending (always last)
    ending = part.get("ending", {})
    if ending:
        seg = resolve_clip(episodes, ending["episode"], ending["start_s"], ending["end_s"],
                           "ending", f"悬念结尾: {ending.get('reason', '')} 第", order)
        if seg:
            segments.append(seg)
            order += 1

    # Calculate timeline positions (cumulative)
    timeline_cursor = 0
    for i, seg in enumerate(segments):
        seg["timeline_order"] = i
        seg["timeline_start_us"] = timeline_cursor
        timeline_cursor += seg["timeline_duration_us"]

    draft_name = f"{merged_data['drama_title']}_Part{part['part_id']}_{part.get('title', '')}"

    # Build subtitle entries from ASR word data
    subtitles = []
    for seg in segments:
        ep = find_episode_by_number(
            episodes,
            int(re.search(r'第(\d+)', seg["label"]).group(1))
            if re.search(r'第(\d+)', seg["label"]) else 0
        )
        if ep:
            source_start_s = seg["source_start_us"] / 1_000_000.0
            source_end_s = (seg["source_start_us"] + seg["source_duration_us"]) / 1_000_000.0
            for asr_seg in ep.get("segments", []):
                asr_start = float(asr_seg.get("start", 0))
                asr_end = float(asr_seg.get("end", 0))
                # Check overlap with source range
                if asr_end > source_start_s and asr_start < source_end_s:
                    # Map to timeline
                    offset_s = asr_start - source_start_s
                    tl_start_us = seg["timeline_start_us"] + seconds_to_us(max(offset_s, 0))
                    tl_duration_us = seconds_to_us(min(asr_end, source_end_s) - max(asr_start, source_start_s))
                    text = str(asr_seg.get("text", "")).strip()
                    if text and tl_duration_us > 0:
                        subtitles.append({
                            "text": text,
                            "start_us": tl_start_us,
                            "duration_us": tl_duration_us,
                            "words": asr_seg.get("words", []),
                        })

    return {
        "part_id": part["part_id"],
        "draft_name": draft_name,
        "canvas": {"width": 1080, "height": 1920, "ratio": "9:16", "fps": 30},
        "total_duration_us": timeline_cursor,
        "segments": segments,
        "subtitles": subtitles,
    }


def main():
    parser = argparse.ArgumentParser(description="Build precise edit plan from AI story analysis.")
    parser.add_argument("--work-dir", required=True, help="ASR work directory.")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)

    merged_path = work_dir / "merged_data.json"
    analysis_path = work_dir / "story_analysis.json"

    if not merged_path.exists():
        raise SystemExit(f"merged_data.json not found in {work_dir}")
    if not analysis_path.exists():
        raise SystemExit(f"story_analysis.json not found in {work_dir}")

    merged_data = json.loads(merged_path.read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    episodes = merged_data.get("episodes", [])
    parts = analysis.get("parts", [])

    part_plans = []
    for part in parts:
        plan = build_part_edit_plan(part, episodes, merged_data)
        part_plans.append(plan)
        print(f"Part {part['part_id']}: {len(plan['segments'])} segments, "
              f"{plan['total_duration_us'] / 1_000_000:.1f}s total")

    edit_plan = {"parts": part_plans}
    output_path = work_dir / "edit_plan.json"
    output_path.write_text(json.dumps(edit_plan, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"\nEdit plan written to {output_path}")


if __name__ == "__main__":
    main()
