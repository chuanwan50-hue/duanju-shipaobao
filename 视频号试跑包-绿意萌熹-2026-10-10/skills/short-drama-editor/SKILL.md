---
name: 短剧精剪
description: 短剧精剪。接收短剧视频文件夹，通过豆包ASR提取全文案和时间戳，AI分析剧情后分成2-3个故事部分，每部分选取高光钩子开场+原声前情提要+剧情主干+悬念结尾，去除无聊过渡，导出剪映专业版草稿。
---

# 短剧精剪 Skill

## 输入

- 短剧视频文件夹，内含多个视频文件（.mp4/.mov/.mkv/.avi），按文件名自然排序
- 示例: `D:/短剧/霸道总裁爱上我/`

## 输出

- 2-3 个剪映专业版草稿，每个对应一个剧情部分
- 草稿位置: `C:/Users/Administrator/AppData/Local/JianyingPro/User Data/Projects/com.liveditor.draft/`
- 中间数据: 短剧文件夹同级目录 `{剧名}_精剪/asr_work/` 下

## 核心规则

1. **全原声**：所有片段保留原始视频音频，不合成任何 TTS
2. **钩子开场**：每个 Part 以高光钩子开场先抓人。**钩子是预告，不是替代**——钩子选取的冲突场景必须在 backbone 中完整保留，观众在剧情推进到该处时应看到完整版本。不能钩子里放了这段冲突、backbone 里却跳过去没有了。
3. **原声前情提要必须形成因果链**（Part 2+）：钩子之后紧跟 2-3 段前情片段，合起来必须是一个完整的微型因果故事——**起因→升级→后果**——让观众能理解主角从之前的故事结尾走到了当前 Part 的开场处境。不能是 2-3 个互不关联的"重要场景"拼盘。每段 8-15 秒即可，总时长 25-40 秒。

   **方法论**：先看当前 Part 的开场情境（主角在哪、面对谁、什么处境），倒推观众需要知道的 2-3 件事，这 2-3 件事必须彼此有因果箭头：A导致B，B导致C，C导致当前处境。

   错误示例：Part 2 开场是家政公司面试，前情提要是「早餐被骂(25s)」+「离家出走(16s)」——两段之间没有因果说明（为什么被骂就会离家？），缺少中间升级事件。

   正确示例：Part 2 开场是家政公司面试，前情提要是「早餐被全家人辱骂(12s)→发现丈夫出轨要离婚(14s)→变卖家产决然离家(13s)」——三件事因果链完整，观众自然理解她为什么 60 岁独闯省城做月嫂。
4. **结尾必须是冲突戛然而止**：每个 Part 的最后一段必须是冲突/对峙/威胁/震惊揭示进行到一半突然切断，让观众立刻想点开下一个视频。绝对禁止独白反思/内心感悟/圆满结局/夕阳镜头作为结尾
5. **每条压缩到 5 分钟左右**：每个 Part 总时长控制在 250-350 秒，不追求完整叙事，只保留情绪爆点——冲突/反转/高潮，狠删所有铺垫/过渡/空镜/重复对白/片头片尾
6. **只留爆点不留水戏**：每场戏只保留最核心的对白，跳过反复强调和解释性对话
7. **去重**：短剧原片常有下一集 recap 和独白/对白说同一件事。AI 分析时必须识别并在 keep_ranges 中跳过重复片段，同一个事件只保留一次
8. **同一事件不拼接两个版本**：如果 Ep3 和 Ep4 都讲了商场对峙这场戏，只选一个版本保留全部，不要把 Ep3 的前半+Ep4 的后半拼成一场戏，观众会感觉同一场对峙看了两遍
9. **相邻 keep_range 不能重叠**：同一个 episode 内的 backbone ranges 必须在时间上连续但不重叠，不能在边界处出现同一句话被两个 segment 各取一半的情况。写完 ranges 后检查相邻 range 的 end_s 和 start_s 是否有重叠的 ASR utterance
10. **backbone 按故事时间线排列，禁止前后跳跃**：所有 backbone 场景必须严格按故事发生的先后顺序排列。不能出现"商场对峙→跳到未来报应→又跳回商场结尾"这种时间线倒挂。如果某段内容时间上在结尾之后，要么删掉，要么放到结尾之前
11. **相邻 backbone 场景必须有因果连接**：观众看完 seg N 后看到 seg N+1 时，应该能自然理解"为什么接下来是这个"。如果出现"为什么这个人突然道歉了"的疑问，说明中间缺了一场过渡戏——要么补上，要么调整顺序

