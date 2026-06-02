"""鼠标移动、点击、拖拽、滚轮操作。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MouseController:
    def click(self, x: int, y: int, button: str = "left", dry_run: bool = False) -> None:
        if dry_run:
            logger.info({"action": "mouse_click", "params": {"x": x, "y": y, "button": button}, "dry_run": True})
            return
        raise NotImplementedError

    def move(self, x: int, y: int, dry_run: bool = False) -> None:
        if dry_run:
            logger.info({"action": "mouse_move", "params": {"x": x, "y": y}, "dry_run": True})
            return
        raise NotImplementedError

    def scroll(self, x: int, y: int, dx: int, dy: int, dry_run: bool = False) -> None:
        if dry_run:
            logger.info({"action": "mouse_scroll", "params": {"x": x, "y": y, "dx": dx, "dy": dy}, "dry_run": True})
            return
        raise NotImplementedError
