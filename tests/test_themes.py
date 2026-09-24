"""界面风格（Material / 极简白）与控件对齐的测试。"""

import unittest

from PySide6 import QtWidgets

from md3.theme import theme as theme_module

from claude_status import app as app_module
from claude_status import models
from claude_status import themes
from claude_status.widgets import common
from tests import qt

_APP = qt.application()


def _rgb(theme: theme_module.Theme, role: str) -> int:
    return theme.argb(role) & 0xFFFFFF


class ThemeTest(unittest.TestCase):
    def setUp(self):
        self.current = theme_module.Theme.from_seed(
            "#D97757", extended=app_module.EXTENDED_COLORS
        )

    def test_minimal_light_and_dark(self):
        light = themes.build(
            models.Settings(theme_style=themes.MINIMAL), self.current
        )
        self.assertEqual(_rgb(light, "surface"), 0xFFFFFF)
        self.assertEqual(_rgb(light, "primary"), 0x1A1A1A)
        self.assertFalse(light.dark)
        # 状态色保持彩色，含义不变。
        self.assertTrue(light.has_color("success"))
        self.assertNotEqual(_rgb(light, "error"), _rgb(light, "on_surface"))
        dark = themes.build(
            models.Settings(theme_style=themes.MINIMAL, dark=True), self.current
        )
        self.assertTrue(dark.dark)
        self.assertEqual(_rgb(dark, "surface"), 0x141414)
        self.assertEqual(_rgb(dark, "on_surface"), 0xEDEDED)

    def test_material_rebuild_is_stable(self):
        settings = models.Settings(seed="#D97757")
        first = themes.build(settings, self.current)
        # 设置没有变化时生成相同的主题，不会触发整页重绘。
        self.assertEqual(first, themes.build(settings, first))
        self.assertNotEqual(_rgb(first, "surface"), 0xFFFFFF)

    def test_settings_roundtrip(self):
        settings = models.Settings(theme_style=themes.MINIMAL)
        restored = models.Settings.from_dict(settings.to_dict())
        self.assertEqual(restored.theme_style, themes.MINIMAL)
        bogus = models.Settings.from_dict({"theme_style": "neon"})
        self.assertEqual(bogus.theme_style, themes.MATERIAL)


class FlushRowTest(unittest.TestCase):
    def test_controls_align_with_text(self):
        host = QtWidgets.QWidget()
        host.resize(300, 120)
        layout = QtWidgets.QVBoxLayout(host)
        layout.setContentsMargins(20, 0, 0, 0)
        button = QtWidgets.QPushButton("x")
        layout.addLayout(common.row(button, None, flush=True))
        label = QtWidgets.QLabel("y")
        layout.addWidget(label)
        host.show()
        _APP.processEvents()
        # md3 控件的可见边缘在控件内缩进 CONTROL_INSET，整行左移同样距离。
        self.assertEqual(
            button.geometry().x() + common.CONTROL_INSET, label.geometry().x()
        )
        host.close()


if __name__ == "__main__":
    unittest.main()
