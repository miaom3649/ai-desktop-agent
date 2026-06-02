"""pytest 共享 fixture 与模块级 mock 配置。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# pyautogui 在 import 时会尝试连接 X11 Display，
# 在无图形界面的 CI 环境中提前注入 mock，避免 KeyError: 'DISPLAY'。
sys.modules.setdefault("pyautogui", MagicMock())
