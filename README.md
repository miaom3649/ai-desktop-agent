# AI Desktop Agent

Meet your most loyal AI desktop secretary — your **digital twin** inside the computer. She carries the same system permissions and operational capabilities as you, the actual user, stepping in to handle all the complex and repetitive tasks you'd otherwise deal with yourself.

## What It Does

AI Desktop Agent accepts natural language instructions and autonomously executes them on your desktop: opening and closing applications, controlling and moving windows, typing text, clicking buttons, and anything else you can do yourself. Its primary purpose is to take over repetitive, low-cognition desktop tasks so you can focus on what matters.

**Example tasks:**
- "Open DingTalk and click the check-in button"
- "Find all PDF files on the desktop and move them to the Documents folder"
- "Fill in this form the same way I did last time"

## Key Features

- **Full desktop control** — mouse, keyboard, window management, clipboard
- **Vision-based understanding** — takes screenshots and uses AI to understand the current screen state before acting
- **Natural language interface** — just describe what you want done
- **Floating assistant** — a character widget lives in the corner of your desktop, always ready; minimizes to the system tray when not needed
- **Safety guardrails** — high-risk actions (deleting files, sending messages) require your explicit confirmation before execution

## AI Model Strategy

AI Desktop Agent is **free to download and use** — the developer bears no AI inference costs.

| User type | How AI works |
|-----------|-------------|
| Has a GPU (6GB+ VRAM) | Runs a local vision model via Ollama — fully offline, private, zero API cost |
| No GPU | Bring Your Own Key: connect your own Gemini / Claude / OpenAI API key |

Recommended local model: `qwen2.5-vl:3b` or `qwen2.5-vl:7b` (via Ollama).  
For BYOK users, Google Gemini offers a generous free tier.

## Supported Platforms

- Windows 10/11
- macOS 12+
- Linux (X11 graphical desktop — Ubuntu, Fedora, etc.)

## Status

> Early development. See [CLAUDE.md](CLAUDE.md) for architecture and roadmap.

---

# AI 桌面助手

这无疑将会是最忠实于你的 AI 桌面秘书，一位你在电脑中的**数字替身**——她能够以你这个实际用户相同的系统权限和操作能力，代替你操控电脑处理繁杂的事务。

## 它能做什么

AI 桌面助手接受自然语言指令，并在桌面上自主执行：打开和关闭应用、控制和移动窗口、输入文字、点击按钮，以及一切你自己能做的操作。它的核心价值是接管重复性、低认知价值的桌面任务，让你专注于更重要的事情。

**示例任务：**
- "打开钉钉，点签到按钮"
- "把桌面上所有 PDF 文件移动到文档文件夹"
- "按照上次的方式帮我填这个表单"

## 核心功能

- **完整桌面控制** — 鼠标、键盘、窗口管理、剪贴板
- **视觉理解** — 截取屏幕截图，用 AI 理解当前界面状态后再执行操作
- **自然语言交互** — 只需描述你想做什么
- **悬浮助手** — 一个角色窗口常驻桌面角落，随时待命；不需要时最小化到系统托盘
- **安全防护** — 高风险操作（删除文件、发送消息）在执行前必须经过你的明确确认

## AI 模型策略

AI 桌面助手**下载和使用完全免费**，开发者不承担任何 AI 推理费用。

| 用户类型 | AI 运行方式 |
|---------|-----------|
| 有独立显卡（6GB+ 显存） | 通过 Ollama 在本地运行视觉模型，完全离线、隐私安全、零 API 成本 |
| 无独立显卡 | 自带密钥（BYOK）：填入自己的 Gemini / Claude / OpenAI API Key |

推荐本地模型：`qwen2.5-vl:3b` 或 `qwen2.5-vl:7b`（通过 Ollama 运行）。  
BYOK 用户推荐使用 Google Gemini，有免费额度可用。

## 支持平台

- Windows 10/11
- macOS 12+
- Linux（X11 图形化桌面，如 Ubuntu、Fedora 等）

## 项目状态

> 早期开发阶段。架构设计与开发路线图见 [CLAUDE.md](CLAUDE.md)。
