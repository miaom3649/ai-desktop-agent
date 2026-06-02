"""键盘文字输入与快捷键触发。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class KeyboardController:
    def type_text(self, text: str, dry_run: bool = False) -> None:
        if dry_run:
            logger.info({"action": "type_text", "params": {"text": text}, "dry_run": True})
            return
        raise NotImplementedError

    def key_press(self, keys: list[str], dry_run: bool = False) -> None:
        if dry_run:
            logger.info({"action": "key_press", "params": {"keys": keys}, "dry_run": True})
            return
        raise NotImplementedError
