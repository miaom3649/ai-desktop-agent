# 开发日志

## 2026-06-05
- 修正 `plan_complete` prompt 语义：将描述从"所有必要物理操作是否已全部派发"改为"首次完整尝试是否已执行完毕"，并明确设为 true 后必须在后续所有步骤保持 true 不得改回；原措辞导致 AI 将"必要"理解为"足以产生视觉效果"，看不到截图变化就始终输出 false，令 latch 守护无法触发；新增序列示例（步骤1点击 plan_complete=true → 步骤2 wait 维持 true → 步骤3 重试维持 true → 守护触发）
- 新增 503 自动重试：`CloudProvider._post` 捕获 HTTP 503，最多重试 3 次（间隔 2 秒），重试信息仅打印到终端（`logger.warning`），不影响对话日志；超出重试次数后抛出异常；新增测试 `TestRetry503` 覆盖重试成功和超限两个场景
- 移除 `toggle_oscillation` 和 `action_loop` 两个守护：前者被 `plan_complete_latch` 覆盖，后者不区分有效/无效重复会误伤需要连续动作的合法任务；守护体系精简为三重：`plan_complete_latch`、`action_stuck`、`max_steps`
- 修复 `_push_message` 前缀：旁白消息从 `"AI: "` 改为 `"[AI] "`，与对话日志前缀规范一致

## 2026-06-04
- 修复 `plan_complete` 语义误判：原 prompt 用"成功执行"表述，AI 将其理解为"视觉上已确认任务完成"，导致只要截图仍显示目标未变化就始终输出 `false`。将定义改为"物理操作是否已全部派发（不看视觉结果）"，并附上示例（点击图标后即使文件列表仍可见，也应设为 true），让 AI 能在操作发出后立即声明完成
- 修复 `plan_complete` 守护逻辑：AI 在 retry 步会将 plan_complete 重置回 false（视觉任务未完成），导致守护永不计数。改为在 agent 侧维护 `plan_complete_latched`——一旦某步 plan_complete=true 即永久锁存，后续无论 AI 输出何值，只要再做非观察性物理动作就计数；`wait` 仍排除在外。触发节奏：click(pc=true→latch)→wait(不计)→retry click(latch触发守护)
- 补充日志字段：`ai_response` 日志新增 `plan_complete` 字段，方便排查 AI 是否正确更新该状态
- 新增测试 `test_plan_complete_latch_catches_retry_even_if_ai_resets_to_false`：验证 AI 在 retry 步输出 pc=false 时 latch 仍能触发守护
- 移除 Ollama 本地模型支持：删除 `ai/ollama_provider.py` 及对应测试 `tests/test_ollama_provider.py`，项目统一使用云端 BYOK 后端（Gemini / Claude / OpenAI）
- 完善 AI 命名规则：系统提示新增第 ③ 条——禁止 AI 自行取名，始终用"喵"自称；仅当主人在对话历史中明确赐名后才可使用该名字；被问及名字时需说明暂无名字并表明自己的桌面助手身份，同时询问主人是否想要取名
- 优化告别指令：停止按钮触发的告别从 `"再见"` 改为 `"[系统] 主人即将离开，请以角色身份向主人告别。"`，明确区分系统信号与用户输入
- 统一对话日志前缀：用户指令显示为 `[主人] ...`，同时以此前缀发送给 AI（与 `[系统]` 保持一致）；AI 回复显示为 `[AI] ...`
- 新增 `plan_complete` 循环守护：`AIResponse` 新增 `plan_complete: bool` 字段；AI 在每步回顾历史动作，若任务所需全部步骤均已执行则设为 `true`；`_loop` 中维护 `plan_complete_count`，连续两次 `true` 但未发出终止动作时打断并请主人介入，解决 AI 重复执行已完成步骤的问题
- 修复 AI 误将重复出现的 `task` 字段理解为主人在重复下令：系统提示补充说明 `[主人]` 标记的任务内容是原始指令而非实时命令，进度判断应以历史动作记录为依据

## 2026-06-03
- 修复跟进问句被误判为任务模式的问题：将 `USER_TEMPLATE` 的 `任务目标：` 标签改为中性的 `主人说：`，避免模型将聊天跟进句（如"现在呢"）强制套入任务框架导致错误触发 `need_clarification`


- 修复切换振荡问题：`agent/core.py` 在 dispatch 前新增同坐标点击守护——统计 action history 中相同 `(mouse_click, x, y)` 的出现次数，≥3 次时触发 `toggle_oscillation` 日志并调用 `_ask_failure_message` 请求主人介入；原有的 `consecutive_same_type` 计数器会被 `wait` 动作打断，无法覆盖"点击-等待-点击"的振荡模式，新守护独立于该计数器



