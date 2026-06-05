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
        self, model: str = "qwen3-vl:4b", base_url: str = "http://localhost:11434"
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
        thinking = raw["message"].get("thinking", "")
        if thinking:
            print(f"\n[模型思考过程]\n{thinking}\n[思考结束]\n")
        content = raw["message"].get("content", "").strip()
        if not content:
            logger.warning("模型返回空 content")
            raise ValueError("模型返回了空响应，请重试")
        return parse_ai_response(content)

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
            {"role": t["role"], "content": t["content"]} for t in request.conversation_history
        ]
        # Ollama /api/chat 用 images 字段传图，不用 OpenAI image_url 格式
        b64 = request.screenshot_b64
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return {
            "model": self.model,
            "stream": False,
            "options": {"think": False},
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                *history,
                {
                    "role": "user",
                    "content": user_text,
                    "images": [b64],
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
