"""股票代码归一化。内部格式：600519.SH / 000858.SZ / 00700.HK"""
from __future__ import annotations
import re
from dataclasses import dataclass

class CodeError(ValueError):
    pass

@dataclass(frozen=True)
class Code:
    code: str      # 内部格式
    market: str    # CN | HK

    @property
    def symbol(self) -> str:
        return self.code.split(".")[0]

    @property
    def exchange(self) -> str:
        return self.code.split(".")[1]

    # 各数据源格式
    @property
    def baostock(self) -> str:
        return f"{self.exchange.lower()}.{self.symbol}"

    @property
    def sina(self) -> str:
        return f"{self.exchange.lower()}{self.symbol}"

    @property
    def tencent(self) -> str:
        return f"hk{self.symbol}" if self.market == "HK" else f"{self.exchange.lower()}{self.symbol}"

    @property
    def yfinance(self) -> str:
        return f"{self.symbol.lstrip('0').zfill(4)}.HK"

    def __str__(self) -> str:
        return self.code


def normalize(raw: str) -> Code:
    s = raw.strip().upper().replace(" ", "")
    if not s:
        raise CodeError("代码为空")
    # 港股：带 .HK 或 HK 前缀，或 1~5 位数字
    m = re.fullmatch(r"(?:HK)?(\d{1,5})(?:\.HK)?", s)
    if m and (s.endswith(".HK") or s.startswith("HK") or len(m.group(1)) <= 5):
        return Code(f"{int(m.group(1)):05d}.HK", "HK")
    # A 股
    m = re.fullmatch(r"(?:(SH|SZ)\.?)?(\d{6})(?:\.(SH|SZ))?", s)
    if m:
        num = m.group(2)
        ex = m.group(1) or m.group(3)
        if not ex:
            if num[0] in "69":
                ex = "SH"
            elif num[0] in "03":
                ex = "SZ"
            elif num[0] in "48":
                raise CodeError(f"{num} 为北交所代码，本期不支持")
            else:
                raise CodeError(f"无法判断 {num} 所属交易所")
        return Code(f"{num}.{ex}", "CN")
    raise CodeError(f"无法识别代码：{raw}")
