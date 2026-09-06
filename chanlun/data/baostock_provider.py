"""baostock：A 股 5/30 分、日、周，前复权。分钟线 time 字段即 K 线结束时间。"""
from __future__ import annotations
from datetime import date
import pandas as pd
from .base import ProviderError, finalize, COLUMNS
from .sina_provider import resample_week
from ..codes import Code
from ..config import Level

_FREQ = {"5m": "5", "30m": "30", "D": "d", "W": "w"}

class BaostockProvider:
    name = "baostock"

    def __init__(self):
        self._bs = None

    def _login(self):
        if self._bs is None:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != "0":
                raise ProviderError(f"baostock 登录失败: {lg.error_msg}")
            self._bs = bs
        return self._bs

    def supports(self, code: Code, level: Level) -> bool:
        return code.market == "CN"

    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame:
        if level == "W":
            # baostock 周线与其日线前复权偶有不一致（如 600519 2015-01-09 周 low），统一由日线聚合
            return resample_week(self.get_klines(code, "D", start, end))
        bs = self._login()
        freq = _FREQ[level]
        minute = level in ("5m", "30m")
        fields = "date,time,open,high,low,close,volume,amount" if minute else "date,open,high,low,close,volume,amount"
        rs = bs.query_history_k_data_plus(
            code.baostock, fields,
            start_date=(start or date(1990, 1, 1)).isoformat(),
            end_date=(end or date.today()).isoformat(),
            frequency=freq, adjustflag="2",
        )
        if rs.error_code != "0":
            raise ProviderError(f"baostock 查询失败: {rs.error_msg}")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(rows, columns=rs.fields)
        if minute:
            # time: YYYYMMDDHHMMSSfff，为 K 线结束时间
            df["ts"] = pd.to_datetime(df["time"].str[:14], format="%Y%m%d%H%M%S")
        else:
            df["ts"] = pd.to_datetime(df["date"])
        df = df.replace("", pd.NA)
        return finalize(df)

    def get_name(self, code: Code) -> str | None:
        bs = self._login()
        rs = bs.query_stock_basic(code=code.baostock)
        if rs.error_code == "0" and rs.next():
            return rs.get_row_data()[1]
        return None
