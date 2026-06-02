"""本地 Ollama 后端（默认首选，零 API 成本）。"""

from __future__ import annotations

from ai.base import AIProvider, AIRequest, AIResponse


class OllamaProvider(AIProvider):
    """通过 Ollama HTTP API 调用本地视觉模型。"""

    def __init__(
        self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"
    ) -> None:
        self.model = model
        self.base_url = base_url

    def complete(self, request: AIRequest) -> AIResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError
