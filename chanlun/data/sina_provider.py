"""新浪：A 股日线（2001 起）、分钟线（5 分约 2 个月、30 分约 1 年），前复权。用作 A 股备源与盘中补数。"""
from __future__ import annotations
from datetime import date
import pandas as pd
from .base import ProviderError, finalize, COLUMNS
from ..codes import Code
from ..config import Level

class SinaProvider:
    name = "sina"

    def supports(self, code: Code, level: Level) -> bool:
        return code.market == "CN"

    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame:
        import akshare as ak
        try:
            if level in ("D", "W"):
                df = ak.stock_zh_a_daily(symbol=code.sina, adjust="qfq",
                                         start_date=(start or date(1990, 1, 1)).strftime("%Y%m%d"),
                                         end_date=(end or date.today()).strftime("%Y%m%d"))
                df = df.rename(columns={"date": "ts"})
                if "amount" not in df:
                    df["amount"] = float("nan")
                df["ts"] = pd.to_datetime(df["ts"])
                df = finalize(df)
                if level == "W":
                    df = resample_week(df)
                return df
            period = {"5m": "5", "30m": "30"}[level]
            df = ak.stock_zh_a_minute(symbol=code.sina, period=period, adjust="qfq")
            df = df.rename(columns={"day": "ts"})
            df["amount"] = float("nan")
            df["ts"] = pd.to_datetime(df["ts"])
            return finalize(df)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"sina 拉取失败: {e}") from e

    def get_name(self, code: Code) -> str | None:
        return None


def suggest_equities(query: str) -> list[tuple[str, str]]:
    """新浪联想：A 股 / 港股名称 → [(内部代码, 名称)]。基金等类型丢掉。"""
    import requests
    from urllib.parse import quote
    from ..codes import normalize, CodeError

    q = (query or "").strip()
    if not q:
        return []
    try:
        r = requests.get(
            f"https://suggest3.sinajs.cn/suggest/type=11,31&key={quote(q)}",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0 Safari/537.36"},
            timeout=8,
        )
        r.raise_for_status()
        txt = r.content.decode("gbk", errors="ignore")
    except Exception:  # noqa: BLE001
        return []
    body = txt.split('="', 1)[-1].rstrip('";\r\n')
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in body.split(";"):
        parts = item.split(",")
        if len(parts) < 4 or parts[1] not in ("11", "31"):
            continue
        name, typ, num, symbol = parts[0], parts[1], parts[2], parts[3]
        raw = symbol if len(symbol) >= 6 else (f"{num}.HK" if typ == "31" else num)
        try:
            code = normalize(raw).code
        except CodeError:
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append((code, name))
    return out


def resample_week(df: pd.DataFrame) -> pd.DataFrame:
    """日线聚合为周线，ts 取该周最后一个交易日。"""
    if df.empty:
        return df
    g = df.set_index("ts").groupby(pd.Grouper(freq="W-FRI"))
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), amount=("amount", "sum"))
    last_ts = df.set_index("ts").groupby(pd.Grouper(freq="W-FRI")).apply(lambda x: x.index.max())
    out["ts"] = last_ts
    out = out.dropna(subset=["open"]).reset_index(drop=True)
    return finalize(out)
