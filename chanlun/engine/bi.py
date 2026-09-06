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

def _not_weaker(a: Fractal, b: Fractal) -> bool:
    """b 不弱于 a（同类型；等价时取后出现者，对齐 chan.py 的 >= 延伸口径）。"""
    return b.price >= a.price if a.kind == "top" else b.price <= a.price

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
    """按 02 §3.4 遍历分型构造笔。

    端点极值约束（对齐 chan.py `bi_end_is_peak`，2026-09-05 交叉验证后补入）：
      X = 候选起点 S 之后出现过的、与 S 异类型的最极端分型（哪怕它离 S 太近不够成笔）。
          终点 E 必须不弱于 X，否则笔内会出现比终点更极端的 K 线。
      Y = 候选终点 E 之后出现过的、与 S 同类型的最极端分型。下一笔的终点必须不弱于 Y。
    候选作废例外：fx 比 S 更极端但与 E 不够成笔时，若 E 已超过前一笔起点则不作废（否则前一笔起点不再是极值），fx 挂起。
    """
    bis: list[Bi] = []
    S: Fractal | None = None   # 候选笔起点
    E: Fractal | None = None   # 候选笔终点
    X: Fractal | None = None   # S 之后异类型分型的极值（终点须不弱于它）
    Y: Fractal | None = None   # E 之后同 S 类型分型的极值（下一终点须不弱于它）
    for fx in fractals:
        if S is None:
            S = fx
            continue
        if E is None:
            if fx.kind == S.kind:
                if _not_weaker(S, fx):
                    S, X = fx, None
                    if bis:  # 前一笔延伸
                        bis[-1].end_fx = fx
            elif X is None or not _more_extreme(fx, X):
                # fx 是 S 之后同类分型中的新极值，才有资格做终点
                X = fx
                if can_form_bi(S, fx, merged, cfg):
                    E, Y = fx, None
            continue
        # 有完整候选 S→E
        if fx.kind == E.kind:
            if _not_weaker(E, fx):
                E, Y = fx, None
            continue
        # fx 与 E 异类型（与 S 同类型）
        peak_ok = Y is None or not _more_extreme(fx, Y)
        if peak_ok:
            Y = fx
        if peak_ok and can_form_bi(E, fx, merged, cfg):
            if bis:
                bis[-1].confirmed = True
                bis[-1].confirmed_at = fx.known_at
            bis.append(Bi(len(bis), "up" if S.kind == "bottom" else "down", S, E))
            S, E, X, Y = E, fx, None, None
        elif _more_extreme(S, fx):
            if bis and _more_extreme(bis[-1].start_fx, E):
                # 例外（对齐 chan.py bi_allow_sub_peak=False）：候选终点 E 已超过前一笔起点，作废会让前一笔内部
                # 出现比起点更极端的 K 线，故不作废；fx 挂起（记入 Y），等待更远的同向分型成笔或 E 继续延伸。
                continue
            # 候选作废，前一笔延伸到最极端的挂起分型（02 §3.4.3）
            tgt = Y if (Y is not None and _more_extreme(fx, Y)) else fx
            if bis:
                bis[-1].end_fx = tgt
            S, E, X, Y = tgt, None, None, None
    if S is not None and E is not None:
        bis.append(Bi(len(bis), "up" if S.kind == "bottom" else "down", S, E, candidate=True))
    return bis
