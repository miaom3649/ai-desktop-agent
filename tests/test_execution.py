"""execution/mouse.py 和 execution/keyboard.py 单元测试，mock pyautogui 不产生真实输入。"""

from __future__ import annotations

from unittest.mock import patch


class TestMouseController:
    def test_click_calls_pyautogui(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().click(100, 200)
            mock_pg.moveTo.assert_called_once_with(100, 200, duration=0.4)
            mock_pg.click.assert_called_once_with(button="left", clicks=1)

    def test_click_dry_run_does_not_call_pyautogui(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().click(100, 200, dry_run=True)
            mock_pg.click.assert_not_called()

    def test_click_double_click(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().click(50, 50, clicks=2)
            mock_pg.moveTo.assert_called_once_with(50, 50, duration=0.4)
            mock_pg.click.assert_called_once_with(button="left", clicks=2)

    def test_move_calls_moveto(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().move(300, 400)
            mock_pg.moveTo.assert_called_once_with(300, 400, duration=0.4)

    def test_drag_calls_moveto_and_dragto(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().drag(0, 0, 100, 100)
            mock_pg.moveTo.assert_called_once_with(0, 0, duration=0.4)
            mock_pg.dragTo.assert_called_once_with(100, 100, button="left", duration=0.4)

    def test_scroll_vertical(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().scroll(200, 300, dx=0, dy=3)
            mock_pg.scroll.assert_called_once_with(3)
            mock_pg.hscroll.assert_not_called()

    def test_scroll_horizontal(self) -> None:
        with patch("execution.mouse.pyautogui") as mock_pg:
            from execution.mouse import MouseController

            MouseController().scroll(200, 300, dx=2, dy=0)
            mock_pg.hscroll.assert_called_once_with(2)
            mock_pg.scroll.assert_not_called()


class TestKeyboardController:
    def test_type_text_uses_clipboard_paste(self) -> None:
        with (
            patch("execution.keyboard.pyautogui") as mock_pg,
            patch("execution.keyboard.pyperclip") as mock_clip,
        ):
            from execution.keyboard import KeyboardController

            KeyboardController().type_text("测试")
            mock_clip.copy.assert_called_once_with("测试")
            mock_pg.hotkey.assert_called_once_with("ctrl", "v")

    def test_type_text_dry_run_does_not_call_pyautogui(self) -> None:
        with (
            patch("execution.keyboard.pyautogui") as mock_pg,
            patch("execution.keyboard.pyperclip") as mock_clip,
        ):
            from execution.keyboard import KeyboardController

            KeyboardController().type_text("hello", dry_run=True)
            mock_pg.hotkey.assert_not_called()
            mock_clip.copy.assert_not_called()

    def test_key_press_calls_hotkey(self) -> None:
        with patch("execution.keyboard.pyautogui") as mock_pg:
            from execution.keyboard import KeyboardController

            KeyboardController().key_press(["ctrl", "c"])
            mock_pg.hotkey.assert_called_once_with("ctrl", "c")

    def test_key_press_dry_run_does_not_call_pyautogui(self) -> None:
        with patch("execution.keyboard.pyautogui") as mock_pg:
            from execution.keyboard import KeyboardController

            KeyboardController().key_press(["ctrl", "v"], dry_run=True)
            mock_pg.hotkey.assert_not_called()
