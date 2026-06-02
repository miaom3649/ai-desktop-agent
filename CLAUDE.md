# AI Desktop Agent

## 项目定位

AI 桌面助手，作为系统用户的"数字替身"。拥有与当前登录用户相同的系统权限和操作能力，通过控制鼠标、键盘、窗口等，自动完成用户能在电脑上执行的任何操作。核心价值：接管重复性桌面任务，用户只需用自然语言描述意图。

面向公众分发的桌面软件，开发者不承担任何 AI 推理成本。

## 目标平台

- Windows 10/11
- macOS 12+
- Linux（X11 图形化桌面，如 Ubuntu、Fedora）

## GUI 设计

三种界面形态并存：

1. **主窗口**：完整的应用界面，用于设置、任务历史、AI 配置等
2. **系统托盘**：最小化后驻留托盘，右键菜单提供快捷操作
3. **悬浮窗**：透明无边框、始终置顶、可拖动的助手角色悬浮在桌面角落，点击呼出快速指令输入框

悬浮窗技术实现：`QWidget` + `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint`，背景透明，角色使用精灵图/GIF 动画（`QMovie`）。

## 系统架构

### 四层模型

```
┌─────────────────────────────────────────────────────────┐
│  用户指令层   自然语言输入（GUI 文字 / 可选语音）            │
├─────────────────────────────────────────────────────────┤
│  感知层       屏幕截图 + 窗口状态（跨平台抽象）              │
├─────────────────────────────────────────────────────────┤
│  认知层       AI Provider 抽象层（本地 / 云端 BYOK）        │
├─────────────────────────────────────────────────────────┤
│  执行层       鼠标 / 键盘 / 窗口管理（跨平台抽象）           │
└─────────────────────────────────────────────────────────┘
```

### Agent 主循环

```
用户指令
  → 任务分解（AI）
  → loop:
      截图 + 窗口状态
      → AI 视觉分析（当前状态 + 任务目标 + 历史动作）
      → 返回结构化下一步动作（Tool Use / JSON）
      → 风险评估
      → [用户确认 if 高风险]
      → 执行动作 + 记录日志
      → 判断完成条件
  → 报告结果，更新 GUI
```

## 技术栈

| 模块 | 技术选型 |
|------|---------|
| 语言 | Python 3.12.13 |
| GUI 框架 | PySide6（Qt6），LGPL 协议 |
| 屏幕捕获 | `mss` + `Pillow`（压缩预处理，仅截主屏） |
| 输入控制 | `pyautogui` + `pynput` |
| 窗口管理 | 平台抽象层（见下文） |
| 剪贴板 | `pyperclip` |
| 配置管理 | `pydantic-settings` + YAML |
| 打包分发 | PyInstaller（生成各平台可执行文件） |

### AI Provider（抽象层）

所有 AI 调用通过统一接口 `AIProvider`，实现两个后端：

**本地后端（GPU 用户，默认首选）**
- 运行时：Ollama（用户自行安装）
- 推荐模型：`qwen2.5-vl:3b`（~4GB 显存）或 `qwen2.5-vl:7b`（~8GB 显存）
- 零 API 成本，截图不出本机

**云端后端（无 GPU 用户，BYOK）**
- 用户在设置页填入自己的 API Key
- 支持：Google Gemini（推荐，有免费额度）、Anthropic Claude、OpenAI
- 费用由用户自己承担，开发者零成本

首次启动时引导用户选择后端，可随时在设置中切换。

### 屏幕截图策略

`perception/screen.py` 始终只截**主屏（primary monitor）**，多显示器场景不拼接。原因：绝大多数任务在主屏完成，拼接会导致图片过宽，压缩后信息损失更大。

> **多屏支持**（让用户在配置中选择截哪个屏）列为 Phase 3 待办项。

### 跨平台窗口管理抽象层

> **当前开发重心：Windows**。Phase 1 & 2 只针对 Windows，使用 `pywin32` 直接实现。抽象层接口在 Phase 3 多平台适配时再建。

```python
# execution/window_ctrl.py
class WindowController:
    def list_windows(self) -> list[WindowInfo]: ...
    def focus_window(self, window_id: str): ...
    def move_window(self, window_id: str, x: int, y: int): ...
    def close_window(self, window_id: str): ...

# 平台实现（按优先级）
# Windows: pywin32 (win32gui)     ← Phase 1 & 2
# macOS:   pyobjc (AppKit)        ← Phase 3
# Linux:   python-ewmh / wmctrl   ← Phase 3
```

