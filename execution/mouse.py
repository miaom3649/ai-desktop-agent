"""鼠标移动、点击、拖拽、滚轮操作。"""

from __future__ import annotations

import logging
import time

import pyautogui

logger = logging.getLogger(__name__)

# pyautogui 全局安全设置
pyautogui.FAILSAFE = True  # 鼠标移到左上角立即中止
pyautogui.PAUSE = 0.05  # 每次操作后短暂停顿，避免操作过快

MOVE_DURATION = 0.4  # 鼠标移动动画时长（秒），让操作过程可见


def _log(action: str, params: dict, result: str = "ok") -> None:
    logger.info({"action": action, "params": params, "result": result, "timestamp": time.time()})


class MouseController:
    """封装 pyautogui 鼠标操作，所有方法支持 dry_run 模式。"""

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        dry_run: bool = False,
    ) -> None:
        params = {"x": x, "y": y, "button": button, "clicks": clicks}
        if dry_run:
            _log("mouse_click", params, result="dry_run")
            return
        pyautogui.moveTo(x, y, duration=MOVE_DURATION)
        pyautogui.click(button=button, clicks=clicks)
        _log("mouse_click", params)

    def move(self, x: int, y: int, dry_run: bool = False) -> None:
        params = {"x": x, "y": y}
        if dry_run:
            _log("mouse_move", params, result="dry_run")
            return
        pyautogui.moveTo(x, y, duration=MOVE_DURATION)
        _log("mouse_move", params)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        button: str = "left",
        dry_run: bool = False,
    ) -> None:
        params = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "button": button}
        if dry_run:
            _log("mouse_drag", params, result="dry_run")
            return
        pyautogui.moveTo(x1, y1, duration=MOVE_DURATION)
        pyautogui.dragTo(x2, y2, button=button, duration=MOVE_DURATION)
        _log("mouse_drag", params)

    def scroll(self, x: int, y: int, dx: int, dy: int, dry_run: bool = False) -> None:
        params = {"x": x, "y": y, "dx": dx, "dy": dy}
        if dry_run:
            _log("mouse_scroll", params, result="dry_run")
            return
        pyautogui.moveTo(x, y, duration=MOVE_DURATION)
        # pyautogui.scroll 只支持垂直滚动；水平滚动用 hscroll
        if dy != 0:
            pyautogui.scroll(dy)
        if dx != 0:
            pyautogui.hscroll(dx)
        _log("mouse_scroll", params)
