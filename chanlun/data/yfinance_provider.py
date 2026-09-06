"""yfinance：港股日 / 周备源（自动复权）。"""
from __future__ import annotations
from datetime import date
import pandas as pd
from .base import ProviderError, finalize, COLUMNS
from ..codes import Code
from ..config import Level

class YfinanceProvider:
    name = "yfinance"

    def supports(self, code: Code, level: Level) -> bool:
        return code.market == "HK" and level in ("D", "W")

    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame:
        import yfinance as yf
        try:
            h = yf.Ticker(code.yfinance).history(period="max", interval="1d" if level == "D" else "1wk", auto_adjust=True)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"yfinance 拉取失败: {e}") from e
        if h is None or h.empty:
            return pd.DataFrame(columns=COLUMNS)
        df = h.reset_index().rename(columns={"Date": "ts", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None).dt.normalize()
        df["amount"] = float("nan")
        if start:
            df = df[df["ts"] >= pd.Timestamp(start)]
        if end:
            df = df[df["ts"] <= pd.Timestamp(end)]
        return finalize(df)

    def get_name(self, code: Code) -> str | None:
        return None
