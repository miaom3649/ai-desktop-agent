"""屏幕截图与图像压缩（发送前缩放至最大宽度 1280px，JPEG 质量 85）。"""

from __future__ import annotations

import base64
import io

import mss
from PIL import Image


class ScreenCapture:
    """截取主屏并输出压缩后的 JPEG base64 字符串。"""

    MAX_WIDTH = 1280
    JPEG_QUALITY = 85

    def capture(self) -> str:
        """截取主屏，压缩后返回 base64 编码的 JPEG 字符串。"""
        img = self._grab_primary()

        if img.width > self.MAX_WIDTH:
            ratio = self.MAX_WIDTH / img.width
            img = img.resize((self.MAX_WIDTH, int(img.height * ratio)), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=self.JPEG_QUALITY)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _grab_primary(self) -> Image.Image:
        """截取主屏原始像素，monitors[1] 是主屏，monitors[0] 是所有屏合并区域。"""
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