- 修复 Agent 在成功执行关闭/删除等操作后错误触发 `need_clarification` 的问题：在系统提示中补充推理规则，要求 AI 结合历史动作的预期效果判断任务是否完成——若已执行对应操作且目标对象在截图中已消失/状态已变更，应使用 `task_done` 而非发起澄清询问
- 修复从系统托盘唤起主窗口时重复发送"新对话开始"打招呼指令的问题：`MainWindow` 新增 `_greeted` 标志，`showEvent` 仅在首次显示且无正在运行的任务时触发问候，后续托盘唤起不再重复触发
- 鼠标操作改为可见动画：`execution/mouse.py` 新增 `MOVE_DURATION = 0.4` 常量，所有操作（点击、移动、拖拽、滚轮）执行前先以平滑动画将光标移至目标位置，效果如同远程桌面操控
- 新增 `wait` 动作：AI 可主动等待 UI 更新后再截图确认，解决点击切换类按钮后截图未及时反映新状态导致反复重试振荡的问题；`agent/core.py` dispatch 层执行 `time.sleep` 并写入结构化日志；系统提示新增三阶段处理策略（wait 观察 → 确认重试 → need_clarification 请主人介入）

- 完善 `gui/main_window.py` 停止按钮状态机：初始为禁用，运行开始时启用，点击停止后禁用并保持灰色直到下次运行
  - 修复 `_set_running(False)` 无条件重新启用停止按钮的问题，改为仅在未按过停止时才重新启用（通过 `_clear_on_next_run` 标志判断）
  - 修复信号连接泄漏：每次运行后在 `_cleanup_thread` 中断开 `_start_requested` 与旧 worker 的连接
- 新增告别功能：按下停止按钮后自动向模型发送"再见"，模型以猫娘风格道别；任务运行中按停止则等当前步骤完成后再发告别
  - 修复双重告别 bug：空闲时直接调用 `_start_farewell()` 前未重置 `_farewell_pending` 标志，导致告别完成后 `_on_finished` 再次触发告别
- 新增终端日志：对话开始时打印 `conversation_start`，按下停止时打印 `conversation_end`，与 `agent.core` 的结构化日志风格一致
- 实现多轮对话历史：`agent/memory.py` 新增 `add_turn / get_conversation / clear_conversation`；`AIRequest` 新增 `conversation_history` 字段；`AgentCore.run()` 每轮结束后记录 user/assistant 对话对，暴露 `reset_conversation()`；Ollama / Gemini / Claude / OpenAI 四个后端均在请求中携带历史消息
- 修复 `parse_ai_response` 中的 `Invalid \escape` 错误：用 `re.sub` 替换模型偶发的非法转义序列（如 `\喵`）为合法的 `\\`
- 修复重复告别消息：`agent/core.py` 对 `task_done` 动作跳过 `narration` 推送（summary 本身即最终消息）；`main_window._on_finished` 去掉"完成："前缀，直接显示结果文本；系统提示注明 `chat_response`/`task_done` 时 narration 留空
- 优化猫娘语气规则：① 用"喵"自称，不用"我"；② 句尾语气词/疑问词可替换为"喵"或保留后补"喵"，以自然好听为准，避免"喵喵"连续重叠；③ 句末"喵"必须在标点之前（"你好喵！"而非"你好！喵"）
- `need_clarification` 动作限定仅用于任务模式下指令不明确时，聊天/情感输入不得使用，防止模型对情感表达错误触发澄清
- 将澄清提示前缀从"需要澄清："改为"不是很确定喵："以符合角色语气
- 新增启动招呼：应用首次显示时通过 `showEvent` + `QTimer.singleShot(200ms)` 触发 `_start_greeting()`，AI 主动向主人打招呼；`_start_greeting` 会先重置对话历史，再发送系统内部指令让模型开场问好

## 2026-06-02

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
- 实现 `ai/cloud_provider.py`：`CloudProvider` 支持 Gemini / Claude / OpenAI 三个云端 BYOK 后端，完成 Phase 1 最后一项
  - 将系统提示、用户消息模板、JSON 解析逻辑提升到 `ai/base.py` 共享，消除两个 Provider 的重复代码
  - 创建 `tests/test_cloud_provider.py`：12 个单元测试，覆盖三后端 complete/鉴权/默认模型
- 修复 `gui/main_window.py`：`_AgentWorker.run()` 捕获异常后通过 `finished` 信号传回 UI，避免 Ollama 未运行时线程崩溃导致界面卡死
- 修复 `main.py`：注册 `SIGINT` + 200ms `QTimer` 心跳，使 Ctrl+C 能正常终止 Qt 应用

## 2026-06-01

- 确定项目定位：AI 桌面助手，作为用户"数字替身"，自动完成桌面重复性任务
- 确定技术栈：Python 3.12+、PySide6、mss、pyautogui、pynput、pywin32
- 确定 AI 策略：本地 Ollama（Qwen2.5-VL，GPU 用户）+ BYOK 云端（无 GPU 用户自填 API Key）
- 确定分发模式：公开免费下载，开发者零 AI 成本
- 确定 GUI 形态：主窗口 + 系统托盘 + 悬浮角色窗口
- 确定开发优先级：先专注 Windows，多平台适配推到 Phase 3
- 初始化 `CLAUDE.md`：完整记录架构、技术栈、安全模型、Git/代码风格/CI 规范、三阶段规划
- 初始化 `README.md`：中英双语项目介绍
