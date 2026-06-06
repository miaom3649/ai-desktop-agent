"""入口：初始化 QApplication，启动托盘和主窗口。"""

from __future__ import annotations

import logging
import os
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from agent.core import AgentCore
from ai.base import build_system_prompt
from ai.cloud_provider import CloudBackend, CloudProvider
from ai.personality import PersonalityProfile
from config.app_config import AppConfig
from gui.main_window import MainWindow
from gui.settings_page import SettingsPage
from gui.tray import TrayIcon

logger = logging.getLogger(__name__)


def _provider_from_config(
    config: AppConfig, personality: PersonalityProfile | None = None
) -> CloudProvider:
    """根据配置构造 CloudProvider。"""
    ai = config.ai
    model = ai.model or None
    match ai.backend:
        case "gemini":
            backend = CloudBackend.GEMINI
        case "claude":
            backend = CloudBackend.CLAUDE
        case _:
            backend = CloudBackend.OPENAI
    system_prompt = build_system_prompt(personality) if personality else ""
    logger.info("云端后端：%s / %s", backend.value, model or "(default)")
    return CloudProvider(backend=backend, api_key=ai.api_key, model=model or "", system_prompt=system_prompt)


def _resolve_api_key(config: AppConfig) -> AppConfig:
    """优先使用环境变量（开发便利），否则用配置文件中的 Key。"""
    env_key = (
        os.getenv("API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if env_key and not config.ai.api_key:
        config.ai.api_key = env_key
        model = os.getenv("CLOUD_MODEL", "")
        if model:
            config.ai.model = model
            if model.startswith("gemini"):
                config.ai.backend = "gemini"
            elif model.startswith("claude"):
                config.ai.backend = "claude"
            else:
                config.ai.backend = "openai"
    return config


def main() -> int:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Ctrl+C 退出支持
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    sigint_timer = QTimer()
    sigint_timer.start(200)
    sigint_timer.timeout.connect(lambda: None)

    config = _resolve_api_key(AppConfig.load())
    personality = PersonalityProfile.load_default()

    # 创建一个占位 provider；若 Key 为空则在引导结束后替换
    if config.ai.api_key:
        provider: CloudProvider | None = _provider_from_config(config, personality)
    else:
        provider = None

    # AgentCore 需要一个 provider，先用占位（无 Key 时不会真正调用）
    # 首次引导完成后通过 set_provider() 替换
    _placeholder = CloudProvider(
        backend=CloudBackend.GEMINI, api_key="placeholder", model="gemini-2.5-flash"
    )
    core = AgentCore(provider or _placeholder)

    def _open_settings(first_launch: bool = False) -> None:
        dlg = SettingsPage(
            config=config,
            on_save=lambda cfg: core.set_provider(_provider_from_config(cfg, personality)),
            parent=window,
            first_launch=first_launch,
        )
        dlg.exec()

    window = MainWindow(core, on_settings=_open_settings)
    tray = TrayIcon(window, on_settings=_open_settings)
    tray.show()

    if not config.ai.api_key:
        # 无 Key 时先弹引导，引导完成后再显示主窗口
        _open_settings(first_launch=True)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