## 目录结构

```
ai-desktop-agent/
├── agent/
│   ├── core.py              # Agent 主循环
│   ├── planner.py           # 任务分解与动作规划
│   └── memory.py            # 上下文窗口与任务历史管理
├── ai/
│   ├── base.py              # AIProvider 抽象接口
│   ├── ollama_provider.py   # 本地 Ollama 后端
│   └── cloud_provider.py    # 云端 BYOK 后端（Gemini/Claude/OpenAI）
├── perception/
│   ├── screen.py            # 屏幕截图，图像压缩（发送前 max 1280px）
│   └── window.py            # 窗口列表与状态读取
├── execution/
│   ├── mouse.py             # 鼠标移动、点击、拖拽、滚轮
│   ├── keyboard.py          # 键盘输入、快捷键
│   └── window_ctrl.py       # 窗口管理跨平台抽象层
├── safety/
│   └── guard.py             # 动作风险评估，确认交互
├── gui/
│   ├── main_window.py       # 主窗口
│   ├── tray.py              # 系统托盘图标与菜单
│   ├── floating_widget.py   # 悬浮助手角色窗口
│   ├── settings_page.py     # AI 配置、平台选择
│   └── assets/
│       ├── character/       # 助手角色精灵图 / GIF
│       └── icons/           # 托盘图标等
├── config/
│   └── settings.yaml        # 用户配置（AI 后端、风险阈值、热键等）
├── tests/
├── main.py                  # 入口
└── requirements.txt
```

## 安全模型

每个动作携带风险等级，决定执行方式：

| 等级 | 示例动作 | 处理方式 |
|------|---------|---------|
| L0 低风险 | 截图、读取窗口信息、移动鼠标 | 静默自动执行 |
| L1 中风险 | 点击按钮、打开应用、输入文字 | 自动执行 + 日志 |
| L2 高风险 | 删除文件、发送消息/邮件、表单提交 | GUI 确认对话框 |
| L3 极高风险 | 系统设置变更、权限修改 | 确认 + 二次确认 |

AI 在规划动作时需同时输出风险等级字段。

## AI 集成规范

- 使用 **Tool Use / 结构化 JSON** 定义所有可执行动作，不解析自由文本
- 截图发送前压缩至 **最大宽度 1280px**，JPEG 格式，质量 85
- 每次请求携带：当前截图 + 任务目标 + 最近 N 步动作历史 + 当前窗口列表
- 云端 BYOK 路径启用 **prompt caching**（Gemini/Claude 均支持）降低用户 token 成本
- AIProvider 接口统一返回格式，底层模型对上层 Agent 透明

### 动作定义结构（示例）

```python
ACTIONS = [
    {"name": "mouse_click",        "params": {"x": int, "y": int, "button": str}},
    {"name": "type_text",          "params": {"text": str}},
    {"name": "key_press",          "params": {"keys": list[str]}},
    {"name": "open_app",           "params": {"app_name": str}},
    {"name": "task_done",          "params": {"summary": str}},
    {"name": "need_clarification", "params": {"question": str}},
]
```

## 开发日志规范

`DEVLOG.md` 记录所有开发进度。每次 PR 合并前，在对应日期下追加本次完成的内容（新日期在文件顶部插入）。格式：

```markdown
## YYYY-MM-DD
- 完成了什么
- 解决了什么问题
- 遗留了什么待处理
```

## README 规范

README.md 使用中英双语，**英文在上，中文在下**。每次更新 README 时遵循此格式，两个语言版本内容保持一致。

## 开发规范

- 执行层所有函数接受 `dry_run: bool = False`，`True` 时只记录日志不触发真实输入
- 每个动作执行前后打结构化日志：`{"action", "params", "result", "timestamp"}`
- 单元测试中对 `pyautogui`、`mss`、`wmctrl` 等做 mock，不产生真实系统事件
- 函数名、方法名、变量名统一使用**英文**（`snake_case`），Phase 1 & 2 中文规范仅适用于注释和 docstring
- Agent 主循环必须响应 `KeyboardInterrupt` 和 GUI 停止信号，立即中止
- 不硬编码屏幕分辨率，始终动态获取
- 窗口管理、输入控制均通过抽象层调用，不在业务代码中直接 import 平台特定库

## Git 规范

**分支命名**

