"""缠论结构说明：只复述引擎字段，空数据不崩；编号与图对齐。"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

from chanlun.config import AppConfig
from chanlun.engine.analyze import analyze_bars
from chanlun.engine.models import AnalysisResult, BSP, Check, Fractal, Seg, ZhongShu
from chanlun.render.narrative import analysis_html, analysis_markdown, analysis_paragraphs
from tests.unit.synth import zigzag

FIX = Path(__file__).resolve().parents[1] / "golden" / "fixtures" / "600519.SH_D.csv"


def _fx(price: float, raw: int = 0) -> Fractal:
    return Fractal("top", 0, price, price, price, raw, pd.Timestamp("2020-01-01"))


def _seg(i: int, d: str, a: float, b: float, *, case: str = "pending", confirmed: bool = False) -> Seg:
    return Seg(i, d, 0, 1, _fx(a), _fx(b), end_case=case, confirmed=confirmed)  # type: ignore[arg-type]


def _zs(i: int, kind: str, zd: float, zg: float, elems: list[int], **kw) -> ZhongShu:
    kw.setdefault("enter_id", None)
    kw.setdefault("leave_id", None)
    kw.setdefault("start_raw", 0)
    kw.setdefault("end_raw", 5)
    kw.setdefault("range_confirmed", True)
    return ZhongShu(id=i, kind=kind, zg=zg, zd=zd, gg=zg, dd=zd, elems=elems, **kw)


def _empty_res(**kw) -> AnalysisResult:
    bars = zigzag([10, 12, 9], n=4)
    base = dict(
        meta={"code": "TEST.SZ", "name": "测试", "level": "D"},
        bars=bars, merged=[], fractals=[], bis=[], segs=[],
        zs_bi=[], zs_seg=[], macd=None, divergences=[], bsps=[],
        trend={"seg": {"type": "none", "zs_count": 0, "dir": None}, "bi": {"type": "none", "zs_count": 0, "dir": None}},
        projection={},
    )
    base.update(kw)
    return AnalysisResult(**base)


def test_fixture_daily_has_structure_sections():
    bars = pd.read_csv(FIX, parse_dates=["ts"])
    r = analyze_bars(bars, AppConfig(), meta={"code": "600519.SH", "name": "贵州茅台", "level": "D"})
    text = analysis_markdown(r)
    assert "日线" in text
    assert "贵州茅台" in text
    assert "**当下**" in text
    assert "**走势**" in text
    assert "**中枢**" in text
    assert "**买卖点**" in text
    assert "不是买卖建议" in text


def test_price_inside_last_zs():
    zs = _zs(0, "seg", 10.0, 20.0, [0, 1, 2])
    bars = zigzag([10, 14, 11], n=4)
    bars.loc[bars.index[-1], "close"] = 15.0
    r = _empty_res(
        bars=bars, zs_seg=[zs],
        trend={"seg": {"type": "range", "zs_count": 1, "dir": None}, "bi": {"type": "none"}},
    )
    text = analysis_markdown(r)
    assert "段中枢#0" in text
    assert "内部" in text
    assert "[10.00, 20.00]" in text
    assert "只有 1 个段中枢" in text


def test_old_bsp_notes_distance():
    bars = zigzag([10, 14, 11], n=4)
    last = bars.ts.iloc[-1]
    p = BSP(
        id=0, type="3b", zs_kind="bi", ts=last - pd.Timedelta(days=200),
        raw_idx=0, price=12.0, grade="suspect", confirmed=True, confirmed_at=None,
        refs={}, reason_short="三买(笔级, 疑似)：测试", checklist=[Check("条件", "pass", "ok")],
        teaching="", risks=[],
    )
    text = analysis_markdown(_empty_res(bars=bars, bsps=[p]))
    assert "疑似三买" in text
    assert "距今 200 天" in text


def test_wording_aligns_chart_and_avoids_old_traps():
    bars = zigzag([26, 30, 27, 28], n=4)
    bars.loc[bars.index[-1], "close"] = 27.99
    last_zs = _zs(3, "seg", 28.07, 29.81, list(range(8)))
    older = _zs(2, "seg", 26.04, 27.69, [0, 1, 2])
    bi_a = _zs(28, "bi", 28.34, 28.83, [1, 2, 3], ended=True, leave_id=245)
    bi_b = _zs(30, "bi", 27.47, 28.05, [4, 5, 6, 7], range_confirmed=False)
    segs = [
        _seg(21, "down", 29.87, 26.89, case="case1", confirmed=True),
        _seg(22, "up", 26.89, 28.33, case="pending", confirmed=False),
    ]
    p = BSP(
        id=0, type="3s", zs_kind="bi", ts=bars.ts.iloc[-1] - pd.Timedelta(days=22),
        raw_idx=0, price=28.08, grade="suspect", confirmed=True, confirmed_at=None,
        refs={"zs": 28}, reason_short="三卖(笔级, 疑似)：测试", checklist=[], teaching="", risks=[],
    )
    r = _empty_res(
        bars=bars, segs=segs, zs_seg=[older, last_zs], zs_bi=[bi_a, bi_b], bsps=[p],
        trend={"seg": {"type": "trend", "zs_count": 3, "dir": "up"}, "bi": {"type": "range", "zs_count": 1, "dir": None}},
    )
    text = analysis_markdown(r)
    assert "段中枢#3" in text
    assert "共 8 段" in text
    assert "线段#22" in text
    assert "3 级上台阶" in text
    assert "不算离开" in text
    assert "笔级别最近两个中枢重叠" in text
    assert "笔中枢#28" in text
    assert "不是当下这笔中枢#30" in text
    assert "第 23 段" not in text
    assert "尚无离开段" not in text
    assert "最近 1 个中枢" not in text


def test_empty_bars_safe():
    r = _empty_res()
    r.bars = r.bars.iloc[0:0]
    paras = analysis_paragraphs(r)
    assert any("没有 K 线" in p for p in paras)
    html = analysis_html(r)
    assert "<section" in html


def test_html_escapes_name():
    r = _empty_res(meta={"code": "X", "name": "甲<script>", "level": "30m"})
    html = analysis_html(r)
    assert "<script>" not in html
    assert "30分钟" in html
