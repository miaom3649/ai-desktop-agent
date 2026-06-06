"""Agent 主循环：截图 → AI 分析 → 执行动作 → 循环。"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import Callable

from agent.memory import Memory
from ai.base import AIProvider, AIRequest
from execution.keyboard import KeyboardController
from execution.mouse import MouseController
from perception.screen import ScreenCapture
from perception.window import WindowPerception

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
        self._window_perception = WindowPerception()
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

    def set_provider(self, provider: AIProvider) -> None:
        """热替换 AI Provider，设置页保存后调用。"""
        self._provider = provider

    def cancel(self) -> None:
        """立刻中断当前 HTTP 请求并停止循环。"""
        self._running = False
        if hasattr(self._provider, "cancel"):
            self._provider.cancel()

    def _push_message(self, text: str) -> None:
        if self.on_message:
            self.on_message(f"[AI] {text}")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _loop(self, instruction: str) -> str:
        consecutive_failures = 0
        last_failed_action: str | None = None
        last_narration: str = ""
        _TERMINAL = {"task_done", "chat_response", "need_clarification"}

        for step in range(1, self._max_steps + 1):
            if not self._running:
                return "任务已停止。"

            logger.info({"event": "step_start", "step": step})

            screenshot = self._screen.capture()
            window_list = [dataclasses.asdict(w) for w in self._window_perception.list_windows()]
            request = AIRequest(
                task=instruction,
                screenshot_b64=screenshot,
                action_history=self._memory.to_list(),
                window_list=window_list,
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
                return question

        return f"已达到最大步数 {self._max_steps}，任务未完成。"

    def _ask_failure_message(self, action: str, error: str, screenshot: str) -> str:
        """守护触发后让 AI 以 need_clarification 向主人说明情况并请求介入，兜底返回固定文本。"""
        try:
            request = AIRequest(
                task=(
                    f"[系统] 守护机制检测到异常：动作 {action} 触发了保护规则，原因：{error}。"
                    "请用 need_clarification 动作，以角色语气向主人说明问题并请求协助确认。"
                ),
                screenshot_b64=screenshot,
                action_history=self._memory.to_list(),
                window_list=[dataclasses.asdict(w) for w in self._window_perception.list_windows()],
                conversation_history=self._memory.get_conversation(),
            )
            resp = self._provider.complete(request)
            question = (
                resp.params.get("question")
                or resp.params.get("message")
                or resp.params.get("summary", "")
            )
            if question:
                return question
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
                case "focus_window":
                    window_id = str(params.get("window_id", ""))
                    if window_id and not dry:
                        import win32con
                        import win32gui

                        hwnd = int(window_id)
                        if win32gui.IsIconic(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                case "open_app":
                    app_name = params.get("app_name", "")
                    if app_name and not dry:
                        import subprocess

                        subprocess.Popen(["cmd", "/c", "start", "", app_name])
                case "get_ui_tree":
                    tree = self._window_perception.get_active_ui_tree()
                    return (
                        json.dumps(tree, ensure_ascii=False)
                        if tree is not None
                        else "（无法获取 UI 树）"
                    )
                case "get_installed_apps":
                    apps = self._window_perception.list_installed_apps()
                    if not apps:
                        return "（无法获取已安装应用列表）"
                    return json.dumps(apps, ensure_ascii=False)
                case "get_desktop_icons":
                    icons = self._window_perception.get_desktop_icons()
                    return (
                        json.dumps(icons, ensure_ascii=False) if icons else "（无法获取桌面图标）"
                    )
                case "wait":
                    seconds = float(params.get("seconds", 1.5))
                    logger.info(
                        {
                            "action": "wait",
                            "params": {"seconds": seconds},
                            "result": "waiting",
                            "timestamp": time.time(),
                        }
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
