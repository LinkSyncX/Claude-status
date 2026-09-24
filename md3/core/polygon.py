"""M3 Expressive 形状库的最小实现：圆角多边形与形状变形。

``RoundedPolygon`` 以顶点坐标和每个顶点的圆角半径描述形状，参数与
androidx.graphics.shapes / Compose ``MaterialShapes`` 一致（不含
smoothing）。为了在任意两个形状之间变形，本模块把轮廓从中心按等角度
采样为极坐标半径序列，插值半径即可得到中间形状；这些形状（星形、
饼干形、胶囊等）相对中心都是星形区域，因此采样是精确的。
"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import functools
import math

from PySide6 import QtCore
from PySide6 import QtGui

# 极坐标采样数：1° 一个样本，19dp 半径上相邻样本相距约 0.33px。
SAMPLE_COUNT = 360
_ARC_SEGMENTS = 12
_TWO_PI = 2.0 * math.pi

Point = tuple[float, float]


def _angle(x: float, y: float) -> float:
    angle = math.atan2(y, x) % _TWO_PI
    # 极小的负角取模后会得到 2π，统一归到 0。
    return 0.0 if angle >= _TWO_PI - 1e-9 else angle


def _roundings(
    rounding: float | Sequence[float], count: int
) -> tuple[float, ...]:
    if isinstance(rounding, int | float):
        return (float(rounding),) * count
    values = tuple(float(r) for r in rounding)
    if len(values) != count:
        raise ValueError("每个顶点都需要一个圆角半径")
    return values


@dataclasses.dataclass(frozen=True)
class Corner:
    """一个顶点经圆角处理后的几何：切点、圆心与半径。

    ``radius`` 为 0 表示未圆角，此时两个切点都等于顶点本身。
    """

    start: Point
    end: Point
    center: Point
    radius: float
    sweep: float


@dataclasses.dataclass(frozen=True)
class RoundedPolygon:
    """顶点带圆角的闭合多边形。

    Attributes:
        vertices: 顶点坐标序列（顺时针或逆时针均可）。
        roundings: 每个顶点的圆角半径，与坐标同单位；过大时自动收缩以免
            相邻圆角重叠。
        center: 形状中心，也是极坐标采样与旋转的原点。
    """

    vertices: tuple[Point, ...]
    roundings: tuple[float, ...]
    center: Point = (0.0, 0.0)

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("多边形至少需要 3 个顶点")
        if len(self.roundings) != len(self.vertices):
            raise ValueError("roundings 数量必须与顶点数一致")

    # ---- 构造 -------------------------------------------------------------

    @classmethod
    def regular(
        cls,
        num_vertices: int,
        radius: float = 1.0,
        rounding: float | Sequence[float] = 0.0,
        center: Point = (0.0, 0.0),
    ) -> RoundedPolygon:
        """正多边形，第一个顶点位于 +x 方向。

        Args:
            num_vertices: 顶点数。
            radius: 外接圆半径。
            rounding: 统一的圆角半径，或每个顶点各自的圆角半径。
            center: 中心。
        """
        step = _TWO_PI / num_vertices
        vertices = tuple(
            (
                center[0] + radius * math.cos(index * step),
                center[1] + radius * math.sin(index * step),
            )
            for index in range(num_vertices)
        )
        return cls(vertices, _roundings(rounding, num_vertices), center)

    @classmethod
    def rectangle(
        cls,
        width: float = 2.0,
        height: float = 2.0,
        rounding: float | Sequence[float] = 0.0,
        center: Point = (0.0, 0.0),
    ) -> RoundedPolygon:
        """矩形，顶点顺序为右下、左下、左上、右上（与 androidx 一致）。"""
        cx, cy = center
        half_w, half_h = width / 2, height / 2
        vertices = (
            (cx + half_w, cy + half_h),
            (cx - half_w, cy + half_h),
            (cx - half_w, cy - half_h),
            (cx + half_w, cy - half_h),
        )
        return cls(vertices, _roundings(rounding, 4), center)

    @classmethod
    def circle(cls, num_vertices: int = 10) -> RoundedPolygon:
        """圆：外接正多边形加上等于半径的圆角，轮廓恰为单位圆。"""
        theta = math.pi / num_vertices
        return cls.regular(num_vertices, 1.0 / math.cos(theta), rounding=1.0)

    @classmethod
    def star(
        cls,
        num_vertices_per_radius: int,
        inner_radius: float,
        rounding: float = 0.0,
        inner_rounding: float | None = None,
        radius: float = 1.0,
        center: Point = (0.0, 0.0),
    ) -> RoundedPolygon:
        """内外半径交替的星形。

        Args:
            num_vertices_per_radius: 外顶点数（内顶点数相同）。
            inner_radius: 内半径与外半径之比。
            rounding: 外顶点圆角半径。
            inner_rounding: 内顶点圆角半径，None 时与 ``rounding`` 相同。
            radius: 外半径。
            center: 中心。
        """
        if inner_rounding is None:
            inner_rounding = rounding
        vertices: list[Point] = []
        roundings: list[float] = []
        step = math.pi / num_vertices_per_radius
        for index in range(num_vertices_per_radius * 2):
            distance = radius if index % 2 == 0 else radius * inner_radius
            angle = index * step
            vertices.append(
                (
                    center[0] + distance * math.cos(angle),
                    center[1] + distance * math.sin(angle),
                )
            )
            roundings.append(rounding if index % 2 == 0 else inner_rounding)
        return cls(tuple(vertices), tuple(roundings), center)

    @classmethod
    def custom(
        cls,
        points: Sequence[tuple[Point, float]],
        reps: int,
        mirroring: bool = False,
        center: Point = (0.5, 0.5),
    ) -> RoundedPolygon:
        """按 ``MaterialShapes`` 的方式由少量控制点重复生成形状。

        Args:
            points: （坐标, 圆角半径）序列，坐标位于以 ``center`` 为中心的
                单位正方形内。
            reps: 绕中心重复的次数。
            mirroring: 为真时每次重复都镜像一次（实际重复 ``2 * reps`` 段）。
            center: 中心。
        """
        result: list[tuple[Point, float]] = []
        cx, cy = center
        if mirroring:
            angles = [
                math.degrees(math.atan2(y - cy, x - cx)) for (x, y), _ in points
            ]
            distances = [math.hypot(x - cx, y - cy) for (x, y), _ in points]
            actual_reps = reps * 2
            section = 360.0 / actual_reps
            for rep in range(actual_reps):
                for index in range(len(points)):
                    i = index if rep % 2 == 0 else len(points) - 1 - index
                    if i == 0 and rep % 2 == 1:
                        continue
                    if rep % 2 == 0:
                        degrees = section * rep + angles[i]
                    else:
                        degrees = section * rep + section - angles[i]
                        degrees += 2 * angles[0]
                    radians = math.radians(degrees)
                    result.append(
                        (
                            (
                                cx + math.cos(radians) * distances[i],
                                cy + math.sin(radians) * distances[i],
                            ),
                            points[i][1],
                        )
                    )
        else:
            for rep in range(reps):
                radians = math.radians(rep * 360.0 / reps)
                cos, sin = math.cos(radians), math.sin(radians)
                for (x, y), rounding in points:
                    dx, dy = x - cx, y - cy
                    result.append(
                        (
                            (
                                cx + dx * cos - dy * sin,
                                cy + dx * sin + dy * cos,
                            ),
                            rounding,
                        )
                    )
        return cls(
            tuple(point for point, _ in result),
            tuple(rounding for _, rounding in result),
            center,
        )

    # ---- 变换 -------------------------------------------------------------

    def rotated(self, degrees: float) -> RoundedPolygon:
        """绕中心旋转（正角度为逆时针，y 轴向上意义下）。"""
        radians = math.radians(degrees)
        cos, sin = math.cos(radians), math.sin(radians)
        cx, cy = self.center
        vertices = tuple(
            (
                cx + (x - cx) * cos - (y - cy) * sin,
                cy + (x - cx) * sin + (y - cy) * cos,
            )
            for x, y in self.vertices
        )
        return dataclasses.replace(self, vertices=vertices)

    def scaled(self, sx: float, sy: float | None = None) -> RoundedPolygon:
        """相对中心缩放；圆角半径按两轴缩放的几何平均缩放。"""
        if sy is None:
            sy = sx
        cx, cy = self.center
        factor = math.sqrt(abs(sx * sy))
        return dataclasses.replace(
            self,
            vertices=tuple(
                (cx + (x - cx) * sx, cy + (y - cy) * sy)
                for x, y in self.vertices
            ),
            roundings=tuple(r * factor for r in self.roundings),
        )

    # ---- 轮廓 -------------------------------------------------------------

    def _corners(self) -> list[tuple[Point, Point, float, float]]:
        """每个顶点的（前向单位向量, 后向单位向量, 半角, 期望切线长）。"""
        count = len(self.vertices)
        corners: list[tuple[Point, Point, float, float]] = []
        for index in range(count):
            px, py = self.vertices[index - 1]
            vx, vy = self.vertices[index]
            nx, ny = self.vertices[(index + 1) % count]
            len1 = math.hypot(px - vx, py - vy)
            len2 = math.hypot(nx - vx, ny - vy)
            if len1 < 1e-9 or len2 < 1e-9:
                corners.append(((0.0, 0.0), (0.0, 0.0), 0.0, 0.0))
                continue
            u1 = ((px - vx) / len1, (py - vy) / len1)
            u2 = ((nx - vx) / len2, (ny - vy) / len2)
            cos_theta = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
            half = math.acos(cos_theta) / 2
            radius = self.roundings[index]
            if radius <= 0 or half < 1e-6 or half > math.pi / 2 - 1e-6:
                corners.append((u1, u2, half, 0.0))
                continue
            corners.append((u1, u2, half, radius / math.tan(half)))
        return corners

    def corners(self) -> list[Corner]:
        """每个顶点圆角后的几何（绝对坐标），按顶点顺序。"""
        count = len(self.vertices)
        raw = self._corners()
        # 相邻两个圆角共享一条边：切线长之和超过边长时按比例同时收缩，
        # 与 androidx.graphics.shapes 的处理一致。
        scales = [1.0] * count
        for index in range(count):
            following = (index + 1) % count
            vx, vy = self.vertices[index]
            nx, ny = self.vertices[following]
            length = math.hypot(nx - vx, ny - vy)
            wanted = raw[index][3] + raw[following][3]
            if wanted > length > 0:
                ratio = length / wanted
                scales[index] = min(scales[index], ratio)
                scales[following] = min(scales[following], ratio)
        result: list[Corner] = []
        for index in range(count):
            vertex = self.vertices[index]
            u1, u2, half, tangent = raw[index]
            tangent *= scales[index]
            if tangent <= 1e-9:
                result.append(Corner(vertex, vertex, vertex, 0.0, 0.0))
                continue
            vx, vy = vertex
            radius = tangent * math.tan(half)
            bisector = (u1[0] + u2[0], u1[1] + u2[1])
            bisector_len = math.hypot(*bisector)
            ox = vx + bisector[0] / bisector_len * radius / math.sin(half)
            oy = vy + bisector[1] / bisector_len * radius / math.sin(half)
            t1 = (vx + u1[0] * tangent, vy + u1[1] * tangent)
            t2 = (vx + u2[0] * tangent, vy + u2[1] * tangent)
            start = math.atan2(t1[1] - oy, t1[0] - ox)
            end = math.atan2(t2[1] - oy, t2[0] - ox)
            sweep = (end - start + math.pi) % _TWO_PI - math.pi
            result.append(Corner(t1, t2, (ox, oy), radius, sweep))
        return result

    def outline(self) -> list[Point]:
        """圆角后的轮廓折线（相对中心的坐标，闭合、不重复首点）。"""
        cx, cy = self.center
        points: list[Point] = []
        for corner in self.corners():
            if corner.radius <= 0:
                points.append((corner.start[0] - cx, corner.start[1] - cy))
                continue
            ox, oy = corner.center
            start = math.atan2(corner.start[1] - oy, corner.start[0] - ox)
            for step in range(_ARC_SEGMENTS + 1):
                angle = start + corner.sweep * step / _ARC_SEGMENTS
                points.append(
                    (
                        ox + corner.radius * math.cos(angle) - cx,
                        oy + corner.radius * math.sin(angle) - cy,
                    )
                )
        return points

    def bounds(self) -> tuple[float, float, float, float]:
        """圆角轮廓的包围盒 (left, top, right, bottom)，绝对坐标。"""
        cx, cy = self.center
        xs = [x + cx for x, _ in self.outline()]
        ys = [y + cy for _, y in self.outline()]
        return min(xs), min(ys), max(xs), max(ys)

    def svg_path(self, size: float = 24.0, margin: float = 1.0) -> str:
        """导出为 SVG 路径数据，圆角使用精确的圆弧命令。

        形状按包围盒等比缩放并居中到 ``size × size`` 的视图框内。

        Args:
            size: 视图框边长。
            margin: 四周留白。
        """
        left, top, right, bottom = self.bounds()
        extent = max(right - left, bottom - top) or 1.0
        scale = (size - 2 * margin) / extent
        offset_x = (size - (right - left) * scale) / 2 - left * scale
        offset_y = (size - (bottom - top) * scale) / 2 - top * scale

        def fmt(point: Point) -> str:
            x = point[0] * scale + offset_x
            y = point[1] * scale + offset_y
            return f"{x:.3f} {y:.3f}"

        corners = self.corners()
        commands = [f"M{fmt(corners[-1].end)}"]
        for corner in corners:
            if corner.radius <= 0:
                commands.append(f"L{fmt(corner.start)}")
                continue
            commands.append(f"L{fmt(corner.start)}")
            radius = corner.radius * scale
            # SVG 的 y 轴向下，正角方向为顺时针，与 atan2 的方向一致。
            sweep_flag = 1 if corner.sweep > 0 else 0
            commands.append(
                f"A{radius:.3f} {radius:.3f} 0 0 {sweep_flag} {fmt(corner.end)}"
            )
        commands.append("Z")
        return "".join(commands)

    def to_svg(self, size: float = 24.0, fill: str = "#000000") -> str:
        """导出为完整的 SVG 文档字符串。"""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size:g} '
            f'{size:g}" width="{size:g}" height="{size:g}">'
            f'<path fill="{fill}" d="{self.svg_path(size)}"/></svg>'
        )

    def radii(self, count: int = SAMPLE_COUNT) -> tuple[float, ...]:
        """从中心按等角度采样轮廓半径，并归一化使最大半径为 1。

        第 ``i`` 个样本对应角度 ``2πi / count``（数学坐标系，逆时针）。
        结果按形状缓存。
        """
        return _sample_radii(self, count)


@functools.cache
def _sample_radii(polygon: RoundedPolygon, count: int) -> tuple[float, ...]:
    outline = polygon.outline()
    # 统一为逆时针遍历，使角度沿轮廓单调递增。
    area = sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(
            outline, outline[1:] + outline[:1], strict=True
        )
    )
    if area < 0:
        outline.reverse()
    angles = [_angle(x, y) for x, y in outline]
    start = min(range(len(outline)), key=angles.__getitem__)
    outline = outline[start:] + outline[:start]
    angles = angles[start:] + angles[:start]
    samples: list[float] = []
    segment = 0
    total = len(outline)
    for index in range(count):
        phi = _TWO_PI * index / count
        if phi < angles[0]:
            # 起点角度之前的样本落在"末点 → 起点"这段跨越 0° 的边上。
            current = total - 1
        else:
            while segment + 1 < total and angles[segment + 1] <= phi:
                segment += 1
            current = segment
        ax, ay = outline[current]
        bx, by = outline[(current + 1) % total]
        ex, ey = bx - ax, by - ay
        dx, dy = math.cos(phi), math.sin(phi)
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-12:
            samples.append(math.hypot(ax, ay))
            continue
        samples.append(abs((ax * ey - ay * ex) / denominator))
    peak = max(samples)
    return tuple(sample / peak for sample in samples)


# ---- 形状之间的变形 ---------------------------------------------------------


def morph_radii(
    start: Sequence[float], end: Sequence[float], progress: float
) -> tuple[float, ...]:
    """按进度在两组极坐标半径之间线性插值。"""
    progress = max(0.0, min(1.0, progress))
    return tuple(
        a + (b - a) * progress for a, b in zip(start, end, strict=True)
    )


def polar_path(
    radii: Sequence[float],
    center: QtCore.QPointF,
    radius: float,
    rotation_degrees: float = 0.0,
) -> QtGui.QPainterPath:
    """把极坐标半径序列还原为屏幕坐标下的闭合路径。

    Args:
        radii: 归一化半径序列，均匀分布在一周。
        center: 屏幕坐标中心。
        radius: 归一化半径 1 对应的像素半径。
        rotation_degrees: 顺时针旋转角度（屏幕坐标 y 向下）。
    """
    path = QtGui.QPainterPath()
    count = len(radii)
    offset = math.radians(rotation_degrees)
    for index, value in enumerate(radii):
        angle = _TWO_PI * index / count + offset
        point = QtCore.QPointF(
            center.x() + value * radius * math.cos(angle),
            center.y() + value * radius * math.sin(angle),
        )
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


# ---- Material 形状 ----------------------------------------------------------
# 参数取自 Compose MaterialShapes，坐标位于以 (0.5, 0.5) 为中心的单位正方形。


def _material_circle() -> RoundedPolygon:
    return RoundedPolygon.circle(10)


def _oval() -> RoundedPolygon:
    return RoundedPolygon.circle(10).scaled(1.0, 0.64).rotated(-45.0)


def _pill() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.961, 0.039), 0.426),
            ((1.001, 0.428), 0.0),
            ((1.000, 0.609), 1.000),
        ],
        reps=2,
        mirroring=True,
    )


def _pentagon() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.500, -0.009), 0.172),
            ((1.030, 0.365), 0.164),
            ((0.828, 0.970), 0.169),
        ],
        reps=1,
        mirroring=True,
    )


def _sunny() -> RoundedPolygon:
    return RoundedPolygon.star(8, 0.8, rounding=0.15)


def _cookie4() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((1.237, 1.236), 0.258), ((0.500, 0.918), 0.233)], reps=4
    )


def _cookie9() -> RoundedPolygon:
    return RoundedPolygon.star(9, 0.8, rounding=0.5).rotated(-90.0)


def _soft_burst() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.193, 0.277), 0.053), ((0.176, 0.055), 0.053)], reps=10
    )


def _square() -> RoundedPolygon:
    return RoundedPolygon.rectangle(1.0, 1.0, rounding=0.3)


def _slanted() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.926, 0.970), 0.189), ((-0.021, 0.967), 0.187)], reps=2
    )


def _arch() -> RoundedPolygon:
    return RoundedPolygon.regular(4, rounding=(1.0, 1.0, 0.2, 0.2)).rotated(
        -135.0
    )


def _fan() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((1.004, 1.000), 0.148),
            ((0.000, 1.000), 0.151),
            ((0.000, -0.003), 0.148),
            ((0.978, 0.020), 0.803),
        ],
        reps=1,
    )


def _arrow() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.500, 0.892), 0.313),
            ((-0.216, 1.050), 0.207),
            ((0.499, -0.160), 0.215),
            ((1.225, 1.060), 0.211),
        ],
        reps=1,
    )


def _semi_circle() -> RoundedPolygon:
    return RoundedPolygon.rectangle(1.6, 1.0, rounding=(0.2, 0.2, 1.0, 1.0))


def _triangle() -> RoundedPolygon:
    return RoundedPolygon.regular(3, rounding=0.2).rotated(-90.0)


def _diamond() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.500, 1.096), 0.151), ((0.040, 0.500), 0.159)], reps=2
    )


def _clam_shell() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.171, 0.841), 0.159),
            ((-0.020, 0.500), 0.140),
            ((0.170, 0.159), 0.159),
        ],
        reps=2,
    )


def _gem() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.499, 1.023), 0.241),
            ((-0.005, 0.792), 0.208),
            ((0.073, 0.258), 0.228),
            ((0.433, -0.000), 0.491),
        ],
        reps=1,
        mirroring=True,
    )


def _very_sunny() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.500, 1.080), 0.085), ((0.358, 0.843), 0.085)], reps=8
    )


def _cookie6() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.723, 0.884), 0.394), ((0.500, 1.099), 0.398)], reps=6
    )


def _cookie7() -> RoundedPolygon:
    return RoundedPolygon.star(7, 0.75, rounding=0.5).rotated(-90.0)


def _cookie12() -> RoundedPolygon:
    return RoundedPolygon.star(12, 0.8, rounding=0.5).rotated(-90.0)


def _ghostish() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.500, 0.000), 1.000),
            ((1.000, 0.000), 1.000),
            ((1.000, 1.140), 0.254),
            ((0.575, 0.906), 0.253),
        ],
        reps=1,
        mirroring=True,
    )


def _clover4() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.500, 0.074), 0.0), ((0.725, -0.099), 0.476)],
        reps=4,
        mirroring=True,
    )


def _clover8() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.500, 0.036), 0.0), ((0.758, -0.101), 0.209)], reps=8
    )


def _burst() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.500, -0.006), 0.006), ((0.592, 0.158), 0.006)], reps=12
    )


def _boom() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [((0.457, 0.296), 0.007), ((0.500, -0.051), 0.007)], reps=15
    )


def _soft_boom() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.733, 0.454), 0.0),
            ((0.839, 0.437), 0.532),
            ((0.949, 0.449), 0.439),
            ((0.998, 0.478), 0.174),
        ],
        reps=16,
        mirroring=True,
    )


def _flower() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.370, 0.187), 0.0),
            ((0.416, 0.049), 0.381),
            ((0.479, 0.001), 0.095),
        ],
        reps=8,
        mirroring=True,
    )


def _puffy() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.500, 0.053), 0.0),
            ((0.545, -0.040), 0.405),
            ((0.670, -0.035), 0.426),
            ((0.717, 0.066), 0.574),
            ((0.722, 0.128), 0.0),
            ((0.777, 0.002), 0.360),
            ((0.914, 0.149), 0.660),
            ((0.926, 0.289), 0.660),
            ((0.881, 0.346), 0.0),
            ((0.940, 0.344), 0.126),
            ((1.003, 0.437), 0.255),
        ],
        reps=2,
        mirroring=True,
    ).scaled(1.0, 0.742)


def _puffy_diamond() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.870, 0.130), 0.146),
            ((0.818, 0.357), 0.0),
            ((1.000, 0.332), 0.853),
        ],
        reps=4,
        mirroring=True,
    )


def _bun() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.796, 0.500), 0.0),
            ((0.853, 0.518), 1.0),
            ((0.992, 0.631), 1.0),
            ((0.968, 1.000), 1.0),
        ],
        reps=2,
        mirroring=True,
    )


def _heart() -> RoundedPolygon:
    return RoundedPolygon.custom(
        [
            ((0.500, 0.268), 0.016),
            ((0.792, -0.066), 0.958),
            ((1.064, 0.276), 1.000),
            ((0.501, 0.946), 0.129),
        ],
        reps=1,
        mirroring=True,
    )


CIRCLE = _material_circle()
SQUARE = _square()
SLANTED = _slanted()
ARCH = _arch()
FAN = _fan()
ARROW = _arrow()
SEMI_CIRCLE = _semi_circle()
OVAL = _oval()
PILL = _pill()
TRIANGLE = _triangle()
DIAMOND = _diamond()
CLAM_SHELL = _clam_shell()
PENTAGON = _pentagon()
GEM = _gem()
SUNNY = _sunny()
VERY_SUNNY = _very_sunny()
COOKIE_4_SIDED = _cookie4()
COOKIE_6_SIDED = _cookie6()
COOKIE_7_SIDED = _cookie7()
COOKIE_9_SIDED = _cookie9()
COOKIE_12_SIDED = _cookie12()
GHOSTISH = _ghostish()
CLOVER_4_LEAF = _clover4()
CLOVER_8_LEAF = _clover8()
BURST = _burst()
SOFT_BURST = _soft_burst()
BOOM = _boom()
SOFT_BOOM = _soft_boom()
FLOWER = _flower()
PUFFY = _puffy()
PUFFY_DIAMOND = _puffy_diamond()
BUN = _bun()
HEART = _heart()

# M3 形状库全部形状，键为规范中的名称（snake_case）。
MATERIAL_SHAPES: dict[str, RoundedPolygon] = {
    "circle": CIRCLE,
    "square": SQUARE,
    "slanted": SLANTED,
    "arch": ARCH,
    "fan": FAN,
    "arrow": ARROW,
    "semi_circle": SEMI_CIRCLE,
    "oval": OVAL,
    "pill": PILL,
    "triangle": TRIANGLE,
    "diamond": DIAMOND,
    "clam_shell": CLAM_SHELL,
    "pentagon": PENTAGON,
    "gem": GEM,
    "sunny": SUNNY,
    "very_sunny": VERY_SUNNY,
    "cookie_4_sided": COOKIE_4_SIDED,
    "cookie_6_sided": COOKIE_6_SIDED,
    "cookie_7_sided": COOKIE_7_SIDED,
    "cookie_9_sided": COOKIE_9_SIDED,
    "cookie_12_sided": COOKIE_12_SIDED,
    "ghostish": GHOSTISH,
    "clover_4_leaf": CLOVER_4_LEAF,
    "clover_8_leaf": CLOVER_8_LEAF,
    "burst": BURST,
    "soft_burst": SOFT_BURST,
    "boom": BOOM,
    "soft_boom": SOFT_BOOM,
    "flower": FLOWER,
    "puffy": PUFFY,
    "puffy_diamond": PUFFY_DIAMOND,
    "bun": BUN,
    "heart": HEART,
}

# 加载指示器（不确定态）依次变形经过的形状。
LOADING_INDICATOR_SHAPES: tuple[RoundedPolygon, ...] = (
    SOFT_BURST,
    COOKIE_9_SIDED,
    PENTAGON,
    PILL,
    SUNNY,
    COOKIE_4_SIDED,
    OVAL,
)
# 加载指示器（确定态）：圆旋转 18° 后再变为 soft burst，使两者的顶点对齐。
DETERMINATE_LOADING_SHAPES: tuple[RoundedPolygon, ...] = (
    CIRCLE.rotated(360.0 / 20),
    SOFT_BURST,
)
