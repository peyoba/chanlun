import pytest
from chanlun.engine.klines import merge_klines
from chanlun.engine.fractal import find_fractals
from chanlun.engine.bi import build_bis
from chanlun.config import BiConfig
from synth import zigzag, bars

def run(df, mode="old", fx="strict"):
    m = merge_klines(df); f = find_fractals(m); return m, f, build_bis(m, f, BiConfig(mode=mode, fx_check=fx))

def test_fractals_alternate_on_zigzag():
    m, f, b = run(zigzag([10, 20, 12, 22, 14, 24, 16]))
    kinds = [x.kind for x in f]
    assert kinds == ["top", "bottom", "top", "bottom", "top", "bottom"] or kinds[0] in ("top", "bottom")
    assert all(a != c for a, c in zip(kinds, kinds[1:]))

def test_bis_on_zigzag():
    # 首个枢轴 10 在序列开头无左邻，不成分型；故从顶 20 开始共 4 笔
    m, f, b = run(zigzag([10, 20, 12, 22, 14, 24, 16], n=5))
    assert len(b) == 4
    assert [x.dir for x in b] == ["down", "up", "down", "up"]
    assert b[0].start_price == pytest.approx(20.3) and b[0].end_price == pytest.approx(11.7)

def test_old_bi_needs_independent_bar():
    # 顶底之间只有 0 根独立 K 线（顶 idx 与底 idx 差 3）：老笔不成，新笔可成（若原始 K 线 ≥3）
    rows = [(10, 9), (11, 10), (12, 11), (13, 12), (12.5, 11.5), (11.5, 10.5), (10.5, 9.5), (11.5, 10.5), (12.5, 11.5), (13.5, 12.5), (14.5, 13.5)]
    m, f, b_old = run(bars(rows), "old")
    assert len(m) == len(rows)
    tops = [x for x in f if x.kind == "top"]; bots = [x for x in f if x.kind == "bottom"]
    assert tops and bots and bots[0].idx - tops[0].idx == 3
    assert len(b_old) == 0
    m, f, b_new = run(bars(rows), "new")
    # 顶 idx=3、底 idx=6：中间原始 K 线 2 根 (<3)，新笔也不成
    assert len(b_new) == 0

def test_new_bi_with_three_raw_between():
    # 顶 idx=3，底 idx=7：老笔 (差4) 成立；新笔要求中间原始 ≥3 也成立
    rows = [(10, 9), (11, 10), (12, 11), (13, 12), (12.5, 11.5), (11.5, 10.5), (10.5, 9.5), (9.5, 8.5), (10.5, 9.5), (11.5, 10.5), (12.5, 11.5)]
    _, _, b_old = run(bars(rows), "old"); _, _, b_new = run(bars(rows), "new")
    assert len(b_old) == 1 and len(b_new) == 1 and b_old[0].dir == "down"

def test_extension_takes_more_extreme_top():
    # 顶 20 后浅回调到 18（未跌破顶分型区间，strict 不成笔），再上到 22：笔起点应延伸为更高的顶 22
    m, f, b = run(zigzag([10, 20, 18, 22, 8, 18], n=5))
    downs = [x for x in b if x.dir == "down"]
    assert downs and downs[0].start_price == pytest.approx(22.3) and downs[0].end_price == pytest.approx(7.7)

def test_candidate_revert_when_lower_low():
    # 底 10 → 顶 20 候选，其后出现更低底 8 但 20 未成笔 → 候选作废，前一笔延伸到 8
    m, f, b = run(zigzag([30, 10, 20, 8, 25], n=5))
    downs = [x for x in b if x.dir == "down"]
    assert downs[0].end_price == pytest.approx(8, abs=0.5)

def test_confirmed_flags():
    m, f, b = run(zigzag([10, 20, 12, 22, 14, 24, 16, 26], n=5))
    assert len(b) >= 4
    assert all(x.confirmed for x in b[:-2]) and not b[-1].confirmed and not b[-2].confirmed
    assert all(x.confirmed_at is not None and x.confirmed_at > x.end_fx.ts for x in b[:-2])

def test_strict_fx_check_rejects_overlap():
    # 顶分型的最高点未高过底分型三根 K 线的最高点 → strict 不成笔，loss 可成
    rows = [(10, 9), (11, 10), (12, 11), (11.5, 10.5), (11, 10), (10.5, 9.5), (11.8, 10.8), (12.5, 11.5), (13, 12)]
    _, f, bs = run(bars(rows), "old", "strict"); _, _, bl = run(bars(rows), "old", "loss")
    assert len(bs) == 0
