"""CloudProvider 单元测试，mock HTTP 调用不依赖真实 API Key。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

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


def _mock_response(body: dict, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.ok = status < 400
    resp.reason = "OK" if status == 200 else "Error"
    resp.text = json.dumps(body)
    resp.json.return_value = body
    resp.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=resp) if status >= 400 else None
    )
    return resp


class TestIsAvailable:
    def test_returns_false_when_key_empty(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "").is_available() is False

    def test_returns_true_when_key_set(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "key-abc").is_available() is True


class TestDefaultModels:
    def test_gemini_default(self) -> None:
        assert CloudProvider(CloudBackend.GEMINI, "k").model == "gemini-2.5-flash"

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
        provider = CloudProvider(CloudBackend.GEMINI, "key")
        with patch.object(provider._session, "post", return_value=_mock_response(body)):
            resp = provider.complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_api_key_in_url(self) -> None:
        body = self._gemini_response(_done_json())
        captured_urls: list[str] = []

        def fake_post(url: str, **kwargs):
            captured_urls.append(url)
            return _mock_response(body)

        provider = CloudProvider(CloudBackend.GEMINI, "my-key")
        with patch.object(provider._session, "post", side_effect=fake_post):
            provider.complete(_make_request())

        assert "key=my-key" in captured_urls[0]


class TestClaudeComplete:
    def _claude_response(self, text: str) -> dict:
        return {"content": [{"type": "text", "text": text}]}

    def test_returns_airesponse(self) -> None:
        body = self._claude_response(_done_json())
        provider = CloudProvider(CloudBackend.CLAUDE, "key")
        with patch.object(provider._session, "post", return_value=_mock_response(body)):
            resp = provider.complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_auth_header_set(self) -> None:
        body = self._claude_response(_done_json())
        captured_headers: list[dict] = []

        def fake_post(url: str, **kwargs):
            captured_headers.append(kwargs.get("headers", {}))
            return _mock_response(body)

        provider = CloudProvider(CloudBackend.CLAUDE, "sk-ant-test")
        with patch.object(provider._session, "post", side_effect=fake_post):
            provider.complete(_make_request())

        assert captured_headers[0].get("x-api-key") == "sk-ant-test"


class TestOpenAIComplete:
    def _openai_response(self, text: str) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    def test_returns_airesponse(self) -> None:
        body = self._openai_response(_done_json())
        provider = CloudProvider(CloudBackend.OPENAI, "key")
        with patch.object(provider._session, "post", return_value=_mock_response(body)):
            resp = provider.complete(_make_request())
        assert isinstance(resp, AIResponse)
        assert resp.action == "task_done"

    def test_auth_header_set(self) -> None:
        body = self._openai_response(_done_json())
        captured_headers: list[dict] = []

        def fake_post(url: str, **kwargs):
            captured_headers.append(kwargs.get("headers", {}))
            return _mock_response(body)

        provider = CloudProvider(CloudBackend.OPENAI, "sk-openai-test")
        with patch.object(provider._session, "post", side_effect=fake_post):
            provider.complete(_make_request())

        assert captured_headers[0].get("Authorization") == "Bearer sk-openai-test"


class TestRetry503:
    def _gemini_response(self, text: str) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def test_retries_on_503_then_succeeds(self) -> None:
        success_body = self._gemini_response(_done_json())
        call_count = 0

        def fake_post(url: str, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response({}, status=503)
            return _mock_response(success_body)

        provider = CloudProvider(CloudBackend.GEMINI, "key")
        with patch.object(provider._session, "post", side_effect=fake_post):
            with patch("time.sleep"):
                resp = provider.complete(_make_request())

        assert resp.action == "task_done"
        assert call_count == 2

    def test_raises_after_max_retries(self) -> None:
        provider = CloudProvider(CloudBackend.GEMINI, "key")
        with patch.object(provider._session, "post", return_value=_mock_response({}, status=503)):
            with patch("time.sleep"):
                with pytest.raises(requests.exceptions.HTTPError):
                    provider.complete(_make_request())
