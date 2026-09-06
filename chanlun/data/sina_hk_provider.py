"""新浪港股：日线自 2004 年起，前复权因子完整（含拆股）。周线由日线聚合。"""
from __future__ import annotations
from datetime import date
import pandas as pd
from .base import ProviderError, finalize, COLUMNS
from .sina_provider import resample_week
from ..codes import Code
from ..config import Level

class SinaHKProvider:
    name = "sina_hk"

    def supports(self, code: Code, level: Level) -> bool:
        return code.market == "HK" and level in ("D", "W")

    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame:
        import akshare as ak
        try:
            df = ak.stock_hk_daily(symbol=code.symbol, adjust="qfq")
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"sina_hk 拉取失败: {e}") from e
        if df is None or df.empty:
            return pd.DataFrame(columns=COLUMNS)
        df = df.rename(columns={"date": "ts"})
        df["ts"] = pd.to_datetime(df["ts"])
        if "amount" not in df:
            df["amount"] = float("nan")
        if start:
            df = df[df.ts >= pd.Timestamp(start)]
        if end:
            df = df[df.ts <= pd.Timestamp(end)]
        df = finalize(df)
        return resample_week(df) if level == "W" else df

    def get_name(self, code: Code) -> str | None:
        return None
