"""云端 BYOK 后端：Gemini / Claude / OpenAI，用户自带 API Key。"""

from __future__ import annotations

from enum import Enum

from ai.base import AIProvider, AIRequest, AIResponse


class CloudBackend(Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    OPENAI = "openai"


class CloudProvider(AIProvider):
    """通过用户提供的 API Key 调用云端模型。"""

    def __init__(self, backend: CloudBackend, api_key: str) -> None:
        self.backend = backend
        self.api_key = api_key

    def complete(self, request: AIRequest) -> AIResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        return bool(self.api_key)
