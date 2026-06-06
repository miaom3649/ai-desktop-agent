"""WindowPerception 单元测试。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import perception.window as wm


class TestNonWindowsPlatform:
    """非 Windows 平台直接返回空值，不调用任何系统 API。"""

    def test_list_windows_empty(self) -> None:
        if sys.platform == "win32":
            pytest.skip("仅在非 Windows 平台运行")
        assert wm.WindowPerception().list_windows() == []

    def test_get_active_ui_tree_none(self) -> None:
        if sys.platform == "win32":
            pytest.skip("仅在非 Windows 平台运行")
        assert wm.WindowPerception().get_active_ui_tree() is None

    def test_list_installed_apps_empty(self) -> None:
        if sys.platform == "win32":
            pytest.skip("仅在非 Windows 平台运行")
        assert wm.WindowPerception().list_installed_apps() == []

    def test_get_desktop_icons_empty(self) -> None:
        if sys.platform == "win32":
            pytest.skip("仅在非 Windows 平台运行")
        assert wm.WindowPerception().get_desktop_icons() == []


def _make_win32gui(hwnd: int = 12345, title: str = "Notepad", pid: int = 100) -> MagicMock:
    m = MagicMock()
    m.GetForegroundWindow.return_value = hwnd
    m.IsWindowVisible.return_value = True
    m.GetWindowText.return_value = title
    m.GetWindowThreadProcessId.return_value = (0, pid)
    m.GetWindowRect.return_value = (10, 20, 810, 620)
    m.IsIconic.return_value = False

    def _fake_enum(cb: object, extra: object) -> None:
        cb(hwnd, None)

    m.EnumWindows.side_effect = _fake_enum
    return m


class TestEnumWindows:
    """list_windows() Windows 逻辑，mock pywin32 + psutil。"""

    def _run(self, win32gui: MagicMock, psutil: MagicMock) -> list[wm.WindowInfo]:
        with patch("perception.window._IS_WINDOWS", True):
            with patch.dict("sys.modules", {"win32gui": win32gui, "psutil": psutil}):
                return wm.WindowPerception().list_windows()

    def test_visible_window_returned(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.Process.return_value.name.return_value = "notepad.exe"
        results = self._run(_make_win32gui(), mock_psutil)

        assert len(results) == 1
        w = results[0]
        assert w.title == "Notepad"
        assert w.app_name == "notepad.exe"
        assert w.x == 10
        assert w.y == 20
        assert w.width == 800
        assert w.height == 600
        assert w.is_focused is True
        assert w.is_minimized is False

    def test_invisible_window_excluded(self) -> None:
        mock_gui = _make_win32gui()
        mock_gui.IsWindowVisible.return_value = False
        results = self._run(mock_gui, MagicMock())
        assert results == []

    def test_empty_title_excluded(self) -> None:
        mock_gui = _make_win32gui()
        mock_gui.GetWindowText.return_value = ""
        results = self._run(mock_gui, MagicMock())
        assert results == []

    def test_minimized_flag(self) -> None:
        mock_gui = _make_win32gui()
        mock_gui.IsIconic.return_value = True
        mock_psutil = MagicMock()
        mock_psutil.Process.return_value.name.return_value = "notepad.exe"
        results = self._run(mock_gui, mock_psutil)
        assert results[0].is_minimized is True

    def test_psutil_error_gives_empty_app_name(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = Exception("no such process")
        results = self._run(_make_win32gui(), mock_psutil)
        assert results[0].app_name == ""


class TestListInstalledApps:
    """list_installed_apps() 从注册表读取应用名称。"""

    def test_returns_sorted_app_names(self) -> None:
        mock_winreg = MagicMock()
        key_mock = MagicMock()
        sub_mock = MagicMock()

        mock_winreg.HKEY_LOCAL_MACHINE = 0x80000002
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.OpenKey.return_value.__enter__ = lambda s: key_mock
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.QueryInfoKey.return_value = (1, 0, 0)
        mock_winreg.EnumKey.return_value = "subkey1"

        ctx = MagicMock()
        ctx.__enter__ = lambda s: sub_mock
        ctx.__exit__ = MagicMock(return_value=False)
        mock_winreg.OpenKey.side_effect = [
            mock_winreg.OpenKey.return_value,
            ctx,
            mock_winreg.OpenKey.return_value,
            ctx,
            mock_winreg.OpenKey.return_value,
            ctx,
        ]
        mock_winreg.QueryValueEx.return_value = ("微信", None)

        with patch("perception.window._IS_WINDOWS", True):
            with patch.dict("sys.modules", {"winreg": mock_winreg}):
                apps = wm.WindowPerception().list_installed_apps()

        assert "微信" in apps

    def test_oserror_skipped_gracefully(self) -> None:
        mock_winreg = MagicMock()
        mock_winreg.HKEY_LOCAL_MACHINE = 0x80000002
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.OpenKey.side_effect = OSError("key not found")

        with patch("perception.window._IS_WINDOWS", True):
            with patch.dict("sys.modules", {"winreg": mock_winreg}):
                apps = wm.WindowPerception().list_installed_apps()

        assert apps == []
