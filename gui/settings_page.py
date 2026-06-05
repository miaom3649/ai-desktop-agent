"""设置页面：AI 后端选择、API Key 配置、首次启动引导。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.app_config import AppConfig

_PROVIDERS: list[tuple[str, str]] = [
    ("gemini", "Google Gemini（推荐，有免费额度）"),
    ("claude", "Anthropic Claude"),
    ("openai", "OpenAI"),
]

_DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}

_KEY_HINTS: dict[str, str] = {
    "gemini": "AIza... （Google AI Studio 获取）",
    "claude": "sk-ant-... （console.anthropic.com 获取）",
    "openai": "sk-... （platform.openai.com 获取）",
}


class SettingsPage(QDialog):
    """AI 配置对话框，可作为首次启动引导或从菜单打开。"""

    def __init__(
        self,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
        parent: QWidget | None = None,
        first_launch: bool = False,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._on_save = on_save
        self._first_launch = first_launch
        self.setWindowTitle("AI 配置")
        self.setMinimumWidth(460)
        if first_launch:
            # 首次启动时禁止关闭，必须完成配置
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if self._first_launch:
            hint = QLabel(
                "首次使用需要配置 AI 服务的 API Key 才能开始工作喵。\n"
                "推荐使用 Google Gemini，有免费额度，开箱即用。"
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        # Provider 选择
        self._backend_combo = QComboBox()
        for key, label in _PROVIDERS:
            self._backend_combo.addItem(label, key)
        backend = self._config.ai.backend
        idx = next((i for i, (k, _) in enumerate(_PROVIDERS) if k == backend), 0)
        self._backend_combo.setCurrentIndex(idx)
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        form.addRow("AI 服务商：", self._backend_combo)

        # 模型名（可选）
        self._model_input = QLineEdit(self._config.ai.model)
        self._model_input.setPlaceholderText(self._default_model())
        form.addRow("模型（留空用默认）：", self._model_input)

        # API Key（密码框 + 显示/隐藏按钮）
        key_row = QHBoxLayout()
        self._key_input = QLineEdit(self._config.ai.api_key)
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText(self._key_hint())
        key_row.addWidget(self._key_input)

        self._show_key_btn = QPushButton("显示")
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.setFixedWidth(52)
        self._show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._show_key_btn)

        key_widget = QWidget()
        key_widget.setLayout(key_row)
        form.addRow("API Key：", key_widget)

        layout.addLayout(form)

        # 确认/取消按钮
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        if self._first_launch:
            btn_box.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        btn_box.accepted.connect(self._on_save_clicked)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _default_model(self) -> str:
        backend = self._backend_combo.currentData()
        return _DEFAULT_MODELS.get(backend, "")

    def _key_hint(self) -> str:
        backend = self._backend_combo.currentData()
        return _KEY_HINTS.get(backend, "粘贴你的 API Key")

    def _on_backend_changed(self, _index: int) -> None:
        self._model_input.setPlaceholderText(self._default_model())
        self._key_input.setPlaceholderText(self._key_hint())

    def _toggle_key_visibility(self, checked: bool) -> None:
        self._key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self._show_key_btn.setText("隐藏" if checked else "显示")

    def _on_save_clicked(self) -> None:
        api_key = self._key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请填入有效的 API Key 才能继续喵。")
            return
        self._config.ai.backend = self._backend_combo.currentData()
        self._config.ai.model = self._model_input.text().strip()
        self._config.ai.api_key = api_key
        self._config.save()
        self._on_save(self._config)
        self.accept()