| 前缀 | 用途 |
|------|------|
| `feat/` | 新功能 |
| `fix/` | Bug 修复 |
| `refactor/` | 重构（不改变行为） |
| `docs/` | 文档更新 |
| `chore/` | 构建、依赖、配置等杂项 |

示例：`feat/floating-widget`、`fix/ollama-timeout`

**Commit 格式**

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <描述>

feat(gui): add floating widget drag support
fix(execution): handle mouse click timeout on macOS
docs(readme): update AI model strategy section
```

- 标题行不超过 72 字符
- 使用祈使句，现在时态（"add" 而非 "added"）
- scope 对应目录模块名：`agent`、`ai`、`gui`、`execution`、`perception`、`safety`

**分支策略**

- `main` 分支受保护，禁止直接 push
- 所有变更通过 Pull Request 合并，使用 **Squash merge**（保持线性历史）
- PR 合并前必须通过全部 CI 检查

## 代码风格

**工具链**

| 工具 | 用途 | 配置文件 |
|------|------|---------|
| `ruff` | 格式化 + Lint + import 排序 | `pyproject.toml` |
| `pyright` | 静态类型检查 | `pyproject.toml` |
| `pytest` | 单元测试 | `tests/` |

**规则**

- 行长度上限：**100 字符**
- 所有函数签名必须有类型注解，包括返回值
- 命名规范：函数/变量用 `snake_case`，类名用 `PascalCase`，常量用 `UPPER_SNAKE_CASE`
- Import 顺序由 ruff 自动管理（stdlib → third-party → local）
- 注释只写"为什么"，不写"做什么"；非必要不写

**注释与文档语言**

- **Phase 1 & 2**：代码注释、docstring 全部使用**中文**
- **Phase 3**：进入发布打磨阶段时，将所有中文注释和文档字符串统一改为**英文**，删除冗余中文内容

**本地检查命令**

```bash
ruff check .          # lint
ruff format .         # 格式化
pyright               # 类型检查
pytest tests/         # 运行测试
```

## CI 规范

使用 **GitHub Actions**，配置文件位于 `.github/workflows/`。

**触发条件**：PR 到 `main`，以及 push 到 `main`。

**检查流水线（PR 合并前必须全部通过）**

| Job | 内容 |
|-----|------|
| `lint` | `ruff check .` + `ruff format --check .` |
| `typecheck` | `pyright` |
| `test` | `pytest tests/`（系统调用全部 mock） |

所有 Job 在 **Linux** 上运行。

**发布流水线**

打 `v*` tag 时触发，在 Windows / macOS / Linux 三平台矩阵上运行 PyInstaller 打包，产物上传至 GitHub Release。

## 开发阶段规划

### Phase 1 — 核心 Agent 可用（仅 Windows）
目标：验证整个技术链路跑通，能截图、能 AI 分析、能控制鼠标键盘，Agent 循环可运行。GUI 只做基础主窗口和托盘，能用即可。

- [ ] 屏幕截图 + AI 视觉分析（Ollama 本地跑通）
- [ ] 基础执行层：鼠标点击、键盘输入（Windows）
- [ ] Agent 主循环（截图 → AI → 执行 → 循环）
- [ ] AI Provider 抽象层（本地 Ollama + Gemini BYOK）
- [ ] 最简 GUI：主窗口 + 系统托盘

### Phase 2 — 功能完整（仅 Windows）
目标：所有核心功能到位，体验闭环。

- [ ] 悬浮助手角色窗口（透明、置顶、可拖动）
- [ ] 安全模型（风险评估 + GUI 确认对话框）
- [ ] 窗口管理层（pywin32）
- [ ] 设置页：AI 后端选择、API Key 配置、首次启动引导
- [ ] 动作重试机制（执行后截图验证状态）

### Phase 3 — 多平台 + 可发布
目标：扩展到 macOS 和 Linux，打磨到普通用户可安装使用。

- [ ] 跨平台窗口管理抽象层（macOS / Linux 实现）
- [ ] PyInstaller 打包——先输出 `--onedir` 便携 ZIP（解压即用），稳定后再制作 Windows 安装包（Inno Setup）；macOS / Linux 跟进
- [ ] 任务模板（保存常用流程）
- [ ] 语音输入（可选，faster-whisper 本地 STT）
- [ ] Wayland 支持（Linux 长期目标）
- [ ] 多显示器支持：在设置中允许用户选择截哪个屏（目前固定截主屏）
