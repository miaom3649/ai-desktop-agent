"""角色性格模块：PersonalityProfile 与加载工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class PersonalityProfile:
    """单个角色性格的完整描述。"""

    id: str
    display_name: str
    chat_prompt: str
    narration_hint: str
    expressions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PersonalityProfile:
        """从 YAML 文件加载性格描述。"""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            id=data["id"],
            display_name=data["display_name"],
            chat_prompt=data["chat_prompt"].strip(),
            narration_hint=data["narration_hint"].strip(),
            expressions=data.get("expressions", {}),
        )

    @classmethod
    def load_default(cls) -> PersonalityProfile:
        """加载默认性格（猫娘女仆）。"""
        default_path = (
            Path(__file__).parent.parent / "config" / "personalities" / "maid_cat.yaml"
        )
        return cls.load(default_path)
