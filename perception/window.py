"""读取当前桌面的窗口列表与各窗口状态。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

_IS_WINDOWS = sys.platform == "win32"

# UIA 树剪枝参数
_MAX_DEPTH = 6
_MAX_ELEMENTS = 300
_SKIP_CTRL_TYPES = {"Pane", "Separator", "Thumb", "ScrollBar", "Unknown"}


@dataclass
class UIElement:
    type: str
    name: str
    rect: dict[str, int]  # {x, y, w, h} 屏幕绝对坐标
    enabled: bool
    value: str = ""
    children: list[UIElement] = field(default_factory=list)


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
    is_minimized: bool


class WindowPerception:
    """读取系统窗口与 UI 状态，非 Windows 平台所有方法返回空值。"""

    def list_windows(self) -> list[WindowInfo]:
        if not _IS_WINDOWS:
            return []
        return self._enum_windows()

    def get_active_ui_tree(self) -> dict | None:
        if not _IS_WINDOWS:
            return None
        return self._build_active_tree()

    def list_installed_apps(self) -> list[str]:
        if not _IS_WINDOWS:
            return []
        return self._read_installed_apps()

    def get_desktop_icons(self) -> list[dict]:
        if not _IS_WINDOWS:
            return []
        return self._read_desktop_icons()

    # ------------------------------------------------------------------
    # Windows 实现
    # ------------------------------------------------------------------

    def _enum_windows(self) -> list[WindowInfo]:
        import psutil
        import win32gui  # type: ignore[import-untyped]

        results: list[WindowInfo] = []
        focused_hwnd = win32gui.GetForegroundWindow()

        def _cb(hwnd: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            try:
                _, pid = win32gui.GetWindowThreadProcessId(hwnd)  # type: ignore[attr-defined]
                app_name = psutil.Process(pid).name()
            except Exception:
                app_name = ""
            try:
                x, y, x2, y2 = win32gui.GetWindowRect(hwnd)
            except Exception:
                x = y = x2 = y2 = 0
            results.append(
                WindowInfo(
                    window_id=str(hwnd),
                    title=title,
                    app_name=app_name,
                    x=x,
                    y=y,
                    width=x2 - x,
                    height=y2 - y,
                    is_focused=(hwnd == focused_hwnd),
                    is_minimized=bool(win32gui.IsIconic(hwnd)),
                )
            )
            return True

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            pass
        return results

    def _build_active_tree(self) -> dict | None:
        import win32gui  # type: ignore[import-untyped]

        try:
            from pywinauto import Application  # type: ignore[import-untyped]
        except ImportError:
            return None

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        try:
            app = Application(backend="uia").connect(handle=hwnd)
            root = app.window(handle=hwnd).wrapper_object()
        except Exception:
            return None

        count = [0]

        def _walk(elem: object, depth: int) -> dict | None:
            if count[0] >= _MAX_ELEMENTS:
                return None
            count[0] += 1
            try:
                ctrl_type = str(getattr(elem.element_info, "control_type", None) or "Unknown")  # type: ignore[attr-defined]
                name = str(getattr(elem.element_info, "name", None) or "")  # type: ignore[attr-defined]
                enabled = bool(getattr(elem.element_info, "enabled", True))  # type: ignore[attr-defined]
                ri = elem.element_info.rectangle  # type: ignore[attr-defined]
                rect = {
                    "x": ri.left,
                    "y": ri.top,
                    "w": ri.right - ri.left,
                    "h": ri.bottom - ri.top,
                }
            except Exception:
                return None

            if rect["w"] == 0 and rect["h"] == 0:
                return None

            value = ""
            try:
                v = getattr(elem.element_info, "value", None)  # type: ignore[attr-defined]
                if v:
                    value = str(v)
            except Exception:
                pass

            node: dict = {"type": ctrl_type, "name": name, "rect": rect, "enabled": enabled}
            if value:
                node["value"] = value

            if depth < _MAX_DEPTH and not (ctrl_type in _SKIP_CTRL_TYPES and depth > 2):
                children: list[dict] = []
                try:
                    for child in elem.children():  # type: ignore[attr-defined]
                        child_node = _walk(child, depth + 1)
                        if child_node is not None:
                            children.append(child_node)
                except Exception:
                    pass
                if children:
                    node["children"] = children

            return node

        return _walk(root, 0)

    def _read_installed_apps(self) -> list[str]:
        import winreg  # type: ignore

        apps: set[str] = set()
        key_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),  # type: ignore[attr-defined]
            (
                winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),  # type: ignore[attr-defined]
        ]
        for hive, path in key_paths:
            try:
                with winreg.OpenKey(hive, path) as key:  # type: ignore[attr-defined]
                    count = winreg.QueryInfoKey(key)[0]  # type: ignore[attr-defined]
                    for i in range(count):
                        try:
                            sub_name = winreg.EnumKey(key, i)  # type: ignore[attr-defined]
                            with winreg.OpenKey(key, sub_name) as sub:  # type: ignore[attr-defined]
                                name = winreg.QueryValueEx(sub, "DisplayName")[0]  # type: ignore[attr-defined]
                                if name and isinstance(name, str):
                                    apps.add(name.strip())
                        except OSError:
                            pass
            except OSError:
                pass
        return sorted(apps)

    def _read_desktop_icons(self) -> list[dict]:
        try:
            import win32gui  # type: ignore[import-untyped]
            from pywinauto import Application  # type: ignore[import-untyped]
        except ImportError:
            return []

        list_view = self._find_desktop_listview(win32gui)
        if not list_view:
            return []

        try:
            app = Application(backend="uia").connect(handle=list_view)
            lv = app.window(handle=list_view).wrapper_object()
            icons: list[dict] = []
            for item in lv.children():
                try:
                    name = str(getattr(item.element_info, "name", None) or "")
                    ri = item.element_info.rectangle
                    w = ri.right - ri.left
                    h = ri.bottom - ri.top
                    if name and w > 0:
                        icons.append(
                            {
                                "name": name,
                                "x": ri.left + w // 2,
                                "y": ri.top + h // 2,
                            }
                        )
                except Exception:
                    pass
            return icons
        except Exception:
            return []

    def _find_desktop_listview(self, win32gui: object) -> int:
        """定位桌面图标所在的 SysListView32 控件句柄。"""
        progman = win32gui.FindWindow("Progman", None)  # type: ignore[attr-defined]
        if not progman:
            return 0

        shell_view = win32gui.FindWindowEx(progman, 0, "SHELLDLL_DefView", None)  # type: ignore[attr-defined]
        if not shell_view:
            # 部分系统桌面渲染在 WorkerW 窗口下
            found: list[int] = []

            def _cb(hwnd: int, _: object) -> bool:
                sv = win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None)  # type: ignore[attr-defined]
                if sv:
                    found.append(sv)
                return True

            win32gui.EnumWindows(_cb, None)  # type: ignore[attr-defined]
            if not found:
                return 0
            shell_view = found[0]

        return win32gui.FindWindowEx(shell_view, 0, "SysListView32", None)  # type: ignore[attr-defined]
