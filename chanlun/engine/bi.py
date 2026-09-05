"""笔（02 文档第 3 节）。

已确认口径（开放问题 6 的裁决，由回放测试验证）：
  构造过程中只有"列表最后一笔"的终点会被延伸，"候选笔"（尚未入列）可能作废。
  一笔一旦有下一笔入列，它的两端就再也不会改变。因此：
  已确认 ⇔ 该笔之后已有一笔**入列**（不含末尾的候选笔）。confirmed_at = 触发下一笔入列的那个分型的成立时间。
  最后入列的一笔（终点可延伸）与候选笔（可作废）为未确认。
"""
from __future__ import annotations
from .models import MergedBar, Fractal, Bi
from ..config import BiConfig

def _more_extreme(a: Fractal, b: Fractal) -> bool:
    """b 是否比 a 更极端（同类型）。"""
    return b.price > a.price if a.kind == "top" else b.price < a.price

def _fx_price_ok(start: Fractal, end: Fractal, mode: str) -> bool:
    top, bot = (start, end) if start.kind == "top" else (end, start)
    if mode in ("strict", "totally"):
        return top.price > bot.range_high and bot.price < top.range_low
    # loss / half：只比较中间 K 线
    return top.price > bot.mid_high and bot.price < top.mid_low

def _distance_ok(start: Fractal, end: Fractal, merged: list[MergedBar], cfg: BiConfig) -> bool:
    d = end.idx - start.idx
    if cfg.mode == "old":
        return d >= 4
    if d < 3:
        return False
    raw_between = merged[end.idx].raw_start - merged[start.idx].raw_end - 1
    return raw_between >= 3

def can_form_bi(start: Fractal, end: Fractal, merged: list[MergedBar], cfg: BiConfig) -> bool:
    if start.kind == end.kind:
        return False
    return _distance_ok(start, end, merged, cfg) and _fx_price_ok(start, end, cfg.fx_check)

def build_bis(merged: list[MergedBar], fractals: list[Fractal], cfg: BiConfig) -> list[Bi]:
    bis: list[Bi] = []
    S: Fractal | None = None   # 候选笔起点
    E: Fractal | None = None   # 候选笔终点
    for fx in fractals:
        if S is None:
            S = fx
            continue
        if E is None:
            if fx.kind == S.kind:
                if _more_extreme(S, fx):
                    S = fx
                    if bis:  # 前一笔延伸
                        bis[-1].end_fx = fx
            elif can_form_bi(S, fx, merged, cfg):
                E = fx
            continue
        # 有完整候选 S→E
        if fx.kind == E.kind:
            if _more_extreme(E, fx):
                E = fx
            continue
        # fx 与 E 异类型（与 S 同类型）
        if can_form_bi(E, fx, merged, cfg):
            if bis:
                bis[-1].confirmed = True
                bis[-1].confirmed_at = fx.known_at
            bis.append(Bi(len(bis), "up" if S.kind == "bottom" else "down", S, E))
            S, E = E, fx
        elif _more_extreme(S, fx):
            # 候选作废，前一笔延伸到 fx
            if bis:
                bis[-1].end_fx = fx
            S, E = fx, None
    if S is not None and E is not None:
        bis.append(Bi(len(bis), "up" if S.kind == "bottom" else "down", S, E, candidate=True))
    return bis
