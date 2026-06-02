"""Agent 主循环：截图 → AI 分析 → 执行动作 → 循环。"""

from __future__ import annotations

import logging

from agent.memory import Memory
from ai.base import AIProvider, AIRequest
from execution.keyboard import KeyboardController
from execution.mouse import MouseController
from perception.screen import ScreenCapture

logger = logging.getLogger(__name__)

MAX_STEPS = 50  # 单次任务最大循环步数，防止失控


class AgentCore:
    """驱动整个感知-认知-执行循环。"""

    def __init__(
        self,
        provider: AIProvider,
        dry_run: bool = False,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._provider = provider
        self._dry_run = dry_run
        self._max_steps = max_steps
        self._screen = ScreenCapture()
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._memory = Memory()
        self._running = False

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def run(self, instruction: str) -> str:
        """执行一条自然语言指令，返回完成摘要或错误信息。"""
        self._running = True
        self._memory.clear()
        logger.info({"event": "task_start", "instruction": instruction})

        try:
            return self._loop(instruction)
        except KeyboardInterrupt:
            logger.info({"event": "task_interrupted"})
            return "任务被用户中断。"
        finally:
            self._running = False

    def stop(self) -> None:
        """从外部（GUI 停止按钮）中止循环。"""
        self._running = False

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _loop(self, instruction: str) -> str:
        for step in range(1, self._max_steps + 1):
            if not self._running:
                return "任务已停止。"

            logger.info({"event": "step_start", "step": step})

            screenshot = self._screen.capture()
            request = AIRequest(
                task=instruction,
                screenshot_b64=screenshot,
                action_history=self._memory.to_list(),
                window_list=[],  # Phase 2 接入窗口管理层后填充
            )

            response = self._provider.complete(request)
            logger.info(
                {
                    "event": "ai_response",
                    "step": step,
                    "action": response.action,
                    "risk_level": response.risk_level,
                    "reasoning": response.reasoning,
                }
            )

            result = self._dispatch(response.action, response.params)
            self._memory.record(
                action=response.action,
                params=response.params,
                result=result,
                risk_level=response.risk_level,
            )

            if response.action == "task_done":
                summary = response.params.get("summary", "任务完成。")
                logger.info({"event": "task_done", "summary": summary})
                return summary

            if response.action == "need_clarification":
                question = response.params.get("question", "")
                logger.info({"event": "need_clarification", "question": question})
                return f"需要澄清：{question}"

        return f"已达到最大步数 {self._max_steps}，任务未完成。"

    # ------------------------------------------------------------------
    # 动作派发
    # ------------------------------------------------------------------

    def _dispatch(self, action: str, params: dict) -> str:
        """将 AI 返回的动作名分发到对应执行器，返回执行结果描述。"""
        dry = self._dry_run
        try:
            match action:
                case "mouse_click":
                    self._mouse.click(
                        params["x"],
                        params["y"],
                        button=params.get("button", "left"),
                        clicks=params.get("clicks", 1),
                        dry_run=dry,
                    )
                case "mouse_move":
                    self._mouse.move(params["x"], params["y"], dry_run=dry)
                case "mouse_drag":
                    self._mouse.drag(
                        params["x1"],
                        params["y1"],
                        params["x2"],
                        params["y2"],
                        button=params.get("button", "left"),
                        dry_run=dry,
                    )
                case "mouse_scroll":
                    self._mouse.scroll(
                        params["x"],
                        params["y"],
                        dx=params.get("dx", 0),
                        dy=params.get("dy", 0),
                        dry_run=dry,
                    )
                case "type_text":
                    self._keyboard.type_text(params["text"], dry_run=dry)
                case "key_press":
                    self._keyboard.key_press(params["keys"], dry_run=dry)
                case "open_app":
                    # Phase 2 接入窗口管理层后实现；目前用键盘快捷键模拟
                    logger.warning({"event": "unimplemented_action", "action": action})
                case "task_done" | "need_clarification":
                    pass  # 由 _loop 处理，不需要执行器
                case _:
                    logger.warning({"event": "unknown_action", "action": action})
                    return f"未知动作：{action}"
        except Exception as exc:
            logger.error({"event": "dispatch_error", "action": action, "error": str(exc)})
            return f"执行失败：{exc}"

        return "ok"
