"""AIProvider 抽象接口，所有后端实现必须继承此类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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


class AIProvider(ABC):
    """所有 AI 后端的统一接口。"""

    @abstractmethod
    def complete(self, request: AIRequest) -> AIResponse: ...

    @abstractmethod
    def is_available(self) -> bool: ...
