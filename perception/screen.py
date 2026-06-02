"""屏幕截图与图像压缩（发送前缩放至最大宽度 1280px，JPEG 质量 85）。"""

from __future__ import annotations


class ScreenCapture:
    """跨平台屏幕截图，输出压缩后的 JPEG base64 字符串。"""

    MAX_WIDTH = 1280
    JPEG_QUALITY = 85

    def capture(self) -> str:
        """截取全屏并返回 base64 编码的 JPEG 字符串。"""
        raise NotImplementedError
