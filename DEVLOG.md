# 开发日志

## 2026-06-02

**完成内容**

- 创建完整目录骨架，覆盖 CLAUDE.md 中规划的所有模块
- 创建 `pyproject.toml`：统一管理依赖（运行时 + dev）、ruff、pyright、pytest 配置，使用 hatchling 构建后端
- 更新 `README.md` 中英文，新增"开发环境搭建"章节，说明用 `pyproject.toml` 管理依赖而非 `requirements.txt`，列出安装命令与工具链使用方式
- 创建 `.github/workflows/ci.yml`：四个 job（install → lint / typecheck / test），install 先行，后三个并行；触发条件为 PR 和 push 到 main
- 实现 `perception/screen.py`：截主屏、等比缩放至最大 1280px、JPEG 质量 85、返回 base64 字符串
- 创建 `tests/test_screen.py`：4 个单元测试，mock mss 不产生真实截图
- 新增开发规范：函数名、方法名、变量名统一使用英文，中文仅用于注释和 docstring
- 实现 `ai/ollama_provider.py`：`OllamaProvider` 完整实现
  - `is_available()`：GET `/api/tags` 检查服务在线 + 模型已拉取
  - `complete()`：POST `/api/chat` 多模态请求，解析返回 JSON 为 `AIResponse`
  - 自动剥离模型可能输出的 markdown 代码块包裹
  - 使用标准库 `urllib` 无额外依赖
- 创建 `tests/test_ollama_provider.py`：7 个单元测试，mock HTTP 不依赖真实 Ollama 服务
- 实现 `execution/mouse.py`：`MouseController` 完整实现（click/move/drag/scroll），pyautogui FAILSAFE 开启
- 实现 `execution/keyboard.py`：`KeyboardController` 完整实现（type_text/key_press）
- 创建 `tests/test_execution.py`：11 个单元测试，mock pyautogui 不产生真实输入
- 实现 `agent/memory.py`：`Memory` 类，维护最近 N 步动作历史，供 AIRequest 携带
- 实现 `agent/core.py`：`AgentCore` 主循环，截图 → AI 分析 → 动作派发 → 循环，支持 `stop()` 中止和最大步数保护
- 创建 `tests/test_agent_core.py`：6 个单元测试，覆盖正常完成/中止/最大步数/历史传递等场景
- 实现 `gui/main_window.py`：Phase 1 最简主窗口（指令输入、运行/停止按钮、日志区），Agent 循环在 QThread 中运行避免卡 UI，关闭按钮最小化到托盘
- 实现 `gui/tray.py`：系统托盘图标与右键菜单（显示主窗口、退出），单击图标切换窗口显示状态
- 实现 `main.py`：入口，初始化 QApplication、OllamaProvider、AgentCore、MainWindow、TrayIcon
- 新增聊天模式：AI 自动判断输入是闲聊还是任务，闲聊时以活泼可爱风格回复（`chat_response` 动作），任务时正常执行；用户风格自定义留待 Phase 2 设置页实现
- 新增任务旁白：`AIResponse` 增加 `narration` 字段，AI 每步以活泼语气向用户说明正在做什么；`AgentCore.on_message` 回调实时推送到 GUI 日志区
- 完成 `Phase 1` 的全部内容

## 2026-06-01

**完成内容**

- 确定项目定位：AI 桌面助手，作为用户"数字替身"，自动完成桌面重复性任务
- 确定技术栈：Python 3.12+、PySide6、mss、pyautogui、pynput、pywin32
- 确定 AI 策略：本地 Ollama（Qwen2.5-VL，GPU 用户）+ BYOK 云端（无 GPU 用户自填 API Key）
- 确定分发模式：公开免费下载，开发者零 AI 成本
- 确定 GUI 形态：主窗口 + 系统托盘 + 悬浮角色窗口
- 确定开发优先级：先专注 Windows，多平台适配推到 Phase 3
- 初始化 `CLAUDE.md`：完整记录架构、技术栈、安全模型、Git/代码风格/CI 规范、三阶段规划
- 初始化 `README.md`：中英双语项目介绍
