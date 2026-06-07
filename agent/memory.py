"""上下文窗口管理与任务历史记录。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class ActionRecord:
    """单步动作的执行记录。"""

    action: str
    params: dict
    result: str
    risk_level: int


class Memory:
    """维护动作历史（任务内循环用）和对话历史（跨轮次用）。"""

    def __init__(self, max_steps: int = 20) -> None:
        self._history: deque[ActionRecord] = deque(maxlen=max_steps)
        self._conversation: list[dict] = []

    # ------------------------------------------------------------------
    # 动作历史（每次任务开始时清空）
    # ------------------------------------------------------------------

    def record(self, action: str, params: dict, result: str, risk_level: int) -> None:
        self._history.append(
            ActionRecord(action=action, params=params, result=result, risk_level=risk_level)
        )

    def to_list(self) -> list[dict]:
        """返回可序列化的动作历史列表，供 AIRequest 携带。"""
        return [
            {
                "action": r.action,
                "params": r.params,
                "result": r.result,
                "risk_level": r.risk_level,
            }
            for r in self._history
        ]

    def clear(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # 对话历史（跨轮次保留，按下停止后才清空）
    # ------------------------------------------------------------------

    def add_turn(self, role: str, content: str) -> None:
        self._conversation.append({"role": role, "content": content})

    def get_conversation(self) -> list[dict]:
        return list(self._conversation)

    def clear_conversation(self) -> None:
        self._conversation.clear()
