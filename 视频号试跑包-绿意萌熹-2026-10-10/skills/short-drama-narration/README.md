# short-drama-narration（短剧解说混剪 Skill）

短剧解说混剪：一部剧抽 N 条（默认 4）不同高光故事线，各写第三人称网感解说稿（各自强钩子开头）→ 逐句豆包 TTS 配音 → 每句配一个原片画面逐句快切 → 原片去硬字幕 → 导出纯解说快剪剪映草稿（画面静音+解说音轨+字幕+引流钩子+合规声明），也可直出成品 MP4。

触发语示例：「短剧解说」「一部剧拆成多条不同角度解说」。

## 安装
把整个 **short-drama-narration** 文件夹放进你的 skills 目录（保持文件夹名不变）：
- Claude Code：`~/.claude/skills/`（Windows：`C:\Users\<你>\.claude\skills\`）
- Codex：`~/.agents/skills/`

> 剪映草稿库 `pyJianYingDraft` 已内置在 `scripts/_vendor/`，本 skill 自包含、无需安装其他 skill。

## 依赖
- Python 3.12（`python` 在 PATH 上）
- ffmpeg / ffprobe 在系统 PATH 上（或设环境变量 `FFMPEG` / `FFPROBE`）
- Python 包：`pip install requests numpy opencv-python imageio`
- 剪映专业版（导草稿用；直出 MP4 则不需要）

## 配置豆包（火山引擎）ASR + TTS 凭据 ★必做
本 skill 用火山引擎「语音识别 流式极速版」提取文案、「语音合成 TTS」配音。**包里凭据已清空，请填你自己的**：
1. 火山引擎控制台 → 语音技术 → 开通「语音识别 流式极速版」和「语音合成 TTS」，拿到 App ID + Access Token
2. 设为系统环境变量（PowerShell，设完重开终端）：
   ```powershell
   setx DOUBAO_APP_ID "你的AppID"
   setx DOUBAO_ACCESS_TOKEN "你的AccessToken"
   ```
3. 脚本会自动从上面的环境变量读取凭据。

详细分步说明见 `SKILL.md`。
