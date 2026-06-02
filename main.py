"""入口：初始化 QApplication，启动托盘和主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from agent.core import AgentCore
from ai.ollama_provider import OllamaProvider
from gui.main_window import MainWindow
from gui.tray import TrayIcon


def main() -> int:
    app = QApplication(sys.argv)
    # 关闭所有窗口后不自动退出，由托盘的"退出"菜单项控制
    app.setQuitOnLastWindowClosed(False)

    provider = OllamaProvider()
    core = AgentCore(provider)

    window = MainWindow(core)
    window.show()

    tray = TrayIcon(window)
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
