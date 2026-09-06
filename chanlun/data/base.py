"""数据源抽象。所有 Provider 返回统一 DataFrame：
columns = [ts, open, high, low, close, volume, amount]，ts 为 K 线结束时间（naive 本地时间，日/周线为当日 00:00），升序、无重复。"""
from __future__ import annotations
from datetime import date
from typing import Protocol
import pandas as pd
from ..codes import Code
from ..config import Level

COLUMNS = ["ts", "open", "high", "low", "close", "volume", "amount"]

class ProviderError(RuntimeError):
    pass

class DataProvider(Protocol):
    name: str
    def supports(self, code: Code, level: Level) -> bool: ...
    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame: ...
    def get_name(self, code: Code) -> str | None: ...

def finalize(df: pd.DataFrame) -> pd.DataFrame:
    """统一列、类型、排序、去重。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = df[COLUMNS].copy()
    df["ts"] = pd.to_datetime(df["ts"])
    for c in COLUMNS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[df["high"] > 0]
    df = df.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
    return df
