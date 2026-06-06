"""云端 BYOK 后端：Gemini / Claude / OpenAI，用户自带 API Key。"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum

import requests

from ai.base import (
    AGENT_SYSTEM_PROMPT,
    USER_TEMPLATE,
    AIProvider,
    AIRequest,
    AIResponse,
    ProviderAuthError,
    parse_ai_response,
)

logger = logging.getLogger(__name__)

_503_MAX_RETRIES = 3
_503_RETRY_DELAY = 2.0  # 秒，每次重试前等待时间

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
        CloudBackend.GEMINI: "gemini-2.5-flash",
        CloudBackend.CLAUDE: "claude-haiku-4-5-20251001",
        CloudBackend.OPENAI: "gpt-4o-mini",
    }

    def __init__(
        self, backend: CloudBackend, api_key: str, model: str = "", system_prompt: str = ""
    ) -> None:
        self.backend = backend
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODELS[backend]
        self._system_prompt = system_prompt or AGENT_SYSTEM_PROMPT
        self._session = requests.Session()

    def cancel(self) -> None:
        """关闭当前 Session，中断正在进行的 HTTP 请求。"""
        self._session.close()
        self._session = requests.Session()

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
            "system_instruction": {"parts": [{"text": self._system_prompt}]},
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
            "system": self._system_prompt,
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
                {"role": "system", "content": self._system_prompt},
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
        headers = {"Content-Type": "application/json", **headers}
        for attempt in range(_503_MAX_RETRIES + 1):
            resp = self._session.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 503 and attempt < _503_MAX_RETRIES:
                logger.warning(
                    "HTTP 503 服务暂时不可用，%.0f 秒后重试（第 %d/%d 次）",
                    _503_RETRY_DELAY,
                    attempt + 1,
                    _503_MAX_RETRIES,
                )
                time.sleep(_503_RETRY_DELAY)
                continue
            if not resp.ok:
                logger.error("HTTP %s %s — %s", resp.status_code, resp.reason, resp.text)
                if resp.status_code in (401, 403):
                    raise ProviderAuthError(f"HTTP {resp.status_code}：API Key 无效或未授权")
                resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")
