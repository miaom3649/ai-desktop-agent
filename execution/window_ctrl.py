"""窗口管理跨平台抽象层（Phase 1 & 2 仅 Windows，Phase 3 扩展 macOS/Linux）。"""

from __future__ import annotations


class WindowController:
    def list_windows(self) -> list:
        raise NotImplementedError

    def focus_window(self, window_id: str) -> None:
        raise NotImplementedError

    def move_window(self, window_id: str, x: int, y: int) -> None:
        raise NotImplementedError

    def close_window(self, window_id: str) -> None:
        raise NotImplementedError
