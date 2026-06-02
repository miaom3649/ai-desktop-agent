# 开发日志

## 2026-06-02

**完成内容**

- 创建完整目录骨架，覆盖 CLAUDE.md 中规划的所有模块
- `agent/`：`core.py`（主循环骨架）、`planner.py`、`memory.py`
- `ai/`：`base.py` 定义 `AIProvider` 抽象接口及 `AIRequest` / `AIResponse` 数据类；`ollama_provider.py`、`cloud_provider.py` 空实现占位
- `perception/`：`screen.py`（截图 + 压缩，MAX_WIDTH=1280）、`window.py`（`WindowInfo` 数据类）
- `execution/`：`mouse.py`、`keyboard.py`（均带 `dry_run` 参数）、`window_ctrl.py`（跨平台抽象）
- `safety/`：`guard.py`，定义 `RiskLevel` 枚举（L0–L3）
- `gui/`：`main_window.py`、`tray.py`、`floating_widget.py`、`settings_page.py`；`assets/character/` 和 `assets/icons/` 占位
- `config/settings.yaml`：AI 后端、截图参数、风险阈值、热键默认配置
- `main.py`：入口占位

**遗留待处理**

- `pyproject.toml` 尚未创建（依赖声明、ruff/pyright 配置）
- GitHub Actions CI 流水线尚未配置
- 所有模块方法均为 `raise NotImplementedError`，Phase 1 实现从 `perception/screen.py` 开始

## 2026-06-01

**完成内容**

- 确定项目定位：AI 桌面助手，作为用户"数字替身"，自动完成桌面重复性任务
- 确定技术栈：Python 3.11+、PySide6、mss、pyautogui、pynput、pywin32
- 确定 AI 策略：本地 Ollama（Qwen2.5-VL，GPU 用户）+ BYOK 云端（无 GPU 用户自填 API Key）
- 确定分发模式：公开免费下载，开发者零 AI 成本
- 确定 GUI 形态：主窗口 + 系统托盘 + 悬浮角色窗口
- 确定开发优先级：先专注 Windows，多平台适配推到 Phase 3
- 初始化 `CLAUDE.md`：完整记录架构、技术栈、安全模型、Git/代码风格/CI 规范、三阶段规划
- 初始化 `README.md`：中英双语项目介绍
