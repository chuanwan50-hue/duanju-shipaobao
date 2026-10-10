"""Merge per-episode ASR transcripts into a unified data file for AI analysis."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Merge per-episode transcripts into merged_data.json.")
    parser.add_argument("--work-dir", required=True, help="ASR work directory containing batch_summary.json.")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    summary_path = work_dir / "batch_summary.json"
    if not summary_path.exists():
        raise SystemExit(f"batch_summary.json not found in {work_dir}")

    batch = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(batch, list) or not batch:
        raise SystemExit("batch_summary.json is empty or invalid.")

    drama_title = work_dir.parent.name.replace("_精剪", "") if "_精剪" in work_dir.parent.name else work_dir.parent.name

    episodes = []
    total_duration = 0.0
    for row in batch:
        if row.get("status") != "ok":
            continue
        item_dir = Path(row["item_dir"])
        segments_path = item_dir / "timeline_segments.json"
        if not segments_path.exists():
            continue

        segments_data = json.loads(segments_path.read_text(encoding="utf-8"))
        duration = float(segments_data.get("duration", 0))
        total_duration += duration

        episodes.append({
            "index": row["index"],
            "filename": Path(row["video"]).name,
            "video_path": row["video"],
            "duration_s": duration,
            "text": str(segments_data.get("text", "")).strip(),
            "segments": segments_data.get("segments", []),
        })

    episodes.sort(key=lambda e: e["index"])

    merged_text_parts = []
    for ep in episodes:
        header = f"\n=== 第{ep['index']}集 {ep['filename']} ===\n"
        merged_text_parts.append(header + ep["text"])

    merged_data = {
        "drama_title": drama_title,
        "work_dir": str(work_dir),
        "video_count": len(episodes),
        "total_duration_s": total_duration,
        "merged_transcript": "".join(merged_text_parts),
        "episodes": episodes,
    }

    output_path = work_dir / "merged_data.json"
    output_path.write_text(json.dumps(merged_data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"Merged {len(episodes)} episodes, total duration {total_duration:.1f}s -> {output_path}")


if __name__ == "__main__":
    main()
