"""K 线包含处理（02 文档第 1 节）。"""
from __future__ import annotations
import pandas as pd
from .models import MergedBar

def merge_klines(bars: pd.DataFrame) -> list[MergedBar]:
    highs = bars["high"].to_numpy(); lows = bars["low"].to_numpy(); ts = bars["ts"].tolist()
    n = len(bars)
    out: list[MergedBar] = []
    i = 0
    # 开头若前两根就包含，丢弃到第一对无包含的相邻 K 线（02 §1 取舍）
    while i + 1 < n and _contains(highs[i], lows[i], highs[i + 1], lows[i + 1]):
        i += 1
    if i >= n:
        return out
    out.append(MergedBar(0, float(highs[i]), float(lows[i]), None, i, i, ts[i], i, i))
    for j in range(i + 1, n):
        last = out[-1]
        h, l = float(highs[j]), float(lows[j])
        if _contains(last.high, last.low, h, l):
            # 方向由 last 相对其前一根决定
            if len(out) >= 2:
                prev = out[-2]
                d = "up" if last.high > prev.high else "down"
            else:
                d = "up"  # 无前一根时默认向上（只影响序列最前端）
            if d == "up":
                nh, nl = max(last.high, h), max(last.low, l)
                high_raw = last.high_raw if last.high >= h else j
                low_raw = last.low_raw if last.low >= l else j
            else:
                nh, nl = min(last.high, h), min(last.low, l)
                high_raw = last.high_raw if last.high <= h else j
                low_raw = last.low_raw if last.low <= l else j
            out[-1] = MergedBar(last.idx, nh, nl, d, last.raw_start, j, ts[j], high_raw, low_raw)
        else:
            d = "up" if h > last.high else "down"
            out.append(MergedBar(len(out), h, l, d, j, j, ts[j], j, j))
    return out

def _contains(h1, l1, h2, l2) -> bool:
    return (h1 >= h2 and l1 <= l2) or (h1 <= h2 and l1 >= l2)
