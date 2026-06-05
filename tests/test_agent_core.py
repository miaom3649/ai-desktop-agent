"""AgentCore 单元测试，mock AI provider 和执行层。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core import AgentCore
from ai.base import AIResponse


def _make_provider(*responses: AIResponse) -> MagicMock:
    """返回依次产出指定 AIResponse 的 mock provider。"""
    provider = MagicMock()
    provider.complete.side_effect = list(responses)
    return provider


def _done(summary: str = "完成") -> AIResponse:
    return AIResponse(action="task_done", params={"summary": summary}, risk_level=0, reasoning="")


def _click(x: int = 100, y: int = 200) -> AIResponse:
    return AIResponse(
        action="mouse_click",
        params={"x": x, "y": y, "button": "left"},
        risk_level=1,
        reasoning="点击",
    )


def _type(text: str = "hello") -> AIResponse:
    return AIResponse(
        action="type_text",
        params={"text": text},
        risk_level=1,
        reasoning="输入",
    )


def _wait() -> AIResponse:
    return AIResponse(
        action="wait",
        params={"seconds": 1.5},
        risk_level=0,
        reasoning="等待",
    )


def _clarify(question: str = "请确认") -> AIResponse:
    return AIResponse(
        action="need_clarification", params={"question": question}, risk_level=0, reasoning=""
    )


class TestAgentCoreRun:
    def test_returns_summary_on_task_done(self) -> None:
        provider = _make_provider(_done("已完成打开记事本"))
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            result = core.run("打开记事本")

        assert result == "已完成打开记事本"

    def test_executes_click_then_done(self) -> None:
        provider = _make_provider(_click(), _done())
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            result = core.run("点击按钮")

        assert result == "完成"
        assert provider.complete.call_count == 2

    def test_stops_on_need_clarification(self) -> None:
        provider = _make_provider(_clarify("请告诉我目标文件名"))
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            result = core.run("删除文件")

        assert "请告诉我目标文件名" in result

    def test_stops_after_max_steps(self) -> None:
        # AI 一直返回 click，永不完成
        provider = MagicMock()
        provider.complete.return_value = _click()
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True, max_steps=3)
            result = core.run("无限循环任务")

        assert provider.complete.call_count == 3
        assert "最大步数" in result

    def test_stop_method_interrupts_loop(self) -> None:
        call_count = 0

        def slow_complete(_request):
            nonlocal call_count
            call_count += 1
            core.stop()  # 第一步执行后立即停止
            return _click()

        provider = MagicMock()
        provider.complete.side_effect = slow_complete
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True, max_steps=10)
            result = core.run("测试停止")

        assert call_count == 1
        assert result == "任务已停止。"

    def test_action_history_passed_to_provider(self) -> None:
        provider = _make_provider(_click(), _done())
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            core.run("测试历史")

        second_call_request = provider.complete.call_args_list[1][0][0]
        assert len(second_call_request.action_history) == 1
        assert second_call_request.action_history[0]["action"] == "mouse_click"
