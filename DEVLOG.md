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
