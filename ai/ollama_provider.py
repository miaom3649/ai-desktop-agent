"""本地 Ollama 后端（默认首选，零 API 成本）。"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ai.base import (
    AGENT_SYSTEM_PROMPT,
    USER_TEMPLATE,
    AIProvider,
    AIRequest,
    AIResponse,
    parse_ai_response,
)

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    """通过 Ollama HTTP API 调用本地视觉模型。"""

    def __init__(
        self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # AIProvider 接口实现
    # ------------------------------------------------------------------

    def complete(self, request: AIRequest) -> AIResponse:
        """调用 Ollama /api/chat，解析返回 JSON 为 AIResponse。"""
        payload = self._build_payload(request)
        raw = self._post("/api/chat", payload)
        return parse_ai_response(raw["message"]["content"])

    def is_available(self) -> bool:
        """检查 Ollama 服务是否在线且目标模型已拉取。"""
        try:
            data = self._get("/api/tags")
            names = [m["name"] for m in data.get("models", [])]
            available = any(n == self.model or n.startswith(self.model + ":") for n in names)
            if not available:
                logger.warning("模型 %s 未在 Ollama 中找到，已有模型：%s", self.model, names)
            return available
        except (urllib.error.URLError, OSError):
            return False

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _build_payload(self, request: AIRequest) -> dict:
        history_text = (
            json.dumps(request.action_history[-10:], ensure_ascii=False, indent=2)
            if request.action_history
            else "（无）"
        )
        windows_text = (
            json.dumps(request.window_list, ensure_ascii=False, indent=2)
            if request.window_list
            else "（无）"
        )
        user_text = USER_TEMPLATE.substitute(
            task=request.task,
            n=min(len(request.action_history), 10),
            history=history_text,
            windows=windows_text,
        )
        history = [
            {"role": t["role"], "content": t["content"]}
            for t in request.conversation_history
        ]
        return {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                *history,
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{request.screenshot_b64}"
                            },
                        },
                    ],
                },
            ],
        }

    def _get(self, path: str) -> dict:
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, payload: dict) -> dict:
        url = self.base_url + path
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
