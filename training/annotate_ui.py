"""AI 辅助标注工具（图形界面版）。

用法：
    python training/annotate_ui.py
    python training/annotate_ui.py --count 600 --output training/data/manual.jsonl

环境变量：
    API_KEY    Gemini API Key

快捷键：
    Ctrl+Enter   保存当前条目
    Ctrl+G       重新生成
    Ctrl+Z       撤销上一条
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

import requests
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.chat_ai import build_router_system_prompt
from ai.personality import PersonalityProfile

CATEGORIES = [
    "日常问候与打招呼",
    "轻松闲聊与情绪陪伴",
    "询问意见或聊天话题",
    "表达喜好、心情、感想",
    "打开或启动应用的指令",
    "搜索或查找信息的指令",
    "文件操作指令（新建/删除/移动/复制）",
    "浏览器操作指令",
    "截图、录屏等系统操作指令",
    "意图模糊、介于闲聊与任务之间的消息",
    "任务成功汇报（user 字段以 [任务完成] 开头）",
    "任务失败汇报（user 字段以 [任务失败] 开头）",
    "澄清问题转发（user 字段以 [需要澄清] 开头）",
]

_GEN_SYSTEM = """\
你是训练数据生成器，负责为 AI 桌面助手"小空"生成对话训练样本。

小空的性格与规则：
{chat_prompt}

你的任务：生成一条属于指定类别的用户消息，以及小空对该消息的理想 JSON 回复。

仅输出如下格式的 JSON，不得包含其他文字：
{{
  "user": "用户发送的消息",
  "response": {{
    "action": "chat_response",
    "params": {{"message": "小空的完整回复"}},
    "expression": "<从可用表情中选一个>",
    "risk_level": 0,
    "reasoning": ""
  }}
}}
若为任务类别，action 改为 route_to_task，params 含 task_instruction（动词开头的单句指令）\
和 message（接单旁白，可为空字符串）。
user 要自然真实，像普通用户随手打的消息。

【可用表情】{expressions}
无后缀 = 身体部位（耳朵/尾巴）有细微变化，表情克制；_full = 表情与身体部位都明显变化。
每条回复必须从中选一个最贴合当前情绪的表情填入 expression 字段。

