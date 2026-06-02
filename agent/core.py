"""Agent 主循环：截图 → AI 分析 → 执行动作 → 循环。"""

from __future__ import annotations


class AgentCore:
    """驱动整个感知-认知-执行循环。"""

    def run(self, instruction: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
