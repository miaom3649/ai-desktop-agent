"""键盘文字输入与快捷键触发。"""

from __future__ import annotations

import logging
import time

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)


def _log(action: str, params: dict, result: str = "ok") -> None:
    logger.info({"action": action, "params": params, "result": result, "timestamp": time.time()})


class KeyboardController:
    """封装 pyautogui 键盘操作，所有方法支持 dry_run 模式。"""

    def type_text(self, text: str, dry_run: bool = False) -> None:
        params = {"text": text}
        if dry_run:
            _log("type_text", params, result="dry_run")
            return
        # typewrite 不支持非 ASCII（如中文），统一走剪贴板粘贴
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        _log("type_text", params)

    def key_press(self, keys: list[str], dry_run: bool = False) -> None:
        params = {"keys": keys}
        if dry_run:
            _log("key_press", params, result="dry_run")
            return
        pyautogui.hotkey(*keys)
        _log("key_press", params)