【特殊类别说明】
- 任务成功汇报：user 字段格式为 "[任务完成] <TaskAI 返回的简短结果描述>"，\
response 固定为 chat_response，message 是小空用角色语气向主人汇报成功的话。
- 任务失败汇报：user 字段格式为 "[任务失败] <TaskAI 返回的失败原因>"，\
response 固定为 chat_response，message 是小空用角色语气向主人说明失败并安抚的话。
- 澄清问题转发：user 字段格式为 "[需要澄清] <TaskAI 提出的问题>"，\
response 固定为 chat_response，message 是小空用角色语气将该问题转达给主人的话。\
"""


def _call_gemini(api_key: str, system: str, user_msg: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        f"/models/gemini-2.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    while True:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 503:
            time.sleep(2)
            continue
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _build_chat(msg: str, expression: str = "idle") -> dict:
    return {
        "action": "chat_response",
        "params": {"message": msg},
        "expression": expression,
        "risk_level": 0,
        "reasoning": "",
    }


def _build_task(task_instr: str, accept_msg: str, expression: str = "idle") -> dict:
    return {
        "action": "route_to_task",
        "params": {"task_instruction": task_instr, "message": accept_msg},
        "expression": expression,
        "risk_level": 0,
        "reasoning": "",
    }


def _flush(output_path: Path, saved: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ex in saved:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


class _Bridge(QObject):
    generated = Signal(str, dict)  # user_input, response
    error = Signal(str)


class AnnotateWindow(QMainWindow):
    def __init__(
        self,
        api_key: str,
        gen_system: str,
        system_prompt: str,
        output_path: Path,
        target: int,
        expressions: list[str],
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self._gen_system = gen_system
        self._system_prompt = system_prompt
        self._output_path = output_path
        self._target = target
        self._expressions = expressions
        self._saved: list[dict] = []
        self._generating = False

        if output_path.exists():
            with output_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._saved.append(json.loads(line))

        self._bridge = _Bridge()
        self._bridge.generated.connect(self._on_generated)
        self._bridge.error.connect(self._on_gen_error)

        self._build_ui()
        self._update_progress()
        if self._saved:
            self._status(f"检测到已有 {len(self._saved)} 条记录，继续追加。")
        self._start_generate()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("AI 辅助标注工具")
        self.resize(720, 580)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(8)

        # 顶部：进度 + 类别
        top_row = QHBoxLayout()
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet("font-weight: bold;")
        top_row.addWidget(self._progress_label)
        top_row.addStretch()
        self._category_label = QLabel()
        self._category_label.setStyleSheet("color: #888;")
        top_row.addWidget(self._category_label)
        layout.addLayout(top_row)

        # 问题
        layout.addWidget(QLabel("问题："))
        self._question_edit = QTextEdit()
        self._question_edit.setMaximumHeight(72)
        self._question_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._question_edit)

        # 回答类型切换
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("回答类型："))
        self._radio_chat = QRadioButton("聊天")
        self._radio_task = QRadioButton("任务")
        self._radio_chat.setChecked(True)
        self._type_group = QButtonGroup()
        self._type_group.addButton(self._radio_chat, 0)
        self._type_group.addButton(self._radio_task, 1)
        self._radio_task.toggled.connect(
            lambda checked: self._stack.setCurrentIndex(1 if checked else 0)
        )
        type_row.addWidget(self._radio_chat)
        type_row.addWidget(self._radio_task)
        type_row.addStretch()
        layout.addLayout(type_row)

        # 聊天 / 任务两个面板
        self._stack = QStackedWidget()

        chat_page = QWidget()
        chat_layout = QVBoxLayout(chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.addWidget(QLabel("聊天回复："))
        self._chat_edit = QTextEdit()
        chat_layout.addWidget(self._chat_edit)
        chat_expr_row = QHBoxLayout()
        chat_expr_row.addWidget(QLabel("表情："))
        self._chat_expr = QComboBox()
        self._chat_expr.addItems(self._expressions)
        chat_expr_row.addWidget(self._chat_expr)
        chat_expr_row.addStretch()
        chat_layout.addLayout(chat_expr_row)
        self._stack.addWidget(chat_page)

        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.addWidget(QLabel("任务指令（动词开头的单句）："))
        self._task_instr_edit = QLineEdit()
        task_layout.addWidget(self._task_instr_edit)
        task_layout.addWidget(QLabel("接单旁白（可空）："))
        self._task_msg_edit = QLineEdit()
        task_layout.addWidget(self._task_msg_edit)
        task_expr_row = QHBoxLayout()
        task_expr_row.addWidget(QLabel("表情："))
        self._task_expr = QComboBox()
        self._task_expr.addItems(self._expressions)
        task_expr_row.addWidget(self._task_expr)
        task_expr_row.addStretch()
        task_layout.addLayout(task_expr_row)
        task_layout.addStretch()
        self._stack.addWidget(task_page)

        layout.addWidget(self._stack)

        # 按钮行
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("重新生成  Ctrl+G")
        self._gen_btn.clicked.connect(self._on_regenerate)
        btn_row.addWidget(self._gen_btn)

        btn_row.addStretch()

        self._undo_btn = QPushButton("撤销上条  Ctrl+Z")
        self._undo_btn.clicked.connect(self._on_undo)
        btn_row.addWidget(self._undo_btn)

        self._save_btn = QPushButton("保存  Ctrl+Enter")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)

        # 状态栏
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._status_label)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._on_save)
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self._on_regenerate)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._on_undo)

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def _start_generate(self) -> None:
        self._set_generating(True)
        category = random.choice(CATEGORIES)
        self._category_label.setText("类别：" + category)

        api_key = self._api_key
        gen_system = self._gen_system

        def _worker() -> None:
            try:
                raw = _call_gemini(api_key, gen_system, f"请生成一条【{category}】类别的训练样例。")
                data = json.loads(raw)
                self._bridge.generated.emit(data["user"], data["response"])
            except Exception as exc:
                self._bridge.error.emit(str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    @Slot(str, dict)
    def _on_generated(self, user_input: str, response: dict) -> None:
        self._set_generating(False)
        self._question_edit.setPlainText(user_input)
        self._populate_response(response)
        self._question_edit.setFocus()

    def _populate_response(self, response: dict) -> None:
        action = response.get("action", "")
        params = response.get("params", {})
        expression = response.get("expression", "idle")
        if action == "route_to_task":
            self._radio_task.setChecked(True)
            self._task_instr_edit.setText(params.get("task_instruction", ""))
            self._task_msg_edit.setText(params.get("message", ""))
            self._set_expr(self._task_expr, expression)
        else:
            self._radio_chat.setChecked(True)
            self._chat_edit.setPlainText(params.get("message", ""))
            self._set_expr(self._chat_expr, expression)

    def _set_expr(self, combo: QComboBox, expression: str) -> None:
        idx = combo.findText(expression)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    @Slot()
    def _on_gen_error(self, error: str) -> None:
        self._set_generating(False)
        self._status("生成失败：" + error, error=True)

    # ------------------------------------------------------------------
    # 按钮操作
    # ------------------------------------------------------------------

    @Slot()
    def _on_save(self) -> None:
        if self._generating:
            return
        question = self._question_edit.toPlainText().strip()
        if not question:
            self._status("问题不能为空", error=True)
            return

        if self._radio_task.isChecked():
            instr = self._task_instr_edit.text().strip()
            if not instr:
                self._status("任务指令不能为空", error=True)
                return
            msg = self._task_msg_edit.text().strip()
            response = _build_task(instr, msg, self._task_expr.currentText())
        else:
            msg = self._chat_edit.toPlainText().strip()
            if not msg:
                self._status("聊天回复不能为空", error=True)
                return
            response = _build_chat(msg, self._chat_expr.currentText())

        record = {
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": question},
                {"role": "assistant", "content": json.dumps(response, ensure_ascii=False)},
            ]
        }
        self._saved.append(record)
        _flush(self._output_path, self._saved)
        self._update_progress()
        self._status(f"已保存（共 {len(self._saved)} 条）")

        if len(self._saved) >= self._target:
            QMessageBox.information(self, "完成", f"已达到目标 {self._target} 条！")
            self.close()
            return

        self._start_generate()

    @Slot()
    def _on_regenerate(self) -> None:
        if not self._generating:
            self._start_generate()

    @Slot()
    def _on_undo(self) -> None:
        if not self._saved:
            self._status("没有可撤销的记录", error=True)
            return
        self._saved.pop()
        _flush(self._output_path, self._saved)
        self._update_progress()
        self._status(f"已撤销（共 {len(self._saved)} 条）")

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _set_generating(self, val: bool) -> None:
        self._generating = val
        self._gen_btn.setEnabled(not val)
        self._save_btn.setEnabled(not val)
        if val:
            self._status("生成中…")

    def _update_progress(self) -> None:
        self._progress_label.setText(f"已保存 {len(self._saved)} / {self._target} 条")
        self._undo_btn.setEnabled(bool(self._saved))

    def _status(self, msg: str, *, error: bool = False) -> None:
        color = "#c00" if error else "#666"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_label.setText(msg)


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 辅助标注工具（图形界面）")
    parser.add_argument("--output", type=Path, default=Path("training/data/manual.jsonl"))
    parser.add_argument("--count", type=int, default=600, help="目标条数")
    args = parser.parse_args()

    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("错误：请设置环境变量 API_KEY（Gemini API Key）")
        sys.exit(1)

    personality = PersonalityProfile.load_default()
    system_prompt = build_router_system_prompt(personality)
    expression_list = ", ".join(personality.expressions.keys())
    gen_system = _GEN_SYSTEM.format(
        chat_prompt=personality.chat_prompt, expressions=expression_list
    )

    app = QApplication(sys.argv)
    window = AnnotateWindow(
        api_key,
        gen_system,
        system_prompt,
        args.output,
        args.count,
        list(personality.expressions.keys()),
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
