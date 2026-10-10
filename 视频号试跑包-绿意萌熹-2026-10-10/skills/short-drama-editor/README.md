# short-drama-editor（短剧精剪 Skill）

短剧精剪：豆包 ASR 提取全文案+时间戳 → AI 分 2-3 个故事段（高光钩子开场+原声前情+主干+悬念结尾，去无聊过渡）→ 导出剪映专业版草稿。

触发语示例：「帮我精剪这部短剧」「这部短剧剪成几段」。

## 安装
把整个 **short-drama-editor** 文件夹放进你的 skills 目录（保持文件夹名不变）：
- Claude Code：`~/.claude/skills/`（Windows：`C:\Users\<你>\.claude\skills\`）
- Codex：`~/.agents/skills/`

## 依赖
- Python 3.12（`python` 在 PATH 上）
- ffmpeg / ffprobe 在系统 PATH 上（或设环境变量 `FFMPEG` / `FFPROBE`）
- Python 包：`pip install requests numpy`
- 剪映专业版（导草稿用）

## 配置豆包（火山引擎）ASR 凭据 ★必做
本 skill 用火山引擎「语音识别 流式极速版（auc_turbo）」提取文案。**包里凭据已清空，请填你自己的**：
1. 火山引擎控制台 → 语音技术 → 开通「语音识别 流式极速版」，拿到 App ID + Access Token
2. 设为系统环境变量（PowerShell，设完重开终端）：
   ```powershell
   setx DOUBAO_APP_ID "你的AppID"
   setx DOUBAO_ACCESS_TOKEN "你的AccessToken"
   ```
3. `assets/doubao_asr_config.json` 里写的是占位符 `${ENV:...}`，脚本会自动读上面的环境变量；也可直接替换成明文（仅本机、勿再分享）。

详细分步说明见 `SKILL.md`。
