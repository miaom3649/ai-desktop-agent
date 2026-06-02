"""动作风险评估与用户确认交互。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0       # 静默执行
    MEDIUM = 1    # 自动执行 + 日志
    HIGH = 2      # GUI 确认对话框
    CRITICAL = 3  # 确认 + 二次确认


@dataclass
class ActionGuard:
    """在执行前评估动作风险等级，并按规则决定是否需要确认。"""

    def assess(self, action: str, params: dict) -> RiskLevel:
        raise NotImplementedError

    def request_confirmation(self, action: str, params: dict, risk: RiskLevel) -> bool:
        """返回 True 表示用户批准执行。"""
        raise NotImplementedError
