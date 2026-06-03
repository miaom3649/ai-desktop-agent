"""云端 BYOK 后端：Gemini / Claude / OpenAI，用户自带 API Key。"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from enum import Enum

from ai.base import (
    AGENT_SYSTEM_PROMPT,
    USER_TEMPLATE,
    AIProvider,
    AIRequest,
    AIResponse,
    parse_ai_response,
)

logger = logging.getLogger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_CLAUDE_BASE = "https://api.anthropic.com"
_OPENAI_BASE = "https://api.openai.com"


class CloudBackend(Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    OPENAI = "openai"


class CloudProvider(AIProvider):
    """通过用户提供的 API Key 调用云端模型。"""

    _DEFAULT_MODELS: dict[CloudBackend, str] = {
        CloudBackend.GEMINI: "gemini-2.0-flash",
        CloudBackend.CLAUDE: "claude-haiku-4-5-20251001",
        CloudBackend.OPENAI: "gpt-4o-mini",
    }

    def __init__(self, backend: CloudBackend, api_key: str, model: str = "") -> None:
        self.backend = backend
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODELS[backend]

    # ------------------------------------------------------------------
    # AIProvider 接口实现
    # ------------------------------------------------------------------

    def complete(self, request: AIRequest) -> AIResponse:
        """根据后端调用对应 API，返回解析后的 AIResponse。"""
        match self.backend:
            case CloudBackend.GEMINI:
                text = self._call_gemini(request)
            case CloudBackend.CLAUDE:
                text = self._call_claude(request)
            case CloudBackend.OPENAI:
                text = self._call_openai(request)
        return parse_ai_response(text)

    def is_available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # 各后端实现
    # ------------------------------------------------------------------

    def _call_gemini(self, request: AIRequest) -> str:
        url = f"{_GEMINI_BASE}/models/{self.model}:generateContent?key={self.api_key}"
        # Gemini 用 "model" 作为 assistant 角色名
        history = [
            {
                "role": "model" if t["role"] == "assistant" else "user",
                "parts": [{"text": t["content"]}],
            }
            for t in request.conversation_history
        ]
        payload = {
            "system_instruction": {"parts": [{"text": AGENT_SYSTEM_PROMPT}]},
            "contents": [
                *history,
                {
                    "role": "user",
                    "parts": [
                        {"text": self._build_user_text(request)},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": request.screenshot_b64,
                            }
                        },
                    ],
                },
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        resp = self._post(url, payload, headers={})
        return resp["candidates"][0]["content"]["parts"][0]["text"]

    def _call_claude(self, request: AIRequest) -> str:
        url = f"{_CLAUDE_BASE}/v1/messages"
        history = [
            {"role": t["role"], "content": t["content"]} for t in request.conversation_history
        ]
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": AGENT_SYSTEM_PROMPT,
            "messages": [
                *history,
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_user_text(request)},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": request.screenshot_b64,
                            },
                        },
                    ],
                },
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        resp = self._post(url, payload, headers=headers)
        return resp["content"][0]["text"]

    def _call_openai(self, request: AIRequest) -> str:
        url = f"{_OPENAI_BASE}/v1/chat/completions"
        history = [
            {"role": t["role"], "content": t["content"]} for t in request.conversation_history
        ]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                *history,
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_user_text(request)},
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
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = self._post(url, payload, headers=headers)
        return resp["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _build_user_text(self, request: AIRequest) -> str:
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
        return USER_TEMPLATE.substitute(
            task=request.task,
            n=min(len(request.action_history), 10),
            history=history_text,
            windows=windows_text,
        )

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            logger.error("HTTP %s %s — %s", e.code, e.reason, body)
            raise
