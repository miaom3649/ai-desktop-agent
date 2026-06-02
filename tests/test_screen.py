"""perception/screen.py 单元测试，mock mss 不产生真实截图。"""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from perception.screen import ScreenCapture


def _make_fake_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color=(100, 149, 237))


def _make_mss_mock(img: Image.Image) -> MagicMock:
    """构造一个模拟 mss.mss() 上下文管理器，返回指定图像的原始数据。"""
    raw_bytes = img.tobytes("raw", "BGRX")

    grab_result = MagicMock()
    grab_result.size = img.size
    grab_result.bgra = raw_bytes

    sct = MagicMock()
    sct.monitors = [None, {"left": 0, "top": 0, "width": img.width, "height": img.height}]
    sct.grab.return_value = grab_result
    sct.__enter__ = MagicMock(return_value=sct)
    sct.__exit__ = MagicMock(return_value=False)

    mss_mock = MagicMock()
    mss_mock.return_value = sct
    return mss_mock


class TestScreenCapture:
    def test_returns_valid_base64_jpeg(self) -> None:
        img = _make_fake_image(800, 600)
        with patch("perception.screen.mss.mss", _make_mss_mock(img)):
            result = ScreenCapture().capture()

        decoded = base64.b64decode(result)
        out = Image.open(io.BytesIO(decoded))
        assert out.format == "JPEG"

    def test_resizes_when_width_exceeds_max(self) -> None:
        img = _make_fake_image(2560, 1440)
        with patch("perception.screen.mss.mss", _make_mss_mock(img)):
            result = ScreenCapture().capture()

        decoded = base64.b64decode(result)
        out = Image.open(io.BytesIO(decoded))
        assert out.width == ScreenCapture.MAX_WIDTH
        assert out.height == int(1440 * ScreenCapture.MAX_WIDTH / 2560)

    def test_no_resize_when_width_within_limit(self) -> None:
        img = _make_fake_image(1024, 768)
        with patch("perception.screen.mss.mss", _make_mss_mock(img)):
            result = ScreenCapture().capture()

        decoded = base64.b64decode(result)
        out = Image.open(io.BytesIO(decoded))
        assert out.width == 1024

    def test_grabs_primary_monitor_not_combined(self) -> None:
        img = _make_fake_image(800, 600)
        mss_mock = _make_mss_mock(img)
        with patch("perception.screen.mss.mss", mss_mock):
            ScreenCapture().capture()

        sct = mss_mock.return_value
        # monitors[1] 是主屏，monitors[0] 是所有屏合并区域
        sct.grab.assert_called_once_with(sct.monitors[1])
