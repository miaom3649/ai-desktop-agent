"""Agent 主循环：截图 → AI 分析 → 执行动作 → 循环。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

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
        self.on_message: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def run(self, instruction: str) -> str:
        """执行一条自然语言指令，返回完成摘要或错误信息。"""
        self._running = True
        self._memory.clear()
        logger.info({"event": "task_start", "instruction": instruction})

        try:
            result = self._loop(instruction)
        except KeyboardInterrupt:
            logger.info({"event": "task_interrupted"})
            result = "任务被用户中断。"
        finally:
            self._running = False

        self._memory.add_turn("user", instruction)
        self._memory.add_turn("assistant", result)
        return result

    def stop(self) -> None:
        """从外部（GUI 停止按钮）中止循环。"""
        self._running = False

    def reset_conversation(self) -> None:
        """清空跨轮次对话历史，开启全新对话。"""
        self._memory.clear_conversation()

    def _push_message(self, text: str) -> None:
        if self.on_message:
            self.on_message(f"AI: {text}")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _loop(self, instruction: str) -> str:
        consecutive_failures = 0
        last_failed_action: str | None = None
        consecutive_same_type = 0
        last_action_type: str | None = None
        last_narration: str = ""

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
                conversation_history=self._memory.get_conversation(),
            )

            response = self._provider.complete(request)
            logger.info(
                {
                    "event": "ai_response",
                    "step": step,
                    "action": response.action,
                    "params": response.params,
                    "risk_level": response.risk_level,
                    "reasoning": response.reasoning,
                }
            )

            # task_done 的 summary 本身就是最终消息，跳过 narration 避免重复
            # 兜底去重：AI 未能变化 narration 时不重复推送相同文本
            if (
                response.narration
                and response.action != "task_done"
                and response.narration != last_narration
            ):
                self._push_message(response.narration)
                last_narration = response.narration

            # 同坐标点击 3 次以上说明陷入切换振荡，停下请主人介入
            if response.action == "mouse_click":
                cx, cy = response.params.get("x"), response.params.get("y")
                same_pos_count = sum(
                    1
                    for h in self._memory.to_list()
                    if h["action"] == "mouse_click"
                    and h.get("params", {}).get("x") == cx
                    and h.get("params", {}).get("y") == cy
                )
                if same_pos_count >= 3:
                    logger.error(
                        {"event": "toggle_oscillation", "x": cx, "y": cy, "count": same_pos_count}
                    )
                    return self._ask_failure_message(
                        response.action,
                        f"同一位置 ({cx}, {cy}) 已点击 {same_pos_count} 次但状态未变",
                        screenshot,
                    )

            result = self._dispatch(response.action, response.params)
            self._memory.record(
                action=response.action,
                params=response.params,
                result=result,
                risk_level=response.risk_level,
            )

            # 同一动作连续失败 3 次，中止避免无效循环消耗 API 配额
            if result.startswith("执行失败："):
                if response.action == last_failed_action:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_failed_action = response.action
                if consecutive_failures >= 3:
                    logger.error(
                        {"event": "action_stuck", "action": response.action, "result": result}
                    )
                    return self._ask_failure_message(response.action, result, screenshot)
            else:
                consecutive_failures = 0
                last_failed_action = None

            # 同类动作连续执行 5 次但任务未完成，说明陷入无效循环
            if response.action == last_action_type:
                consecutive_same_type += 1
            else:
                consecutive_same_type = 1
                last_action_type = response.action
            if consecutive_same_type >= 5:
                logger.error({"event": "action_loop", "action": response.action, "step": step})
                return self._ask_failure_message(
                    response.action, "重复相同操作但未取得进展", screenshot
                )

            if response.action == "task_done":
                summary = response.params.get("summary", "任务完成。")
                logger.info({"event": "task_done", "summary": summary})
                return summary

            if response.action == "chat_response":
                message = response.params.get("message", "")
                logger.info({"event": "chat_response", "message": message})
                return message

            if response.action == "need_clarification":
                question = response.params.get("question", "")
                logger.info({"event": "need_clarification", "question": question})
                return f"不是很确定喵：{question}"

        return f"已达到最大步数 {self._max_steps}，任务未完成。"

    def _ask_failure_message(self, action: str, error: str, screenshot: str) -> str:
        """连续失败后让 AI 自己生成角色风格的失败告知消息，兜底返回固定文本。"""
        try:
            request = AIRequest(
                task=f"动作 {action} 连续执行失败，错误信息：{error}。"
                "请用你的角色语气告诉主人你无法完成这个任务。",
                screenshot_b64=screenshot,
                action_history=self._memory.to_list(),
                window_list=[],
                conversation_history=self._memory.get_conversation(),
            )
            resp = self._provider.complete(request)
            msg = resp.params.get("message") or resp.params.get("summary", "")
            if msg:
                return msg
        except Exception as exc:
            logger.error({"event": "failure_message_error", "error": str(exc)})
        return "呜呜，喵试了好几次都没办法完成这个操作喵…主人要帮喵看看出了什么问题吗 (இдஇ)"

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
                case "wait":
                    seconds = float(params.get("seconds", 1.5))
                    logger.info(
                        {"action": "wait", "params": {"seconds": seconds},
                         "result": "waiting", "timestamp": time.time()}
                    )
                    if not dry:
                        time.sleep(seconds)
                case "task_done" | "need_clarification" | "chat_response":
                    pass  # 由 _loop 处理，不需要执行器
                case _:
                    logger.warning({"event": "unknown_action", "action": action})
                    return f"未知动作：{action}"
        except Exception as exc:
            logger.error({"event": "dispatch_error", "action": action, "error": str(exc)})
            return f"执行失败：{exc}"

        return "ok"
