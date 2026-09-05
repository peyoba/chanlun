"""MACD 与段力度。"""
from __future__ import annotations
import pandas as pd
from ..config import MacdConfig

def compute_macd(bars: pd.DataFrame, cfg: MacdConfig) -> pd.DataFrame:
    c = bars["close"]
    ema_f = c.ewm(span=cfg.fast, adjust=False).mean()
    ema_s = c.ewm(span=cfg.slow, adjust=False).mean()
    dif = ema_f - ema_s
    dea = dif.ewm(span=cfg.signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return pd.DataFrame({"ts": bars["ts"], "dif": dif, "dea": dea, "hist": hist})

def strength(macd: pd.DataFrame, start_raw: int, end_raw: int, direction: str) -> dict[str, float]:
    """段力度：同向 MACD 柱面积、DIF 峰值绝对值。"""
    seg = macd.iloc[start_raw:end_raw + 1]
    h = seg["hist"]
    area = float(h[h > 0].sum()) if direction == "up" else float(-h[h < 0].sum())
    dif = seg["dif"]
    peak = float(dif.max()) if direction == "up" else float(-dif.min())
    return {"area": area, "dif_peak": max(peak, 0.0)}
