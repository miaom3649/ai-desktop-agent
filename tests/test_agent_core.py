"""AgentCore 单元测试，mock AI provider 和执行层。"""

from __future__ import annotations

import threading
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

    def test_need_clarification_pauses_and_resumes(self) -> None:
        """need_clarification 触发暂停，resume() 后循环继续直到 task_done。"""
        provider = _make_provider(_clarify("请告诉我目标文件名"), _done("已根据回复完成"))
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)

            paused = threading.Event()
            core.on_pause = lambda: paused.set()

            result_box: list[str] = []
            t = threading.Thread(target=lambda: result_box.append(core.run("删除文件")))
            t.start()
            paused.wait(timeout=5)
            core.resume("目标文件是 test.txt")
            t.join(timeout=5)

        assert result_box[0] == "已根据回复完成"
        assert provider.complete.call_count == 2

    def test_need_clarification_stop_while_paused(self) -> None:
        """need_clarification 暂停期间调用 stop()，循环立即终止。"""
        provider = _make_provider(_clarify("请告诉我目标文件名"))
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)

            paused = threading.Event()
            core.on_pause = lambda: paused.set()

            result_box: list[str] = []
            t = threading.Thread(target=lambda: result_box.append(core.run("删除文件")))
            t.start()
            paused.wait(timeout=5)
            core.stop()
            t.join(timeout=5)

        assert result_box[0] == "任务已停止。"

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

    def test_guard_injects_hint_after_threshold(self) -> None:
        """连续 3 次相同动作后，下一步 AI 请求的 task 中含有 [系统提示]。"""
        provider = _make_provider(_click(), _click(), _click(), _done())
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            core.run("连续点击测试")

        fourth_call_request = provider.complete.call_args_list[3][0][0]
        assert "[系统提示]" in fourth_call_request.task

    def test_guard_resets_on_action_change(self) -> None:
        """动作变化时计数器重置，不触发守护。"""
        provider = _make_provider(_click(), _click(), _type(), _done())
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)
            core.run("点击后输入")

        for call in provider.complete.call_args_list:
            assert "[系统提示]" not in call[0][0].task

    def test_guard_threshold_doubles_on_continue(self) -> None:
        """用户回复"继续"后阈值翻倍，需要连续 6 次才再次触发守护。"""
        provider = _make_provider(
            _click(), _click(), _click(),
            _clarify("检测到重复，要继续吗？"),
            _click(), _click(), _click(), _click(), _click(), _click(),
            _done("完成"),
        )
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)

            paused = threading.Event()
            core.on_pause = lambda: paused.set()

            result_box: list[str] = []
            t = threading.Thread(target=lambda: result_box.append(core.run("重复点击任务")))
            t.start()
            paused.wait(timeout=5)
            core.resume("继续")
            t.join(timeout=5)

        assert result_box[0] == "完成"
        assert "[系统提示]" in provider.complete.call_args_list[3][0][0].task
        assert "[系统提示]" in provider.complete.call_args_list[10][0][0].task

    def test_guard_threshold_set_on_n_more_times(self) -> None:
        """用户回复"再做N次"时阈值精确设为 N，再次触发守护。"""
        provider = _make_provider(
            _click(), _click(), _click(),
            _clarify("检测到重复，如何处理？"),
            _click(), _click(), _click(),
            _done("完成"),
        )
        with patch("agent.core.ScreenCapture") as mock_sc:
            mock_sc.return_value.capture.return_value = "fake_b64"
            core = AgentCore(provider, dry_run=True)

            paused = threading.Event()
            core.on_pause = lambda: paused.set()

            result_box: list[str] = []
            t = threading.Thread(target=lambda: result_box.append(core.run("重复点击任务")))
            t.start()
            paused.wait(timeout=5)
            core.resume("再做3次")
            t.join(timeout=5)

        assert result_box[0] == "完成"
        assert "[系统提示]" in provider.complete.call_args_list[3][0][0].task
        assert "[系统提示]" in provider.complete.call_args_list[7][0][0].task