## Part 结构

```
Part 1: [高光钩子] → [剧情主干 01] → [剧情主干 02] → ... → [悬念结尾]

Part 2+: [高光钩子] → [前情片段01(原声)] → [前情片段02(原声)] → [剧情主干 01] → ... → [悬念结尾]
```

## 工具路径

| 工具 | 路径 |
|------|------|
| Python | C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python |
| asr_transcribe.py | scripts/asr_transcribe.py |
| merge_transcripts.py | scripts/merge_transcripts.py |
| build_embeddings.py | scripts/build_embeddings.py |
| build_edit_plan.py | scripts/build_edit_plan.py |
| build_draft.py | scripts/build_draft.py |

---

## 执行流程

### ▶ Step 1: 批量 ASR 转写

**目的**：将短剧文件夹中所有视频逐集调用豆包 ASR API，获取完整文案和词级时间戳。

**执行命令**：
```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python scripts/asr_transcribe.py \
  --input-root "{短剧文件夹路径}" \
  --output-root "{短剧文件夹}_精剪/asr_work"
```

**Gate 检查**：
- [ ] `batch_summary.json` 存在，所有视频 status 为 "ok"
- [ ] 逐集目录下 `timeline_segments.json` 存在
- [ ] 如有失败的视频，报告给用户

**说明**：支持断点续传，已成功转写的视频会跳过。如需重跑全部，删除 asr_work 目录后重新运行。

---

### ▶ Step 2: 合并转写稿

**目的**：将所有逐集 transcript 合并为一个统一的 JSON 文件，包含完整串联文本供 AI 阅读。

**执行命令**：
```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python scripts/merge_transcripts.py \
  --work-dir "{短剧文件夹}_精剪/asr_work"
```

**Gate 检查**：
- [ ] `merged_data.json` 存在
- [ ] `merged_transcript` 字段包含完整串联文本
- [ ] `episodes` 数组包含所有 episode

---

### ▶ Step 2.5: Embedding 向量化 + 去重检测 + 场景边界

**目的**：对所有 ASR segment 计算语义向量，自动检测跨 episode 重复内容和场景切换点，为 AI 分析提供精确参考数据。

**执行命令**：
```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python scripts/build_embeddings.py \
  --work-dir "{短剧文件夹}_精剪/asr_work"
```

**产出**：
- `embeddings.npz`：所有 segment 的 384 维向量 + 元数据（供语义搜索）
- `duplicates_report.json`：跨 episode 高相似度 segment 对（similarity > 0.92），按 episode pair 分组
- `scene_boundaries.json`：每集内相邻 segment 相似度骤降的位置 = 场景切换点

**AI 如何使用这些产出**：
- **去重**：`duplicates_report.json` 直接告诉你哪些 episode pair 有大量重复内容。在 Step 3 写 keep_ranges 时跳过重复 episode 中的重复时间段
- **场景边界**：`scene_boundaries.json` 标记了每集的场景切换时间点。写 keep_ranges 时以这些边界为参考，不要把两个场景硬切在一个 range 里
- **语义搜索**：AI 需要定位特定内容时，可用 `search_similar()` 函数找到精确时间范围，不再凭记忆猜

**说明**：首次运行需下载模型 `paraphrase-multilingual-MiniLM-L12-v2`（~420MB），后续使用 `--skip-encode` 跳过编码直接加载缓存。

---

### ▶ Step 3: AI 剧情分析

**目的**：AI 读懂全剧剧本，先梳理出完整干净的故事，再拆分结构，最后映射回时间戳。

**核心原则**：先写故事，再拆结构，最后定位时间。不能跳过"完整故事"这一步直接跳到 keep_ranges，否则会像碎纸机一样切得太乱。

**分析步骤**：

**3a. 理解剧情全貌 + 写出完整故事场景列表**
- 阅读完整的 `merged_transcript`，理解完整的剧情脉络
- 识别主要角色、核心关系、中心冲突、结局走向
- 填写 `character_list`
- **关键产出：`scene_list`** —— 按故事实际发生的时间顺序，列出所有有叙事价值的场景。每个场景是一条完整的情节推进，不是单个爆点片段
- 场景粒度：每集 2-4 个场景，每个场景是一个完整的戏剧单元（有起承转合），时长通常 30-90 秒
- 去重规则在此执行：
  1. 同一事件出现在多个 episode（recap/闪回）→ 只在 scene_list 中保留首次出现
  2. 独白叙述+对白演绎同一事件 → 只保留对白版
  3. 纯 recap 的 episode（如 Ep9/10 回顾前面内容）→ 整集不进入 scene_list
