"""读取当前桌面的窗口列表与各窗口状态。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowInfo:
    window_id: str
    title: str
    app_name: str
    x: int
    y: int
    width: int
    height: int
    is_focused: bool


class WindowReader:
    """枚举当前所有可见窗口并返回结构化信息。"""

    def list_windows(self) -> list[WindowInfo]:
        raise NotImplementedError
