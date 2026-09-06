"""引擎数据模型。所有结构带 confirmed（是否已确认）与 confirmed_at（确认时间，即满足确认条件的那根原始 K 线时间戳）。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal, Any
import pandas as pd

Dir = Literal["up", "down"]

@dataclass
class MergedBar:
    idx: int            # 合并 K 线序号
    high: float
    low: float
    dir: Dir | None     # 合并方向（首根为 None）
    raw_start: int      # 原始 K 线起始索引
    raw_end: int        # 原始 K 线结束索引（含）
    ts: pd.Timestamp    # 取 raw_end 的时间戳
    # 极值所在原始 K 线索引与时间（用于绘图定位、分型发生时间）
    high_raw: int = -1
    low_raw: int = -1
    high_ts: pd.Timestamp | None = None
    low_ts: pd.Timestamp | None = None

@dataclass
class Fractal:
    kind: Literal["top", "bottom"]
    idx: int            # 中间 K 线的合并索引
    price: float        # 顶取 high，底取 low
    range_high: float   # 三根 K 线整体最高
    range_low: float    # 三根 K 线整体最低
    raw_idx: int        # 极值所在原始 K 线索引
    ts: pd.Timestamp    # 极值发生时间
    mid_high: float = 0.0   # 中间 K 线 high
    mid_low: float = 0.0    # 中间 K 线 low
    known_at: pd.Timestamp | None = None  # 分型成立时间（第三根 K 线结束）

@dataclass
class Bi:
    id: int
    dir: Dir
    start_fx: Fractal
    end_fx: Fractal
    confirmed: bool = False
    confirmed_at: pd.Timestamp | None = None
    candidate: bool = False     # 末尾候选笔（尚未正式入列，可能作废）

    @property
    def high(self) -> float:
        return max(self.start_fx.price, self.end_fx.price)

    @property
    def low(self) -> float:
        return min(self.start_fx.price, self.end_fx.price)

    @property
    def start_idx(self) -> int:
        return self.start_fx.idx

    @property
    def end_idx(self) -> int:
        return self.end_fx.idx

    @property
    def start_raw(self) -> int:
        return self.start_fx.raw_idx

    @property
    def end_raw(self) -> int:
        return self.end_fx.raw_idx

    @property
    def start_price(self) -> float:
        return self.start_fx.price

    @property
    def end_price(self) -> float:
        return self.end_fx.price

    @property
    def merged_count(self) -> int:
        return self.end_idx - self.start_idx + 1

@dataclass
class Seg:
    id: int
    dir: Dir
    start_bi: int       # Bi.id
    end_bi: int
    start_fx: Fractal
    end_fx: Fractal
    end_case: Literal["case1", "case2", "pending"] = "pending"
    confirmed: bool = False
    confirmed_at: pd.Timestamp | None = None

    @property
    def high(self) -> float:
        return max(self.start_fx.price, self.end_fx.price)

    @property
    def low(self) -> float:
        return min(self.start_fx.price, self.end_fx.price)

    @property
    def start_raw(self) -> int:
        return self.start_fx.raw_idx

    @property
    def end_raw(self) -> int:
        return self.end_fx.raw_idx

    @property
    def start_price(self) -> float:
        return self.start_fx.price

    @property
    def end_price(self) -> float:
        return self.end_fx.price

    @property
    def bi_count(self) -> int:
        return self.end_bi - self.start_bi + 1

@dataclass
class ZhongShu:
    id: int
    kind: Literal["bi", "seg"]
    zg: float
    zd: float
    gg: float
    dd: float
    elems: list[int]            # 元素 id（Bi.id 或 Seg.id）
    enter_id: int | None        # 进入段 id
    leave_id: int | None        # 离开段 id
    start_raw: int
    end_raw: int
    back_id: int | None = None  # 回抽段 id（首个完全在区间外的元素）
    ext_count: int = 0          # 延伸次数（超出前三元素的元素数）
    range_confirmed: bool = False
    range_confirmed_at: pd.Timestamp | None = None
    ended: bool = False
    end_confirmed: bool = False
    end_confirmed_at: pd.Timestamp | None = None
    hints: list[str] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.range_confirmed

@dataclass
class Divergence:
    id: int
    kind: Literal["trend", "range"]
    dir: Dir                 # 背驰段方向
    seg_a: int               # 比较段 a（进入段）id
    seg_c: int               # 背驰段 c（离开段）id
    zs_id: int
    metrics: dict[str, Any]  # {area: (a, c), dif_peak: (a, c)}
    zero_return: bool
    grade: Literal["strict", "suspect"]
    confirmed: bool
    confirmed_at: pd.Timestamp | None
    raw_idx: int
    price: float

@dataclass
class Check:
    cond: str
    status: Literal["pass", "fail", "weak"]
    value: str = ""

@dataclass
class BSP:
    id: int
    type: str                # 1b 2b 3b 1s 2s 3s 2b_like 2s_like
    zs_kind: Literal["bi", "seg"]
    ts: pd.Timestamp
    raw_idx: int
    price: float
    grade: Literal["strict", "suspect"]
    confirmed: bool
    confirmed_at: pd.Timestamp | None
    refs: dict[str, Any]
    reason_short: str
    checklist: list[Check]
    teaching: str
    risks: list[str]

    def summary(self) -> str:
        return f"{self.ts.date()} {self.reason_short}"

@dataclass
class LevelResult:
    meta: dict[str, Any]
    bars: pd.DataFrame
    merged: list[MergedBar]
    fractals: list[Fractal]
    bis: list[Bi]
    segs: list[Seg]
    zs_bi: list[ZhongShu]
    zs_seg: list[ZhongShu]
    macd: pd.DataFrame | None
    divergences: list[Divergence]
    bsps: list[BSP]
    trend: dict[str, Any]

@dataclass
class AnalysisResult(LevelResult):
    projection: dict[str, Any] = field(default_factory=dict)

def _ser(o):
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if isinstance(o, pd.DataFrame):
        return o.assign(ts=o.ts.astype(str)).to_dict("records")
    if hasattr(o, "__dataclass_fields__"):
        d = {k: _ser(getattr(o, k)) for k in o.__dataclass_fields__}
        for extra in ("high", "low", "start_raw", "end_raw", "start_price", "end_price"):
            if hasattr(o, extra) and extra not in d:
                d[extra] = getattr(o, extra)
        return d
    if isinstance(o, (list, tuple)):
        return [_ser(x) for x in o]
    if isinstance(o, dict):
        return {k: _ser(v) for k, v in o.items()}
    return o

def to_json_dict(res: LevelResult) -> dict:
    return _ser(res)
