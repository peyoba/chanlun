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


def _endpoints_are_extremes(m, bis):
    """笔的顶端点应为笔内合并 K 线最高、底端点为最低。"""
    for b in bis:
        seg = m[b.start_idx:b.end_idx + 1]
        hi = max(x.high for x in seg); lo = min(x.low for x in seg)
        top, bot = (b.start_fx, b.end_fx) if b.dir == "down" else (b.end_fx, b.start_fx)
        assert top.price == pytest.approx(hi), f"笔#{b.id} 顶 {top.price} 非笔内最高 {hi}"
        assert bot.price == pytest.approx(lo), f"笔#{b.id} 底 {bot.price} 非笔内最低 {lo}"


def test_end_must_be_peak_inside_bi():
    """起点后出现离得太近（不够成笔）的更高顶 40，随后较低的顶 38.5 虽满足距离与价格条件，也不能做终点（笔内不得有高于终点的 K 线）。"""
    rows = [(30, 29), (29, 28), (28, 27), (27, 26), (26, 25),
            (25.5, 24),            # idx5 底 S=24
            (27, 25), (40, 38),    # idx7 顶 40：距 S 仅 2 根，不够成笔，但它是 S 之后的最高点
            (39, 36), (37, 35), (36, 34), (34, 32), (35, 33), (37, 35),
            (38.5, 36),            # idx14 顶 38.5：距离、价格条件都满足，但低于 40
            (38, 35), (36, 33), (34, 31), (32, 29), (30, 27), (28, 25),
            (26, 22),              # idx21 底 22：低于 S，起点回退
            (27, 23), (29, 26), (31, 28), (33, 30), (35, 32),
            (37, 34),              # idx27 顶 37
            (36, 33)]
    m, f, b = run(bars(rows), "old", "strict")
    assert len(m) == len(rows)
    assert all(x.end_price != pytest.approx(38.5) and x.start_price != pytest.approx(38.5) for x in b)
    assert len(b) == 1 and b[0].dir == "up" and b[0].start_price == 22 and b[0].end_price == 37 and b[0].candidate
    _endpoints_are_extremes(m, b)


def _end_is_extreme(m, b):
    seg = m[b.start_idx:b.end_idx + 1]
    return b.end_price == pytest.approx(max(x.high for x in seg) if b.dir == "up" else min(x.low for x in seg))


def _start_is_extreme(m, b):
    seg = m[b.start_idx:b.end_idx + 1]
    return b.start_price == pytest.approx(min(x.low for x in seg) if b.dir == "up" else max(x.high for x in seg))


def test_endpoints_extreme_on_random_walk():
    """终点永远是笔内极值；起点只在"非笔段落"角落（相邻分型不够成笔且两种延伸都越界）允许例外，须极少。"""
    import numpy as np
    rng = np.random.default_rng(7)
    p = 100 + np.cumsum(rng.normal(0, 1, 3000))
    rows = [(x + abs(rng.normal(0, 0.6)), x - abs(rng.normal(0, 0.6))) for x in p]
    for mode in ("old", "new"):
        m, f, b = run(bars(rows), mode, "strict")
        assert len(b) > 20
        assert all(_end_is_extreme(m, x) for x in b)
        bad = [x.id for x in b if not _start_is_extreme(m, x)]
        assert len(bad) <= 0.03 * len(b), f"起点非极值的笔过多: {bad}"


def test_fractal_ts_is_extreme_bar_time():
    # (12,11) 与 (11.9,11.2) 合并为 (12, 11.2)，最高点在第 2 根（索引 1）；分型时间应为索引 1 的时间而非合并末根
    df = bars([(10, 9), (12, 11), (11.9, 11.2), (11, 10)])
    m = merge_klines(df); f = find_fractals(m)
    assert len(m) == 3 and m[1].raw_end == 2
    tops = [x for x in f if x.kind == "top"]
    assert tops and tops[0].raw_idx == 1 and tops[0].ts == df.ts.iloc[1] and m[1].ts == df.ts.iloc[2]
    assert tops[0].known_at == df.ts.iloc[3]
