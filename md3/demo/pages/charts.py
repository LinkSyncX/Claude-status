"""Charts 页面：柱状、折线、饼图、散点、雷达、仪表盘、热力图与扩展图表。"""

from __future__ import annotations

import random

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import charts
from md3.components import selection
from md3.components import slider
from md3.components import snackbar
from md3.core import typography
from md3.demo.pages import _common

MONTHS = ["1月", "2月", "3月", "4月", "5月", "6月"]
REGIONS = ["华东", "华北", "华南", "西南", "东北"]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五"]
HOURS = ["9时", "11时", "13时", "15时", "17时", "19时"]
TRAITS = ["性能", "价格", "外观", "续航", "服务", "生态"]


def _random_series(
    names: list[str], low: int, high: int, count: int = len(MONTHS)
) -> list[charts.Series]:
    return [
        charts.Series(name, [random.randint(low, high) for _ in range(count)])
        for name in names
    ]


def _random_points(name: str, count: int, bubbles: bool) -> charts.PointSeries:
    points = [
        (round(random.uniform(0, 10), 1), round(random.uniform(0, 100), 1))
        for _ in range(count)
    ]
    sizes = [random.randint(5, 60) for _ in range(count)] if bubbles else None
    return charts.PointSeries(name, points, sizes)


def _random_candles(count: int) -> list[charts.Candle]:
    candles: list[charts.Candle] = []
    close = 100.0
    for _ in range(count):
        open_ = close
        close = round(open_ + random.uniform(-6, 6), 2)
        high = round(max(open_, close) + random.uniform(0, 3), 2)
        low = round(min(open_, close) - random.uniform(0, 3), 2)
        candles.append(charts.Candle(open_, high, low, close))
    return candles


def _random_boxes(count: int) -> list[charts.BoxStats]:
    return [
        charts.BoxStats.from_values(
            [random.gauss(50 + index * 5, 8) for _ in range(40)]
            + [random.uniform(90, 110)]
        )
        for index in range(count)
    ]


