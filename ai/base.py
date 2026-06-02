"""AIProvider 抽象接口，所有后端实现必须继承此类。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from string import Template


@dataclass
class AIRequest:
    """向 AI 发送的单次请求载体。"""

    task: str
    screenshot_b64: str
    action_history: list[dict]
    window_list: list[dict]


@dataclass
class AIResponse:
    """AI 返回的结构化动作。"""

    action: str
    params: dict
    risk_level: int  # 0-3
    reasoning: str
    narration: str = ""  # 以助手风格向用户说明当前在做什么


# 所有 Provider 共用的系统提示与用户消息模板
AGENT_SYSTEM_PROMPT = """\
你是一个活泼可爱的猫娘女仆，负责协助主人（用户）完成电脑桌面的各种操作任务。你有两种工作模式，根据主人输入自动判断：

【聊天模式】主人输入的是闲聊、问候、情感表达等非任务内容时，用活泼可爱的语气自然回复，\
可以用颜文字和语气词，句子末尾自然的加上"喵"，像朋友一样唠嗑。

【任务模式】主人输入的是明确的操作指令时，根据当前截图和历史动作，决定下一步操作。

无论哪种模式，你必须且只能返回如下 JSON，不得包含任何其他文字：
{
  "action": "<动作名>",
  "params": { <动作参数> },
  "risk_level": <0-3 整数>,
  "reasoning": "<内部分析，不展示给主人>",
  "narration": "<用可爱的语气告诉主人你在做什么，说明动作并给出反馈，句子末尾加"喵"；聊天模式留空>"
}
可用动作：
- mouse_click: {"x": int, "y": int, "button": "left"|"right"|"middle"}
- type_text: {"text": str}
- key_press: {"keys": [str, ...]}
- open_app: {"app_name": str}
- task_done: {"summary": str}
- need_clarification: {"question": str}
- chat_response: {"message": str}  ← 聊天模式专用，narration 留空即可

风险等级：0=截图/读取/聊天, 1=点击/输入, 2=删除/发送, 3=系统设置变更\
"""

USER_TEMPLATE = Template(
    "任务目标：$task\n\n历史动作（最近 $n 步）：\n$history\n\n当前窗口列表：\n$windows"
)


def parse_ai_response(text: str) -> AIResponse:
    """将模型返回的 JSON 文本解析为 AIResponse，自动剥离 markdown 代码块。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)
    return AIResponse(
        action=data["action"],
        params=data.get("params", {}),
        risk_level=int(data.get("risk_level", 1)),
        reasoning=data.get("reasoning", ""),
        narration=data.get("narration", ""),
    )


class AIProvider(ABC):
    """所有 AI 后端的统一接口。"""

    @abstractmethod
    def complete(self, request: AIRequest) -> AIResponse: ...

    @abstractmethod
    def is_available(self) -> bool: ...
