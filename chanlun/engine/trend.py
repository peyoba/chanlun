"""走势类型（02 文档第 6 节）。"""
from __future__ import annotations
from .models import ZhongShu

def classify_trend(zs_seg: list[ZhongShu], zs_bi: list[ZhongShu]) -> dict:
    def _run(zss: list[ZhongShu]) -> dict:
        if not zss:
            return {"type": "none", "zs_count": 0, "dir": None}
        # 从最后一个中枢向前找同向不重叠序列
        last = zss[-1]
        count = 1; d = None
        for prev in reversed(zss[:-1]):
            nxt = zss[zss.index(prev) + 1]
            if nxt.zd > prev.zg and d in (None, "up"):
                d = "up"; count += 1
            elif nxt.zg < prev.zd and d in (None, "down"):
                d = "down"; count += 1
            else:
                break
        t = "trend" if count >= 2 else "range"
        return {"type": t, "zs_count": count, "dir": d, "last_zs": last.id}
    return {"seg": _run(zs_seg), "bi": _run(zs_bi)}
