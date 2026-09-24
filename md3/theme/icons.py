"""Material Symbols 与 SVG 图标。

Material Symbols 图标以字体字形绘制，名称即图标名（例如 ``"home"``、
``"favorite"``），通过码点表解析，填充、粗细等样式由可变字体轴控制。
``SvgIcon`` 以 ``QSvgRenderer`` 绘制任意 SVG 文件或内联数据，默认按内容色
着色（单色图标），也可保留原始配色。

SVG 图标可以注册到图标库后按名称使用：``register_svg("logo", path)`` 之后
所有接受图标名的组件都能写 ``icon="logo"``；``register_svg_directory``
一次注册整个文件夹。随包附带 M3 形状库的 33 个形状，名称形如
``"shapes/soft_burst"``。
"""

from __future__ import annotations

from collections.abc import Iterable
import dataclasses
import hashlib
import logging
import pathlib

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtSvg

from md3 import assets
from md3.theme import fonts

_LOGGER = logging.getLogger(__name__)

DEFAULT_SIZE = 24.0
BUNDLED_SVG_PREFIX = "shapes/"
_PIXMAP_CACHE_LIMIT = 512

# 码点表在首次使用时读取一次。
_codepoints: dict[str, str] | None = None
_pixmap_cache: dict[tuple, QtGui.QPixmap] = {}
_missing_font_reported = False
# SVG：渲染器按来源缓存；内联数据按摘要存放；图标库按名称登记。
_renderers: dict[str, QtSvg.QSvgRenderer] = {}
_inline_sources: dict[str, bytes] = {}
_svg_registry: dict[str, SvgIcon] = {}
_bundled_loaded = False


def _load_codepoints() -> dict[str, str]:
    global _codepoints  # pylint: disable=global-statement
    if _codepoints is not None:
        return _codepoints
    table: dict[str, str] = {}
    path = assets.MATERIAL_SYMBOLS_CODEPOINTS_FILE
    if path.is_file():
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                parts = line.split()
                if len(parts) == 2:
                    table[parts[0]] = chr(int(parts[1], 16))
    else:
        _LOGGER.warning("未找到图标码点表: %s", path)
    _codepoints = table
    return table


def codepoint(name: str) -> str:
    """返回图标对应的单字符字形。

    Raises:
        KeyError: 图标名不存在。
    """
    table = _load_codepoints()
    try:
        return table[name]
    except KeyError as exc:
        raise KeyError(f"未知的 Material Symbols 图标: {name!r}") from exc


def has_icon(name: str) -> bool:
    """图标名是否存在。"""
    return name in _load_codepoints()


def icon_names() -> tuple[str, ...]:
    """全部可用图标名，按字母序。"""
    return tuple(sorted(_load_codepoints()))


