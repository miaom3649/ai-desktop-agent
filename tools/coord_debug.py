"""坐标诊断工具：对比截图坐标空间与屏幕坐标，定位 AI 点击偏移的根本原因。

使用方法：
  python tools/coord_debug.py

窗口操作：
  - 鼠标悬停在截图上 → 实时显示截图坐标以及它映射到屏幕的坐标
  - 移动鼠标到屏幕上某个目标元素（离开截图窗口）→ 右侧"实际光标"更新
  - 在底部输入框粘贴 AI 日志里的坐标 → 立即显示映射结果和误差
"""

from __future__ import annotations

import io
import os
import sys

# 把项目根目录加入 path，这样可以直接 import 项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mss
import pyautogui
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

MAX_COMPRESSED_WIDTH = 1280
JPEG_QUALITY = 85


# ---------------------------------------------------------------------------
# 截图 & 尺寸计算
# ---------------------------------------------------------------------------


def _capture() -> tuple[Image.Image, Image.Image]:
    """返回 (raw_img, compressed_img)，raw 是 mss 原始像素，compressed 是压缩后图。"""
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
        raw_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if raw_img.width > MAX_COMPRESSED_WIDTH:
        ratio = MAX_COMPRESSED_WIDTH / raw_img.width
        comp = raw_img.resize(
            (MAX_COMPRESSED_WIDTH, int(raw_img.height * ratio)), Image.Resampling.LANCZOS
        )
    else:
        comp = raw_img.copy()

    return raw_img, comp


# ---------------------------------------------------------------------------
# 可悬停截图标签
# ---------------------------------------------------------------------------


class HoverImageLabel(QLabel):
    """显示截图并在鼠标悬停时回调坐标。"""

    def __init__(self, pixmap: QPixmap, on_hover) -> None:
        super().__init__()
        self._on_hover = on_hover
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event) -> None:
        self._on_hover(event.pos().x(), event.pos().y())

    def leaveEvent(self, event) -> None:
        self._on_hover(None, None)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------


