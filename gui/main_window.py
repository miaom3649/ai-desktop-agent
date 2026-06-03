"""主窗口：指令输入、运行/停止控制、日志输出。"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agent.core import AgentCore

logger = logging.getLogger(__name__)


class _AgentWorker(QObject):
    """在子线程中运行 AgentCore，通过 Signal 向主窗口传递日志和结果。"""

    log = Signal(str)
    finished = Signal(str)

    def __init__(self, core: AgentCore) -> None:
        super().__init__()
        self._core = core

    @Slot(str)
    def run(self, instruction: str) -> None:
        self._core.on_message = lambda text: self.log.emit(text)
        try:
            result = self._core.run(instruction)
        except Exception as exc:
            result = f"错误：{exc}"
        finally:
            self._core.on_message = None
        self.finished.emit(result)


class MainWindow(QMainWindow):
    """Phase 1 最简主窗口。"""

    _start_requested = Signal(str)

    def __init__(self, core: AgentCore) -> None:
        super().__init__()
        self.setWindowTitle("AI Desktop Agent")
        self.resize(640, 480)

        self._core = core
        self._thread: QThread | None = None
        self._worker: _AgentWorker | None = None
        self._clear_on_next_run: bool = False
        self._farewell_pending: bool = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # 指令输入行
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("输入指令，例如：打开记事本并输入 Hello")
        self._input.returnPressed.connect(self._on_run)
        input_row.addWidget(self._input)

        self._run_btn = QPushButton("运行")
        self._run_btn.clicked.connect(self._on_run)
        input_row.addWidget(self._run_btn)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        input_row.addWidget(self._stop_btn)

        layout.addLayout(input_row)

        # 日志区
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("运行日志将显示在这里…")
        layout.addWidget(self._log)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._thread is None:
            QTimer.singleShot(200, self._start_greeting)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭按钮只隐藏窗口，保持托盘驻留。"""
        event.ignore()
        self.hide()

    @Slot()
    def _on_run(self) -> None:
        instruction = self._input.text().strip()
        if not instruction or self._thread is not None:
            return

        if self._clear_on_next_run:
            self._log.clear()
            self._core.reset_conversation()
            self._clear_on_next_run = False
        logger.info({"event": "conversation_start", "instruction": instruction})
        self._append_log(f">>> {instruction}")
        self._set_running(True)

        self._thread = QThread()
        self._worker = _AgentWorker(self._core)
        self._worker.moveToThread(self._thread)

        self._start_requested.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

        self._start_requested.emit(instruction)

    @Slot()
    def _on_stop(self) -> None:
        self._clear_on_next_run = True
        self._farewell_pending = True
        self._stop_btn.setEnabled(False)
        logger.info({"event": "conversation_end"})
        if self._thread is None:
            self._farewell_pending = False
            self._start_farewell()
            return
        self._core.stop()
        self._append_log("正在停止，等待当前步骤完成…")

    @Slot(str)
    def _on_finished(self, result: str) -> None:
        self._append_log(result)
        self._cleanup_thread()
        if self._farewell_pending:
            self._farewell_pending = False
            self._start_farewell()
        else:
            self._set_running(False)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @Slot(str)
    def _append_log(self, text: str) -> None:
        self._log.append(text)

    def _start_farewell(self) -> None:
        self._set_running(True)
        self._stop_btn.setEnabled(False)
        self._thread = QThread()
        self._worker = _AgentWorker(self._core)
        self._worker.moveToThread(self._thread)
        self._start_requested.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()
        self._start_requested.emit("再见")

    def _start_greeting(self) -> None:
        self._core.reset_conversation()
        self._set_running(True)
        self._stop_btn.setEnabled(False)
        self._thread = QThread()
        self._worker = _AgentWorker(self._core)
        self._worker.moveToThread(self._thread)
        self._start_requested.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()
        self._start_requested.emit("（新对话开始，请主动向主人打招呼）")

    def _set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)
        self._input.setEnabled(not running)
        if running:
            self._stop_btn.setEnabled(True)
        elif not self._clear_on_next_run:
            self._stop_btn.setEnabled(True)

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            if self._worker is not None:
                try:
                    self._start_requested.disconnect(self._worker.run)
                except RuntimeError:
                    pass
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
