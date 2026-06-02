"""CloudProvider 单元测试，mock HTTP 调用不依赖真实 API Key。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ai.base import AIRequest, AIResponse
from ai.cloud_provider import CloudBackend, CloudProvider


def _make_request() -> AIRequest:
    return AIRequest(
        task="打开记事本",
        screenshot_b64="aGVsbG8=",
        action_history=[],
        window_list=[],
    )


def _done_json() -> str:
    return json.dumps(
        {"action": "task_done", "params": {"summary": "完成"}, "risk_level": 0, "reasoning": ""}
    )


def _mock_urlopen(response_body: dict):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read.return_value = json.dumps(response_body).encode()
    return cm


class TestIsAvailable:
    def test_returns_false_when_key_empty(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "").is_available() is False

    def test_returns_true_when_key_set(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "key-abc").is_available() is True


class TestDefaultModels:
    def test_gemini_default(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "k").model == "gemini-2.0-flash"

    def test_claude_default(self) -> None:
        assert CloudProvider(CloudBackend.CLAUDE, "k").model == "claude-haiku-4-5-20251001"

    def test_openai_default(self) -> None:
        assert CloudProvider(CloudBackend.OPENAI, "k").model == "gpt-4o-mini"

    def test_custom_model_overrides_default(self) -> None:
        p = CloudProvider(CloudBackend.GEMINI, "k", model="gemini-1.5-pro")
        assert p.model == "gemini-1.5-pro"


class TestGeminiComplete:
    def _gemini_response(self, text: str) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def test_returns_airesponse(self) -> None:
        body = self._gemini_response(_done_json())
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            resp = CloudProvider(CloudBackend.GEMINI, "key").complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_api_key_in_url(self) -> None:
        body = self._gemini_response(_done_json())
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=60):
            captured_urls.append(req.full_url)
            return _mock_urlopen(body)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            CloudProvider(CloudBackend.GEMINI, "my-key").complete(_make_request())

        assert "key=my-key" in captured_urls[0]


class TestClaudeComplete:
    def _claude_response(self, text: str) -> dict:
        return {"content": [{"type": "text", "text": text}]}

    def test_returns_airesponse(self) -> None:
        body = self._claude_response(_done_json())
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            resp = CloudProvider(CloudBackend.CLAUDE, "key").complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_auth_header_set(self) -> None:
        body = self._claude_response(_done_json())
        captured_headers: list[dict] = []

        def fake_urlopen(req, timeout=60):
            captured_headers.append(dict(req.headers))
            return _mock_urlopen(body)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            CloudProvider(CloudBackend.CLAUDE, "sk-ant-test").complete(_make_request())

        assert captured_headers[0].get("X-api-key") == "sk-ant-test"


class TestOpenAIComplete:
    def _openai_response(self, text: str) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    def test_returns_airesponse(self) -> None:
        body = self._openai_response(_done_json())
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            resp = CloudProvider(CloudBackend.OPENAI, "key").complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_auth_header_set(self) -> None:
        body = self._openai_response(_done_json())
        captured_headers: list[dict] = []

        def fake_urlopen(req, timeout=60):
            captured_headers.append(dict(req.headers))
            return _mock_urlopen(body)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            CloudProvider(CloudBackend.OPENAI, "sk-openai-test").complete(_make_request())

        assert captured_headers[0].get("Authorization") == "Bearer sk-openai-test"
