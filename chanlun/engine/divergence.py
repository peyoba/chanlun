"""背驰（02 文档第 7 节）。

- 趋势背驰：趋势中最后中枢的离开段 c 与进入段 a 比较（中间有中枢 B），c 创新高/新低且力度弱于 a。
- 盘整背驰：单中枢，离开段弱于进入段。
- 严格：area 与 dif_peak 两项同时背驰，且 a、c 之间 DIF 回抽零轴（|DIF| ≤ zero_band）；疑似：仅一项或未回零轴。
在段中枢（元素为线段）与笔中枢（元素为笔）上各跑一遍。
"""
from __future__ import annotations
import pandas as pd
from .models import Bi, Seg, ZhongShu, Divergence
from .macd import strength
from ..config import DivergenceConfig

def _zero_return(macd: pd.DataFrame, a_end: int, c_start: int, band: float) -> bool:
    seg = macd["dif"].iloc[a_end:c_start + 1]
    return bool((seg.abs() <= band).any()) if len(seg) else False

def _one(elems, zss: list[ZhongShu], macd: pd.DataFrame, cfg: DivergenceConfig, start_id: int, kind_prefix: str) -> list[Divergence]:
    out: list[Divergence] = []
    by_id = {e.id: e for e in elems}
    dif_scale = float(macd["dif"].abs().quantile(0.9)) if len(macd) else 1.0
    band = cfg.zero_band if cfg.zero_band is not None else dif_scale * cfg.zero_band_ratio
    for k, zs in enumerate(zss):
        if zs.enter_id is None or zs.leave_id is None:
            continue
        a = by_id.get(zs.enter_id); c = by_id.get(zs.leave_id)
        if a is None or c is None or a.dir != c.dir:
            continue
        d = c.dir
        # c 必须创新高 / 新低（相对 a）
        if d == "up" and not c.high > a.high:
            continue
        if d == "down" and not c.low < a.low:
            continue
        # 趋势 or 盘整：前一中枢是否同向不重叠
        trend = k > 0 and ((d == "up" and zs.zd > zss[k - 1].zg) or (d == "down" and zs.zg < zss[k - 1].zd))
        sa = strength(macd, a.start_raw, a.end_raw, d); sc = strength(macd, c.start_raw, c.end_raw, d)
        hits = [m for m in cfg.metrics if sc[m] < sa[m]]
        if not hits:
            continue
        zr = _zero_return(macd, a.end_raw, c.start_raw, band)
        grade = "strict" if len(hits) == len(cfg.metrics) and zr else "suspect"
        confirmed = a.confirmed and c.confirmed
        out.append(Divergence(start_id + len(out), "trend" if trend else "range", d, a.id, c.id, zs.id,
                              {m: (round(sa[m], 4), round(sc[m], 4)) for m in cfg.metrics}, zr, grade, confirmed,
                              c.confirmed_at if confirmed else None, c.end_raw, c.end_price))
    return out

def find_divergences(segs: list[Seg], zs_seg: list[ZhongShu], bis: list[Bi], zs_bi: list[ZhongShu], macd: pd.DataFrame, bars, cfg: DivergenceConfig) -> list[Divergence]:
    out = _one(segs, zs_seg, macd, cfg, 0, "seg")
    out += _one(bis, zs_bi, macd, cfg, len(out), "bi")
    return out
