"""颜色选择器：基于 HCT 色彩空间的色相 / 色度 / 色调滑块。

HCT 是 M3 配色算法使用的感知均匀色彩空间，用它取色可以保证同一色调下
的颜色明暗一致、在色相环上移动时不会忽明忽暗。滑块轨道用当前其余两个
分量实时渲染渐变；超出 sRGB 色域的组合由 HCT 求解器自动压回色域。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.color import hct
from md3.components.dialogs import dialog as dialog_module
from md3.components.text_fields import text_field
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing
from md3.tokens import typography as typography_tokens

TRACK_HEIGHT = 24.0
HANDLE_WIDTH = 4.0
HANDLE_HEIGHT = 40.0
HANDLE_GAP = 6.0
GRADIENT_STOPS = 32
PREVIEW_SIZE = 72.0
SWATCH_SIZE = 32.0
MAX_CHROMA = 120.0
CHANNEL_LABEL_WIDTH = 40.0
VALUE_LABEL_WIDTH = 44.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
VALUE_STYLE = typography_tokens.TypeRole.BODY_MEDIUM

ColorProvider = Callable[[float], QtGui.QColor]


def hct_color(hue: float, chroma: float, tone: float) -> QtGui.QColor:
    """由 HCT 分量得到（已压回 sRGB 色域的）颜色。"""
    return theme_module.qcolor(hct.Hct.from_hct(hue, chroma, tone).to_int())


def to_hct(color: QtGui.QColor | str | int) -> tuple[float, float, float]:
    """把颜色分解为 (色相, 色度, 色调)。"""
    value = hct.Hct.from_int(theme_module.parse_seed(color))
    return value.hue, value.chroma, value.tone


class GradientSlider(widget.MaterialWidget):
    """轨道为渐变的滑块，M3 Expressive 风格：粗轨道、细把手、两侧留空。

    Args:
        minimum: 最小值。
        maximum: 最大值。
        value: 初始值。
        colors: 把 0–1 的位置映射为轨道颜色的函数。
        step: 键盘调整步长，None 时为范围的 1%。
        parent: 父控件。
    """

    value_changed = QtCore.Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float,
        colors: ColorProvider,
        step: float | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._value = self._clamp(value)
        self._colors = colors
        self._step = step if step is not None else (maximum - minimum) / 100
        self._gradient: QtGui.QLinearGradient | None = None
        self._dragging = False
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def _clamp(self, value: float) -> float:
        return max(self._minimum, min(self._maximum, float(value)))

    @property
    def value(self) -> float:
        """当前值。"""
        return self._value

    def set_value(self, value: float) -> None:
        """设置值，变化时发出 ``value_changed``。"""
        value = self._clamp(value)
        if value == self._value:
            return
        self._value = value
        self.value_changed.emit(value)
        self.update()

    def refresh_gradient(self) -> None:
        """其余参数变化后重新渲染轨道渐变。"""
        self._gradient = None
        self.update()

    def track_rect(self) -> QtCore.QRectF:
        """轨道矩形。"""
        rect = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            rect.left() + HANDLE_WIDTH,
            rect.center().y() - TRACK_HEIGHT / 2,
            rect.width() - 2 * HANDLE_WIDTH,
            TRACK_HEIGHT,
        )

    def handle_x(self) -> float:
        """把手中心的 x 坐标。"""
        track = self.track_rect()
        fraction = (self._value - self._minimum) / (
            self._maximum - self._minimum
        )
        return track.left() + fraction * track.width()

    def _value_at(self, x: float) -> float:
        track = self.track_rect()
        if track.width() <= 0:
            return self._minimum
        fraction = (x - track.left()) / track.width()
        return self._minimum + fraction * (self._maximum - self._minimum)

    def _build_gradient(self, track: QtCore.QRectF) -> QtGui.QLinearGradient:
        gradient = QtGui.QLinearGradient(
            QtCore.QPointF(track.left(), 0), QtCore.QPointF(track.right(), 0)
        )
        for index in range(GRADIENT_STOPS + 1):
            position = index / GRADIENT_STOPS
            gradient.setColorAt(position, self._colors(position))
        return gradient

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(240, int(HANDLE_HEIGHT + 8))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(96, int(HANDLE_HEIGHT + 8))

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._gradient = None

    @override
    def on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self._gradient = None

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        track = self.track_rect()
        if self._gradient is None:
            self._gradient = self._build_gradient(track)
        x = self.handle_x()
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        # 轨道在把手两侧各留 6dp 空隙。
        painter.setClipPath(
            shape_utils.rounded_rect_path(track, shape_tokens.SHAPE_FULL)
        )
        painter.setBrush(self._gradient)
        left = QtCore.QRectF(
            track.left(),
            track.top(),
            max(0.0, x - HANDLE_WIDTH / 2 - HANDLE_GAP - track.left()),
            track.height(),
        )
        right_start = x + HANDLE_WIDTH / 2 + HANDLE_GAP
        right = QtCore.QRectF(
            right_start,
            track.top(),
            max(0.0, track.right() - right_start),
            track.height(),
        )
        for part in (left, right):
            if part.width() > 0:
                painter.drawPath(
                    shape_utils.rounded_rect_path(part, shape_tokens.SHAPE_FULL)
                )
        painter.restore()
        handle = QtCore.QRectF(
            x - HANDLE_WIDTH / 2,
            track.center().y() - HANDLE_HEIGHT / 2,
            HANDLE_WIDTH,
            HANDLE_HEIGHT,
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(handle, shape_tokens.SHAPE_FULL),
            self.color("primary"),
        )
        if self.hasFocus():
            ring = handle.adjusted(-3, -3, 3, 3)
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(ring, shape_tokens.SHAPE_FULL),
                None,
                self.color("secondary"),
                2.0,
            )

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self.set_value(self._value_at(event.position().x()))
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            self.set_value(self._value_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        direction = 1 if event.angleDelta().y() > 0 else -1
        self.set_value(self._value + direction * self._step)
        event.accept()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Down):
            self.set_value(self._value - self._step)
        elif key in (QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Up):
            self.set_value(self._value + self._step)
        elif key == QtCore.Qt.Key.Key_Home:
            self.set_value(self._minimum)
        elif key == QtCore.Qt.Key.Key_End:
            self.set_value(self._maximum)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class _Preview(widget.MaterialWidget):
    """当前颜色的预览色块。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QtGui.QColor("#6750A4")
        self.setFixedSize(int(PREVIEW_SIZE), int(PREVIEW_SIZE))

    def set_color(self, color: QtGui.QColor) -> None:
        """设置显示的颜色。"""
        self._color = QtGui.QColor(color)
        self.update()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        path = shape_utils.rounded_rect_path(
            QtCore.QRectF(self.rect()), shape_tokens.SHAPE_LARGE
        )
        shape_utils.fill_shape(
            painter, path, self._color, self.color("outline_variant"), 1.0
        )


