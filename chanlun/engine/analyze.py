"""单级别分析编排：只用本级别 K 线，不访问其他级别。"""
from __future__ import annotations
from datetime import datetime
from typing import Any
import pandas as pd
from ..config import AppConfig, Level
from ..data.store import Store, data_hash
from .models import LevelResult
from .klines import merge_klines
from .fractal import find_fractals
from .bi import build_bis

def analyze_bars(bars: pd.DataFrame, cfg: AppConfig, meta: dict[str, Any] | None = None) -> LevelResult:
    """对给定 K 线（已按 ts 升序）做全链路计算。M1：包含处理 → 分型 → 笔 → 笔中枢。"""
    bars = bars.reset_index(drop=True)
    merged = merge_klines(bars)
    fractals = find_fractals(merged)
    bis = build_bis(merged, fractals, cfg.engine.bi)
    from .zs import build_bi_zs
    from .seg import build_segs
    segs = build_segs(bis, merged) if len(bis) >= 3 else []
    zs_bi = build_bi_zs(bis, segs, cfg.engine.zs, merged)
    from .zs import build_seg_zs
    zs_seg = build_seg_zs(segs, cfg.engine.zs, merged) if segs else []
    from .macd import compute_macd
    macd = compute_macd(bars, cfg.engine.macd)
    from .divergence import find_divergences
    from .trend import classify_trend
    trend = classify_trend(zs_seg, zs_bi)
    divergences = find_divergences(segs, zs_seg, bis, zs_bi, macd, bars, cfg.engine.divergence)
    from .bsp import find_bsps
    bsps = find_bsps(bars, bis, segs, zs_bi, zs_seg, divergences, cfg.engine)
    m = dict(meta or {})
    m.update(config_hash=cfg.engine.hash(), data_hash=data_hash(bars), bars=len(bars),
             first_ts=bars.ts.iloc[0] if len(bars) else None, last_ts=bars.ts.iloc[-1] if len(bars) else None)
    return LevelResult(m, bars, merged, fractals, bis, segs, zs_bi, zs_seg, macd, divergences, bsps, trend)

def analyze_level(code: str, level: Level, cfg: AppConfig, *, as_of: datetime | None = None, store: Store | None = None) -> LevelResult:
    own = store is None
    store = store or Store(cfg.db_path)
    bars = store.load_klines(code, level, as_of=as_of)
    name = store.get_name(code) or ""
    log = store.get_log(code, level) or {}
    if own:
        store.close()
    if bars.empty:
        raise ValueError(f"{code} {level} 无本地数据，请先 chan update {code}")
    meta = {"code": code, "name": name, "level": level, "as_of": as_of, "data_updated_at": log.get("updated_at"), "stale": log.get("status") == "error"}
    return analyze_bars(bars, cfg, meta)
