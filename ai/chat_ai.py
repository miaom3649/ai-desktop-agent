"""聊天 AI：小空角色对话生成器与任务路由器。

职责：
1. 接收所有用户输入，判断是闲聊还是任务指令
2. 闲聊直接生成角色回复；任务指令提炼后转发给 TaskAI
3. TaskAI 执行完毕后，将结果包装为角色风格的汇报语

当前实现：以云端 Provider 代理，使用角色专属系统提示。
目标实现（Phase 2）：替换为 Qwen2.5-3B-Instruct + LoRA 微调的本地模型（OllamaProvider）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.base import AIProvider, AIRequest
from ai.personality import PersonalityProfile

# ──────────────────────────────────────────────
# 路由系统提示
# ──────────────────────────────────────────────

ROUTER_SYSTEM_TEMPLATE = """\
<<CHAT_PROMPT>>

你是主人的对话入口。主人的所有输入都先到你这里，由你判断意图并路由。

你必须且只能返回如下 JSON 之一，不得包含其他文字：

【闲聊 / 情感 / 问答 / 意图不明确时】
{
  "action": "chat_response",
  "params": {"script": [{"text": "...", "pause": <毫秒>}, ...]},
  "risk_level": 0,
  "reasoning": ""
}

【明确的电脑操作指令】
{
  "action": "route_to_task",
  "params": {
    "task_instruction": "<单句、动词开头的清晰任务描述>",
    "script": [{"text": "...", "pause": <毫秒>}, ...]
  },
  "risk_level": 0,
  "reasoning": ""
}

【任务执行结果通报（输入以 "[任务完成]" 或 "[任务失败]" 开头）】
固定返回 chat_response，以角色语气向主人汇报结果，script 须有实质内容。

【判断规则】
- 操作指令：含明确的电脑操作意图（打开/关闭/搜索/新建/发送/删除/下载/截图……）
- 其他一切（对话/情感/问候/询问意见/模糊表达）：返回 chat_response

【route_to_task 的 script】
接受任务时的简短角色回应（如"好的喵，马上去做"），可为空列表 []。

【script 分段规范】
将回复拆成若干片段，每片段是一口气能说完的短句或词组。\
在思考词、转折词、语气词后单独成段并赋予较长停顿。
pause 取值（毫秒）：斟酌时 1000-2000；语气词习惯 300-600；句中节奏 0-300；句末 400-700；末段 0。
默认使用中文回复。\
"""


def build_router_system_prompt(personality: PersonalityProfile) -> str:
    """将性格脚本注入路由系统提示模板。"""
    return ROUTER_SYSTEM_TEMPLATE.replace("<<CHAT_PROMPT>>", personality.chat_prompt)


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class ChatAIResponse:
    """ChatAI.classify() 的返回值。"""

    mode: str  # "chat" | "task"
    script: list[dict] = field(default_factory=list)  # 聊天回复 或 接受任务的旁白
    task_instruction: str = ""  # mode == "task" 时有效，提炼后的任务指令


# ──────────────────────────────────────────────
# ChatAI 主体
# ──────────────────────────────────────────────


class ChatAI:
    """小空角色对话生成器与任务路由器。

    接收一个已用路由系统提示配置好的 AIProvider 实例。
    Phase 2 换本地模型时，只需替换传入的 Provider（OllamaProvider）。
    """

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def classify(self, user_input: str, conversation_history: list[dict]) -> ChatAIResponse:
        """判断用户输入是闲聊还是任务，返回路由结果。"""
        request = AIRequest(
            task=user_input,
            screenshot_b64="",
            action_history=[],
            window_list=[],
            conversation_history=conversation_history,
        )
        response = self._provider.complete(request)

        if response.action == "route_to_task":
            return ChatAIResponse(
                mode="task",
                script=response.params.get("script", []),
                task_instruction=response.params.get("task_instruction", user_input),
            )

        # chat_response 或意外 action，均视为闲聊
        return ChatAIResponse(
            mode="chat",
            script=response.params.get("script", []),
        )

    def report_result(
        self, outcome: str, success: bool, conversation_history: list[dict]
    ) -> list[dict]:
        """接收 TaskAI 执行结果，生成角色风格的汇报脚本。"""
        status = "任务完成" if success else "任务失败"
        request = AIRequest(
            task=f"[{status}] {outcome}",
            screenshot_b64="",
            action_history=[],
            window_list=[],
            conversation_history=conversation_history,
        )
        response = self._provider.complete(request)
        return response.params.get("script", [])
