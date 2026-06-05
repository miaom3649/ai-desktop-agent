"""OllamaProvider 单元测试，mock HTTP 调用不依赖真实 Ollama 服务。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ai.base import AIRequest, AIResponse
from ai.ollama_provider import OllamaProvider


def _make_request(task: str = "打开记事本") -> AIRequest:
    return AIRequest(
        task=task,
        screenshot_b64="aGVsbG8=",
        action_history=[],
        window_list=[],
    )


def _mock_urlopen(response_body: dict):
    """返回一个可作为 urlopen 上下文管理器使用的 mock。"""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read.return_value = json.dumps(response_body).encode()
    return cm


class TestIsAvailable:
    def test_returns_true_when_model_found(self) -> None:
        body = {"models": [{"name": "qwen3-vl:4b"}]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            assert OllamaProvider().is_available() is True

    def test_returns_false_when_model_missing(self) -> None:
        body = {"models": [{"name": "llama3:8b"}]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            assert OllamaProvider().is_available() is False

    def test_returns_false_when_service_down(self) -> None:
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert OllamaProvider().is_available() is False


class TestComplete:
    def _ollama_response(self, content: str) -> dict:
        return {"message": {"role": "assistant", "content": content}}

    def test_returns_airesponse_from_valid_json(self) -> None:
        payload = json.dumps(
            {
                "action": "mouse_click",
                "params": {"x": 100, "y": 200, "button": "left"},
                "risk_level": 1,
                "reasoning": "点击目标按钮",
            }
        )
        body = self._ollama_response(payload)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            resp = OllamaProvider().complete(_make_request())

        assert isinstance(resp, AIResponse)
        assert resp.action == "mouse_click"
        assert resp.params == {"x": 100, "y": 200, "button": "left"}
        assert resp.risk_level == 1
        assert resp.reasoning == "点击目标按钮"

    def test_strips_markdown_code_fence(self) -> None:
        inner = json.dumps(
            {"action": "task_done", "params": {"summary": "完成"}, "risk_level": 0, "reasoning": ""}
        )
        wrapped = f"```json\n{inner}\n```"
        body = self._ollama_response(wrapped)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            resp = OllamaProvider().complete(_make_request())

        assert resp.action == "task_done"

    def test_uses_correct_model_in_payload(self) -> None:
        payload = json.dumps(
            {"action": "task_done", "params": {}, "risk_level": 0, "reasoning": ""}
        )
        body = self._ollama_response(payload)
        captured: list[bytes] = []

        def fake_urlopen(req, timeout=60):
            captured.append(req.data)
            return _mock_urlopen(body)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OllamaProvider(model="qwen2.5-vl:3b").complete(_make_request())

        sent = json.loads(captured[0])
        assert sent["model"] == "qwen2.5-vl:3b"

    def test_screenshot_included_in_payload(self) -> None:
        payload = json.dumps(
            {"action": "task_done", "params": {}, "risk_level": 0, "reasoning": ""}
        )
        body = self._ollama_response(payload)
        captured: list[bytes] = []

        def fake_urlopen(req, timeout=60):
            captured.append(req.data)
            return _mock_urlopen(body)

        req = _make_request()
        req.screenshot_b64 = "dGVzdA=="
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OllamaProvider().complete(req)

        sent = json.loads(captured[0])
        user_content = sent["messages"][1]["content"]
        image_parts = [p for p in user_content if p.get("type") == "image_url"]
        assert len(image_parts) == 1
        assert "dGVzdA==" in image_parts[0]["image_url"]["url"]
