from chanlun.engine.klines import merge_klines
from synth import bars

def test_no_containment_unchanged():
    m = merge_klines(bars([(10, 9), (11, 10), (12, 11), (11.5, 10.5)]))
    assert [(x.high, x.low) for x in m] == [(10, 9), (11, 10), (12, 11), (11.5, 10.5)]

def test_up_merge_takes_max_high_max_low():
    # 上升中 (12,11) 包含 (11.8,11.2) → (12, 11.2)
    m = merge_klines(bars([(10, 9), (12, 11), (11.8, 11.2)]))
    assert (m[-1].high, m[-1].low) == (12, 11.2) and m[-1].raw_start == 1 and m[-1].raw_end == 2

def test_down_merge_takes_min_high_min_low():
    m = merge_klines(bars([(12, 11), (10, 9), (9.8, 9.2)]))
    assert (m[-1].high, m[-1].low) == (9.8, 9) and m[-1].dir == "down"

def test_chain_merge():
    m = merge_klines(bars([(10, 9), (12, 11), (11.8, 11.2), (11.9, 11.3), (13, 12.5)]))
    assert len(m) == 3 and (m[1].high, m[1].low) == (12, 11.3) and m[1].raw_end == 3

def test_leading_containment_dropped():
    m = merge_klines(bars([(12, 9), (11, 10), (13, 12), (14, 13)]))
    assert m[0].raw_start == 1 and len(m) == 3

def test_one_bar_limit_up_equal_hl():
    # 一字板 (11,11) 被前一根 (12,10) 包含
    m = merge_klines(bars([(9, 8), (12, 10), (11, 11), (13, 12)]))
    assert len(m) == 3 and (m[1].high, m[1].low) == (12, 11)

def test_equal_bars_are_containment():
    m = merge_klines(bars([(9, 8), (12, 10), (12, 10)]))
    assert len(m) == 2
