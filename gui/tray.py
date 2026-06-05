"""系统托盘图标与右键菜单。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon


class TrayIcon(QSystemTrayIcon):
    """驻留系统托盘，提供显示主窗口和退出的快捷菜单。"""

    def __init__(
        self,
        main_window: QMainWindow,
        on_settings: Callable[[], None] | None = None,
    ) -> None:
        # 暂用 Qt 内置图标占位，等 assets/icons/ 有正式图标后替换
        icon = QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_ComputerIcon  # type: ignore[attr-defined]
        )
        super().__init__(icon)

        self._main = main_window
        self._on_settings = on_settings
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        show_action = menu.addAction("显示主窗口")
        show_action.triggered.connect(self._show_main)

        if self._on_settings:
            settings_action = menu.addAction("设置")
            settings_action.triggered.connect(self._on_settings)

        menu.addSeparator()

        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(QApplication.quit)

        self.setContextMenu(menu)
        self.setToolTip("AI Desktop Agent")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """单击托盘图标时切换主窗口显示状态。"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._main.isVisible():
                self._main.hide()
            else:
                self._show_main()

    def _show_main(self) -> None:
        self._main.show()
        self._main.raise_()
        self._main.activateWindow()