@dataclasses.dataclass(frozen=True)
class Icon:
    """一个可绘制的 Material Symbols 图标。

    Attributes:
        name: 图标名。
        size: 图标尺寸（dp）。
        fill: 是否填充。
        weight: 线条粗细（100–700）。
        grade: 灰度（-25–200）。
        optical_size: 光学尺寸，默认等于 size。
    """

    name: str
    size: float = DEFAULT_SIZE
    fill: bool = False
    weight: int = 400
    grade: int = 0
    optical_size: float | None = None

    @property
    def glyph(self) -> str:
        """字形字符。"""
        return codepoint(self.name)

    def font(self) -> QtGui.QFont | None:
        """图标字体，图标字体不可用时为 None。"""
        return fonts.symbols_font(
            self.size,
            fill=self.fill,
            weight=self.weight,
            grade=self.grade,
            optical_size=self.optical_size,
        )

    def with_fill(self, fill: bool) -> Icon:
        """返回切换填充状态后的图标。"""
        return dataclasses.replace(self, fill=fill)

    def with_size(self, size: float) -> Icon:
        """返回改变尺寸后的图标。"""
        return dataclasses.replace(self, size=size)

    def paint(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF | QtCore.QRect,
        color: QtGui.QColor,
    ) -> None:
        """把图标居中绘制到矩形内。"""
        font = self.font()
        if font is None:
            _report_missing_font()
            return
        painter.save()
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(
            QtCore.QRectF(rect),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            self.glyph,
        )
        painter.restore()

    def pixmap(
        self, color: QtGui.QColor, device_pixel_ratio: float = 1.0
    ) -> QtGui.QPixmap:
        """渲染为带缓存的 ``QPixmap``。"""
        key = (
            self.name,
            self.size,
            self.fill,
            self.weight,
            self.grade,
            self.optical_size,
            color.rgba(),
            device_pixel_ratio,
        )
        cached = _pixmap_cache.get(key)
        if cached is not None:
            return cached
        side = max(1, round(self.size * device_pixel_ratio))
        image = QtGui.QImage(
            side, side, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        image.setDevicePixelRatio(device_pixel_ratio)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        self.paint(painter, QtCore.QRectF(0, 0, self.size, self.size), color)
        painter.end()
        pixmap = QtGui.QPixmap.fromImage(image)
        _store_pixmap(key, pixmap)
        return pixmap

    def qicon(self, color: QtGui.QColor) -> QtGui.QIcon:
        """转换为可用于原生 Qt 控件的 ``QIcon``。"""
        icon = QtGui.QIcon()
        for ratio in (1.0, 2.0):
            icon.addPixmap(self.pixmap(color, ratio))
        return icon


def _store_pixmap(key: tuple, pixmap: QtGui.QPixmap) -> None:
    if len(_pixmap_cache) > _PIXMAP_CACHE_LIMIT:
        _pixmap_cache.clear()
    _pixmap_cache[key] = pixmap


def _inline_key(data: bytes) -> str:
    return "data:" + hashlib.sha1(data).hexdigest()  # noqa: S324 - 仅作缓存键


def _renderer(source: str) -> QtSvg.QSvgRenderer:
    renderer = _renderers.get(source)
    if renderer is None:
        if source in _inline_sources:
            renderer = QtSvg.QSvgRenderer(
                QtCore.QByteArray(_inline_sources[source])
            )
        else:
            renderer = QtSvg.QSvgRenderer(source)
        if not renderer.isValid():
            _LOGGER.warning("SVG 无法解析: %s", source[:80])
        _renderers[source] = renderer
    return renderer


@dataclasses.dataclass(frozen=True)
class SvgIcon:
    """一个以 SVG 绘制的图标，接口与 ``Icon`` 一致。

    通过 ``SvgIcon.from_file`` / ``SvgIcon.from_data`` 创建，或经
    ``register_svg`` 注册后按名称使用。

    Attributes:
        source: 文件路径，或内联数据的摘要标识。
        size: 图标尺寸（dp），SVG 按比例缩放并居中。
        tint: 为真时忽略 SVG 自身颜色，整体以内容色着色；为假时保留原色。
        filled_source: ``with_fill(True)`` 时使用的替代来源（如填充版文件）。
        name: 便于识别的名称（注册名或文件名）。
    """

    source: str
    size: float = DEFAULT_SIZE
    tint: bool = True
    filled_source: str | None = None
    name: str = ""

    @classmethod
    def from_file(
        cls,
        path: str | pathlib.Path,
        size: float = DEFAULT_SIZE,
        tint: bool = True,
        filled_path: str | pathlib.Path | None = None,
        name: str = "",
    ) -> SvgIcon:
        """由 SVG 文件创建图标。"""
        path = pathlib.Path(path)
        return cls(
            str(path),
            size,
            tint,
            str(filled_path) if filled_path is not None else None,
            name or path.stem,
        )

    @classmethod
    def from_data(
        cls,
        data: str | bytes,
        size: float = DEFAULT_SIZE,
        tint: bool = True,
        name: str = "",
    ) -> SvgIcon:
        """由内联 SVG 文本或字节创建图标。"""
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        key = _inline_key(payload)
        _inline_sources.setdefault(key, payload)
        return cls(key, size, tint, None, name)

    def renderer(self) -> QtSvg.QSvgRenderer:
        """共享的 ``QSvgRenderer``（按来源缓存）。"""
        return _renderer(self.source)

    def is_valid(self) -> bool:
        """SVG 是否成功解析。"""
        return self.renderer().isValid()

    def with_fill(self, fill: bool) -> SvgIcon:
        """切换到填充版来源（未提供替代来源时返回自身）。"""
        if not fill or self.filled_source is None:
            return self
        return dataclasses.replace(
            self, source=self.filled_source, filled_source=None
        )

    def with_size(self, size: float) -> SvgIcon:
        """返回改变尺寸后的图标。"""
        return dataclasses.replace(self, size=size)

    def with_tint(self, tint: bool) -> SvgIcon:
        """返回切换着色方式后的图标。"""
        return dataclasses.replace(self, tint=tint)

    def _target_rect(self, bounds: QtCore.QRectF) -> QtCore.QRectF:
        """SVG 在目标矩形内等比缩放并居中后的绘制矩形。"""
        view = self.renderer().viewBoxF()
        if view.isEmpty():
            default = self.renderer().defaultSize()
            view = QtCore.QRectF(0, 0, default.width(), default.height())
        if view.isEmpty():
            return bounds
        scale = min(
            bounds.width() / view.width(), bounds.height() / view.height()
        )
        width, height = view.width() * scale, view.height() * scale
        return QtCore.QRectF(
            bounds.center().x() - width / 2,
            bounds.center().y() - height / 2,
            width,
            height,
        )

    def paint(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF | QtCore.QRect,
        color: QtGui.QColor,
    ) -> None:
        """把图标居中绘制到矩形内（大小取 ``size``）。"""
        rect = QtCore.QRectF(rect)
        device = painter.device()
        ratio = device.devicePixelRatioF() if device is not None else 1.0
        pixmap = self.pixmap(color, ratio)
        if pixmap.isNull():
            return
        logical = QtCore.QSizeF(pixmap.size()) / ratio
        painter.drawPixmap(
            QtCore.QPointF(
                rect.center().x() - logical.width() / 2,
                rect.center().y() - logical.height() / 2,
            ),
            pixmap,
        )

    def pixmap(
        self, color: QtGui.QColor, device_pixel_ratio: float = 1.0
    ) -> QtGui.QPixmap:
        """渲染为带缓存的 ``QPixmap``。"""
        key = (
            "svg",
            self.source,
            self.size,
            self.tint,
            color.rgba() if self.tint else 0,
            device_pixel_ratio,
        )
        cached = _pixmap_cache.get(key)
        if cached is not None:
            return cached
        renderer = self.renderer()
        side = max(1, round(self.size * device_pixel_ratio))
        image = QtGui.QImage(
            side, side, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        image.setDevicePixelRatio(device_pixel_ratio)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        if renderer.isValid():
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform
            )
            bounds = QtCore.QRectF(0, 0, self.size, self.size)
            renderer.render(painter, self._target_rect(bounds))
            if self.tint:
                # 只保留 SVG 的透明度，颜色全部替换为内容色。
                painter.setCompositionMode(
                    QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
                )
                painter.fillRect(bounds, color)
            painter.end()
        pixmap = QtGui.QPixmap.fromImage(image)
        _store_pixmap(key, pixmap)
        return pixmap

    def qicon(self, color: QtGui.QColor) -> QtGui.QIcon:
        """转换为可用于原生 Qt 控件的 ``QIcon``。"""
        icon = QtGui.QIcon()
        for ratio in (1.0, 2.0):
            icon.addPixmap(self.pixmap(color, ratio))
        return icon


AnyIcon = Icon | SvgIcon
IconLike = str | pathlib.Path | Icon | SvgIcon | None


# ---- SVG 图标库 -------------------------------------------------------------


def register_svg(
    name: str,
    source: str | pathlib.Path | bytes,
    filled: str | pathlib.Path | None = None,
    tint: bool = True,
) -> SvgIcon:
    """把一个 SVG 注册到图标库，之后可按 ``name`` 在任何组件中使用。

    Args:
        name: 图标名，建议使用 ``分组/名称`` 的形式避免与 Material Symbols
            重名。
        source: SVG 文件路径，或 SVG 字节内容。
        filled: 可选的填充版文件，用于 ``with_fill(True)``。
        tint: 是否按内容色着色。

    Returns:
        注册的图标（尺寸为默认 24dp）。
    """
    if isinstance(source, bytes):
        icon = SvgIcon.from_data(source, tint=tint, name=name)
    else:
        icon = SvgIcon.from_file(
            source, tint=tint, filled_path=filled, name=name
        )
    _svg_registry[name] = icon
    return icon


def register_svg_directory(
    directory: str | pathlib.Path,
    prefix: str = "",
    recursive: bool = False,
    tint: bool = True,
) -> list[str]:
    """把文件夹中的全部 ``*.svg`` 注册到图标库，名称为 ``prefix + 文件名``。

    以 ``_filled`` 结尾的文件会作为同名图标的填充版而不单独注册。

    Returns:
        新注册的图标名（按字母序）。
    """
    directory = pathlib.Path(directory)
    pattern = "**/*.svg" if recursive else "*.svg"
    files = {path.stem: path for path in sorted(directory.glob(pattern))}
    names: list[str] = []
    for stem, path in files.items():
        if stem.endswith("_filled") and stem[: -len("_filled")] in files:
            continue
        filled = files.get(f"{stem}_filled")
        name = f"{prefix}{stem}"
        register_svg(name, path, filled=filled, tint=tint)
        names.append(name)
    return sorted(names)


def unregister_svg(name: str) -> None:
    """从图标库移除一个图标（不存在时忽略）。"""
    _svg_registry.pop(name, None)


def _ensure_bundled() -> None:
    """首次访问时注册随包附带的形状库。"""
    global _bundled_loaded  # pylint: disable=global-statement
    if _bundled_loaded:
        return
    _bundled_loaded = True
    shapes = assets.SVG_DIR / "shapes"
    if shapes.is_dir():
        register_svg_directory(shapes, prefix=BUNDLED_SVG_PREFIX)
    else:
        _LOGGER.warning("未找到随包 SVG 形状库: %s", shapes)


def svg_icon(name: str) -> SvgIcon | None:
    """按名称查找已注册的 SVG 图标。"""
    _ensure_bundled()
    return _svg_registry.get(name)


def has_svg(name: str) -> bool:
    """是否存在同名的 SVG 图标。"""
    return svg_icon(name) is not None


def svg_names(prefix: str = "") -> tuple[str, ...]:
    """已注册的 SVG 图标名（可按前缀筛选），按字母序。"""
    _ensure_bundled()
    return tuple(sorted(n for n in _svg_registry if n.startswith(prefix)))


def search_icons(
    query: str, names: Iterable[str] | None = None, limit: int = 200
) -> list[str]:
    """按子串搜索图标名，默认在 Material Symbols 中搜索。"""
    query = query.strip().lower().replace(" ", "_")
    pool = icon_names() if names is None else tuple(names)
    if not query:
        return list(pool[:limit])

    def base(name: str) -> str:
        return name.rsplit("/", 1)[-1].lower()

    starts = [n for n in pool if base(n).startswith(query)]
    contains = [
        n for n in pool if query in n.lower() and not base(n).startswith(query)
    ]
    return (starts + contains)[:limit]


def coerce(icon: IconLike, size: float = DEFAULT_SIZE) -> AnyIcon | None:
    """把图标名、路径或图标对象统一转换为可绘制的图标。

    字符串先在 SVG 图标库中查找，其次视 ``.svg`` 结尾的为文件路径，
    否则作为 Material Symbols 图标名。
    """
    if icon is None:
        return None
    if isinstance(icon, Icon | SvgIcon):
        return icon
    if isinstance(icon, pathlib.Path):
        return SvgIcon.from_file(icon, size=size)
    registered = svg_icon(icon)
    if registered is not None:
        return registered.with_size(size)
    if icon.lower().endswith(".svg"):
        return SvgIcon.from_file(icon, size=size)
    return Icon(icon, size=size)


def _report_missing_font() -> None:
    global _missing_font_reported  # pylint: disable=global-statement
    if not _missing_font_reported:
        _missing_font_reported = True
        _LOGGER.warning(
            "Material Symbols 字体不可用，图标未绘制；"
            "运行 python -m md3.assets.fetch 下载字体"
        )
