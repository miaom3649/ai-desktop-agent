# 开发日志

## 2026-06-07
- 持续对话模式架构重构：将原单次 `run()` + 每条消息独立 QThread 的一问一答模式，改为基于后台常驻线程 + 消息队列的持续会话架构
  - `agent/core.py`：移除 `run()` / `_run_with_chat_ai()`，新增 `start_session()` / `stop_session()` / `send()`；会话线程从 `_session_queue` 按序取消息，调用 `_process_input()` 完成路由→执行→汇报全流程；`need_clarification` 时任务循环直接阻塞在会话队列上等待用户下一条消息，不再需要独立的 `_pause_event` / `resume()` 机制；回调由 `on_chat_script` 改为 `on_chat_messages`（`list[str]`），新增 `on_thinking`（处理中/空闲指示）和 `on_auth_error`
  - `ai/chat_ai.py`：响应格式从 `script: list[dict]` 改为 `messages: list[str]`，AI 可在单次回复中输出多条消息；系统提示同步更新，描述新格式用法（`……` 可单独作为一条消息表达沉默/犹豫）；`ChatAIResponse` 字段 `script` → `messages`；`report_result()` 返回值改为 `list[str]`；`_extract_messages()` 兼容旧 `script` / `message` 字段
  - `gui/main_window.py`：移除 `_AgentWorker` 类和单次 QThread 模式；输入框和发送按钮**始终可用**，不因 AI 处理中而禁用；新增 `_Bridge(QObject)` 负责跨线程信号传递；`_TypewriterRenderer` 重写为接受 `list[str]`，逐条渲染，消息显示前按内容规则等待（`……` 等 1800ms，其他 600ms）；问候/告别统一通过 `core.send()` 入队，不再单独开 QThread；顶部状态栏显示"小空正在思考…"
- 训练数据管道：移除自动生成脚本 `training/gen_data.py`（改为全手写策略）；`training/annotate.py` 精简为纯手写模式，移除 Gemini 出题分支和 `--no-gen` 标志，默认目标 600 条，随时退出自动续接；`training/train.py` 错误提示从"请先运行 gen_data.py"更新为"请先运行 annotate.py"
- ChatAI 响应格式讨论与定型：调研 Neuro-sama / ChatTTS / Fish Speech / Bark 等项目对停顿和节奏的处理方式，确认业界普遍做法是停顿归 TTS 层（特殊 token），LLM 不直接输出毫秒数；最终定型：模型输出纯文本 `messages` 数组，停顿由 GUI 规则层填充，TTS 由语音模型自身的韵律机制处理

## 2026-06-06
- 本地模型接入准备（Phase 2 小空小模型预埋）：`config/app_config.py` `AIConfig` 新增 `chat_backend`（"cloud"|"local"，默认 cloud）和 `local_model`（ollama 模型名，默认 "xiaokuu"）两个字段；新建 `ai/local_provider.py`，实现 `OllamaProvider`（调用 `localhost:11434/api/chat`，支持 conversation history 和可选 system_prompt，`is_available()` 探测 ollama 服务状态，`cancel()` 重置 Session）；`main.py` `_chat_ai_from_config` 加 `chat_backend == "local"` 分支，切换时只需改 `settings.yaml` 一行，ChatAI 和任务 AI 代码均不受影响；修正 `ai/chat_ai.py` 注释中误写的"Phase 3"为"Phase 2"
- 修复 ChatAI 未接入主循环的 Bug：`main.py` 补充 `_chat_ai_from_config()` 构造函数（以路由系统提示创建独立 CloudProvider），在 `main()` 中实例化并传入 `AgentCore(chat_ai=...)`；`agent/core.py` 新增 `set_chat_ai()` 热替换方法，设置页保存后同步调用；此前 TaskAI 返回空 `chat_response` 但 ChatAI 未运行，导致小空完全静默
- 修正 CLAUDE.md 双 AI 架构章节：小空聊天小模型的计划阶段从"Phase 3"更正为"Phase 2"；明确当前状态为"已接入，以云端 Gemini 作为临时代理运行，等待小模型训练完成后替换"
- 双 AI 架构完整实现（ChatAI 前置路由版）：用户输入全部先经由 ChatAI 判断，ChatAI 决定是闲聊直接回复还是任务转发 TaskAI 执行，TaskAI 完成后再由 ChatAI 生成角色风格汇报语。