class _Swatch(widget.InteractiveWidget):
    """预设颜色圆点。"""

    def __init__(
        self, color: QtGui.QColor, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.swatch_color = QtGui.QColor(color)
        self.selected = False
        self.set_outer_margin(4.0)
        self.setFixedSize(int(SWATCH_SIZE + 8), int(SWATCH_SIZE + 8))
        self.setToolTip(self.swatch_color.name().upper())

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_FULL

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        path = self.container_path()
        shape_utils.fill_shape(painter, path, self.swatch_color)
        if self.selected:
            shape_utils.fill_shape(
                painter, path, None, self.color("on_surface"), 2.0
            )


class ColorPicker(widget.MaterialWidget):
    """HCT 颜色选择器。

    Args:
        color: 初始颜色（``QColor``、``#RRGGBB`` 或 ARGB 整数）。
        presets: 预设颜色列表，显示为可点击的圆点。
        show_hex: 是否显示十六进制输入框。
        parent: 父控件。
    """

    color_changed = QtCore.Signal(QtGui.QColor)

    def __init__(
        self,
        color: QtGui.QColor | str | int = "#6750A4",
        presets: Sequence[QtGui.QColor | str | int] | None = None,
        show_hex: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._hue, self._chroma, self._tone = to_hct(color)
        self._updating = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(spacing.SPACE_2))

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(round(spacing.SPACE_4))
        self._preview = _Preview()
        header.addWidget(self._preview, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._hex: text_field.OutlinedTextField | None = None
        if show_hex:
            self._hex = text_field.OutlinedTextField(
                i18n.tr("hex_code"), prefix="#"
            )
            self._hex.editor.setValidator(
                QtGui.QRegularExpressionValidator(
                    QtCore.QRegularExpression("[0-9A-Fa-f]{0,6}"), self._hex
                )
            )
            self._hex.editing_finished.connect(self._commit_hex)
            header.addWidget(self._hex, 1, QtCore.Qt.AlignmentFlag.AlignTop)
        else:
            header.addStretch()
        layout.addLayout(header)

        self._hue_slider = GradientSlider(
            0.0, 360.0, self._hue, self._hue_gradient, step=1.0
        )
        self._chroma_slider = GradientSlider(
            0.0, MAX_CHROMA, self._chroma, self._chroma_gradient, step=1.0
        )
        self._tone_slider = GradientSlider(
            0.0, 100.0, self._tone, self._tone_gradient, step=1.0
        )
        self._value_labels: list[typography.Label] = []
        for name, slider in (
            (i18n.tr("hue"), self._hue_slider),
            (i18n.tr("chroma"), self._chroma_slider),
            (i18n.tr("tone"), self._tone_slider),
        ):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(round(spacing.SPACE_3))
            label = typography.Label(name, LABEL_STYLE, "on_surface")
            label.setFixedWidth(int(CHANNEL_LABEL_WIDTH))
            row.addWidget(label)
            row.addWidget(slider, 1)
            value = typography.Label("", VALUE_STYLE, "on_surface_variant")
            value.setFixedWidth(int(VALUE_LABEL_WIDTH))
            value.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            row.addWidget(value)
            self._value_labels.append(value)
            layout.addLayout(row)
        self._hue_slider.value_changed.connect(self._on_hue)
        self._chroma_slider.value_changed.connect(self._on_chroma)
        self._tone_slider.value_changed.connect(self._on_tone)

        self._swatches: list[_Swatch] = []
        if presets:
            swatches = QtWidgets.QHBoxLayout()
            swatches.setSpacing(0)
            for preset in presets:
                swatch = _Swatch(
                    theme_module.qcolor(theme_module.parse_seed(preset))
                )
                swatch.clicked.connect(
                    lambda s=swatch: self.set_selected_color(s.swatch_color)
                )
                swatches.addWidget(swatch)
                self._swatches.append(swatch)
            swatches.addStretch()
            layout.addLayout(swatches)
        self._refresh(emit=False)

    # ---- 状态 -------------------------------------------------------------

    @property
    def selected_color(self) -> QtGui.QColor:
        """当前颜色。"""
        return hct_color(self._hue, self._chroma, self._tone)

    @property
    def hct(self) -> tuple[float, float, float]:
        """当前的 (色相, 色度, 色调)。"""
        return self._hue, self._chroma, self._tone

    def set_selected_color(self, color: QtGui.QColor | str | int) -> None:
        """设置颜色（分解为 HCT 并更新滑块）。"""
        self._hue, self._chroma, self._tone = to_hct(color)
        self._refresh(emit=True)

    def set_hct(self, hue: float, chroma: float, tone: float) -> None:
        """直接设置 HCT 分量。"""
        self._hue = hue % 360.0
        self._chroma = max(0.0, min(MAX_CHROMA, chroma))
        self._tone = max(0.0, min(100.0, tone))
        self._refresh(emit=True)

    # ---- 渐变 -------------------------------------------------------------

    def _hue_gradient(self, position: float) -> QtGui.QColor:
        return hct_color(position * 360.0, self._chroma, self._tone)

    def _chroma_gradient(self, position: float) -> QtGui.QColor:
        return hct_color(self._hue, position * MAX_CHROMA, self._tone)

    def _tone_gradient(self, position: float) -> QtGui.QColor:
        return hct_color(self._hue, self._chroma, position * 100.0)

    # ---- 同步 -------------------------------------------------------------

    def _on_hue(self, value: float) -> None:
        if self._updating:
            return
        self._hue = value
        self._chroma_slider.refresh_gradient()
        self._tone_slider.refresh_gradient()
        self._refresh(emit=True, sliders=False)

    def _on_chroma(self, value: float) -> None:
        if self._updating:
            return
        self._chroma = value
        self._hue_slider.refresh_gradient()
        self._tone_slider.refresh_gradient()
        self._refresh(emit=True, sliders=False)

    def _on_tone(self, value: float) -> None:
        if self._updating:
            return
        self._tone = value
        self._hue_slider.refresh_gradient()
        self._chroma_slider.refresh_gradient()
        self._refresh(emit=True, sliders=False)

    def _refresh(self, emit: bool, sliders: bool = True) -> None:
        self._updating = True
        try:
            if sliders:
                self._hue_slider.set_value(self._hue)
                self._chroma_slider.set_value(self._chroma)
                self._tone_slider.set_value(self._tone)
                for slider in (
                    self._hue_slider,
                    self._chroma_slider,
                    self._tone_slider,
                ):
                    slider.refresh_gradient()
            color = self.selected_color
            self._preview.set_color(color)
            if self._hex is not None and not self._hex.hasFocus():
                self._hex.set_text(color.name()[1:].upper())
                self._hex.set_error(False)
            self._value_labels[0].setText(f"{self._hue:.0f}°")
            self._value_labels[1].setText(f"{self._chroma:.0f}")
            self._value_labels[2].setText(f"{self._tone:.0f}")
            for swatch in self._swatches:
                swatch.selected = swatch.swatch_color.rgb() == color.rgb()
                swatch.update()
        finally:
            self._updating = False
        if emit:
            self.color_changed.emit(color)

    def _commit_hex(self) -> None:
        if self._hex is None:
            return
        text = self._hex.text.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        candidate = QtGui.QColor(f"#{text}")
        if len(text) != 6 or not candidate.isValid():
            self._hex.set_error(True, i18n.tr("invalid_hex"))
            return
        self._hex.set_error(False)
        self.set_selected_color(candidate)


class ColorPickerDialog(dialog_module.BasicDialog):
    """模态颜色选择对话框。

    Args:
        color: 初始颜色。
        headline: 标题。
        presets: 预设颜色。
        parent: 父控件。
    """

    color_selected = QtCore.Signal(QtGui.QColor)

    def __init__(
        self,
        color: QtGui.QColor | str | int = "#6750A4",
        headline: str | None = None,
        presets: Sequence[QtGui.QColor | str | int] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            i18n.tr("select_color") if headline is None else headline,
            parent=parent,
        )
        self._picker = ColorPicker(color, presets)
        self._picker.setMinimumWidth(360)
        self.set_content(self._picker)
        self.add_action(
            i18n.tr("cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole
        )
        self.add_action(i18n.tr("confirm"))
        self.accepted.connect(
            lambda: self.color_selected.emit(self.selected_color)
        )

    @property
    def picker(self) -> ColorPicker:
        """内部选择器。"""
        return self._picker

    @property
    def selected_color(self) -> QtGui.QColor:
        """当前颜色。"""
        return self._picker.selected_color