class DebugWindow(QMainWindow):
    def __init__(
        self,
        raw_w: int,
        raw_h: int,
        comp_img: Image.Image,
        screen_w: int,
        screen_h: int,
    ) -> None:
        super().__init__()
        self._comp_w = comp_img.width
        self._comp_h = comp_img.height
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._scale_x = screen_w / comp_img.width
        self._scale_y = screen_h / comp_img.height

        self.setWindowTitle(
            f"坐标诊断  —  "
            f"截图 {self._comp_w}×{self._comp_h}  →  屏幕 {screen_w}×{screen_h}  "
            f"(缩放 x={self._scale_x:.3f}, y={self._scale_y:.3f})"
        )
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # PIL → QPixmap
        buf = io.BytesIO()
        comp_img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setSpacing(6)

        # --- 信息栏 ---
        info_box = QGroupBox("尺寸与缩放系数")
        info_layout = QVBoxLayout(info_box)
        mono = QFont("Monospace", 9)
        compress_note = (
            f"  （压缩比 {raw_w / self._comp_w:.2f}x）" if raw_w != self._comp_w else "  （未压缩）"
        )
        info_text = (
            f"mss 物理截图:   {raw_w} × {raw_h} px\n"
            f"压缩后 (AI视角): {self._comp_w} × {self._comp_h} px{compress_note}\n"
            f"pyautogui 逻辑: {screen_w} × {screen_h} px\n"
            f"坐标缩放系数:    x = {self._scale_x:.4f},  y = {self._scale_y:.4f}\n"
        )
        if abs(self._scale_x - 1.0) > 0.01 or abs(self._scale_y - 1.0) > 0.01:
            info_text += "⚠  缩放系数 ≠ 1 — AI 坐标传给 pyautogui 前必须乘以此系数！"
        else:
            info_text += "✓  缩放系数 ≈ 1 — 坐标空间一致，无需映射。"
        lbl = QLabel(info_text)
        lbl.setFont(mono)
        info_layout.addWidget(lbl)
        main_layout.addWidget(info_box)

        # --- 截图 + 侧栏 ---
        splitter = QSplitter(Qt.Horizontal)

        # 截图区
        self._img_label = HoverImageLabel(pixmap, self._on_hover)
        splitter.addWidget(self._img_label)

        # 侧栏
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setAlignment(Qt.AlignTop)

        # 悬停坐标
        hover_box = QGroupBox("鼠标悬停（在截图上移动）")
        hover_layout = QVBoxLayout(hover_box)
        self._hover_img = QLabel("截图坐标:  —")
        self._hover_screen = QLabel("映射屏幕:  —")
        self._hover_img.setFont(mono)
        self._hover_screen.setFont(mono)
        hover_layout.addWidget(self._hover_img)
        hover_layout.addWidget(self._hover_screen)
        side_layout.addWidget(hover_box)

        # 实际光标
        cursor_box = QGroupBox("实际光标（移到屏幕目标元素时记录）")
        cursor_layout = QVBoxLayout(cursor_box)
        self._cursor_label = QLabel("pyautogui.position():  —")
        self._cursor_label.setFont(mono)
        cursor_layout.addWidget(self._cursor_label)
        side_layout.addWidget(cursor_box)

        # 手动输入 AI 坐标
        input_box = QGroupBox("输入 AI 日志中的坐标（验证映射）")
        input_layout = QVBoxLayout(input_box)
        coord_row = QHBoxLayout()
        coord_row.addWidget(QLabel("x:"))
        self._input_x = QLineEdit()
        self._input_x.setPlaceholderText("如 640")
        coord_row.addWidget(self._input_x)
        coord_row.addWidget(QLabel("y:"))
        self._input_y = QLineEdit()
        self._input_y.setPlaceholderText("如 360")
        coord_row.addWidget(self._input_y)
        input_layout.addLayout(coord_row)
        self._manual_result = QLabel("映射结果: —")
        self._manual_result.setFont(mono)
        self._manual_result.setWordWrap(True)
        input_layout.addWidget(self._manual_result)
        self._input_x.textChanged.connect(self._on_manual_input)
        self._input_y.textChanged.connect(self._on_manual_input)
        side_layout.addWidget(input_box)

        # 差值说明
        note = QLabel(
            "使用方法：\n"
            "① 悬停在截图目标元素上，记下映射屏幕坐标\n"
            "② 把鼠标移到屏幕上同一元素，读实际光标值\n"
            "③ 两者之差即当前代码的点击偏移量"
        )
        note.setWordWrap(True)
        note.setFont(QFont("", 8))
        side_layout.addWidget(note)

        splitter.addWidget(side)
        splitter.setSizes([self._comp_w, 340])
        main_layout.addWidget(splitter)

        # 定时刷新光标位置
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_cursor)
        self._timer.start(80)

    def _on_hover(self, img_x, img_y) -> None:
        if img_x is None:
            self._hover_img.setText("截图坐标:  —")
            self._hover_screen.setText("映射屏幕:  —")
            return
        sx = round(img_x * self._scale_x)
        sy = round(img_y * self._scale_y)
        self._hover_img.setText(f"截图坐标:  ({img_x}, {img_y})")
        self._hover_screen.setText(f"映射屏幕:  ({sx}, {sy})")

    def _update_cursor(self) -> None:
        try:
            pos = pyautogui.position()
            self._cursor_label.setText(f"pyautogui.position():  ({pos.x}, {pos.y})")
        except Exception:
            pass

    def _on_manual_input(self) -> None:
        try:
            ai_x = int(self._input_x.text())
            ai_y = int(self._input_y.text())
        except ValueError:
            self._manual_result.setText("映射结果: —")
            return
        sx = round(ai_x * self._scale_x)
        sy = round(ai_y * self._scale_y)
        in_bounds = 0 <= sx < self._screen_w and 0 <= sy < self._screen_h
        bounds_note = "" if in_bounds else "  ⚠ 超出屏幕范围！"
        self._manual_result.setText(
            f"AI ({ai_x}, {ai_y})  →  屏幕 ({sx}, {sy}){bounds_note}\n"
            f"当前代码（无缩放）点到: ({ai_x}, {ai_y})"
            + (f"\n偏移量: Δx={sx - ai_x:+d}, Δy={sy - ai_y:+d}" if self._scale_x != 1.0 else "")
        )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    print("正在截图…")
    raw_img, comp_img = _capture()
    screen_w, screen_h = pyautogui.size()

    print(f"mss 物理截图:    {raw_img.width} × {raw_img.height}")
    print(f"压缩后 (AI视角): {comp_img.width} × {comp_img.height}")
    print(f"pyautogui 逻辑: {screen_w} × {screen_h}")
    scale_x = screen_w / comp_img.width
    scale_y = screen_h / comp_img.height
    print(f"坐标缩放系数:    x={scale_x:.4f}, y={scale_y:.4f}")

    if abs(scale_x - 1.0) > 0.01 or abs(scale_y - 1.0) > 0.01:
        print("\n⚠  坐标空间不一致：AI 坐标需要乘以缩放系数才能对应到正确屏幕位置。")
        print("   当前代码未做此映射，这可能是点击偏移的原因。")
    else:
        print("\n✓  截图与屏幕坐标空间一致，坐标映射无问题。")

    app = QApplication(sys.argv)
    win = DebugWindow(
        raw_w=raw_img.width,
        raw_h=raw_img.height,
        comp_img=comp_img,
        screen_w=screen_w,
        screen_h=screen_h,
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
