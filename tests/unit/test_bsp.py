"""买卖点：笔/段 id 都从 0 起，不能把笔级背驰挂到同号线段上。"""
from pathlib import Path
import pandas as pd
from chanlun.config import AppConfig
from chanlun.engine.analyze import analyze_bars

FIX = Path(__file__).resolve().parents[1] / "golden" / "fixtures" / "600519.SH_D.csv"


def test_bsp_confirmed_at_not_before_event():
    bars = pd.read_csv(FIX, parse_dates=["ts"])
    r = analyze_bars(bars, AppConfig())
    early = [(p.type, str(p.ts.date()), str(p.confirmed_at.date()), p.zs_kind)
             for p in r.bsps if p.confirmed_at is not None and p.confirmed_at < p.ts]
    assert not early, f"确认时间早于发生时间: {early}"


def test_type1_matches_leave_of_same_kind():
    bars = pd.read_csv(FIX, parse_dates=["ts"])
    r = analyze_bars(bars, AppConfig())
    zmap = {("bi", z.id): z for z in r.zs_bi}
    zmap.update({("seg", z.id): z for z in r.zs_seg})
    for p in r.bsps:
        if not p.type.startswith("1"):
            continue
        zs = zmap.get((p.zs_kind, p.refs.get("zs")))
        assert zs is not None
        assert zs.leave_id == p.refs.get(p.zs_kind)
