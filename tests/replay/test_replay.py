"""回放测试：逐根追加 K 线，断言已确认结构永不改变。M1 核心验收项。"""
import pytest, pandas as pd
from chanlun.config import load_config
from chanlun.data.store import Store
from chanlun.engine.analyze import analyze_bars

def _bars(code, level, n_tail):
    cfg = load_config(); st = Store(cfg.db_path)
    df = st.load_klines(code, level); st.close()
    if df.empty:
        pytest.skip(f"{code} {level} 无本地数据")
    return cfg, df.tail(n_tail).reset_index(drop=True)

def _key_bi(b): return (b.dir, b.start_raw, round(b.start_price, 4), b.end_raw, round(b.end_price, 4))
def _key_seg(s): return (s.dir, s.start_raw, round(s.start_price, 4), s.end_raw, round(s.end_price, 4), s.end_case)
def _key_zs(z): return (z.kind, round(z.zg, 4), round(z.zd, 4), z.start_raw, tuple(z.elems[:3]))

@pytest.mark.parametrize("code,level,n,step", [("600519.SH", "D", 1500, 1), ("600519.SH", "30m", 1500, 1), ("00700.HK", "D", 1500, 1)])
def test_confirmed_never_repaint(code, level, n, step):
    cfg, bars = _bars(code, level, n)
    warm = 400
    seen_bi: dict[tuple, int] = {}; seen_seg: dict[tuple, int] = {}; seen_zs: dict[tuple, int] = {}
    prev_bi: list = []; prev_seg: list = []; prev_zs: list = []
    for i in range(warm, len(bars) + 1, step):
        r = analyze_bars(bars.iloc[:i], cfg)
        # 由于开头包含处理丢弃取决于全序列前端，前端固定，故 raw 索引稳定
        cur_bi = [_key_bi(b) for b in r.bis if b.confirmed]
        cur_seg = [_key_seg(s) for s in r.segs if s.confirmed]
        cur_zs = [_key_zs(z) for z in r.zs_bi + r.zs_seg if z.range_confirmed]
        # 已确认前缀必须是上次已确认前缀的超集且顺序一致
        assert cur_bi[:len(prev_bi)] == prev_bi, f"笔在第 {i} 根重画：{set(prev_bi)-set(cur_bi)}"
        assert cur_seg[:len(prev_seg)] == prev_seg, f"线段在第 {i} 根重画：{set(prev_seg)-set(cur_seg)}"
        for z in prev_zs:
            assert z in cur_zs, f"中枢区间在第 {i} 根重画：{z}"
        prev_bi, prev_seg, prev_zs = cur_bi, cur_seg, cur_zs

@pytest.mark.parametrize("code,level", [("600519.SH", "D")])
def test_confirmed_at_after_event(code, level):
    cfg, bars = _bars(code, level, 3000)
    r = analyze_bars(bars, cfg)
    for b in r.bis:
        if b.confirmed:
            assert b.confirmed_at is not None and b.confirmed_at > b.end_fx.ts
    for s in r.segs:
        if s.confirmed:
            assert s.confirmed_at is not None and s.confirmed_at > s.end_fx.ts

@pytest.mark.parametrize("code,level", [("600519.SH", "D")])
def test_as_of_equals_truncated(code, level):
    """用 as_of 截断 = 用前缀数据计算，且截断时点已确认的结构在全量结果里保持一致。"""
    cfg, bars = _bars(code, level, 2000)
    cut = 1200
    r_cut = analyze_bars(bars.iloc[:cut], cfg); r_all = analyze_bars(bars, cfg)
    conf_cut = [_key_bi(b) for b in r_cut.bis if b.confirmed]
    conf_all = [_key_bi(b) for b in r_all.bis if b.confirmed]
    assert conf_all[:len(conf_cut)] == conf_cut
