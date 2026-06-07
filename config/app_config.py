"""应用配置模型：从 settings.yaml 加载，支持持久化写回。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_PATH = Path(__file__).parent / "settings.yaml"


class AIConfig(BaseModel):
    backend: str = "gemini"
    model: str = ""
    api_key: str = ""
    chat_backend: str = "cloud"   # "cloud" | "local"
    local_model: str = "xiaokuu"  # ollama 模型名，chat_backend="local" 时使用


class SafetyConfig(BaseModel):
    require_confirmation_level: int = 2


class HotkeyConfig(BaseModel):
    toggle_floating: str = "ctrl+shift+space"


class ScreenshotConfig(BaseModel):
    max_width: int = 1280
    jpeg_quality: int = 85


class AppConfig(BaseModel):
    ai: AIConfig = Field(default_factory=AIConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    hotkeys: HotkeyConfig = Field(default_factory=HotkeyConfig)
    screenshot: ScreenshotConfig = Field(default_factory=ScreenshotConfig)

    @classmethod
    def load(cls) -> AppConfig:
        """从 settings.yaml 加载配置，文件不存在时写入默认值并返回。"""
        if _CONFIG_PATH.exists():
            raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            return cls.model_validate(raw)
        config = cls()
        config.save()
        return config

    def save(self) -> None:
        """将当前配置写回 settings.yaml。"""
        _CONFIG_PATH.write_text(
            yaml.dump(self.model_dump(), allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
