"""入口：初始化 QApplication，启动托盘和主窗口。"""

from __future__ import annotations

import logging
import os
import signal
import sys

from dotenv import load_dotenv
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from agent.core import AgentCore
from ai.cloud_provider import CloudBackend, CloudProvider
from gui.main_window import MainWindow
from gui.tray import TrayIcon


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    # 关闭所有窗口后不自动退出，由托盘的"退出"菜单项控制
    app.setQuitOnLastWindowClosed(False)

    # Qt 的 C++ 事件循环不会自动让 Python 处理 SIGINT，
    # 用一个短周期 timer 定期唤醒 Python，配合信号处理器实现 Ctrl+C 退出
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    sigint_timer = QTimer()
    sigint_timer.start(200)
    sigint_timer.timeout.connect(lambda: None)

    api_key = os.environ.get("API_KEY", "")
    model = os.environ.get("CLOUD_MODEL", "")
    provider = CloudProvider(CloudBackend.GEMINI, api_key=api_key, model=model)
    core = AgentCore(provider)

    window = MainWindow(core)
    window.show()

    tray = TrayIcon(window)
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