- 平淡过渡场景（纯走路/空镜/片头片尾）→ 不进入 scene_list
- **⚠️ 情感桥接场景不属于"平淡过渡"**：人物独白反思处境变化、告别重要关系、做出重大决定前的犹豫——这些是叙事胶水，必须进入 scene_list。判断标准：如果删掉这段，观众会问"她为什么突然做了那个决定？"→ 这段就不能删
- 格式: `[{"order": 1, "description": "场景简述", "episode": 1, "start_s": 85.8, "end_s": 181.6, "keep_reason": "为什么保留"}]`
- scene_list 是一条**连贯的故事线**，读起来应该像故事大纲，而不像碎片合集。写完 scene_list 后自检：按 order 连续读一遍，有任何"为什么突然…"的疑问就说明缺了场景

**3b. 将 scene_list 划分为 2-3 个 Part**
- 在 scene_list 中识别自然的故事分段点（重大反转、时间跳跃、地点变换）
- 标记每个 Part 包含哪些 scene（通过 scene order 范围）
- 每部分覆盖一个连贯的故事弧线
- 为每部分写一段 summary

**3c. 选择高光钩子（每 Part 1 个）**
- 从该 Part 的 scenes 中选出一个冲突最强的场景作为钩子
- **钩子是冲突峰值，不是故事终点**。绝对禁止选情感和解/成功录用/团圆拥抱/感动落泪被接受
- 正确钩子：激烈对峙、当众羞辱/拒绝、震惊揭示、被逼到绝境的反击
- **钩子标注了 scene_list 中的 order**，该场景必须同时保留在 backbone 的 keep_ranges 中——钩子只是提前预告，完整场景仍要在 backbone 里按时间线出现。写 keep_ranges 时检查：钩子场景的 episode+时间范围是否被 backbone 覆盖？没覆盖就是缺了

**3d. 选择悬念结尾（每 Part 1 个）**
- 结尾必须是冲突戛然而止，让观众立刻想看下一 Part
- 绝对禁止独白反思/内心感悟/夕阳镜头/圆满结局
- 正确结尾：对峙进行中切断、震惊揭示出现后立即切断、威胁甩出后黑屏

**3e. 选择前情提要场景（Part 2+ 必填）—— 因果链倒推法**
- **第一步：确定当前 Part 的开场情境**。主角在本 Part 第一个 backbone 场景里：在哪里？面对谁？什么处境？（例如：在家政公司被前台轻蔑，林雨晴闻香而来）
- **第二步：倒推因果链**。观众要理解这个处境，最少需要知道哪 2-3 件事？这些事必须有因果箭头：**A → B → C → 当前开场**
  - A = 起因（主角被怎样对待/失去了什么）
  - B = 升级（冲突加剧/被逼到绝路）
  - C = 后果（主角做了什么决定/行动，直接导致当前处境）
- **第三步：每件事选最精简的原声片段**。每段 8-15 秒，只取最核心的对白+反应，总长 25-40 秒
- **第四步：按因果顺序排列 context_clips**：A → B → C（不是 episode 编号顺序，是故事因果顺序）
- **自检**：如果把这三段连起来看，一个没看过剧的路人能不能理解"主角为什么在这里"？能 → 合格。不能 → 缺了某个因果环节，补上
- 每段标注其在 scene_list 中的 order，以及 `purpose`（这段在因果链中的位置：起因/升级/后果）

**3f. 生成 keep_ranges_by_episode**
- 从 scene_list 按 Part 分组，转换为 keep_ranges_by_episode 格式
- **重要：同一 episode 内相邻且间隔小于 10 秒的 keep_ranges 应该合并**，避免把一个完整场景切成碎片
- keep_ranges_by_episode 的 key 顺序 = 故事时间线顺序（不是 episode 编号顺序）
- 每个 Part 的 scenes 数量应相近（目标每 Part 8-12 个场景）

**3g. 验证与输出**
写完 keep_ranges 后，必须完成以下验证，通过后才能写入 story_analysis.json：