- 双 AI 架构初版实现（已被上方版本迭代覆盖，保留记录）：
  - `ai/base.py`：从 `AIResponse` 移除 `narration` 字段；从系统提示模板中删除 narration 规范（4 条规则）、narration 在 JSON 输出格式中的占位、以及各动作描述中的 narration 提示；`chat_response` 动作重新定义为路由信号（params 留空），实际对话由聊天 AI 生成；`parse_ai_response` 同步去掉 narration 提取。
  - `agent/memory.py`：`ActionRecord` 移除 `narration` 字段；`record()` 和 `to_list()` 同步清理，动作历史不再携带 narration。
  - `ai/cloud_provider.py`：三个后端（Gemini / Claude / OpenAI）的图片附件改为条件添加，`screenshot_b64` 为空时跳过，为聊天 AI 无截图调用做铺垫。
  - `ai/chat_ai.py`（新建）：`ChatAI` 类，接收已用角色系统提示配置好的 `AIProvider` 实例；`generate(user_input, history)` 向 Provider 发送无截图请求，提取并返回 script 段落列表；`build_chat_system_prompt(personality)` 工厂函数将性格脚本注入聊天专用模板。Phase 3 换本地小模型时只需替换传入的 Provider。
  - `agent/core.py`：构造函数新增可选参数 `chat_ai: ChatAI | None`；主循环移除所有 narration 相关逻辑（last_narration 变量、push_message 推送、记录时的 narration 字段）；`chat_response` 分支：若 chat_ai 存在则调用 `chat_ai.generate()` 生成实际对话，否则退回 Task AI 的 params（向后兼容）。
  - 全部 52 个测试通过，pyright 0 errors。


- 架构决策（双 AI）：深入研究 Neuro-sama 架构后，确定采用任务 AI + 聊天 AI 分离的双 AI 架构，核心原因如下：

  **根本矛盾**：大模型与小模型在角色扮演上存在不可调和的能力悖论——
  - 大模型（Gemini / Claude / GPT-4）具备足够的视觉理解、多步骤推理和任务执行能力，但个人开发者无法对其进行微调；只能靠 prompt engineering 维持角色风格，而 prompt 方案存在天花板：模型会对示例做模式匹配而非真正内化性格，遇到未见过的情境就退回默认中性语气，无法从根本上解决角色一致性问题。
  - 小模型（Qwen2.5-3B 等）可以通过 LoRA 微调将角色性格直接烧进权重，语言风格高度稳定且可控；但其推理能力远不足以胜任截图理解、多步骤桌面操作规划等任务，强迫小模型做任务执行只会得到 Neuro-sama 级别的失误率——在娱乐场景可接受，在真实桌面自动化中不可接受。

  **解决方案**：将两种能力需求分配给两个独立模型——任务 AI（Gemini）静默执行桌面操作，只输出结构化 JSON；聊天 AI（小空专用小模型）只负责对话和情感响应，只处理纯文字输入输出，完全不接触视觉和任务逻辑。两者各司其职，互不干扰。

  同步移除任务执行过程中的每步 narration 输出（任务 AI 静默执行），聊天 AI 仅在用户主动对话时介入；基础模型选 Qwen2.5-3B-Instruct，训练数据通过大模型蒸馏（Claude Sonnet + 小空 prompt）批量生成后人工筛选，微调方法为 Unsloth + QLoRA；已更新 CLAUDE.md 双 AI 架构设计章节和 Phase 2 规划
- 性格系统精简：将 `narration_hint` 从 `config/personalities/maid_cat.yaml` 完全移除，narration 运营规则统一收归 `ai/base.py` 的 `_SYSTEM_PROMPT_TEMPLATE`；`ai/personality.py` `PersonalityProfile` 移除 `narration_hint` 字段；`build_system_prompt()` 简化为单占位符注入（仅 `<<CHAT_PROMPT>>`）
- 小空角色描述调整：新增正面情绪词禁用规则（"很高兴""荣幸""欣慰"不出现在小空口中）；反感表达改为无礼貌铺垫直接说出；`chat_prompt` 加入 14 条对话示例用于锚定语气和措辞风格，覆盖被关心、摸头、吃醋、被冷落、游戏、主人夸别人、被质疑、犯错、被夸奖、喜欢被点破、独处、被问是否喜欢主人、讨厌的人、主人说要离开等典型场景
- 性格系统模块化：将角色性格从系统提示硬编码中完全抽离，实现一键换性格的设计。新增 `ai/personality.py`（`PersonalityProfile` dataclass，含 `load(path)` / `load_default()` 类方法）；新增 `config/personalities/maid_cat.yaml`（猫娘女仆完整性格脚本，含 `chat_prompt` / `narration_hint` / `expressions` 三块）；`ai/base.py` 将 `AGENT_SYSTEM_PROMPT` 拆解为 `_SYSTEM_PROMPT_TEMPLATE`（含 `<<CHAT_PROMPT>>` / `<<NARRATION_HINT>>` 占位符）+ `build_system_prompt(personality)` 注入函数，向后兼容导出维持不变；`ai/cloud_provider.py` `__init__` 新增 `system_prompt` 参数；`main.py` 启动时 `load_default()` 加载性格并注入 Provider，设置页保存时同步替换；切换性格只需添加新 YAML，无需改动任何代码；同步在 CLAUDE.md 记录性格系统设计规范和 `chat_response` 分段渲染方案（后者暂不实现）
- 新增重复动作守护机制：`agent/core.py` 在每步执行后对非 terminal action 检测连续相同 `(action, params)` 组合（严格相等），达到阈值时往 `instruction` 追加 `[系统提示]` 要求 AI 自行判断是否 `task_done` 或 `need_clarification`；阈值初始为 3，用户回复"继续"后 ×2（3→6→12…），回复"再做N次"后重置为 N；每次 `need_clarification` 回复后 `count` 清零重新计数；动作变化时 `count`/`threshold` 同步重置；新增 4 个测试覆盖触发、重置、阈值翻倍、"再做N次"四个场景
- 修复 `need_clarification` 双条显示：AI 对 terminal action 同时填写了 `narration` 和专属消息字段（`question`/`message`/`summary`），导致 GUI 显示两条相近文本；修复方式：系统提示 narration 说明补充 `need_clarification` 时留空；`agent/core.py` narration 推送条件从 `!= "task_done"` 改为 `not in _TERMINAL` 做兜底

