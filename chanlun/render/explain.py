"""理由文案：简短版 / 教学说明 / 风险。"""
from __future__ import annotations

_NAME = {"1b": "一买", "1s": "一卖", "2b": "二买", "2s": "二卖", "3b": "三买", "3s": "三卖"}
_GRADE = {"strict": "严格", "suspect": "疑似"}
_KIND = {"bi": "笔级", "seg": "段级"}

_TEACH = {
    "1": "第一类买卖点（第 17 / 24 课）：趋势的最后一个中枢之后，离开段与进入段相比出现背驰，说明推动力量衰竭，背驰段的极值点就是一买/一卖。它出现在趋势末端，是三类里位置最好但也最需要背驰确认的一类。",
    "2": "第二类买卖点（第 17 课）：一买之后的第一次上涨结束，随后回调的低点不低于一买低点，这个回调低点即二买。二买的本质是确认一买有效，风险低于一买。",
    "3": "第三类买卖点（第 17 / 20 课）：走势离开中枢后第一次回抽，回抽低点不再回到中枢区间（高于 ZG），说明中枢已被向上突破，这个回抽点是三买。三买是趋势延续的买点。",
}

def explain(bsp, ctx: dict) -> None:
    t = bsp.type[:2]
    name = _NAME.get(t, t)
    head = f"{name}({_KIND[bsp.zs_kind]}, {_GRADE[bsp.grade]})"
    if t[0] == "1":
        dv = ctx["dv"]; zs = ctx["zs"]
        kind = "趋势背驰" if dv.kind == "trend" else "单中枢盘整背驰"
        area = dv.metrics.get("area"); pk = dv.metrics.get("dif_peak")
        parts = [kind]
        if area: parts.append(f"MACD 面积 {area[1]:.1f} {'<' if area[1] < area[0] else '≥'} {area[0]:.1f}")
        if pk: parts.append(f"DIF 峰值 {pk[1]:.2f} {'<' if pk[1] < pk[0] else '≥'} {pk[0]:.2f}")
        parts.append("DIF 已回零轴" if dv.zero_return else "DIF 未回零轴")
        bsp.reason_short = f"{head}：" + "，".join(parts)
    elif t[0] == "2":
        b1 = ctx["bsp1"]; back = ctx["back"]
        bsp.reason_short = f"{head}：{b1.type[:2] and _NAME[b1.type[:2]]}({b1.price:.2f})后回调低点 {back.end_price:.2f} 未破" if t == "2b" else f"{head}：一卖({b1.price:.2f})后反弹高点 {back.end_price:.2f} 未破"
    else:
        zs = ctx["zs"]; back = ctx["back"]
        bsp.reason_short = f"{head}：离开中枢[{zs.zd:.2f}, {zs.zg:.2f}]后回抽{'低点' if t == '3b' else '高点'} {back.end_price:.2f} 未回中枢"
    bsp.teaching = _TEACH[t[0]]
    risks = [c.cond for c in bsp.checklist if c.status == "weak"]
    fails = [c.cond for c in bsp.checklist if c.status == "fail"]
    bsp.risks = [f"勉强满足：{r}" for r in risks] + [f"未满足：{f}" for f in fails]
    if not bsp.confirmed:
        bsp.risks.append("依赖的结构尚未确认，后续 K 线可能改变此信号")
