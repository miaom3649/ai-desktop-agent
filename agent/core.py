"""Agent 主循环：截图 → AI 分析 → 执行动作 → 循环。"""

from __future__ import annotations

import dataclasses
import json
import logging
import queue
import re
import threading
import time
from collections.abc import Callable

from agent.memory import Memory
from ai.base import AIProvider, AIRequest
from ai.chat_ai import ChatAI
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
        chat_ai: ChatAI | None = None,
    ) -> None:
        self._provider = provider
        self._chat_ai = chat_ai
        self._dry_run = dry_run
        self._max_steps = max_steps
        self._screen = ScreenCapture()
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._memory = Memory()
        self._window_perception = WindowPerception()
        self._running = False
        self.on_message: Callable[[str], None] | None = None
        self.on_pause: Callable[[], None] | None = None
        self.on_chat_script: Callable[[list[dict]], None] | None = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为"未暂停"状态
        self._user_reply: queue.Queue[str] = queue.Queue()
        self._last_chat_text: str = ""

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def run(self, instruction: str) -> str:
        """执行一条自然语言指令，返回完成摘要或错误信息。"""
        self._running = True
        self._memory.clear()
        logger.info({"event": "task_start", "instruction": instruction})

        if self._chat_ai is not None:
            return self._run_with_chat_ai(instruction)

        try:
            result = self._loop(instruction)
        except KeyboardInterrupt:
            logger.info({"event": "task_interrupted"})
            result = "任务被用户中断。"
        finally:
            self._running = False

        self._memory.add_turn("user", instruction)
        self._memory.add_turn("assistant", result if result else self._last_chat_text)
        self._last_chat_text = ""
        return result

    def _run_with_chat_ai(self, instruction: str) -> str:
        """有 ChatAI 时的完整流程：路由判断 → 条件执行任务 → ChatAI 汇报结果。"""
        assert self._chat_ai is not None
        result = ""
        try:
            classified = self._chat_ai.classify(instruction, self._memory.get_conversation())
            logger.info({"event": "chat_ai_classify", "mode": classified.mode})

            # 推送接受任务 / 聊天 的角色旁白
            if classified.script and self.on_chat_script:
                self.on_chat_script(classified.script)

            if classified.mode == "chat":
                self._last_chat_text = self._script_to_text(classified.script)
            else:
                # 执行任务
                task_instruction = classified.task_instruction or instruction
                result = self._loop(task_instruction)
                # ChatAI 将执行结果包装为角色汇报语
                success = self._is_task_success(result)
                report_script = self._chat_ai.report_result(
                    result, success, self._memory.get_conversation()
                )
                logger.info({"event": "chat_ai_report", "success": success})
                if report_script and self.on_chat_script:
                    self.on_chat_script(report_script)
                self._last_chat_text = self._script_to_text(report_script)

        except KeyboardInterrupt:
            logger.info({"event": "task_interrupted"})
            result = "任务被用户中断。"
        finally:
            self._running = False

        self._memory.add_turn("user", instruction)
        self._memory.add_turn("assistant", result if result else self._last_chat_text)
        self._last_chat_text = ""
        return result

    @staticmethod
    def _script_to_text(script: list[dict]) -> str:
        return " ".join(s.get("text", "") for s in script if s.get("text"))

    @staticmethod
    def _is_task_success(result: str) -> bool:
        failure_prefixes = ("已达到最大步数", "任务被用户中断", "任务已停止", "已多次尝试")
        return not any(result.startswith(p) for p in failure_prefixes)

    def stop(self) -> None:
        """从外部（GUI 停止按钮）中止循环。"""
        self._running = False
        self._pause_event.set()  # 若正在等待主人回复，立即解除阻塞

    def reset_conversation(self) -> None:
        """清空跨轮次对话历史，开启全新对话。"""
        self._memory.clear_conversation()

    def set_provider(self, provider: AIProvider) -> None:
        """热替换 AI Provider，设置页保存后调用。"""
        self._provider = provider

    def set_chat_ai(self, chat_ai: ChatAI) -> None:
        """热替换 ChatAI，设置页保存后调用。"""
        self._chat_ai = chat_ai

    def cancel(self) -> None:
        """立刻中断当前 HTTP 请求并停止循环。"""
        self._running = False
        self._pause_event.set()  # 若正在等待主人回复，立即解除阻塞
        if hasattr(self._provider, "cancel"):
            self._provider.cancel()

    def resume(self, reply: str) -> None:
        """主人回复澄清问题后，由 GUI 调用以继续循环。"""
        self._user_reply.put(reply)
        self._pause_event.set()

    def _push_message(self, text: str) -> None:
        if self.on_message:
            self.on_message(f"[AI] {text}")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _loop(self, instruction: str) -> str:
        consecutive_failures = 0
        last_failed_action: str | None = None
        _TERMINAL = {"task_done", "chat_response", "need_clarification"}
        consecutive_same_count = 0
        last_action_key: tuple | None = None
        repeat_threshold = 3
        guard_active = False

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

            # 守护机制：检测连续重复动作，避免 AI 陷入无效循环
            if response.action not in _TERMINAL:
                action_key = (response.action, json.dumps(response.params, sort_keys=True))
                if action_key == last_action_key:
                    consecutive_same_count += 1
                else:
                    consecutive_same_count = 1
                    last_action_key = action_key
                    repeat_threshold = 3
                    guard_active = False
                if consecutive_same_count >= repeat_threshold:
                    guard_active = True
                    instruction = (
                        f"{instruction}\n[系统提示] 你已连续执行相同动作"
                        f" {consecutive_same_count} 次"
                        f"（{response.action}），请判断任务是否完成或向主人寻求帮助。"
                    )

            if response.action == "task_done":
                summary = response.params.get("summary", "任务完成。")
                logger.info({"event": "task_done", "summary": summary})
                return summary

            if response.action == "chat_response":
                # 有 ChatAI 时，Task AI 不应返回 chat_response（路由已在 _run_with_chat_ai 完成）
                if self._chat_ai is not None:
                    logger.warning({"event": "unexpected_chat_response_in_task_loop"})
                    return ""
                script = self._extract_script(response.params)
                logger.info({"event": "chat_response", "segments": len(script)})
                self._last_chat_text = self._script_to_text(script)
                if self.on_chat_script:
                    self.on_chat_script(script)
                return ""

            if response.action == "need_clarification":
                script = self._extract_script(response.params)
                logger.info({"event": "need_clarification", "segments": len(script)})
                if self.on_chat_script:
                    self.on_chat_script(script)
                else:
                    self._push_message(" ".join(s.get("text", "") for s in script))
                # 暂停循环，等待主人回复
                self._pause_event.clear()
                if self.on_pause:
                    self.on_pause()
                self._pause_event.wait()
                if not self._running:
                    return "任务已停止。"
                try:
                    user_reply = self._user_reply.get_nowait()
                except queue.Empty:
                    user_reply = ""
                self._memory.record(
                    action="user_reply",
                    params={"reply": user_reply},
                    result="ok",
                    risk_level=0,
                )
                if guard_active:
                    guard_active = False
                    consecutive_same_count = 0
                    m = re.search(r"再做\s*(\d+)\s*次", user_reply)
                    if m:
                        repeat_threshold = int(m.group(1))
                    else:
                        repeat_threshold *= 2
                if user_reply:
                    instruction = f"{instruction}\n[主人补充] {user_reply}"
                continue

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
            script = self._extract_script(resp.params)
            if script:
                return " ".join(s.get("text", "") for s in script if s.get("text"))
            fallback = resp.params.get("summary", "")
            if fallback:
                return fallback
        except Exception as exc:
            logger.error({"event": "failure_message_error", "error": str(exc)})
        return "已多次尝试仍无法完成该操作喵。主人要帮忙确认一下吗喵。"

    def _extract_script(self, params: dict) -> list[dict]:
        """从 params 提取 script 段落列表，兼容旧 message/question 字段。"""
        script = params.get("script")
        if isinstance(script, list) and script:
            return script
        text = params.get("message") or params.get("question") or ""
        return [{"text": text, "pause": 0}] if text else []

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
                        import win32con  # type: ignore[import-untyped]
                        import win32gui  # type: ignore[import-untyped]

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
