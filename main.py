"""入口：初始化 QApplication，启动托盘和主窗口。"""

from __future__ import annotations

import logging
import os
import signal
import sys

from dotenv import load_dotenv
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from agent.core import AgentCore
from ai.cloud_provider import CloudBackend, CloudProvider
from gui.main_window import MainWindow
from gui.tray import TrayIcon

logger = logging.getLogger(__name__)


def _create_provider() -> CloudProvider:
    """从环境变量构建云端 Provider，未配置时抛出带提示的异常。"""
    api_key = (
        os.getenv("API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "未找到 API Key。\n\n"
            "请在项目根目录创建 .env 文件并填入：\n"
            "  API_KEY=你的密钥\n"
            "  CLOUD_MODEL=gemini-2.5-flash\n\n"
            "参考 .env.example 文件。"
        )
    model = os.getenv("CLOUD_MODEL", "gemini-2.5-flash")
    if model.startswith("gemini"):
        backend = CloudBackend.GEMINI
    elif model.startswith("claude"):
        backend = CloudBackend.CLAUDE
    else:
        backend = CloudBackend.OPENAI
    logger.info("云端后端：%s / %s", backend.value, model)
    return CloudProvider(backend=backend, api_key=api_key, model=model)


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

    try:
        provider = _create_provider()
    except RuntimeError as exc:
        QMessageBox.critical(None, "配置错误", str(exc))
        return 1
    core = AgentCore(provider)

    window = MainWindow(core)
    window.show()

    tray = TrayIcon(window)
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
