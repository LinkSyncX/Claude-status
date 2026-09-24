"""HCT 方程求解器：由色相、色度、色调反求 sRGB 颜色。

先用牛顿迭代寻找精确解；若目标色度超出 sRGB 色域，则在保持色相与色调
的前提下，沿色域边界二分搜索得到色度最大的可显示颜色。
"""

from __future__ import annotations

import math

from md3.color import cam16
from md3.color import utils
from md3.color import viewing_conditions as vc_module

_SCALED_DISCOUNT_FROM_LINRGB: utils.Matrix3 = (
    (0.001200833568784504, 0.002389694492170889, 0.0002795742885861124),
    (0.0005891086651375999, 0.0029785502573438758, 0.0003270666104008398),
    (0.00010146692491640572, 0.0005364214359186694, 0.0032979401770712076),
)

_LINRGB_FROM_SCALED_DISCOUNT: utils.Matrix3 = (
    (1373.2198709594231, -1100.4251190754821, -7.278681089101213),
    (-271.815969077903, 559.6580465940733, -32.46047482791194),
    (1.9622899599665666, -57.173814538844006, 308.7233197812385),
)

_Y_FROM_LINRGB: utils.Vector3 = (0.2126, 0.7152, 0.0722)

# 每个 sRGB 量化边界（i + 0.5，i = 0..254）对应的线性 RGB 值。
_CRITICAL_PLANES: tuple[float, ...] = tuple(
    utils.linearized(i + 0.5) for i in range(255)
)

_OUT_OF_CUBE = (-1.0, -1.0, -1.0)


def _sanitize_radians(angle: float) -> float:
    return (angle + math.pi * 8) % (math.pi * 2)


def _true_delinearized(rgb_component: float) -> float:
    """不做取整的线性 RGB 反变换，返回 0–255 的浮点数。"""
    normalized = rgb_component / 100.0
    if normalized <= 0.0031308:
        value = normalized * 12.92
    else:
        value = 1.055 * math.pow(normalized, 1.0 / 2.4) - 0.055
    return value * 255.0


def _chromatic_adaptation(component: float) -> float:
    af = math.pow(abs(component), 0.42)
    return utils.signum(component) * 400.0 * af / (af + 27.13)


def _hue_of(linrgb: utils.Vector3) -> float:
    """线性 RGB 颜色在 CAM16 中的色相（弧度）。"""
    scaled = utils.matrix_multiply(linrgb, _SCALED_DISCOUNT_FROM_LINRGB)
    r_a = _chromatic_adaptation(scaled[0])
    g_a = _chromatic_adaptation(scaled[1])
    b_a = _chromatic_adaptation(scaled[2])
    a = (11.0 * r_a + -12.0 * g_a + b_a) / 11.0
    b = (r_a + g_a - 2.0 * b_a) / 9.0
    return math.atan2(b, a)


def _are_in_cyclic_order(a: float, b: float, c: float) -> bool:
    delta_ab = _sanitize_radians(b - a)
    delta_ac = _sanitize_radians(c - a)
    return delta_ab < delta_ac


def _intercept(source: float, mid: float, target: float) -> float:
    return (mid - source) / (target - source)


def _lerp_point(
    source: utils.Vector3, t: float, target: utils.Vector3
) -> utils.Vector3:
    return (
        source[0] + (target[0] - source[0]) * t,
        source[1] + (target[1] - source[1]) * t,
        source[2] + (target[2] - source[2]) * t,
    )


def _set_coordinate(
    source: utils.Vector3,
    coordinate: float,
    target: utils.Vector3,
    axis: int,
) -> utils.Vector3:
    """线段与平面 axis = coordinate 的交点。"""
    t = _intercept(source[axis], coordinate, target[axis])
    return _lerp_point(source, t, target)


def _is_bounded(x: float) -> bool:
    return 0.0 <= x <= 100.0


def _nth_vertex(y: float, n: int) -> utils.Vector3:
    """Y 平面与 RGB 立方体相交多边形的第 n 个候选顶点（0 <= n <= 11）。"""
    k_r, k_g, k_b = _Y_FROM_LINRGB
    coord_a = 0.0 if n % 4 <= 1 else 100.0
    coord_b = 0.0 if n % 2 == 0 else 100.0
    if n < 4:
        g = coord_a
        b = coord_b
        r = (y - g * k_g - b * k_b) / k_r
        return (r, g, b) if _is_bounded(r) else _OUT_OF_CUBE
    if n < 8:
        b = coord_a
        r = coord_b
        g = (y - r * k_r - b * k_b) / k_g
        return (r, g, b) if _is_bounded(g) else _OUT_OF_CUBE
    r = coord_a
    g = coord_b
    b = (y - r * k_r - g * k_g) / k_b
    return (r, g, b) if _is_bounded(b) else _OUT_OF_CUBE


def _bisect_to_segment(
    y: float, target_hue: float
) -> tuple[utils.Vector3, utils.Vector3]:
    """找到包含目标色相的多边形边（两个端点）。"""
    left = _OUT_OF_CUBE
    right = left
    left_hue = 0.0
    right_hue = 0.0
    initialized = False
    uncut = True
    for n in range(12):
        mid = _nth_vertex(y, n)
        if mid[0] < 0:
            continue
        mid_hue = _hue_of(mid)
        if not initialized:
            left = mid
            right = mid
            left_hue = mid_hue
            right_hue = mid_hue
            initialized = True
            continue
        if uncut or _are_in_cyclic_order(left_hue, mid_hue, right_hue):
            uncut = False
            if _are_in_cyclic_order(left_hue, target_hue, mid_hue):
                right = mid
                right_hue = mid_hue
            else:
                left = mid
                left_hue = mid_hue
    return left, right


