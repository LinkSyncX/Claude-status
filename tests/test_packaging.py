"""打包相关：应用图标（.ico / .icns）与构建脚本的辅助函数。"""

import importlib.util
import os
import pathlib
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

import PySide6
from PySide6 import QtCore
from PySide6 import QtGui

import build
from claude_status import app as app_module
from claude_status import app_icon
from tests import qt

_APP = qt.application()
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int]:
    image = QtGui.QImage.fromData(data, "PNG")
    return image.width(), image.height()


class AppIconTest(unittest.TestCase):
    def test_render_sizes(self):
        for size in (16, 48, 256):
            image = app_icon.render(size)
            self.assertEqual((image.width(), image.height()), (size, size))
            # 圆角外透明，中心不透明。
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertEqual(image.pixelColor(size // 2, size // 2).alpha(), 255)

    def test_ico_structure(self):
        data = app_icon.ico_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", data)
        self.assertEqual((reserved, kind, count), (0, 1, len(app_icon.ICON_SIZES)))
        for index, size in enumerate(app_icon.ICON_SIZES):
            side, _, _, _, planes, bits, length, offset = struct.unpack_from(
                "<BBBBHHII", data, 6 + 16 * index
            )
            self.assertEqual(side, 0 if size == 256 else size)
            self.assertEqual((planes, bits), (1, 32))
            image = data[offset : offset + length]
            self.assertTrue(image.startswith(_PNG_MAGIC))
            self.assertEqual(_png_size(image), (size, size))

    def test_ico_readable_by_qt(self):
        buffer = QtCore.QBuffer()
        buffer.setData(app_icon.ico_bytes())
        buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
        reader = QtGui.QImageReader(buffer, b"ico")
        self.assertEqual(reader.imageCount(), len(app_icon.ICON_SIZES))
        self.assertFalse(reader.read().isNull())

    def test_write_by_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            ico = app_icon.write(folder / "app.ico").read_bytes()
            icns = app_icon.write(folder / "app.icns").read_bytes()
            png = app_icon.write(folder / "app.png").read_bytes()
        self.assertEqual(ico, app_icon.ico_bytes())
        self.assertEqual(icns[:4], b"icns")
        self.assertEqual(_png_size(png), (512, 512))

    def test_icns_structure(self):
        data = app_icon.icns_bytes()
        self.assertEqual(data[:4], b"icns")
        self.assertEqual(struct.unpack_from(">I", data, 4)[0], len(data))
        position, seen = 8, []
        while position < len(data):
            kind = data[position : position + 4]
            (length,) = struct.unpack_from(">I", data, position + 4)
            image = data[position + 8 : position + length]
            self.assertTrue(image.startswith(_PNG_MAGIC))
            seen.append((kind, _png_size(image)[0]))
            position += length
        self.assertEqual(position, len(data))
        self.assertEqual(seen, list(app_icon.ICNS_ENTRIES))

    def test_window_icon_sizes(self):
        sizes = app_icon.icon().availableSizes()
        self.assertIn(QtCore.QSize(16, 16), sizes)
        self.assertIn(QtCore.QSize(256, 256), sizes)

    def test_write_rejects_unknown_format(self):
        with self.assertRaises(ValueError):
            app_icon.write(pathlib.Path("app.bmp"))


class BuildScriptTest(unittest.TestCase):
    def test_unwanted_binaries(self):
        for dest in (
            "PySide6/opengl32sw.dll",
            r"PySide6\plugins\platforminputcontexts\qtvirtualkeyboardplugin.dll",
            "PySide6/plugins/imageformats/qpdf.dll",
        ):
            self.assertTrue(build.unwanted_binary(dest), dest)
        for dest in (
            "PySide6/plugins/platforms/qwindows.dll",
            "PySide6/plugins/imageformats/qsvg.dll",
            "PySide6/Qt6Gui.dll",
        ):
            self.assertFalse(build.unwanted_binary(dest), dest)

    def test_trim_datas_drops_qt_translations(self):
        datas = [
            ("PySide6/translations/qtbase_zh_CN.qm", "x", "DATA"),
            ("PySide6/Qt/translations/qt_de.qm", "x", "DATA"),
            ("md3/assets/fonts/Roboto.ttf", "x", "DATA"),
        ]
        self.assertEqual(
            [dest for dest, _, _ in build.trim_datas(datas)],
            ["md3/assets/fonts/Roboto.ttf"],
        )

    def test_trim_binaries_only_on_windows(self):
        binaries = [("PySide6/opengl32sw.dll", "x", "BINARY")]
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(build.trim_binaries(binaries), binaries)

    @unittest.skipUnless(
        sys.platform == "win32" and importlib.util.find_spec("PyInstaller"),
        "需要 Windows 与 PyInstaller",
    )
    def test_trim_binaries_keeps_linked_qt_libraries(self):
        # 用本机 PySide6 的真实文件：QtWidgets 扩展模块依赖 Core / Gui /
        # Widgets，没有文件引用的 Qt Quick 应被去掉。
        folder = pathlib.Path(PySide6.__file__).parent
        names = ["QtWidgets.pyd", "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"]
        names.append("Qt6Quick.dll")
        binaries = [
            (f"PySide6/{name}", str(folder / name), "BINARY") for name in names
        ]
        kept = {dest for dest, _, _ in build.trim_binaries(binaries)}
        self.assertEqual(
            kept, {f"PySide6/{name}" for name in names if name != "Qt6Quick.dll"}
        )

    def test_version_numbers(self):
        self.assertEqual(build.version_numbers("0.1.0"), (0, 1, 0, 0))
        self.assertEqual(build.version_numbers("1.2.3.4.5"), (1, 2, 3, 4))
        self.assertEqual(build.version_numbers("2.0rc1"), (2, 0, 0, 0))

    # 版本信息只用于 Windows 版；PyInstaller 读取它所需的 pefile 也只在
    # Windows 上随 PyInstaller 安装。
    @unittest.skipUnless(
        sys.platform == "win32" and importlib.util.find_spec("PyInstaller"),
        "需要 Windows 与 PyInstaller",
    )
    def test_version_info_accepted_by_pyinstaller(self):
        from PyInstaller.utils.win32 import versioninfo

        text = build.VERSION_INFO.format(
            numbers=(0, 1, 0, 0),
            version="0.1.0",
            name="Claude Status",
            exe_name="ClaudeStatus.exe",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "version_info.txt"
            path.write_text(text, encoding="utf-8")
            info = versioninfo.load_version_info_from_text_file(str(path))
        self.assertEqual(info.ffi.fileVersionMS, 1)  # 0.1 → (0 << 16) | 1
        self.assertIn("ClaudeStatus.exe", str(info))


class SystemCertificatesTest(unittest.TestCase):
    """打包后的程序在 macOS / Linux 上改用系统的根证书文件。"""

    FEDORA = "/etc/pki/tls/certs/ca-bundle.crt"

    def _run(self, platform, frozen=True, cafile=None, env=None):
        environ = {
            key: value
            for key, value in os.environ.items()
            if key != "SSL_CERT_FILE"
        }
        environ.update(env or {})
        defaults = types.SimpleNamespace(cafile=cafile, capath=None)
        with (
            mock.patch.dict(os.environ, environ, clear=True),
            mock.patch.object(sys, "platform", platform),
            mock.patch.object(sys, "frozen", frozen, create=True),
            mock.patch.object(
                app_module.ssl, "get_default_verify_paths", return_value=defaults
            ),
            mock.patch.object(
                app_module.os.path, "isfile", side_effect=lambda p: p == self.FEDORA
            ),
        ):
            app_module._use_system_certificates()  # pylint: disable=protected-access
            return os.environ.get("SSL_CERT_FILE")

    def test_uses_system_bundle_when_default_missing(self):
        self.assertEqual(self._run("linux"), self.FEDORA)

    def test_keeps_working_defaults_and_user_choice(self):
        self.assertIsNone(self._run("linux", cafile="/usr/lib/ssl/cert.pem"))
        self.assertEqual(
            self._run("linux", env={"SSL_CERT_FILE": "/my/ca.pem"}), "/my/ca.pem"
        )

    def test_only_for_frozen_non_windows(self):
        self.assertIsNone(self._run("linux", frozen=False))
        self.assertIsNone(self._run("win32"))


if __name__ == "__main__":
    unittest.main()
