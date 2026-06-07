"""本地模型后端：通过 Ollama 调用本地部署的小模型（聊天 AI 专用）。"""

from __future__ import annotations

import logging

import requests

from ai.base import AIProvider, AIRequest, AIResponse, parse_ai_response

logger = logging.getLogger(__name__)

_OLLAMA_BASE = "http://localhost:11434"


class OllamaProvider(AIProvider):
    """通过 Ollama 调用本地模型（如 Qwen2.5-3B-Instruct + LoRA 微调版小空）。

    性格已烧进权重，system_prompt 可为空；
    过渡期若需要注入，传入 system_prompt 即可。
    """

    def __init__(
        self,
        model: str = "xiaokuu",
        base_url: str = _OLLAMA_BASE,
        system_prompt: str = "",
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._system_prompt = system_prompt
        self._session = requests.Session()

    def complete(self, request: AIRequest) -> AIResponse:
        messages: list[dict] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        for turn in request.conversation_history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": request.task})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }
        resp = self._session.post(
            f"{self._base_url}/api/chat", json=payload, timeout=60
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        logger.debug({"event": "ollama_response", "model": self._model, "content": content})
        return parse_ai_response(content)

    def is_available(self) -> bool:
        """检查 Ollama 服务是否正在运行。"""
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=3)
            return resp.ok
        except requests.RequestException:
            return False

    def cancel(self) -> None:
        self._session.close()
        self._session = requests.Session()
