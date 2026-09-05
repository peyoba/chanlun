"""线段：标准特征序列法（02 文档第 4 节）。

- 向上线段的特征序列元素 = 其中的向下笔，区间 [low, high]；向下线段对称。
- 候选终点 P = 目前最极端的同向笔终点（笔 p）。e1 = 笔 p+1。e0 = p 之前的特征元素经包含处理后的最后一个。
  e0 与 e1 之间不做包含处理；e1 之后的元素先与 e1 按线段方向做包含合并。
- 出现分型（某元素 e2 弱于 e1）：
  - 第一种情况（e0、e1 无缺口）：线段在 p 结束，立即确认，confirmed_at = e2 所在笔的终点分型成立时间。
  - 第二种情况（有缺口）：需从 P 出发的反向线段的特征序列出现分型才确认；确认前若同向笔越过 P，则候选作废、线段延续。
- 最后一段：pending（无分型）或 case2 等待确认。

已确认口径（由回放测试验证）：线段 k 已确认 ⇔
  (a) 其结束分型成立（case1 / case2 已获反向确认）且触发确认的那一笔已确认（不会作废）；
  (b) 线段 k+1 已至少有 3 笔且第 3 笔已确认（否则若反向笔越过线段 k 终点，k 并未结束——见 build_segs 的回退重扫）。
  一旦某段未确认，其后所有段均未确认。confirmed_at = (a)(b) 两条件中较晚满足的时间。
"""
from __future__ import annotations
from dataclasses import dataclass
from .models import Bi, Seg, MergedBar

@dataclass
class _Elem:
    low: float
    high: float
    bi: int

def _elem(b: Bi) -> _Elem:
    return _Elem(b.low, b.high, b.id)

def _contained(a: _Elem, b: _Elem) -> bool:
    return (a.high >= b.high and a.low <= b.low) or (a.high <= b.high and a.low >= b.low)

def _combine(a: _Elem, b: _Elem, d: str) -> _Elem:
    return _Elem(max(a.low, b.low), max(a.high, b.high), a.bi) if d == "up" else _Elem(min(a.low, b.low), min(a.high, b.high), a.bi)

def _push(elems: list[_Elem], e: _Elem, d: str) -> None:
    if elems and _contained(elems[-1], e):
        elems[-1] = _combine(elems[-1], e, d)
    else:
        elems.append(e)

def _ext(b: Bi, d: str) -> float:
    return b.high if d == "up" else b.low

def _beyond(x: float, p: float, d: str) -> bool:
    return x >= p if d == "up" else x <= p

def _weaker(e: _Elem, e1: _Elem, d: str) -> bool:
    return e.high < e1.high if d == "up" else e.low > e1.low

def _gap(e0: _Elem, e1: _Elem, d: str) -> bool:
    return e1.low > e0.high if d == "up" else e1.high < e0.low


def _scan(bis: list[Bi], start: int, breach: tuple[float, str] | None, nested: bool, min_end: int):
    """从 start 起扫描方向为 bis[start].dir 的线段。
    breach   (价位, 方向)：反向笔越过该价位时返回 breach_j。顶层调用时是前一线段终点（只在本段不足 3 笔时生效）；
             nested（第二种情况的反向段）时是原线段候选终点 P（任何时候生效）。
    min_end  终点笔索引下限：p < min_end 时出现的分型忽略（保证 ≥3 笔；重扫时跳过已被否定的分型）。
    返回 (p, case, conf_j, breach_j)。
    """
    d = bis[start].dir
    n = len(bis)
    left: list[_Elem] = []
    p, P = start, _ext(bis[start], d)
    e1: _Elem | None = None
    j = start + 1
    while j < n:
        b = bis[j]
        if b.dir == d:
            if _beyond(_ext(b, d), P, d):
                if e1 is not None:
                    _push(left, e1, d)
                p, P, e1 = j, _ext(b, d), None
            j += 1
            continue
        # 反向笔
        if breach is not None and (nested or p < start + 2) and _beyond(_ext(b, breach[1]), breach[0], breach[1]):
            return None, "pending", None, j
        if j == p + 1:
            e1 = _elem(b); j += 1; continue
        if e1 is None:
            _push(left, _elem(b), d); j += 1; continue
        e = _elem(b)
        if _contained(e1, e):
            e1 = _combine(e1, e, d); j += 1; continue
        if not _weaker(e, e1, d):
            j += 1; continue
        # 分型成立
        if p < min_end:
            # 不足 3 笔或已被否定：忽略此分型，e1 并入左侧，e 成为新 e1 候选的左侧
            _push(left, e1, d); _push(left, e, d); e1 = None
            j += 1; continue
        e0 = left[-1] if left else None
        if nested or e0 is None or not _gap(e0, e1, d):
            return p, "case1", j, None
        # 第二种情况
        rp, rcase, rconf, rbreach = _scan(bis, p + 1, (P, d), True, p + 3)
        if rbreach is not None:
            _push(left, e1, d)
            for k in range(p + 2, rbreach):
                if bis[k].dir != d:
                    _push(left, _elem(bis[k]), d)
            p, P, e1 = rbreach, _ext(bis[rbreach], d), None
            j = rbreach + 1
            continue
        if rp is not None:
            return p, "case2", rconf, None
        return p, "case2", None, None
    return None, "pending", None, None


def build_segs(bis: list[Bi], merged: list[MergedBar] | None = None) -> list[Seg]:
    n = len(bis)
    segs: list[Seg] = []
    if n < 3:
        return segs
    start = 0
    while start + 2 < n:
        a, c = bis[start], bis[start + 2]
        if max(a.low, c.low) < min(a.high, c.high):
            break
        start += 1
    else:
        return segs
    min_end = start + 2
    guard = 0
    confs: list[int | None] = []
    while start < n and guard < 10 * n:
        guard += 1
        d = bis[start].dir
        prev = segs[-1] if segs else None
        breach = (prev.end_price, prev.dir) if prev else None
        p, case, conf, bj = _scan(bis, start, breach, False, min_end)
        if bj is not None and prev is not None:
            segs.pop(); confs.pop()
            start, min_end = prev.start_bi, bj
            continue
        if p is None:
            p = _best(bis, start, d)
            segs.append(Seg(len(segs), d, start, p, bis[start].start_fx, bis[p].end_fx, "pending", False, None)); confs.append(None)
            break
        segs.append(Seg(len(segs), d, start, p, bis[start].start_fx, bis[p].end_fx, case, False, None)); confs.append(conf)
        if conf is None:
            break
        start = p + 1
        min_end = start + 2
    # 确认标记
    for k, sg in enumerate(segs):
        conf = confs[k]
        ok = conf is not None and bis[conf].confirmed
        nxt_third = None
        if ok and k + 1 < len(segs):
            nxt = segs[k + 1]
            nxt_third = nxt.start_bi + 2
            ok = nxt.end_bi >= nxt_third and nxt_third < n and bis[nxt_third].confirmed
        else:
            ok = False
        if not ok:
            break
        sg.confirmed = True
        times = [t for t in (bis[conf].confirmed_at, bis[nxt_third].confirmed_at) if t is not None]
        sg.confirmed_at = max(times) if times else None
    return segs


def _best(bis: list[Bi], start: int, d: str) -> int:
    p, P = start, _ext(bis[start], d)
    for j in range(start + 2, len(bis), 2):
        if _beyond(_ext(bis[j], d), P, d):
            p, P = j, _ext(bis[j], d)
    return p
