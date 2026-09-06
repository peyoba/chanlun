"""作图：窗外线段插值裁剪；纵轴锁定且不跟假线撑开。"""
from __future__ import annotations

from chanlun.engine.models import AnalysisResult, ZhongShu
from chanlun.render.plotly_chart import build_figure, clip_span, visible_yrange
from tests.unit.synth import zigzag


def _result(n: int = 40, zs_start: int = 0) -> AnalysisResult:
    bars = zigzag([10, 14, 9, 15, 8], n=n // 4 + 2).iloc[:n].reset_index(drop=True)
    zs = ZhongShu(
        id=0, kind="bi", zg=13.0, zd=9.0, gg=15.0, dd=8.0,
        elems=[], enter_id=None, leave_id=None,
        start_raw=zs_start, end_raw=n - 1, range_confirmed=True,
    )
    return AnalysisResult(
        meta={"code": "TEST", "name": "t", "level": "30m"},
        bars=bars, merged=[], fractals=[], bis=[], segs=[],
        zs_bi=[zs], zs_seg=[], macd=None, divergences=[], bsps=[],
        trend={},
        projection={"level": "D", "zs": [{"start_ts": bars.ts.iloc[0], "end_ts": bars.ts.iloc[-1], "zd": 9.0, "zg": 13.0}], "bi_points": []},
    )


def test_clip_span_interpolates_left_edge():
    # 起点在窗口外、终点在窗口内：左端 y 应按比例插值，不能仍是旧高点
    span = clip_span(s_raw=0, s_p=2000.0, e_raw=100, e_p=1000.0, off=50, n=50)
    assert span is not None
    x0, y0, x1, y1 = span
    assert x0 == 0.0
    assert x1 == 49.0  # e_raw 100 → x=50, 裁到 n-1=49
    assert 1000.0 < y0 < 2000.0
    assert abs(y0 - (2000.0 + (50 - 0) / (100 - 0) * (1000.0 - 2000.0))) < 1e-6


def test_yaxis_locked_shapes_numeric_and_in_window():
    fig = build_figure(_result(40, zs_start=0), max_bars=10)
    assert fig.layout.yaxis.fixedrange is True
    assert fig.layout.yaxis.autorange is False
    assert fig.layout.yaxis2.fixedrange is True
    assert fig.data[0].x[0] == 0
    for sh in fig.layout.shapes or []:
        assert isinstance(sh.x0, (int, float))
        assert sh.x0 >= -0.5


def test_linear_axis_covers_recent_window():
    fig = build_figure(_result(40), max_bars=40)
    xa = fig.layout.xaxis
    assert xa.type == "linear"
    r0, r1 = float(xa.range[0]), float(xa.range[1])
    assert r1 - r0 > 20
    assert fig.layout.xaxis.showticklabels is True
    assert fig.layout.xaxis2.showticklabels is False
    assert fig.layout.xaxis.tickmode == "auto"
    assert fig.layout.xaxis.labelalias["0"]
    assert fig.layout.xaxis.tickangle == 0


def test_visible_yrange_follows_window():
    bars = _result(40).bars
    full = visible_yrange(bars.high, bars.low, -0.5, 39.5)
    right = visible_yrange(bars.high, bars.low, 30, 39.5)
    assert full[0] <= right[0]
    assert full[1] >= right[1]
    assert right[1] > right[0]
