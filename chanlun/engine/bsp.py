"""三类买卖点（02 文档第 8 节）。grade = 规则满足度：strict / suspect。

一买：下跌趋势（≥2 下跌中枢）最后离开段趋势背驰，背驰段低点；单中枢盘整背驰或疑似背驰 → suspect。
二买：一买之后第一次上涨（一笔/一段）结束后的回调低点 ≥ 一买低点。本级别实现：一买后的第 2 个反向元素终点。
      次级别验证在 assemble 中补充（无低一级 → suspect 并说明）。
三买：中枢向上离开段之后第一次回抽低点 > ZG。严格：段中枢 + 回抽为已确认的一笔；笔中枢或回抽未确认 → suspect。
卖点对称。
"""
from __future__ import annotations
from .models import Bi, Seg, ZhongShu, Divergence, BSP, Check
from ..config import EngineConfig
from ..render.explain import explain

def _elem_seq(kind: str, bis, segs):
    return segs if kind == "seg" else bis

def find_bsps(bars, bis: list[Bi], segs: list[Seg], zs_bi: list[ZhongShu], zs_seg: list[ZhongShu], divs: list[Divergence], cfg: EngineConfig) -> list[BSP]:
    out: list[BSP] = []
    ts = bars["ts"]
    for kind, zss, elems in (("seg", zs_seg, segs), ("bi", zs_bi, bis)):
        by_id = {e.id: e for e in elems}
        # ---- 一买/一卖 ----
        if 1 in cfg.bsp.types:
            for dv in divs:
                # 笔/段各自从 0 编号；必须用「本级别中枢的离开段 == 背驰段」对齐，避免笔级背驰挂到同号线段上
                zs = next((z for z in zss if z.id == dv.zs_id and z.kind == kind), None)
                if zs is None or zs.leave_id != dv.seg_c:
                    continue
                c = by_id.get(dv.seg_c)
                if c is None:
                    continue
                side = "b" if dv.dir == "down" else "s"
                grade = "strict" if (dv.kind == "trend" and dv.grade == "strict" and kind == "seg") else "suspect"
                checks = [
                    Check("趋势成立（≥2 个同向不重叠中枢）", "pass" if dv.kind == "trend" else "fail", dv.kind),
                    Check("MACD 面积背驰", "pass" if "area" in dv.metrics and dv.metrics["area"][1] < dv.metrics["area"][0] else "fail", str(dv.metrics.get("area"))),
                    Check("DIF 峰值背驰", "pass" if "dif_peak" in dv.metrics and dv.metrics["dif_peak"][1] < dv.metrics["dif_peak"][0] else "fail", str(dv.metrics.get("dif_peak"))),
                    Check("a、c 之间 DIF 回抽零轴", "pass" if dv.zero_return else "weak"),
                    Check("基于段中枢", "pass" if kind == "seg" else "weak", kind),
                ]
                bsp = BSP(len(out), f"1{side}", kind, ts.iloc[c.end_raw], c.end_raw, c.end_price, grade, dv.confirmed, dv.confirmed_at,
                          {"zs": dv.zs_id, "div": dv.id, kind: c.id}, "", checks, "", [])
                explain(bsp, {"dv": dv, "zs": zs})
                out.append(bsp)
                # ---- 二买/二卖：一买之后第 2 个反向元素的终点 ----
                if 2 in cfg.bsp.types:
                    seq = elems
                    ci = seq.index(c)
                    if ci + 2 < len(seq):
                        back = seq[ci + 2]  # c 之后：ci+1 反向（第一次上涨），ci+2 回调
                        ok = back.end_price > c.end_price if side == "b" else back.end_price < c.end_price
                        if ok:
                            g2 = "strict" if grade == "strict" and back.confirmed else "suspect"
                            checks2 = [
                                Check("一买/一卖为严格档", "pass" if grade == "strict" else "weak", grade),
                                Check("回调低点不破一买低点" if side == "b" else "反弹高点不破一卖高点", "pass", f"{back.end_price:.2f} vs {c.end_price:.2f}"),
                                Check("回调段已确认", "pass" if back.confirmed else "weak"),
                                Check("次级别验证", "weak", "本级别元素近似；assemble 阶段用低一级复核"),
                            ]
                            bsp2 = BSP(len(out), f"2{side}", kind, ts.iloc[back.end_raw], back.end_raw, back.end_price, g2, back.confirmed, back.confirmed_at,
                                       {"bsp1": bsp.id, kind: back.id}, "", checks2, "", [])
                            explain(bsp2, {"bsp1": bsp, "back": back})
                            out.append(bsp2)
        # ---- 三买/三卖 ----
        if 3 in cfg.bsp.types:
            for zs in zss:
                if zs.leave_id is None:
                    continue
                leave = by_id.get(zs.leave_id); back = by_id.get(zs.back_id) if zs.back_id is not None else None
                if leave is None or back is None:
                    continue
                if leave.dir == "up" and back.low > zs.zg:
                    side = "b"; cond = f"回抽低点 {back.low:.2f} > ZG {zs.zg:.2f}"
                elif leave.dir == "down" and back.high < zs.zd:
                    side = "s"; cond = f"反弹高点 {back.high:.2f} < ZD {zs.zd:.2f}"
                else:
                    continue
                grade = "strict" if kind == "seg" and back.confirmed else "suspect"
                checks = [
                    Check("离开段脱离中枢区间", "pass", f"[{zs.zd:.2f}, {zs.zg:.2f}]"),
                    Check("回抽不回中枢", "pass", cond),
                    Check("基于段中枢", "pass" if kind == "seg" else "weak", kind),
                    Check("回抽已确认", "pass" if back.confirmed else "weak"),
                ]
                bsp = BSP(len(out), f"3{side}", kind, ts.iloc[back.end_raw], back.end_raw, back.end_price, grade, back.confirmed and zs.end_confirmed, back.confirmed_at,
                          {"zs": zs.id, kind: back.id}, "", checks, "", [])
                explain(bsp, {"zs": zs, "back": back, "leave": leave})
                out.append(bsp)
    # 同一位置合并
    merged: dict[int, BSP] = {}
    for b in out:
        if b.raw_idx in merged:
            m = merged[b.raw_idx]
            m.reason_short += " | " + b.reason_short
            m.checklist += b.checklist
            m.type += "+" + b.type
            if b.grade == "strict":
                m.grade = "strict"
        else:
            merged[b.raw_idx] = b
    res = sorted(merged.values(), key=lambda b: b.raw_idx)
    for i, b in enumerate(res):
        b.id = i
    return res
