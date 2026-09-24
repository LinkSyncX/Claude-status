"""色彩空间转换与数学工具。

移植自 material-color-utilities 的 ``color_utils`` 与 ``math_utils``。
线性 RGB 与 XYZ 的取值范围为 0–100，sRGB 分量为 0–255。
"""

from __future__ import annotations

from collections.abc import Sequence
import math

from md3.tokens import color as color_tokens

Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]

SRGB_TO_XYZ: Matrix3 = (
    (0.41233895, 0.35762064, 0.18051042),
    (0.2126, 0.7152, 0.0722),
    (0.01932141, 0.11916382, 0.95034478),
)

XYZ_TO_SRGB: Matrix3 = (
    (3.2413774792388685, -1.5376652402851851, -0.49885366846268053),
    (-0.9691452513005321, 1.8758853451067872, 0.04156585616912061),
    (0.05562093689691305, -0.20395524564742123, 1.0571799111220335),
)

WHITE_POINT_D65: Vector3 = (95.047, 100.0, 108.883)

_LAB_E = 216.0 / 24389.0
_LAB_KAPPA = 24389.0 / 27.0


def signum(value: float) -> int:
    """返回符号：正数为 1，负数为 -1，零为 0。"""
    if value < 0:
        return -1
    if value == 0:
        return 0
    return 1


def lerp(start: float, stop: float, amount: float) -> float:
    """线性插值，amount 为 0 时返回 start，为 1 时返回 stop。"""
    return (1.0 - amount) * start + amount * stop


def clamp_int(minimum: int, maximum: int, value: int) -> int:
    """把整数限制在 [minimum, maximum] 内。"""
    return max(minimum, min(maximum, value))


def clamp_double(minimum: float, maximum: float, value: float) -> float:
    """把浮点数限制在 [minimum, maximum] 内。"""
    return max(minimum, min(maximum, value))


def round_half_up(value: float) -> int:
    """按 JavaScript ``Math.round`` 语义四舍五入（0.5 进位）。"""
    return math.floor(value + 0.5)


def sanitize_degrees_int(degrees: int) -> int:
    """把角度规范到 [0, 360) 的整数。"""
    return degrees % 360


def sanitize_degrees_double(degrees: float) -> float:
    """把角度规范到 [0.0, 360.0) 的浮点数。"""
    degrees = degrees % 360.0
    if degrees < 0:
        degrees += 360.0
    return degrees


def rotation_direction(from_degrees: float, to_degrees: float) -> float:
    """返回从一个角度到另一个角度的最短旋转方向（1 或 -1）。"""
    increasing = sanitize_degrees_double(to_degrees - from_degrees)
    return 1.0 if increasing <= 180.0 else -1.0


def difference_degrees(a: float, b: float) -> float:
    """两个角度在圆周上的最短距离。"""
    return 180.0 - abs(abs(a - b) - 180.0)


def matrix_multiply(row: Sequence[float], matrix: Matrix3) -> Vector3:
    """1x3 行向量乘以 3x3 矩阵。"""
    return (
        row[0] * matrix[0][0] + row[1] * matrix[0][1] + row[2] * matrix[0][2],
        row[0] * matrix[1][0] + row[1] * matrix[1][1] + row[2] * matrix[1][2],
        row[0] * matrix[2][0] + row[1] * matrix[2][1] + row[2] * matrix[2][2],
    )


def argb_from_rgb(red: int, green: int, blue: int) -> int:
    """由 sRGB 分量组合出不透明的 ARGB 整数。"""
    return color_tokens.argb_from_rgb(red, green, blue)


def argb_from_linrgb(linrgb: Sequence[float]) -> int:
    """由线性 RGB（0–100）组合出 ARGB 整数。"""
    return argb_from_rgb(
        delinearized(linrgb[0]),
        delinearized(linrgb[1]),
        delinearized(linrgb[2]),
    )


def is_opaque(argb: int) -> bool:
    """颜色是否完全不透明。"""
    return color_tokens.alpha_of(argb) >= 255


def argb_from_xyz(x: float, y: float, z: float) -> int:
    """XYZ 转 ARGB。"""
    matrix = XYZ_TO_SRGB
    linear_r = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z
    linear_g = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z
    linear_b = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z
    return argb_from_rgb(
        delinearized(linear_r),
        delinearized(linear_g),
        delinearized(linear_b),
    )


def xyz_from_argb(argb: int) -> Vector3:
    """ARGB 转 XYZ。"""
    return matrix_multiply(
        (
            linearized(color_tokens.red_of(argb)),
            linearized(color_tokens.green_of(argb)),
            linearized(color_tokens.blue_of(argb)),
        ),
        SRGB_TO_XYZ,
    )


def argb_from_lab(l_star: float, a: float, b: float) -> int:
    """CIE L*a*b* 转 ARGB。"""
    fy = (l_star + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    return argb_from_xyz(
        _lab_invf(fx) * WHITE_POINT_D65[0],
        _lab_invf(fy) * WHITE_POINT_D65[1],
        _lab_invf(fz) * WHITE_POINT_D65[2],
    )


def lab_from_argb(argb: int) -> Vector3:
    """ARGB 转 CIE L*a*b*。"""
    x, y, z = xyz_from_argb(argb)
    fx = _lab_f(x / WHITE_POINT_D65[0])
    fy = _lab_f(y / WHITE_POINT_D65[1])
    fz = _lab_f(z / WHITE_POINT_D65[2])
    return 116.0 * fy - 16, 500.0 * (fx - fy), 200.0 * (fy - fz)


def argb_from_lstar(lstar: float) -> int:
    """由 L* 生成对应明度的灰色。"""
    component = delinearized(y_from_lstar(lstar))
    return argb_from_rgb(component, component, component)


def lstar_from_argb(argb: int) -> float:
    """计算颜色的 L*（感知明度）。"""
    y = xyz_from_argb(argb)[1]
    return 116.0 * _lab_f(y / 100.0) - 16.0


def y_from_lstar(lstar: float) -> float:
    """L* 转相对亮度 Y。"""
    return 100.0 * _lab_invf((lstar + 16.0) / 116.0)


def lstar_from_y(y: float) -> float:
    """相对亮度 Y 转 L*。"""
    return _lab_f(y / 100.0) * 116.0 - 16.0


def linearized(rgb_component: float) -> float:
    """sRGB 分量（0–255）转线性 RGB（0–100）。"""
    normalized = rgb_component / 255.0
    if normalized <= 0.040449936:
        return normalized / 12.92 * 100.0
    return math.pow((normalized + 0.055) / 1.055, 2.4) * 100.0


def delinearized(rgb_component: float) -> int:
    """线性 RGB（0–100）转 sRGB 分量（0–255 整数）。"""
    normalized = rgb_component / 100.0
    if normalized <= 0.0031308:
        value = normalized * 12.92
    else:
        value = 1.055 * math.pow(normalized, 1.0 / 2.4) - 0.055
    return clamp_int(0, 255, round_half_up(value * 255.0))


def white_point_d65() -> Vector3:
    """标准 D65 白点。"""
    return WHITE_POINT_D65


def _lab_f(t: float) -> float:
    if t > _LAB_E:
        return math.pow(t, 1.0 / 3.0)
    return (_LAB_KAPPA * t + 16) / 116


def _lab_invf(ft: float) -> float:
    ft3 = ft * ft * ft
    if ft3 > _LAB_E:
        return ft3
    return (116 * ft - 16) / _LAB_KAPPA
