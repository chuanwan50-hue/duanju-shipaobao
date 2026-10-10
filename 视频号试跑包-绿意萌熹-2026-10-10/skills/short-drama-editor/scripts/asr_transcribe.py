"""Batch Doubao ASR transcription for short drama episodes."""

import argparse
import base64
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CONFIG = SKILL_DIR / "assets" / "doubao_asr_config.json"


def natural_key(text: str) -> list:
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_config(path: Path) -> dict:
    import os
    data = json.loads(path.read_text(encoding="utf-8"))
    # 支持 config 里写 ${ENV:VAR} 占位符，从环境变量读取凭据（避免明文泄露）
    for _k in ("app_id", "access_token"):
        _v = data.get(_k)
        if isinstance(_v, str) and _v.startswith("${ENV:") and _v.endswith("}"):
            _name = _v[6:-1]
            _env = os.environ.get(_name)
            if not _env:
                raise ValueError(f"环境变量 {_name} 未设置（config 占位符 {_v}）")
            data[_k] = _env
    required = ["flash_url", "resource_id", "app_id", "access_token"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(f"Missing config fields: {', '.join(missing)}")
    return data


def ms_to_seconds(value) -> float:
    return round(max(float(value), 0.0) / 1000.0, 6)


def normalize_doubao_result(response_json: dict) -> dict:
    result_payload = response_json.get("result", {})
    utterances = result_payload.get("utterances") or []
    segments = []

    for idx, utterance in enumerate(utterances):
        seg_text = str(utterance.get("text") or "").strip()
        words_payload = utterance.get("words") or []
        normalized_words = []
        pending_prefix = ""

        for w in words_payload:
            token = str(w.get("text") or "")
            if not token:
                continue
            st = float(w.get("start_time", -1))
            et = float(w.get("end_time", -1))
            if st < 0 or et < 0:
                if normalized_words:
                    normalized_words[-1]["word"] += token
                else:
                    pending_prefix += token
                continue
            normalized_words.append({
                "word": pending_prefix + token,
                "start": ms_to_seconds(st),
                "end": ms_to_seconds(et),
                "confidence": w.get("confidence"),
            })
            pending_prefix = ""

        if pending_prefix and normalized_words:
            normalized_words[-1]["word"] += pending_prefix

        if not seg_text and normalized_words:
            seg_text = "".join(w["word"] for w in normalized_words).strip()

        segments.append({
            "id": idx,
            "start": ms_to_seconds(utterance.get("start_time", 0)),
            "end": ms_to_seconds(utterance.get("end_time", 0)),
            "text": seg_text,
            "words": normalized_words,
        })

    duration_ms = (response_json.get("audio_info", {}).get("duration")
                   or result_payload.get("additions", {}).get("duration") or 0)

    return {
        "text": str(result_payload.get("text") or "").strip(),
        "segments": segments,
        "language": "zh",
        "duration": ms_to_seconds(duration_ms),
        "provider": "doubao-flash-asr",
    }


def iter_videos(input_root: Path) -> list[Path]:
    exts = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}
    return sorted(
        [p for p in input_root.iterdir() if p.is_file() and p.suffix.lower() in exts],
        key=lambda p: natural_key(p.name),
    )


def run_ffmpeg_extract(video_path: Path, wav_path: Path) -> None:
    ensure_dir(wav_path.parent)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def doubao_flash_recognize(wav_path: Path, config: dict) -> requests.Response:
    audio_b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
    headers = {
        "X-Api-App-Key": str(config["app_id"]),
        "X-Api-Access-Key": str(config["access_token"]),
        "X-Api-Resource-Id": str(config["resource_id"]),
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    payload = {
        "user": {"uid": str(config["app_id"])},
        "audio": {"data": audio_b64},
        "request": config.get("request_defaults", {
            "model_name": "bigmodel",
            "enable_itn": True,
            "show_utterances": True,
        }),
    }
    last_exc = None
    for attempt in range(1, 4):
        try:
            return requests.post(str(config["flash_url"]), headers=headers, json=payload, timeout=1800)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt == 3:
                raise
            time.sleep(attempt * 2)
    if last_exc:
        raise last_exc
    raise RuntimeError("Doubao recognition request failed.")


def main():
    parser = argparse.ArgumentParser(description="Batch transcribe drama episodes via Doubao ASR.")
    parser.add_argument("--input-root", required=True, help="Folder containing drama video files.")
    parser.add_argument("--output-root", required=True, help="Output work directory.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Doubao API config JSON path.")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_root = Path(args.output_root)
    ensure_dir(output_root)

    videos = iter_videos(Path(args.input_root))
    if not videos:
        raise SystemExit("No video files found in input root.")

    summary_path = output_root / "batch_summary.json"
    existing_by_video = {}
    if summary_path.exists():
        try:
            rows = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("video"):
                        existing_by_video[str(row["video"])] = row
        except Exception:
            pass

    batch_rows = []
    for idx, video_path in enumerate(videos, start=1):
        item_dir = output_root / f"{idx:03d}_{video_path.stem}"
        ensure_dir(item_dir)
        wav_path = item_dir / "audio_16k_mono.wav"

        # Resume: skip if already processed successfully
        existing = existing_by_video.get(str(video_path))
        segments_path = item_dir / "timeline_segments.json"
        if existing and existing.get("status") == "ok" and segments_path.exists():
            batch_rows.append(existing)
            print(f"[{idx}/{len(videos)}] SKIP {video_path.name} (already done)")
            continue

        status = "ok"
        message = ""
        status_code = 0
        try:
            print(f"[{idx}/{len(videos)}] Processing {video_path.name} ...")
            run_ffmpeg_extract(video_path, wav_path)
            response = doubao_flash_recognize(wav_path=wav_path, config=config)
            status_code = response.status_code

            if response.status_code != 200:
                status = "failed"
                message = f"HTTP {response.status_code}"
            else:
                try:
                    response_json = response.json()
                except Exception:
                    response_json = {"raw_text": response.text}

                # Check API status
                api_status = ""
                try:
                    api_status = response.headers.get("X-Api-Status-Code", "")
                except Exception:
                    pass

                if api_status != "20000000":
                    status = "failed"
                    message = f"API status={api_status}, message={response.headers.get('X-Api-Message', '')}"
                else:
                    normalized = normalize_doubao_result(response_json)
                    segments_path.write_text(
                        json.dumps(normalized, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")

                    plain_text = normalized.get("text", "")
                    (item_dir / "transcript.txt").write_text(plain_text, encoding="utf-8", newline="\n")
                    (item_dir / "response.json").write_text(
                        json.dumps(response_json, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")

        except Exception as exc:
            status = "failed"
            message = repr(exc)

        batch_rows.append({
            "index": idx,
            "video": str(video_path),
            "item_dir": str(item_dir),
            "status": status,
            "http_status": status_code,
            "message": message,
        })

        # Save progress after each episode
        progress = {
            "processed": idx, "total": len(videos),
            "last_video": video_path.name, "last_status": status,
            "ok": sum(1 for r in batch_rows if r["status"] == "ok"),
            "failed": sum(1 for r in batch_rows if r["status"] == "failed"),
        }
        (output_root / "progress.json").write_text(
            json.dumps(progress, ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")

    summary_path.write_text(
        json.dumps(batch_rows, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")

    ok = sum(1 for r in batch_rows if r["status"] == "ok")
    failed = sum(1 for r in batch_rows if r["status"] == "failed")
    print(f"\nDone. {ok} ok, {failed} failed out of {len(batch_rows)} total.")


if __name__ == "__main__":
    main()