## 2026-06-05
- `need_clarification` 改为中途暂停信号：不再终止任务循环，改为 `threading.Event` + `queue.Queue` 实现阻塞等待；`AgentCore` 新增 `on_pause` 回调和 `resume(reply)` 方法；`stop()` / `cancel()` 同时 `set()` 事件防止暂停时卡死；`_AgentWorker` 新增 `paused` Signal，`MainWindow` 新增 `_on_paused` 槽，暂停时重新开放输入框，主人回复后调 `core.resume()` 继续循环；同步更新 `test_agent_core.py`，将原 `test_stops_on_need_clarification` 拆为 `test_need_clarification_pauses_and_resumes` 和 `test_need_clarification_stop_while_paused`
- 盘点感知层与窗口管理实现状态：`perception/window.py` 的 Windows UIA 感知已完整实现（`list_windows` / `get_active_ui_tree` / `list_installed_apps` / `get_desktop_icons`），`agent/core.py` 每步传 `window_list` 给 AI 并支持 `get_ui_tree` / `get_installed_apps` / `get_desktop_icons` / `focus_window` / `open_app` 五个动作，测试覆盖完整；`execution/window_ctrl.py` 目前仅为 Phase 3 多平台适配预留的抽象骨架（方法全部 `NotImplementedError`），`focus_window` 动作逻辑暂时内联在 `agent/core.py` dispatch 层（直接调 win32gui）
- Phase 2 设置页：新增 `config/app_config.py`（pydantic BaseModel，`load()`/`save()` 读写 `settings.yaml`）；`gui/settings_page.py` 实现 QDialog，含 Provider 下拉、模型输入、API Key 密码框（含显示/隐藏）和首次启动引导模式（不可关闭）；托盘右键菜单新增"设置"项；`AgentCore.set_provider()` 支持热替换 Provider；`main.py` 重构为从 `AppConfig` 加载配置，无 Key 时自动弹引导对话框，支持环境变量覆盖（开发便利）
- 告别情绪继承：停止按钮触发的告别指令从通用的"以角色身份向主人告别"改为要求 AI 回顾 `conversation_history` 中本次对话的情绪氛围，以贴合当前情境的情绪告别；若对话中积累了负面情绪（如多次无效澄清、被无视），告别时自然流露，禁止强行切换为温暖中性语气；同时保留对正面情绪的继承规则
- 去除 `need_clarification` 固定前缀：`agent/core.py` 原来在 `need_clarification` 响应前硬拼 `"不是很确定喵："` 前缀，改为直接返回 AI `question` 字段的完整内容；同步修改 `_ask_failure_message` 的兜底返回路径；系统提示 `question` 字段说明同步更新为"须以角色语气写完整，不加任何固定前缀"
- `need_clarification` 情绪递增规则：系统提示新增——当 `conversation_history` 中同一模糊指令已多次出现且每次均以澄清问题回应时，须随重复次数递增情绪（不耐烦→明显生气），第三次起直接表达生气
- 修复 `USER_TEMPLATE` 标记：将 `主人说：$task` 改为 `【当前输入】$task`，并在系统提示中同步说明该标记仅代表本轮原始指令；避免 AI 误将 `【当前任务】` 类关键词联想为任务模式，同时与 `conversation_history` 中的 `[主人]` 前缀视觉区分，防止 AI 混淆当前指令与历史记录
- 修复 `need_clarification` 误触发：新增"重复指令确认"规则后，AI 误将 action_history 中本轮已执行的动作认定为"主人曾发出过相同指令"，导致任务执行到最后一步时错误发出 need_clarification 而非 task_done；修复方式：明确判断依据是 conversation_history 中 user 角色的历史消息（而非 action_history），并规定 action_history 非空时（任务执行中）禁止触发此规则：新增"重复指令确认"规则后，AI 误将 action_history 中本轮已执行的动作认定为"主人曾发出过相同指令"，导致任务执行到最后一步时错误发出 need_clarification 而非 task_done；修复方式：明确判断依据是 conversation_history 中 user 角色的历史消息（而非 action_history），并规定 action_history 非空时（任务执行中）禁止触发此规则
- 优化 narration 过渡词：明确"严禁相邻两步使用相同过渡词"并给出反例（"接下来喵…接下来喵"）及可替换词表；补充正常步骤中对动作描述要极度精简（可省略主谓语，如"接下来喵，文本框喵"）
- 优化 narration 语气：正常步骤加入过渡词/反应词/感叹词指引，体现思考感；重试步骤新增"体现真实情绪或安抚主人"的角色意识要求，但不强制每次都包含
- 修正 `plan_complete` prompt 语义：将描述从"所有必要物理操作是否已全部派发"改为"首次完整尝试是否已执行完毕"，并明确设为 true 后必须在后续所有步骤保持 true 不得改回；原措辞导致 AI 将"必要"理解为"足以产生视觉效果"，看不到截图变化就始终输出 false，令 latch 守护无法触发；新增序列示例（步骤1点击 plan_complete=true → 步骤2 wait 维持 true → 步骤3 重试维持 true → 守护触发）
- 新增 503 自动重试：`CloudProvider._post` 捕获 HTTP 503，最多重试 3 次（间隔 2 秒），重试信息仅打印到终端（`logger.warning`），不影响对话日志；超出重试次数后抛出异常；新增测试 `TestRetry503` 覆盖重试成功和超限两个场景
- 移除 `toggle_oscillation` 和 `action_loop` 两个守护：前者被 `plan_complete_latch` 覆盖，后者不区分有效/无效重复会误伤需要连续动作的合法任务；守护体系精简为三重：`plan_complete_latch`、`action_stuck`、`max_steps`
- 修复 `_push_message` 前缀：旁白消息从 `"AI: "` 改为 `"[AI] "`，与对话日志前缀规范一致
- 移除 `plan_complete` 硬守护机制，改为 AI 自我监督：删除 `AIResponse.plan_complete` 字段及 `_loop` 中的 latch 计数逻辑；系统提示新增自我监督指令，要求 AI 回顾 `action_history`，若同一目标经过 10 次或以上完整尝试（含不同策略）均失败，必须主动发出 `need_clarification` 请求介入；原机制依赖 AI 自我报告且与 `consecutive_failures` 覆盖范围高度重叠，新方案能覆盖每轮策略不同导致连续动作计数无法累积的盲区
- 主窗口加设置按钮：`MainWindow` 接受 `on_settings` 回调，输入行右侧新增"设置"按钮，运行时不禁用
- 中断按钮：主窗口新增"中断"按钮，点击后立刻调用 `core.cancel()`；`AgentCore.cancel()` 同时设 `_running=False` 并调 `CloudProvider.cancel()`；`CloudProvider` 从 `urllib` 迁移到 `requests.Session`，`cancel()` 关闭 Session 使正在等待的 HTTP 请求立刻抛出 `ConnectionError`，实现真正的即时中断；`_on_finished` 检测 `_interrupting` 标志，中断后静默丢弃结果
- API Key 无效时弹窗：`CloudProvider._post` 在 HTTP 401/403 时抛出 `ProviderAuthError`；`_AgentWorker` 捕获后通过 `auth_error` Signal 通知主线程；`MainWindow` 弹出警告对话框，提供"去设置"快捷入口
- 设置页重置按钮：底部左侧新增"重置所有设置"按钮，确认后立即还原默认值并写入文件，同步热替换 Provider
- `settings.yaml` 纳入 `.gitignore`，从 git 追踪移除；`AppConfig.load()` 改为文件不存在时自动创建默认配置文件
- Phase 2 设计决策：确定角色系统技术方案——悬浮窗角色由 Live2D（Cubism Web SDK）渲染，通过 `QWebEngineView` 嵌入本地 HTML，Python 经 JS Bridge 驱动；`AIResponse` 新增 `expression` 字段，AI 从 10-15 个预定义语义标签（idle/thinking/happy/done 等）中选择，`ExpressionSelector` 维护标签→Cubism 动作映射；TTS 语音输出与真唇同步（narration → TTS 音频 → 实时音量振幅驱动 `PARAM_MOUTH_OPEN_Y`）一并纳入 Phase 2，与 Live2D/表情系统作为一个完整角色 feature 同步交付；同步更新 CLAUDE.md Phase 2 目标和悬浮窗技术描述

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
