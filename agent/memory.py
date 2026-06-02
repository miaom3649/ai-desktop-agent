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
    """维护最近 N 步动作历史，供 AI 请求携带。"""

    def __init__(self, max_steps: int = 20) -> None:
        self._history: deque[ActionRecord] = deque(maxlen=max_steps)

    def record(self, action: str, params: dict, result: str, risk_level: int) -> None:
        self._history.append(
            ActionRecord(action=action, params=params, result=result, risk_level=risk_level)
        )

    def to_list(self) -> list[dict]:
        """返回可序列化的历史列表，供 AIRequest 携带。"""
        return [
            {"action": r.action, "params": r.params, "result": r.result, "risk_level": r.risk_level}
            for r in self._history
        ]

    def clear(self) -> None:
        self._history.clear()