def _build_extended(page: _common.Page) -> None:
    section = page.section(
        "统计与层级图表",
        "K 线图按涨跌着色；箱线图显示四分位、须线与离群点；瀑布图把增减"
        "累加成小计；漏斗图标注逐级转化率；树图用 squarify 布局按比例铺满。",
    )
    days = [f"{day}日" for day in range(1, 13)]
    candles = charts.CandlestickChart(_random_candles(12), days, title="K 线图")
    boxes = charts.BoxPlotChart(
        _random_boxes(5), ["A", "B", "C", "D", "E"], title="箱线图"
    )
    waterfall = charts.WaterfallChart(
        [320, 80, -45, 120, 0, -60, 30, 0],
        ["期初", "新增", "流失", "升级", "小计", "退款", "补贴", "期末"],
        title="瀑布图",
        totals={4, 7},
    )
    funnel = charts.FunnelChart(
        [1200, 860, 540, 310, 120],
        ["访问", "注册", "激活", "付费", "复购"],
        title="漏斗图",
    )
    treemap = charts.TreemapChart(
        [
            charts.TreemapItem("华东", 38),
            charts.TreemapItem("华北", 24),
            charts.TreemapItem("华南", 18),
            charts.TreemapItem("西南", 11),
            charts.TreemapItem("东北", 6),
            charts.TreemapItem("其他", 3),
        ],
        title="树图",
    )
    grid = QtWidgets.QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(24)
    for index, chart in enumerate((candles, boxes, waterfall, funnel, treemap)):
        chart.setMinimumSize(360, 300)
        grid.addWidget(chart, index // 2, index % 2)
    section.addLayout(grid)
    refresh = buttons.OutlinedButton("重新采样", icon="refresh")

    def resample() -> None:
        candles.set_candles(_random_candles(12), days)
        boxes.set_boxes(_random_boxes(5), ["A", "B", "C", "D", "E"])
        treemap.set_items(
            [
                charts.TreemapItem(item.label, random.randint(2, 40))
                for item in treemap.items
            ]
        )

    refresh.clicked.connect(resample)
    page.row(section, [refresh])


def _build_streaming(page: _common.Page) -> None:
    section = page.section(
        "流式数据、缩放与导出",
        "append 逐点追加并丢弃旧点；滚轮缩放、拖动平移、双击复位；"
        "十字游标读数；to_image / export_svg 导出。",
    )
    chart = charts.LineChart(
        [charts.Series("CPU", [random.randint(20, 60) for _ in range(30)])],
        [str(index) for index in range(30)],
        title="实时负载",
        fill_area=True,
        show_points=False,
    )
    chart.set_zoomable(True, min_visible=5)
    chart.set_crosshair(True)
    chart.setMinimumHeight(300)
    section.addWidget(chart)
    timer = QtCore.QTimer(chart)
    timer.setInterval(600)
    timer.timeout.connect(
        lambda: chart.append([random.randint(20, 60)], max_points=60)
    )
    stream = buttons.FilledTonalButton("开始推送", icon="play_arrow")

    def toggle_stream() -> None:
        if timer.isActive():
            timer.stop()
            stream.set_text("开始推送")
            stream.set_icon("play_arrow")
        else:
            timer.start()
            stream.set_text("暂停推送")
            stream.set_icon("pause")

    stream.clicked.connect(toggle_stream)
    crosshair = selection.Switch("十字游标", checked=True)
    crosshair.toggled.connect(chart.set_crosshair)
    reset = buttons.TextButton("复位缩放", icon="zoom_out_map")
    reset.clicked.connect(chart.reset_zoom)
    export = buttons.OutlinedButton("导出 PNG / SVG", icon="download")
    status = typography.Label(
        "显示全部 30 点", "body-medium", "on_surface_variant"
    )

    def describe(start: int, count: int) -> None:
        total = chart.total_category_count()
        if chart.zoomed:
            status.setText(f"显示第 {start + 1}–{start + count} / {total} 点")
        else:
            status.setText(f"显示全部 {total} 点")

    chart.visible_range_changed.connect(describe)

    def do_export() -> None:
        path, _selected = QtWidgets.QFileDialog.getSaveFileName(
            chart, "导出图表", "chart.png", "PNG (*.png);;SVG (*.svg)"
        )
        if not path:
            return
        ok = (
            chart.export_svg(path)
            if path.lower().endswith(".svg")
            else chart.export_image(path)
        )
        snackbar.show(chart, f"已导出 {path}" if ok else "导出失败")

    export.clicked.connect(do_export)
    page.row(section, [stream, reset, export, crosshair, status], gap=16)


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "图表",
        "使用主题色彩角色着色的图表；支持悬停提示、入场与数据过渡动画，"
        "点击图例可隐藏或显示系列。",
    )

    controls = page.section(
        "交互",
        "随机数据会以过渡动画从旧值变到新值；点击任意图表下方的图例条目可"
        "隐藏该系列。",
    )
    randomize = buttons.FilledTonalButton("随机数据", icon="casino")
    page.row(controls, [randomize])

    grouped = charts.BarChart(
        [
            charts.Series("收入", [120, 180, 150, 210, 260, 240]),
            charts.Series("支出", [80, 110, 95, 140, 160, 150]),
        ],
        MONTHS,
        show_values=True,
        title="月度收支（分组柱状图 + 数值标签）",
    )
    grouped.set_axis_titles("月份", "万元")
    stacked = charts.BarChart(
        [
            charts.Series("移动端", [40, 55, 60, 75, 90, 100]),
            charts.Series("桌面端", [30, 32, 35, 33, 38, 40]),
            charts.Series("其他", [10, 12, 9, 14, 12, 16]),
        ],
        MONTHS,
        stacked=True,
        title="访问来源（堆叠柱状图）",
    )
    horizontal = charts.HorizontalBarChart(
        [charts.Series("销量", [320, 280, 210, 150, 90])],
        REGIONS,
        show_values=True,
        title="区域销量排行（横向柱状图）",
    )
    line = charts.LineChart(
        [
            charts.Series("北京", [12, 18, 15, 24, 28, 26]),
            charts.Series("上海", [10, 12, 20, 18, 22, 30]),
            charts.Series("广州", [8, 9, 14, 12, 19, 21]),
        ],
        MONTHS,
        fill_area=True,
        title="活跃用户（万，平滑折线 + 面积）",
    )
    area = charts.LineChart(
        [
            charts.Series("移动端", [40, 55, 60, 75, 90, 100]),
            charts.Series("桌面端", [30, 32, 35, 33, 38, 40]),
            charts.Series("其他", [10, 12, 9, 14, 12, 16]),
        ],
        MONTHS,
        stacked=True,
        show_points=False,
        title="访问来源（堆叠面积图）",
    )
    sparkline = charts.LineChart(
        [charts.Series("温度 °C", [-3, 2, 9, 17, 23, 28])],
        MONTHS,
        smooth=False,
        title="无坐标轴的迷你图",
        show_legend=False,
    )
    sparkline.set_show_axes(False)
    scatter = charts.ScatterChart(
        [
            _random_points("A 组", 8, bubbles=True),
            _random_points("B 组", 8, bubbles=True),
        ],
        title="投入产出（气泡图）",
        x_title="投入（万元）",
        y_title="产出",
    )
    radar = charts.RadarChart(
        [
            charts.Series("产品 A", [80, 65, 90, 70, 60, 75]),
            charts.Series("产品 B", [60, 85, 55, 75, 90, 65]),
        ],
        TRAITS,
        title="产品对比（雷达图）",
    )
    gauge = charts.GaugeChart(
        72,
        bands=[
            charts.GaugeBand(0, 40, "error"),
            charts.GaugeBand(40, 70, "tertiary"),
            charts.GaugeBand(70, 100, "primary"),
        ],
        label="目标完成率 %",
        target=85,
        title="仪表盘",
    )
    heatmap = charts.HeatmapChart(
        WEEKDAYS,
        HOURS,
        [[random.randint(0, 20) for _ in HOURS] for _ in WEEKDAYS],
        show_values=True,
        title="访问热力图（人次）",
    )
    donut = charts.PieChart(
        [42, 26, 18, 9, 5],
        ["搜索", "直接访问", "社交", "邮件", "其他"],
        title="流量占比（环形图）",
    )
    pie = charts.PieChart([3, 2, 1], ["A", "B", "C"], donut=False, title="饼图")

    gauge_section = page.section(
        "仪表盘数值", "拖动滑块，指示弧以进度弹簧跟随。"
    )
    gauge_slider = slider.Slider(0, 100, 72)
    gauge_slider.value_changed.connect(gauge.set_value)
    gauge_section.addWidget(gauge_slider)

    grid_section = page.section("图表")
    grid = QtWidgets.QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(24)
    all_charts = [
        grouped,
        stacked,
        horizontal,
        line,
        area,
        sparkline,
        scatter,
        radar,
        gauge,
        heatmap,
        donut,
        pie,
    ]
    for index, chart in enumerate(all_charts):
        chart.setMinimumSize(360, 300)
        grid.addWidget(chart, index // 2, index % 2)
    grid_section.addLayout(grid)

    def shuffle() -> None:
        grouped.set_data(MONTHS, _random_series(["收入", "支出"], 50, 300))
        stacked.set_data(
            MONTHS, _random_series(["移动端", "桌面端", "其他"], 10, 100)
        )
        horizontal.set_data(
            REGIONS, _random_series(["销量"], 50, 400, len(REGIONS))
        )
        line.set_data(MONTHS, _random_series(["北京", "上海", "广州"], 5, 30))
        area.set_data(
            MONTHS, _random_series(["移动端", "桌面端", "其他"], 10, 100)
        )
        sparkline.set_data(MONTHS, _random_series(["温度 °C"], -10, 30))
        scatter.set_point_series(
            [
                _random_points("A 组", 8, bubbles=True),
                _random_points("B 组", 8, bubbles=True),
            ]
        )
        radar.set_data(
            TRAITS, _random_series(["产品 A", "产品 B"], 40, 100, len(TRAITS))
        )
        value = random.randint(0, 100)
        gauge_slider.set_value(value)
        gauge.set_value(value)
        heatmap.set_matrix(
            WEEKDAYS,
            HOURS,
            [[random.randint(0, 20) for _ in HOURS] for _ in WEEKDAYS],
        )
        donut.set_values([random.randint(5, 50) for _ in range(5)])
        pie.set_values([random.randint(1, 5) for _ in range(3)])

    randomize.clicked.connect(shuffle)
    _build_extended(page)
    _build_streaming(page)
    page.finish()
    return page
