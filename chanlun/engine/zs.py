"""中枢（02 文档第 5 节）。笔中枢与段中枢共用同一构造器，元素类型不同。

约定
- 中枢首元素方向与进入段相反：进入段向上 → 首元素向下。等价：从元素序列中任一位置 i 起，
  若 i, i+1, i+2 有公共区间（ZG > ZD），且元素 i 的方向与 i-1（进入段）相反，则成立。
- 延伸：后续元素与 [ZD, ZG] 有交集则并入；ZG / ZD 不变，GG / DD 更新。
- 结束：首个完全位于区间外的元素 e 是"回抽段"（它必然与离开方向相反），e 的前一个元素是"离开段"（最后一个与区间重叠、
  并把价格带出区间的元素，不计入中枢元素）。回抽段终点确定（已确认）后，中枢结束才算确认；若回抽段还在延伸中并重新
  进入区间，则它会重叠区间而成为延伸元素——这就是"回抽重新进入视为延伸"的实现方式。
- 已确认：range_confirmed = 前三元素都已确认；end_confirmed = 回抽段已确认。
- 笔中枢不跨线段（cfg.bi_zs_cross_seg=False，默认）：元素序列按线段切分后分别构造，首元素与线段反向；
  中枢的已确认还须所属线段已确认，最后一段之后的尾部中枢一律未确认。
"""
from __future__ import annotations
from typing import Sequence
from .models import Bi, Seg, ZhongShu, MergedBar
from ..config import ZsConfig

def _build(elems: Sequence, kind: str, cfg: ZsConfig, first_dir: str | None = None) -> list[ZhongShu]:
    """first_dir：限定首元素方向（不跨线段模式下 = 所属线段的反方向，对齐 chan.py zs_algo=normal）；
    None 时按"首元素方向与进入段相反"判定。"""
    out: list[ZhongShu] = []
    n = len(elems)
    i = 1  # 首元素至少要有进入段
    while i + 2 < n:
        a, b, c = elems[i], elems[i + 1], elems[i + 2]
        zg = min(a.high, b.high, c.high); zd = max(a.low, b.low, c.low)
        enter = elems[i - 1]
        dir_ok = (a.dir == first_dir) if first_dir is not None else (a.dir != enter.dir)
        if zg > zd and dir_ok:
            zs = ZhongShu(len(out), kind, zg, zd, max(a.high, b.high, c.high), min(a.low, b.low, c.low),
                          [a.id, b.id, c.id], enter.id, None, a.start_raw, c.end_raw)
            zs.range_confirmed = a.confirmed and b.confirmed and c.confirmed
            if zs.range_confirmed:
                zs.range_confirmed_at = max(x.confirmed_at for x in (a, b, c) if x.confirmed_at is not None) if any(x.confirmed_at is not None for x in (a, b, c)) else None
            j = i + 3
            while j < n:
                e = elems[j]
                if e.high >= zd and e.low <= zg:
                    zs.elems.append(e.id); zs.ext_count += 1
                    zs.gg = max(zs.gg, e.high); zs.dd = min(zs.dd, e.low); zs.end_raw = e.end_raw
                    j += 1
                    continue
                # e 完全在区间外：e 是"回抽段"，它前一个元素（最后一个与区间重叠、并把价格带出区间的元素）是离开段
                leave = elems[j - 1]
                zs.leave_id = leave.id
                if leave.id in zs.elems[3:]:
                    zs.elems.remove(leave.id); zs.ext_count -= 1
                    zs.end_raw = elems[j - 2].end_raw
                    zs.gg = max(x.high for x in elems[i:j - 1]); zs.dd = min(x.low for x in elems[i:j - 1])
                zs.ended = True
                zs.end_confirmed = e.confirmed          # 回抽段终点确定后，才能断定它没回到区间
                zs.end_confirmed_at = e.confirmed_at
                zs.back_id = e.id
                break
            else:
                # 元素用尽：最后一个元素仍与区间重叠，中枢延伸中
                pass
            if zs.ext_count + 3 >= cfg.upgrade_hint_after:
                zs.hints.append(f"延伸达 {zs.ext_count + 3} 段，疑似升级")
            if out and out[-1].zd <= zs.zg and zs.zd <= out[-1].zg:
                zs.hints.append("与前一中枢区间重叠，疑似扩展")
            out.append(zs)
            # 下一个中枢从离开段之后开始找（离开段作为进入段）
            i = j if zs.ended else n
        else:
            i += 1
    return out


def _opposite(d: str) -> str:
    return "down" if d == "up" else "up"


def build_bi_zs(bis: list[Bi], segs: list[Seg], cfg: ZsConfig, merged: list[MergedBar] | None = None) -> list[ZhongShu]:
    if cfg.bi_zs_cross_seg or not segs:
        return _build(bis, "bi", cfg)
    out: list[ZhongShu] = []
    for s in segs:
        # 线段内部笔序列：首元素必须与线段反向（上升段内中枢从向下笔开始），线段首笔即进入段
        lo = max(0, s.start_bi - 1)
        sub = _build(bis[lo:s.end_bi + 1], "bi", cfg, first_dir=_opposite(s.dir))
        for z in sub:
            # 中枢按线段切分后，区间 / 结束的"已确认"还须所属线段已确认（线段边界未定时中枢会随之重画）
            if not s.confirmed:
                z.range_confirmed = False; z.range_confirmed_at = None
                z.end_confirmed = False; z.end_confirmed_at = None
            elif z.range_confirmed and s.confirmed_at is not None:
                z.range_confirmed_at = max(z.range_confirmed_at, s.confirmed_at) if z.range_confirmed_at is not None else s.confirmed_at
                if z.end_confirmed:
                    z.end_confirmed_at = max(z.end_confirmed_at, s.confirmed_at) if z.end_confirmed_at is not None else s.confirmed_at
            z.id = len(out); out.append(z)
    # 最后一段之后的尾部笔：视为一段方向相反的、尚未成型的线段（对齐 chan.py 对未成段部分的处理），一律未确认
    last = segs[-1]
    if last.end_bi + 3 < len(bis):
        sub = _build(bis[last.end_bi:], "bi", cfg, first_dir=last.dir)
        for z in sub:
            z.range_confirmed = False; z.range_confirmed_at = None
            z.end_confirmed = False; z.end_confirmed_at = None
            z.id = len(out); out.append(z)
    return out


def build_seg_zs(segs: list[Seg], cfg: ZsConfig, merged: list[MergedBar] | None = None) -> list[ZhongShu]:
    return _build(segs, "seg", cfg)
