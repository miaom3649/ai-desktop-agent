"""聊天 AI：小空角色对话生成器与任务路由器。

职责：
1. 接收所有用户输入，判断是闲聊还是任务指令
2. 闲聊直接生成角色回复（单条完整消息）；任务指令提炼后转发给 TaskAI
3. TaskAI 执行完毕后，将结果包装为角色风格的汇报语

当前实现：以云端 Provider 代理，使用角色专属系统提示。
目标实现（Phase 2）：替换为 Qwen2.5-3B-Instruct + LoRA 微调的本地模型（OllamaProvider）。
"""

from __future__ import annotations

from dataclasses import dataclass

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
  "params": {"message": "完整的回复内容"},
  "expression": "<从可用表情中选一个>",
  "risk_level": 0,
  "reasoning": ""
}

【明确的电脑操作指令】
{
  "action": "route_to_task",
  "params": {
    "task_instruction": "<单句、动词开头的清晰任务描述>",
    "message": "<接受任务时的简短角色回应，可为空字符串>"
  },
  "expression": "<从可用表情中选一个>",
  "risk_level": 0,
  "reasoning": ""
}

【任务执行结果通报（输入以 "[任务完成]" 或 "[任务失败]" 或 "[需要澄清]" 开头）】
固定返回 chat_response，以角色语气向主人汇报或转达，message 须有实质内容。

【判断规则】
- 操作指令：含明确的电脑操作意图（打开/关闭/搜索/新建/发送/删除/下载/截图……）
- 其他一切（对话/情感/问候/询问意见/模糊表达）：返回 chat_response

【可用表情】<<EXPRESSIONS>>
无后缀 = 身体部位（耳朵/尾巴）有细微变化，表情克制；_full = 表情与身体部位都明显变化。
每条回复必须从中选一个最贴合当前情绪的表情填入 expression 字段。

默认使用中文回复。\
"""


def build_router_system_prompt(personality: PersonalityProfile) -> str:
    """将性格脚本与表情列表注入路由系统提示模板。"""
    expression_list = ", ".join(personality.expressions.keys())
    return ROUTER_SYSTEM_TEMPLATE.replace("<<CHAT_PROMPT>>", personality.chat_prompt).replace(
        "<<EXPRESSIONS>>", expression_list
    )


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class ChatAIResponse:
    """ChatAI.classify() / report_result() 的返回值。"""

    mode: str  # "chat" | "task"
    message: str = ""
    task_instruction: str = ""  # mode == "task" 时有效


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
                message=self._extract_message(response.params),
                task_instruction=response.params.get("task_instruction", user_input),
            )

        return ChatAIResponse(
            mode="chat",
            message=self._extract_message(response.params),
        )

    def report_result(self, outcome: str, success: bool, conversation_history: list[dict]) -> str:
        """接收 TaskAI 执行结果，生成角色风格的汇报消息。"""
        status = "任务完成" if success else "任务失败"
        request = AIRequest(
            task=f"[{status}] {outcome}",
            screenshot_b64="",
            action_history=[],
            window_list=[],
            conversation_history=conversation_history,
        )
        response = self._provider.complete(request)
        return self._extract_message(response.params)

    @staticmethod
    def _extract_message(params: dict) -> str:
        """从 params 提取消息文本，兼容旧 messages / script 字段。"""
        msg = params.get("message")
        if isinstance(msg, str) and msg:
            return msg
        msgs = params.get("messages")
        if isinstance(msgs, list) and msgs:
            return str(msgs[0])
        script = params.get("script")
        if isinstance(script, list) and script:
            return script[0].get("text", "")
        return ""
