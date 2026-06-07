"""主窗口：持续对话模式，输入框始终可用。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QShowEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agent.core import AgentCore

logger = logging.getLogger(__name__)

# 规则映射：消息内容 → 发送前等待毫秒数
_PAUSE_RULES: list[tuple[str, int]] = [
    ("……", 1800),
    ("…", 1200),
]
_DEFAULT_PAUSE = 600


def _pause_for(message: str) -> int:
    """根据消息内容决定显示前的等待时长（毫秒）。"""
    for marker, ms in _PAUSE_RULES:
        if marker in message:
            return ms
    return _DEFAULT_PAUSE


class _TypewriterRenderer(QObject):
    """逐字渲染 AI 消息，内部维护队列，新消息追加而不打断当前渲染。"""

    finished = Signal()  # 队列清空、全部渲染完毕

    def __init__(self, log: QTextEdit) -> None:
        super().__init__()
        self._log = log
        self._current = ""
        self._char_idx = 0
        self._pending: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def enqueue(self, message: str) -> None:
        """追加一条消息；当前空闲时立即开始渲染。"""
        if not message:
            return
        self._pending.append(message)
        if not self._timer.isActive() and not self._current:
            self._start_next()

    def stop(self) -> None:
        self._timer.stop()
        self._pending.clear()
        self._current = ""
        self._char_idx = 0

    def _start_next(self) -> None:
        if not self._pending:
            return
        msg = self._pending.pop(0)
        pause = _pause_for(msg)
        self._current = msg
        self._char_idx = 0
        QTimer.singleShot(pause, self._begin_typing)

    def _begin_typing(self) -> None:
        if not self._current:
            return
        cursor = QTextCursor(self._log.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        cursor.insertText("[小空] ")
        self._log.ensureCursorVisible()
        self._timer.start()

    def _tick(self) -> None:
        if self._char_idx < len(self._current):
            cursor = QTextCursor(self._log.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(self._current[self._char_idx])
            self._log.ensureCursorVisible()
            self._char_idx += 1
        else:
            self._timer.stop()
            self._current = ""
            if self._pending:
                self._start_next()
            else:
                self.finished.emit()


class _Bridge(QObject):
    """在会话线程与 Qt 主线程之间传递信号（线程安全）。"""

    chat_messages = Signal(list)
    thinking = Signal(bool)
    auth_error = Signal()


class MainWindow(QMainWindow):
    """持续对话主窗口。"""

    def __init__(
        self,
        core: AgentCore,
        on_settings: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("AI Desktop Agent")
        self.resize(640, 480)

        self._core = core
        self._on_settings = on_settings
        self._greeted = False
        self._renderer: _TypewriterRenderer | None = None
        self._awaiting_farewell = False
        self._needs_clear = False

        self._bridge = _Bridge()
        self._bridge.chat_messages.connect(self._on_chat_messages)
        self._bridge.thinking.connect(self._on_thinking)
        self._bridge.auth_error.connect(self._on_auth_error)

        self._core.on_chat_messages = lambda msgs: self._bridge.chat_messages.emit(msgs)
        self._core.on_thinking = lambda v: self._bridge.thinking.emit(v)
        self._core.on_auth_error = lambda: self._bridge.auth_error.emit()

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # 输入行
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("发送消息…")
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input)

        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        self._stop_btn = QPushButton("结束对话")
        self._stop_btn.clicked.connect(self._on_stop)
        input_row.addWidget(self._stop_btn)

        self._settings_btn = QPushButton("设置")
        self._settings_btn.setEnabled(self._on_settings is not None)
        if self._on_settings:
            self._settings_btn.clicked.connect(self._on_settings)
        input_row.addWidget(self._settings_btn)

        layout.addLayout(input_row)

        # 状态指示
        self._status = QLabel("")
        layout.addWidget(self._status)

        # 对话区
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("对话将显示在这里…")
        layout.addWidget(self._log)

        self._renderer = _TypewriterRenderer(self._log)
        self._renderer.finished.connect(self._on_renderer_finished)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._greeted:
            self._greeted = True
            self._core.start_session()
            QTimer.singleShot(300, self._send_greeting)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()

    @Slot()
    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        if self._needs_clear:
            self._needs_clear = False
            self._log.clear()
            self._stop_btn.setEnabled(True)
        self._append_log(f"[主人] {text}")
        self._core.send(text)

    @Slot()
    def _on_stop(self) -> None:
        """结束对话：等告别语渲染完毕后再重置会话。"""
        self._stop_btn.setEnabled(False)
        self._greeted = False
        self._awaiting_farewell = True
        self._core.send(
            "[系统] 主人即将离开，请回顾 conversation_history 中本次对话的情绪氛围，"
            "以贴合当前情境的情绪向主人告别。"
        )

    @Slot()
    def _on_renderer_finished(self) -> None:
        if not self._awaiting_farewell:
            return
        self._awaiting_farewell = False
        QTimer.singleShot(1500, self._end_session)

    @Slot(list)
    def _on_chat_messages(self, messages: list) -> None:
        if self._renderer:
            for msg in messages:
                self._renderer.enqueue(msg)

    @Slot(bool)
    def _on_thinking(self, thinking: bool) -> None:
        self._status.setText("小空正在思考…" if thinking else "")

    @Slot()
    def _on_auth_error(self) -> None:
        self._status.setText("")
        msg = QMessageBox(self)
        msg.setWindowTitle("API Key 无效")
        msg.setText("请求被拒绝（401/403），可能是 API Key 未设置或已失效。")
        msg.setIcon(QMessageBox.Icon.Warning)
        settings_btn = msg.addButton("去设置", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() is settings_btn and self._on_settings:
            self._on_settings()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _send_greeting(self) -> None:
        self._core.reset_conversation()
        self._core.send("[系统] 新对话开始，请主动向主人打招呼。")

    def _end_session(self) -> None:
        self._core.reset_conversation()
        if self._renderer:
            self._renderer.stop()
        self._needs_clear = True

    @Slot(str)
    def _append_log(self, text: str) -> None:
        self._log.append(text)
