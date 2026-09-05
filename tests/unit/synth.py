"""合成 K 线工具：由一串枢轴价构造锯齿 K 线，每两枢轴之间 n 根，K 线无包含。"""
import pandas as pd, numpy as np

def zigzag(pivots, n=5, start="2020-01-01", width=0.3):
    rows = []
    t = pd.Timestamp(start)
    for a, b in zip(pivots, pivots[1:]):
        for k in range(n):
            lo = a + (b - a) * k / n; hi = a + (b - a) * (k + 1) / n
            l, h = min(lo, hi), max(lo, hi)
            rows.append((t, l, h + width, l - width, h))
            t += pd.Timedelta(days=1)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["volume"] = 1.0; df["amount"] = 1.0
    return df

def bars(rows, start="2020-01-01"):
    """rows: [(high, low), ...]"""
    t = pd.Timestamp(start)
    out = []
    for h, l in rows:
        out.append((t, l, h, l, h, 1.0, 1.0)); t += pd.Timedelta(days=1)
    return pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume", "amount"])
