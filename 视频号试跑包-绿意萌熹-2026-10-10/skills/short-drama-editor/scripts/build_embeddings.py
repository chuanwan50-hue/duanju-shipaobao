"""Build segment embeddings, detect duplicates, and find scene boundaries.

Uses paraphrase-multilingual-MiniLM-L12-v2 to encode every ASR segment,
then computes:
  - Cross-episode duplicate pairs (cosine similarity > 0.92)
  - Within-episode scene boundaries (adjacent similarity drops)
  - Semantic search index for AI-assisted time range lookup
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL_PATH = str(Path.home() / ".cache" / "huggingface" / "hub" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2" / "snapshots" / "e8f8c211226b894fcb81acc59f3b34ba3efd5f42")
DUPLICATE_THRESHOLD = 0.92
BOUNDARY_STD_FACTOR = 1.0  # drop below (mean - N*std) = boundary


def load_segments(work_dir: Path) -> list[dict]:
    """Load all segments from merged_data.json, each tagged with episode info."""
    merged_path = work_dir / "merged_data.json"
    if not merged_path.exists():
        raise SystemExit(f"merged_data.json not found in {work_dir}")

    data = json.loads(merged_path.read_text(encoding="utf-8"))
    all_segments = []
    for ep in data.get("episodes", []):
        for seg in ep.get("segments", []):
            text = str(seg.get("text", "")).strip()
            if not text or len(text) < 2:
                continue
            all_segments.append({
                "uid": f"ep{ep['index']:03d}_seg{seg['id']:04d}",
                "episode": ep["index"],
                "filename": ep["filename"],
                "video_path": ep["video_path"],
                "start_s": float(seg.get("start", 0)),
                "end_s": float(seg.get("end", 0)),
                "text": text,
            })
    return all_segments


def compute_embeddings(segments: list[dict]) -> np.ndarray:
    """Encode all segment texts into 384-dim vectors."""
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    model_path = MODEL_PATH if Path(MODEL_PATH).exists() else MODEL_NAME
    model = SentenceTransformer(model_path, local_files_only=True)
    texts = [s["text"] for s in segments]
    print(f"Encoding {len(texts)} segments with {MODEL_NAME} ...")
    vectors = model.encode(texts, show_progress_bar=True, batch_size=64)
    return vectors


def detect_duplicates(segments: list[dict], vectors: np.ndarray) -> list[dict]:
    """Find pairs of segments from DIFFERENT episodes with high similarity."""
    sim_matrix = cosine_similarity(vectors)
    n = len(segments)
    duplicates = []

    for i in range(n):
        for j in range(i + 1, n):
            if segments[i]["episode"] == segments[j]["episode"]:
                continue  # only cross-episode
            score = float(sim_matrix[i][j])
            if score >= DUPLICATE_THRESHOLD:
                duplicates.append({
                    "seg_a": segments[i]["uid"],
                    "seg_b": segments[j]["uid"],
                    "ep_a": segments[i]["episode"],
                    "ep_b": segments[j]["episode"],
                    "similarity": round(score, 4),
                    "text_a": segments[i]["text"][:80],
                    "text_b": segments[j]["text"][:80],
                    "time_a": f"{segments[i]['start_s']:.1f}-{segments[i]['end_s']:.1f}s",
                    "time_b": f"{segments[j]['start_s']:.1f}-{segments[j]['end_s']:.1f}s",
                })

    duplicates.sort(key=lambda d: -d["similarity"])
    return duplicates


def summarize_duplicates(duplicates: list[dict]) -> dict:
    """Group duplicates by episode pair to show which episodes overlap."""
    ep_pairs = {}
    for d in duplicates:
        key = tuple(sorted([d["ep_a"], d["ep_b"]]))
        ep_pairs.setdefault(key, []).append(d)

    summary = []
    for (e1, e2), items in sorted(ep_pairs.items()):
        total_time = sum(
            abs(float(it["time_a"].split("-")[0].replace("s", "")) -
                float(it["time_a"].split("-")[1].replace("s", "")))
            for it in items
        )
        summary.append({
            "episode_pair": [e1, e2],
            "duplicate_segment_pairs": len(items),
            "max_similarity": max(it["similarity"] for it in items),
            "estimated_duplicate_duration_s": round(total_time, 1),
            "sample": items[0]["text_a"][:60] if items else "",
        })
    return {"threshold": DUPLICATE_THRESHOLD, "total_duplicate_pairs": len(duplicates), "by_episode_pair": summary}


def detect_scene_boundaries(segments: list[dict], vectors: np.ndarray) -> list[dict]:
    """Within each episode, find where adjacent segment similarity drops sharply."""
    boundaries = []
    sim_matrix = cosine_similarity(vectors)

    # Group segment indices by episode
    ep_groups: dict[int, list[int]] = {}
    for idx, seg in enumerate(segments):
        ep_groups.setdefault(seg["episode"], []).append(idx)

    for ep_num, indices in sorted(ep_groups.items()):
        if len(indices) < 3:
            continue

        # Compute adjacent similarities within this episode
        adj_sims = []
        for k in range(len(indices) - 1):
            i, j = indices[k], indices[k + 1]
            adj_sims.append(float(sim_matrix[i][j]))

        if not adj_sims:
            continue

        mean_sim = np.mean(adj_sims)
        std_sim = np.std(adj_sims)
        threshold = mean_sim - BOUNDARY_STD_FACTOR * std_sim

        for k, sim in enumerate(adj_sims):
            if sim < threshold:
                i, j = indices[k], indices[k + 1]
                boundaries.append({
                    "episode": ep_num,
                    "after_segment": segments[i]["uid"],
                    "before_segment": segments[j]["uid"],
                    "time_s": round(segments[i]["end_s"], 1),
                    "adjacent_similarity": round(sim, 4),
                    "episode_mean_sim": round(mean_sim, 4),
                    "episode_std_sim": round(std_sim, 4),
                    "text_before": segments[i]["text"][:60],
                    "text_after": segments[j]["text"][:60],
                })

    boundaries.sort(key=lambda b: (b["episode"], b["time_s"]))
    return boundaries


def build_search_index(segments: list[dict], vectors: np.ndarray, output_dir: Path) -> None:
    """Save vectors + metadata as npz for semantic search."""
    starts = np.array([s["start_s"] for s in segments], dtype=np.float32)
    ends = np.array([s["end_s"] for s in segments], dtype=np.float32)
    episodes = np.array([s["episode"] for s in segments], dtype=np.int32)
    uids = np.array([s["uid"] for s in segments])

    npz_path = output_dir / "embeddings.npz"
    np.savez_compressed(npz_path, vectors=vectors, starts=starts, ends=ends, episodes=episodes, uids=uids)
    print(f"Saved search index: {npz_path} ({len(segments)} segments, {vectors.shape[1]}d)")


def search_similar(segments: list[dict], vectors: np.ndarray, query: str, top_k: int = 5) -> list[dict]:
    """Semantic search: find segments most similar to a query string."""
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    model_path = MODEL_PATH if Path(MODEL_PATH).exists() else MODEL_NAME
    model = SentenceTransformer(model_path, local_files_only=True)
    q_vec = model.encode([query])
    scores = cosine_similarity(q_vec, vectors)[0]
    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in top_indices:
        results.append({
            "uid": segments[idx]["uid"],
            "episode": segments[idx]["episode"],
            "time": f"{segments[idx]['start_s']:.1f}-{segments[idx]['end_s']:.1f}s",
            "similarity": round(float(scores[idx]), 4),
            "text": segments[idx]["text"][:120],
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Build segment embeddings + detect duplicates and scene boundaries.")
    parser.add_argument("--work-dir", required=True, help="ASR work directory containing merged_data.json.")
    parser.add_argument("--skip-encode", action="store_true", help="Skip encoding if embeddings.npz already exists.")
    args = parser.parse_args()

    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"

    work_dir = Path(args.work_dir)
    npz_path = work_dir / "embeddings.npz"

    segments = load_segments(work_dir)
    print(f"Loaded {len(segments)} segments from {len(set(s['episode'] for s in segments))} episodes.")

    if args.skip_encode and npz_path.exists():
        print(f"Loading cached embeddings from {npz_path}")
        idx = np.load(npz_path, allow_pickle=True)
        vectors = idx["vectors"]
        # Re-sync segments order with cached index
        cached_uids = list(idx["uids"])
        segments = [s for s in segments if s["uid"] in cached_uids]
        uid_map = {uid: i for i, uid in enumerate(cached_uids)}
        segments.sort(key=lambda s: uid_map.get(s["uid"], 0))
    else:
        vectors = compute_embeddings(segments)
        build_search_index(segments, vectors, work_dir)

    print("Detecting cross-episode duplicates ...")
    duplicates = detect_duplicates(segments, vectors)
    dup_summary = summarize_duplicates(duplicates)
    dup_path = work_dir / "duplicates_report.json"
    dup_path.write_text(json.dumps(dup_summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"  {dup_summary['total_duplicate_pairs']} duplicate segment pairs across episodes → {dup_path}")
    for ep_pair in dup_summary["by_episode_pair"]:
        print(f"    Ep {ep_pair['episode_pair'][0]} <-> Ep {ep_pair['episode_pair'][1]}: "
              f"{ep_pair['duplicate_segment_pairs']} pairs, max_sim={ep_pair['max_similarity']:.3f}")

    print("Detecting scene boundaries ...")
    boundaries = detect_scene_boundaries(segments, vectors)
    bdy_path = work_dir / "scene_boundaries.json"
    bdy_path.write_text(json.dumps(boundaries, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"  {len(boundaries)} scene boundaries found → {bdy_path}")
    for b in boundaries:
        print(f"    Ep {b['episode']:2d} @ {b['time_s']:6.1f}s  sim={b['adjacent_similarity']:.3f}  "
              f"「{b['text_before'][:40]}」→「{b['text_after'][:40]}」")


if __name__ == "__main__":
    main()
