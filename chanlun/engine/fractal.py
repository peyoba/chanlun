"""分型（02 文档第 2 节）。"""
from __future__ import annotations
from .models import MergedBar, Fractal

def find_fractals(merged: list[MergedBar]) -> list[Fractal]:
    out: list[Fractal] = []
    for i in range(1, len(merged) - 1):
        a, b, c = merged[i - 1], merged[i], merged[i + 1]
        if b.high > a.high and b.high > c.high:
            out.append(Fractal("top", i, b.high, max(a.high, b.high, c.high), min(a.low, b.low, c.low), b.high_raw, b.high_ts if b.high_ts is not None else b.ts, b.high, b.low, c.ts))
        elif b.low < a.low and b.low < c.low:
            out.append(Fractal("bottom", i, b.low, max(a.high, b.high, c.high), min(a.low, b.low, c.low), b.low_raw, b.low_ts if b.low_ts is not None else b.ts, b.high, b.low, c.ts))
    return out
