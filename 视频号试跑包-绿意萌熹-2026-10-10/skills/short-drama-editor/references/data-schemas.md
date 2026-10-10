# Data Schema Reference

## File Flow

```
batch_summary.json (Step 1 output)
  → merged_data.json (Step 2 output)
    → story_analysis.json (Step 3 AI output)
      → edit_plan.json (Step 4 output)
        → draft_content.json + draft_meta_info.json (Step 5 output)
```

---

## batch_summary.json (Step 1)

```json
[
  {
    "index": 1,
    "video": "D:/短剧/剧名/第01集.mp4",
    "item_dir": "D:/短剧/剧名_精剪/asr_work/001_第01集",
    "status": "ok",
    "http_status": 200,
    "message": ""
  }
]
```

## timeline_segments.json (Step 1, per episode)

```json
{
  "text": "完整转写文本",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "对白文本",
      "words": [
        {"word": "你", "start": 0.0, "end": 0.3, "confidence": 0.98}
      ]
    }
  ],
  "language": "zh",
  "duration": 61.2,
  "provider": "doubao-flash-asr"
}
```

## merged_data.json (Step 2)

```json
{
  "drama_title": "剧名",
  "work_dir": "D:/短剧/剧名_精剪/asr_work",
  "video_count": 30,
  "total_duration_s": 1850.3,
  "merged_transcript": "\n=== 第1集 第01集.mp4 ===\n完整文本...",
  "episodes": [
    {
      "index": 1,
      "filename": "第01集.mp4",
      "video_path": "D:/短剧/剧名/第01集.mp4",
      "duration_s": 61.2,
      "text": "完整转写文本",
      "segments": [ /* same as timeline_segments.json segments */ ]
    }
  ]
}
```

## story_analysis.json (Step 3, AI writes)

```json
{
  "drama_title": "剧名",
  "part_count": 3,
  "character_list": [
    {"name": "角色A", "description": "身份和性格一句话", "intro_episode": 1}
  ],
  "parts": [
    {
      "part_id": 1,
      "title": "部分标题",
      "summary": "这部分讲什么（一段话）",
      "episode_range": [1, 10],
      "hook": {
        "episode": 5,
        "start_s": 18.5,
        "end_s": 35.2,
        "text_snippet": "钩子对白片段",
        "reason": "为什么选这段做钩子"
      },
      "ending": {
        "episode": 10,
        "start_s": 55.0,
        "end_s": 61.0,
        "text_snippet": "结尾对白",
        "reason": "为什么这个结尾能勾住观众"
      },
      "keep_ranges_by_episode": {
        "1": [
          {"start_s": 2.5, "end_s": 45.0, "reason": "主角出场+面试场景"},
          {"start_s": 50.0, "end_s": 58.5, "reason": "首次相遇结尾"}
        ]
      },
      "context_clips": []
    },
    {
      "part_id": 2,
      "title": "真相浮现",
      "episode_range": [11, 20],
      "hook": { /* same structure as above */ },
      "ending": { /* same structure as above */ },
      "keep_ranges_by_episode": { /* ... */ },
      "context_clips": [
        {
          "episode": 1,
          "start_s": 5.0,
          "end_s": 18.0,
          "text_snippet": "对白片段",
          "purpose": "回顾女主初入公司，建立人物背景"
        },
        {
          "episode": 5,
          "start_s": 20.0,
          "end_s": 35.0,
          "text_snippet": "对白片段",
          "purpose": "回顾男女主冲突名场面"
        }
      ]
    }
  ]
}
```

### Field Notes

- `episode_range`: 1-based, inclusive
- `hook.episode` / `ending.episode`: Must be within `episode_range`
- `keep_ranges_by_episode` keys are episode numbers as strings ("1", "2", ...)
- `context_clips`: Empty array for Part 1; 2-4 clips for Parts 2+
- `text_snippet`: For AI reference only, not used by scripts
- `reason` / `purpose`: For documentation, not used by scripts

## edit_plan.json (Step 4)

```json
{
  "parts": [
    {
      "part_id": 1,
      "draft_name": "剧名_Part1_标题",
      "canvas": {"width": 1080, "height": 1920, "ratio": "9:16", "fps": 30},
      "total_duration_us": 450000000,
      "segments": [
        {
          "timeline_order": 0,
          "role": "hook",
          "video_path": "D:/短剧/剧名/第05集.mp4",
          "source_start_us": 18500000,
          "source_duration_us": 16700000,
          "timeline_start_us": 0,
          "timeline_duration_us": 16700000,
          "audio_volume": 1.0,
          "label": "钩子：雨中质问 第5集 [18.5s-35.2s]"
        }
      ],
      "subtitles": [
        {
          "text": "你知不知道我是谁",
          "start_us": 0,
          "duration_us": 2000000,
          "words": [
            {"word": "你", "start": 0.0, "end": 0.3, "confidence": 0.98}
          ]
        }
      ]
    }
  ]
}
```

### Segment Roles

| role | Position | Notes |
|------|----------|-------|
| `hook` | timeline_order=0 | 1 per Part |
| `context` | after hook, before backbone | Part 2+ only |
| `backbone` | after context, before ending | Sorted by episode |
| `ending` | last | 1 per Part |