def _midpoint(a: utils.Vector3, b: utils.Vector3) -> utils.Vector3:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def _critical_plane_below(x: float) -> int:
    return math.floor(x - 0.5)


def _critical_plane_above(x: float) -> int:
    return math.ceil(x - 0.5)


def _bisect_to_limit(y: float, target_hue: float) -> utils.Vector3:
    """在色域边界上找到给定 Y 与色相的颜色（线性 RGB）。"""
    left, right = _bisect_to_segment(y, target_hue)
    left_hue = _hue_of(left)
    for axis in range(3):
        if left[axis] == right[axis]:
            continue
        if left[axis] < right[axis]:
            l_plane = _critical_plane_below(_true_delinearized(left[axis]))
            r_plane = _critical_plane_above(_true_delinearized(right[axis]))
        else:
            l_plane = _critical_plane_above(_true_delinearized(left[axis]))
            r_plane = _critical_plane_below(_true_delinearized(right[axis]))
        for _ in range(8):
            if abs(r_plane - l_plane) <= 1:
                break
            m_plane = math.floor((l_plane + r_plane) / 2.0)
            mid_plane_coordinate = _CRITICAL_PLANES[m_plane]
            mid = _set_coordinate(left, mid_plane_coordinate, right, axis)
            mid_hue = _hue_of(mid)
            if _are_in_cyclic_order(left_hue, target_hue, mid_hue):
                right = mid
                r_plane = m_plane
            else:
                left = mid
                left_hue = mid_hue
                l_plane = m_plane
    return _midpoint(left, right)


def _inverse_chromatic_adaptation(adapted: float) -> float:
    adapted_abs = abs(adapted)
    base = max(0.0, 27.13 * adapted_abs / (400.0 - adapted_abs))
    return utils.signum(adapted) * math.pow(base, 1.0 / 0.42)


def _find_result_by_j(hue_radians: float, chroma: float, y: float) -> int:
    """用牛顿法沿明度 J 搜索精确解，找不到时返回 0。"""
    j = math.sqrt(y) * 11.0
    conditions = vc_module.DEFAULT
    t_inner_coeff = 1 / math.pow(1.64 - math.pow(0.29, conditions.n), 0.73)
    e_hue = 0.25 * (math.cos(hue_radians + 2.0) + 3.8)
    p1 = e_hue * (50000.0 / 13.0) * conditions.nc * conditions.ncb
    h_sin = math.sin(hue_radians)
    h_cos = math.cos(hue_radians)
    for iteration_round in range(5):
        j_normalized = j / 100.0
        if chroma == 0.0 or j == 0.0:
            alpha = 0.0
        else:
            alpha = chroma / math.sqrt(j_normalized)
        t = math.pow(alpha * t_inner_coeff, 1.0 / 0.9)
        ac = conditions.aw * math.pow(
            j_normalized, 1.0 / conditions.c / conditions.z
        )
        p2 = ac / conditions.nbb
        gamma = (
            23.0
            * (p2 + 0.305)
            * t
            / (23.0 * p1 + 11 * t * h_cos + 108.0 * t * h_sin)
        )
        a = gamma * h_cos
        b = gamma * h_sin
        r_a = (460.0 * p2 + 451.0 * a + 288.0 * b) / 1403.0
        g_a = (460.0 * p2 - 891.0 * a - 261.0 * b) / 1403.0
        b_a = (460.0 * p2 - 220.0 * a - 6300.0 * b) / 1403.0
        linrgb = utils.matrix_multiply(
            (
                _inverse_chromatic_adaptation(r_a),
                _inverse_chromatic_adaptation(g_a),
                _inverse_chromatic_adaptation(b_a),
            ),
            _LINRGB_FROM_SCALED_DISCOUNT,
        )
        if linrgb[0] < 0 or linrgb[1] < 0 or linrgb[2] < 0:
            return 0
        k_r, k_g, k_b = _Y_FROM_LINRGB
        fnj = k_r * linrgb[0] + k_g * linrgb[1] + k_b * linrgb[2]
        if fnj <= 0:
            return 0
        if iteration_round == 4 or abs(fnj - y) < 0.002:
            if linrgb[0] > 100.01 or linrgb[1] > 100.01 or linrgb[2] > 100.01:
                return 0
            return utils.argb_from_linrgb(linrgb)
        # 以 2 * fn(j) / j 近似 fn'(j) 进行牛顿迭代。
        j = j - (fnj - y) * j / (2 * fnj)
    return 0


def solve_to_int(hue_degrees: float, chroma: float, lstar: float) -> int:
    """求与给定色相、色度、L* 最接近的 sRGB 颜色。

    若目标色度不可达，则色相与 L* 保持接近，色度取可显示的最大值。

    Args:
        hue_degrees: 色相（度）。
        chroma: 色度。
        lstar: L*（0–100）。

    Returns:
        ARGB 整数。
    """
    if chroma < 0.0001 or lstar < 0.0001 or lstar > 99.9999:
        return utils.argb_from_lstar(lstar)
    hue_degrees = utils.sanitize_degrees_double(hue_degrees)
    hue_radians = math.radians(hue_degrees)
    y = utils.y_from_lstar(lstar)
    exact_answer = _find_result_by_j(hue_radians, chroma, y)
    if exact_answer != 0:
        return exact_answer
    return utils.argb_from_linrgb(_bisect_to_limit(y, hue_radians))


def solve_to_cam(
    hue_degrees: float, chroma: float, lstar: float
) -> cam16.Cam16:
    """与 ``solve_to_int`` 相同，但返回 CAM16 表示。"""
    return cam16.Cam16.from_int(solve_to_int(hue_degrees, chroma, lstar))