**① ASR 数据验证**
- 打开对应 episode 的 `timeline_segments.json`，检查每个 keep_range 的 ASR 文本是否与预期一致
- 检查是否有半句话被切掉（range 边界是否落在句子中间）
- 检查是否和其他 episode 的 range 内容重复（参考 duplicates_report.json）

**② 故事连续性朗读**
- 把每个 Part 的 backbone 场景按时间线连起来朗读一遍。出现以下情况 = 断层，扩展 keep_range 边界补上：
  - "她为什么突然做了 X？" → 缺动机过渡
  - "这人是谁？为什么在这？" → 缺人物关系
  - 早上直接跳到晚上无锚点 → 缺时间过渡
  - 上一场景哭、下一场景笑无解释 → 缺情绪转折

**③ 三项覆盖检查**
- **钩子覆盖**：每 Part 的钩子场景是否也在 backbone keep_ranges 中？（钩子是预告不是替代）
- **前情因果链**（Part 2+）：context_clips 按 A→B→C 排列，连起来路人能否理解主角处境？
- **去重**：同一事件是否在两个 episode 的 backbone 中各出现一次？

**④ 输出场景文案（在对话中展示）**
- 格式：`[Part X] seg0(epY, role, Xs): 前30字 → seg1(...): ... → ...`
- 对照文案逐段复查①②③，发现问题立即修正，重新 build

**⑤ 写入 story_analysis.json**
- [ ] scene_list 连贯（无"为什么突然"断点，含情感桥接场景）
- [ ] 每 Part 有 hook/ending/keep_ranges/context_clips(Part 2+)
- [ ] 同 episode 内无间隔 <10s 的相邻 range
- [ ] ①②③④ 全部通过


---

### ▶ Step 4: 构建剪辑计划

**目的**：将 AI 的语义分析转换为精确的微秒级时间线。

**执行命令**：
```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python scripts/build_edit_plan.py \
  --work-dir "{短剧文件夹}_精剪/asr_work"
```

**说明**：脚本自动完成以下工作：
- 解析 hook / context_clips / keep_ranges / ending 为精确 segment
- 按序排列: hook → context_clips → backbone → ending
- 计算累计时间线位置
- 为每个 segment 生成对应的字幕 cue（从 ASR 词级时间戳映射）

**Gate 检查**：
- [ ] `edit_plan.json` 存在
- [ ] 每个 Part 的 total_duration_us > 0
- [ ] segments 按 timeline_order 排列，无间隙无重叠
- [ ] 第一个 segment 是 hook (role=hook)
- [ ] 最后一个 segment 是 ending (role=ending)

---

### ▶ Step 5: 导出剪映草稿

**目的**：将每个 Part 的编辑计划导出为剪映草稿。

**执行命令**（每个 Part 独立执行，可并行）：
```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python scripts/build_draft.py \
  --work-dir "{短剧文件夹}_精剪/asr_work" \
  --part-id 1
```

**说明**：
- 每个 Part 生成一个独立草稿到剪映草稿目录
- 所有片段保留原视频音频
- 字幕默认开启，可用 `--no-subtitles` 关闭
- 如果存在同名草稿，自动追加数字后缀避免覆盖
- 用 `--overwrite` 覆盖已有草稿

**Gate 检查**：
- [ ] 每个 Part 的 `draft_content.json` 存在于剪映草稿目录
- [ ] `root_meta_info.json` 已更新，草稿出现在剪映项目列表
- [ ] 报告每个草稿的名称、时长、片段数、字幕数

---

## 错误处理

- **ASR 失败**：个别视频 ASR 失败不影响整体流程，Step 1 的 batch_summary.json 中标记为 failed。AI 决定是否重试
- **空转写**：如果某集 ASR 转写为空（纯音乐/B-roll），该集的 keep_ranges 可为空（全部删除）
- **钩子/结尾找不到**：如果 AI 指定的时间范围在 merged_data 中找不到对应 episode，build_edit_plan.py 会跳过该 segment
- **剪映草稿目录不存在**：build_draft.py 会自动创建

## 注意事项

1. Python 脚本通过 CLI 参数交互，不要修改脚本内部逻辑
2. AI 在 Step 3 的分析质量直接决定剪辑效果，务必认真阅读全剧剧本
3. 前情提要片段必须剪短，只保留最必要的人物介绍和剧情铺垫
4. de drama 结尾务必保留悬念感，这是短剧吸引用户追看的关键
