"""与 chan.py（Vespa314）交叉验证。

把本地 SQLite 里同一份 K 线同时喂给本项目引擎与 chan.py，比较：
  - 笔端点（时间 + 价格）        → 目标一致率 ≥ 95%（SPEC 成功标准）
  - 线段端点（时间 + 价格）      → 目标 ≥ 90%
  - 笔中枢区间（ZG / ZD + 时间重叠）→ 目标 ≥ 90%
  - 段中枢区间                  → 参考
  - 买卖点（同一根 K 线）         → 仅参考对照，不设阈值

一致率定义（对称）：2 × 匹配数 / (我方数量 + chan.py 数量)。
"已确认"口径：我方 confirmed=True 的结构 / chan.py is_sure=True 的结构；末端未确认结构两边算法天然不同，单独列出。

用法（需先 `git clone https://github.com/Vespa314/chan.py.git tests/crossval/chan.py` 并 checkout BASELINE.md 里的 commit）：
  .venv/bin/python tests/crossval/run.py 600519 -l D
  .venv/bin/python tests/crossval/run.py --all -l D,W --report docs/reports/交叉验证报告.md
  .venv/bin/chan verify 600519 -l D
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHANPY_DIR = HERE / "chan.py"
BASELINE_COMMIT = "429d6ed3043e27c93a003ba2b10e70a05575e1f5"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chanlun.config import AppConfig, Level, load_config  # noqa: E402
from chanlun.data.store import Store, data_hash  # noqa: E402
from chanlun.engine.analyze import analyze_bars  # noqa: E402
from chanlun.engine.models import LevelResult  # noqa: E402

PRICE_TOL = 1e-6


# ----------------------------------------------------------------------------
# chan.py 加载与数据注入
# ----------------------------------------------------------------------------
_chanpy: dict[str, Any] = {}


def load_chanpy() -> dict[str, Any]:
    """把 chan.py 仓库根目录加入 sys.path 并导入所需模块（只做一次）。"""
    if _chanpy:
        return _chanpy
    if not (CHANPY_DIR / "Chan.py").exists():
        raise RuntimeError(
            f"未找到 chan.py 基准库：{CHANPY_DIR}\n"
            f"请执行：git clone https://github.com/Vespa314/chan.py.git {CHANPY_DIR} && "
            f"git -C {CHANPY_DIR} checkout {BASELINE_COMMIT}"
        )
    if str(CHANPY_DIR) not in sys.path:
        sys.path.insert(0, str(CHANPY_DIR))
    from Chan import CChan  # type: ignore
    from ChanConfig import CChanConfig  # type: ignore
    from Common.CEnum import BSP_TYPE, DATA_FIELD, KL_TYPE  # type: ignore
    from Common.CTime import CTime  # type: ignore
    from DataAPI.CommonStockAPI import CCommonStockApi  # type: ignore
    from KLine.KLine_Unit import CKLine_Unit  # type: ignore

    _chanpy.update(CChan=CChan, CChanConfig=CChanConfig, KL_TYPE=KL_TYPE, DATA_FIELD=DATA_FIELD,
                   CTime=CTime, CCommonStockApi=CCommonStockApi, CKLine_Unit=CKLine_Unit, BSP_TYPE=BSP_TYPE)
    return _chanpy


LEVEL_MAP = {"5m": "K_5M", "30m": "K_30M", "D": "K_DAY", "W": "K_WEEK"}


def _frames_registry() -> dict:
    return _chanpy.setdefault("frames", {})


def _make_store_api():
    """构造从 DataFrame 读数的 chan.py 数据源类（类级注册表按 code 取帧）。"""
    if "StoreAPI" in _chanpy:
        return _chanpy["StoreAPI"]
    cp = load_chanpy()
    CCommonStockApi, CKLine_Unit, CTime, DATA_FIELD = cp["CCommonStockApi"], cp["CKLine_Unit"], cp["CTime"], cp["DATA_FIELD"]

    class StoreAPI(CCommonStockApi):  # type: ignore[misc]
        def __init__(self, code, k_type=None, begin_date=None, end_date=None, autype=None):
            super().__init__(code, k_type, begin_date, end_date, autype)

        def get_kl_data(self):
            df = _frames_registry()[self.code]
            for r in df.itertuples(index=False):
                t: pd.Timestamp = r.ts
                ct = CTime(t.year, t.month, t.day, t.hour, t.minute)
                d = {DATA_FIELD.FIELD_TIME: ct, DATA_FIELD.FIELD_OPEN: float(r.open), DATA_FIELD.FIELD_HIGH: float(r.high),
                     DATA_FIELD.FIELD_LOW: float(r.low), DATA_FIELD.FIELD_CLOSE: float(r.close)}
                if r.volume is not None and not pd.isna(r.volume):
                    d[DATA_FIELD.FIELD_VOLUME] = float(r.volume)
                if r.amount is not None and not pd.isna(r.amount):
                    d[DATA_FIELD.FIELD_TURNOVER] = float(r.amount)
                yield CKLine_Unit(d, autofix=True)

        def SetBasciInfo(self):
            pass

        @classmethod
        def do_init(cls):
            pass

        @classmethod
        def do_close(cls):
            pass

    _chanpy["StoreAPI"] = StoreAPI
    return StoreAPI


def chanpy_config(cfg: AppConfig) -> dict:
    """02 文档第 12 节的配置对照。"""
    return {
        "bi_algo": "normal",
        "bi_strict": cfg.engine.bi.mode == "old",      # 老笔 = 严格笔（顶底间 ≥ 4 根合并 K 线）
        "bi_fx_check": cfg.engine.bi.fx_check,          # 分型价格条件
        "gap_as_kl": False,                             # 缺口不算 K 线（本项目不计缺口）
        "bi_end_is_peak": True,                         # 笔终点必须是区间极值（本项目算法等价）
        "bi_allow_sub_peak": False,                     # 不允许次高低点成笔：候选笔作废、前一笔延伸（02 §3.4.3）
        "seg_algo": "chan",                             # 特征序列法
        "left_seg_method": "peak",
        "zs_algo": "normal",                            # 中枢不跨线段
        "zs_combine": False,                            # 不合并中枢
        "one_bi_zs": False,
        "trigger_step": False,
        "kl_data_check": False,
        "print_warning": False,
        "print_err_time": False,
        "bs_type": "1,2,3a,3b",
        "macd_algo": "area",
        "divergence_rate": float("inf"),
        "min_zs_cnt": 1,
    }


def run_chanpy(code: str, level: Level, bars: pd.DataFrame, cfg: AppConfig):
    cp = load_chanpy()
    StoreAPI = _make_store_api()
    _frames_registry()[code] = bars

    class _Chan(cp["CChan"]):  # type: ignore[misc, valid-type]
        def GetStockAPI(self):
            return StoreAPI

    conf = cp["CChanConfig"](dict(chanpy_config(cfg)))
    kl_type = getattr(cp["KL_TYPE"], LEVEL_MAP[level])
    chan = _Chan(code=code, data_src="custom:store", lv_list=[kl_type], config=conf)
    return chan[0]


# ----------------------------------------------------------------------------
# 结构抽取：两边都转成同一种轻量表示
# ----------------------------------------------------------------------------
def _ct2ts(t) -> pd.Timestamp:
    return pd.Timestamp(year=t.year, month=t.month, day=t.day, hour=t.hour, minute=t.minute)


@dataclass
class Pivot:
    ts: pd.Timestamp
    price: float
    kind: str           # top / bottom
    confirmed: bool
    idx: int            # 所属线/段序号（用于差异定位）


@dataclass
class ZsBox:
    zg: float
    zd: float
    start: pd.Timestamp
    end: pd.Timestamp
    confirmed: bool
    n: int


@dataclass
class Side:
    name: str
    bi: list[Pivot]
    seg: list[Pivot]
    zs_bi: list[ZsBox]
    zs_seg: list[ZsBox]
    bsp: list[tuple[pd.Timestamp, str]]
    n_bars: int


def _ours_pivots(items, bars_ts) -> list[Pivot]:
    out: list[Pivot] = []
    for it in items:
        if getattr(it, "candidate", False):
            continue
        if not out:
            out.append(Pivot(it.start_fx.ts, float(it.start_price), it.start_fx.kind, True, it.id))
        out.append(Pivot(it.end_fx.ts, float(it.end_price), it.end_fx.kind, bool(it.confirmed), it.id))
    return out


def ours_side(res: LevelResult) -> Side:
    ts = res.bars.ts
    bi = _ours_pivots(res.bis, ts)
    seg = _ours_pivots(res.segs, ts)
    zs_bi = [ZsBox(z.zg, z.zd, ts.iloc[z.start_raw], ts.iloc[z.end_raw], z.range_confirmed, len(z.elems)) for z in res.zs_bi]
    zs_seg = [ZsBox(z.zg, z.zd, ts.iloc[z.start_raw], ts.iloc[z.end_raw], z.range_confirmed, len(z.elems)) for z in res.zs_seg]
    bsp = [(b.ts, b.type) for b in res.bsps]
    return Side("chanlun", bi, seg, zs_bi, zs_seg, bsp, len(res.bars))


def _theirs_pivots(lines) -> list[Pivot]:
    out: list[Pivot] = []
    for ln in lines:
        is_up = str(ln.dir).endswith("UP")
        b_kind, e_kind = ("bottom", "top") if is_up else ("top", "bottom")
        if not out:
            out.append(Pivot(_ct2ts(ln.get_begin_klu().time), float(ln.get_begin_val()), b_kind, True, ln.idx))
        out.append(Pivot(_ct2ts(ln.get_end_klu().time), float(ln.get_end_val()), e_kind, bool(ln.is_sure), ln.idx))
    return out


def theirs_side(kl_list) -> Side:
    bi = _theirs_pivots(list(kl_list.bi_list))
    seg = _theirs_pivots(list(kl_list.seg_list))

    def _zs(lst):
        out = []
        for z in lst:
            out.append(ZsBox(float(z.high), float(z.low), _ct2ts(z.begin.time), _ct2ts(z.end.time), bool(z.is_sure), len(z.bi_lst)))
        return out

    zs_bi = _zs(list(kl_list.zs_list))
    zs_seg = _zs(list(kl_list.segzs_list))
    bsp = []
    for p in kl_list.bs_point_lst.getSortedBspList():
        bsp.append((_ct2ts(p.klu.time), ("b" if p.is_buy else "s") + ":" + p.type2str()))
    return Side("chan.py", bi, seg, zs_bi, zs_seg, bsp, len(kl_list))


# ----------------------------------------------------------------------------
# 比较
# ----------------------------------------------------------------------------
@dataclass
class Diff:
    where: str          # ours_only / theirs_only
    ts: str
    price: float
    kind: str
    category: str
    note: str = ""


@dataclass
class Compare:
    n_ours: int
    n_theirs: int
    matched: int
    n_ours_conf: int
    n_theirs_conf: int
    matched_conf: int
    diffs: list[Diff] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return 2 * self.matched / (self.n_ours + self.n_theirs) if (self.n_ours + self.n_theirs) else 1.0

    @property
    def rate_conf(self) -> float:
        d = self.n_ours_conf + self.n_theirs_conf
        return 2 * self.matched_conf / d if d else 1.0


def _classify(p: Pivot, other: list[Pivot], tail_ts: pd.Timestamp | None, head_ts: pd.Timestamp | None = None) -> tuple[str, str]:
    if head_ts is not None and p.ts < head_ts:
        return "序列开头", "位于首个共同端点之前：两边对序列最前端（开头包含处理、第一笔）的处理不同"
    if tail_ts is not None and p.ts >= tail_ts:
        return "末端未确认", "位于任一方最后已确认端点之后，两边算法对末端处理不同"
    same_price = [o for o in other if abs(o.price - p.price) <= PRICE_TOL * max(1.0, abs(p.price)) and o.kind == p.kind]
    if same_price:
        o = min(same_price, key=lambda o: abs((o.ts - p.ts).total_seconds()))
        return "同价异根", f"对方同价端点在 {o.ts}（极值相等时选取的原始 K 线不同）"
    near = [o for o in other if o.kind == p.kind and abs((o.ts - p.ts).days) <= 45]
    if near:
        o = min(near, key=lambda o: abs((o.ts - p.ts).total_seconds()))
        return "端点位置差异", f"对方邻近同类端点 {o.ts} @ {o.price:.3f}"
    return "多/少一笔或一段", "对方在附近没有同类端点（成笔 / 成段条件判定不同）"


def compare_pivots(a: list[Pivot], b: list[Pivot]) -> Compare:
    ka = {p.ts: p for p in a}
    kb = {p.ts: p for p in b}
    matched_ts = [t for t in ka if t in kb and abs(ka[t].price - kb[t].price) <= PRICE_TOL * max(1.0, abs(ka[t].price))]
    conf_a = [p for p in a if p.confirmed]
    conf_b = [p for p in b if p.confirmed]
    kca = {p.ts for p in conf_a}
    kcb = {p.ts for p in conf_b}
    matched_conf = [t for t in matched_ts if t in kca and t in kcb]
    last_conf = [max(kca) if kca else None, max(kcb) if kcb else None]
    tail_ts = min([t for t in last_conf if t is not None], default=None)
    head_ts = min(matched_ts) if matched_ts else None
    mset = set(matched_ts)
    diffs: list[Diff] = []
    for p in a:
        if p.ts in mset:
            continue
        if p.ts in kb:
            diffs.append(Diff("ours_only", str(p.ts), p.price, p.kind, "同根异价", f"对方价格 {kb[p.ts].price:.4f}"))
            continue
        cat, note = _classify(p, b, tail_ts, head_ts)
        diffs.append(Diff("ours_only", str(p.ts), p.price, p.kind, cat, note))
    for p in b:
        if p.ts in ka:
            continue
        cat, note = _classify(p, a, tail_ts, head_ts)
        diffs.append(Diff("theirs_only", str(p.ts), p.price, p.kind, cat, note))
    return Compare(len(a), len(b), len(matched_ts), len(conf_a), len(conf_b), len(matched_conf), diffs)


def compare_zs(a: list[ZsBox], b: list[ZsBox]) -> Compare:
    used = set()
    matched = 0
    matched_conf = 0
    diffs: list[Diff] = []
    for z in a:
        hit = None
        for j, o in enumerate(b):
            if j in used:
                continue
            tol = PRICE_TOL * max(1.0, abs(z.zg))
            if abs(z.zg - o.zg) <= tol and abs(z.zd - o.zd) <= tol and o.start <= z.end and z.start <= o.end:
                hit = j
                break
        if hit is None:
            diffs.append(Diff("ours_only", f"{z.start.date()}~{z.end.date()}", z.zg, f"zd={z.zd:.3f} n={z.n}",
                              "中枢无对应" if z.confirmed else "末端未确认", ""))
        else:
            used.add(hit)
            matched += 1
            if z.confirmed and b[hit].confirmed:
                matched_conf += 1
    for j, o in enumerate(b):
        if j not in used:
            diffs.append(Diff("theirs_only", f"{o.start.date()}~{o.end.date()}", o.zg, f"zd={o.zd:.3f} n={o.n}",
                              "中枢无对应" if o.confirmed else "末端未确认", ""))
    return Compare(len(a), len(b), matched, sum(z.confirmed for z in a), sum(z.confirmed for z in b), matched_conf, diffs)


def compare_bsp(a: list[tuple[pd.Timestamp, str]], b: list[tuple[pd.Timestamp, str]]) -> dict:
    sa = {t for t, _ in a}
    sb = {t for t, _ in b}
    both = sa & sb
    return {"ours": len(sa), "theirs": len(sb), "same_bar": len(both),
            "ours_only": len(sa - sb), "theirs_only": len(sb - sa)}


# ----------------------------------------------------------------------------
# 单股单级别
# ----------------------------------------------------------------------------
@dataclass
class Result:
    code: str
    level: str
    n_bars: int
    data_hash: str
    bi: Compare
    seg: Compare
    zs_bi: Compare
    zs_seg: Compare
    bsp: dict
    t_ours: float
    t_theirs: float

    def row(self) -> dict:
        return {
            "code": self.code, "level": self.level, "bars": self.n_bars, "data_hash": self.data_hash,
            "bi_all": round(self.bi.rate, 4), "bi_conf": round(self.bi.rate_conf, 4), "bi_n": f"{self.bi.n_ours}/{self.bi.n_theirs}",
            "seg_all": round(self.seg.rate, 4), "seg_conf": round(self.seg.rate_conf, 4), "seg_n": f"{self.seg.n_ours}/{self.seg.n_theirs}",
            "zsbi_all": round(self.zs_bi.rate, 4), "zsbi_conf": round(self.zs_bi.rate_conf, 4), "zsbi_n": f"{self.zs_bi.n_ours}/{self.zs_bi.n_theirs}",
            "zsseg_all": round(self.zs_seg.rate, 4), "zsseg_n": f"{self.zs_seg.n_ours}/{self.zs_seg.n_theirs}",
            "bsp": f"{self.bsp['same_bar']}/{self.bsp['ours']}/{self.bsp['theirs']}",
            "t_ours": round(self.t_ours, 2), "t_theirs": round(self.t_theirs, 2),
        }


def verify_bars(code: str, level: Level, bars: pd.DataFrame, cfg: AppConfig) -> Result:
    t0 = time.time()
    ours = ours_side(analyze_bars(bars, cfg))
    t1 = time.time()
    theirs = theirs_side(run_chanpy(code, level, bars, cfg))
    t2 = time.time()
    return Result(code, level, len(bars), data_hash(bars),
                  compare_pivots(ours.bi, theirs.bi), compare_pivots(ours.seg, theirs.seg),
                  compare_zs(ours.zs_bi, theirs.zs_bi), compare_zs(ours.zs_seg, theirs.zs_seg),
                  compare_bsp(ours.bsp, theirs.bsp), t1 - t0, t2 - t1)


def verify(code: str, level: Level, cfg: AppConfig | None = None, tail: int | None = None, store: Store | None = None) -> Result:
    cfg = cfg or load_config()
    own = store is None
    store = store or Store(cfg.db_path)
    try:
        bars = store.load_klines(code, level)
    finally:
        if own:
            store.close()
    if bars.empty:
        raise ValueError(f"{code} {level} 无本地数据，请先 chan update {code}")
    if tail:
        bars = bars.tail(tail).reset_index(drop=True)
    return verify_bars(code, level, bars, cfg)


# ----------------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def summarize(results: list[Result]) -> dict:
    def agg(getter, conf: bool):
        m = n = 0
        for r in results:
            c = getter(r)
            if conf:
                m += c.matched_conf; n += c.n_ours_conf + c.n_theirs_conf
            else:
                m += c.matched; n += c.n_ours + c.n_theirs
        return 2 * m / n if n else 1.0

    return {
        "bi_conf": agg(lambda r: r.bi, True), "bi_all": agg(lambda r: r.bi, False),
        "seg_conf": agg(lambda r: r.seg, True), "seg_all": agg(lambda r: r.seg, False),
        "zs_bi_conf": agg(lambda r: r.zs_bi, True), "zs_bi_all": agg(lambda r: r.zs_bi, False),
        "zs_seg_all": agg(lambda r: r.zs_seg, False),
    }


def diff_categories(results: list[Result], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        for d in getattr(r, attr).diffs:
            out[d.category] = out.get(d.category, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def write_report(results: list[Result], path: Path, cfg: AppConfig, detail_dir: Path | None = None) -> None:
    s = summarize(results)
    lines = [
        "---", "type: report", "project: 缠论分析工具", f"created: {pd.Timestamp.today().date()}",
        "tags: [缠论, 交叉验证, chan.py]", "---",
        "# 交叉验证报告：本项目引擎 vs chan.py", "",
        f"生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M}。基准：chan.py `{BASELINE_COMMIT[:7]}`（见 `tests/crossval/BASELINE.md`）。"
        f"引擎配置哈希 `{cfg.engine.hash()}`（笔模式 {cfg.engine.bi.mode}，fx_check {cfg.engine.bi.fx_check}，笔中枢跨段 {cfg.engine.zs.bi_zs_cross_seg}）。", "",
        "一致率 = 2 × 匹配数 / (我方数 + chan.py 数)。「已确认」只统计我方 confirmed / chan.py is_sure 的结构；「全部」含末端未确认结构。", "",
        "## 总体", "",
        "| 项目 | 已确认 | 全部 | 目标 |", "|---|---|---|---|",
        f"| 笔端点 | **{_pct(s['bi_conf'])}** | {_pct(s['bi_all'])} | ≥ 95% |",
        f"| 线段端点 | **{_pct(s['seg_conf'])}** | {_pct(s['seg_all'])} | ≥ 90% |",
        f"| 笔中枢区间 | **{_pct(s['zs_bi_conf'])}** | {_pct(s['zs_bi_all'])} | ≥ 90% |",
        f"| 段中枢区间 | — | {_pct(s['zs_seg_all'])} | 参考 |", "",
        "## 逐股逐级别", "",
        "| 代码 | 级别 | K线 | 笔(已确认/全部) | 我/它 | 线段(已确认/全部) | 我/它 | 笔中枢(已确认/全部) | 我/它 | 段中枢 | 买卖点 同根/我/它 | 耗时 我/它 s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.code} | {r.level} | {r.n_bars} | {_pct(r.bi.rate_conf)} / {_pct(r.bi.rate)} | {r.bi.n_ours}/{r.bi.n_theirs} "
            f"| {_pct(r.seg.rate_conf)} / {_pct(r.seg.rate)} | {r.seg.n_ours}/{r.seg.n_theirs} "
            f"| {_pct(r.zs_bi.rate_conf)} / {_pct(r.zs_bi.rate)} | {r.zs_bi.n_ours}/{r.zs_bi.n_theirs} "
            f"| {_pct(r.zs_seg.rate)} ({r.zs_seg.n_ours}/{r.zs_seg.n_theirs}) "
            f"| {r.bsp['same_bar']}/{r.bsp['ours']}/{r.bsp['theirs']} | {r.t_ours:.1f}/{r.t_theirs:.1f} |")
    lines += ["", "## 差异分类（自动归类，逐条明细见 output/crossval/）", ""]
    for attr, title in (("bi", "笔端点"), ("seg", "线段端点"), ("zs_bi", "笔中枢"), ("zs_seg", "段中枢")):
        cats = diff_categories(results, attr)
        lines.append(f"### {title}")
        lines.append("")
        if not cats:
            lines.append("无差异。")
        else:
            lines.append("| 类别 | 条数 |"); lines.append("|---|---|")
            for k, v in cats.items():
                lines.append(f"| {k} | {v} |")
        lines.append("")
    expl = HERE / "EXPLANATIONS.md"
    lines += ["## 差异解释", ""]
    if expl.exists():
        lines += [expl.read_text(encoding="utf-8").strip(), ""]
    else:
        lines += ["（人工逐类解释写在 tests/crossval/EXPLANATIONS.md，重新生成报告时自动并入。）", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    if detail_dir is not None:
        detail_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            rows = []
            for attr in ("bi", "seg", "zs_bi", "zs_seg"):
                for d in getattr(r, attr).diffs:
                    rows.append({"struct": attr, **d.__dict__})
            (detail_dir / f"{r.code}_{r.level}.json").write_text(
                json.dumps({"summary": r.row(), "diffs": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def print_result(r: Result) -> None:
    print(f"{r.code} {r.level} bars={r.n_bars} hash={r.data_hash}")
    print(f"  笔    已确认 {_pct(r.bi.rate_conf)}  全部 {_pct(r.bi.rate)}  (我 {r.bi.n_ours} / 它 {r.bi.n_theirs}, 匹配 {r.bi.matched})")
    print(f"  线段  已确认 {_pct(r.seg.rate_conf)}  全部 {_pct(r.seg.rate)}  (我 {r.seg.n_ours} / 它 {r.seg.n_theirs}, 匹配 {r.seg.matched})")
    print(f"  笔中枢 已确认 {_pct(r.zs_bi.rate_conf)}  全部 {_pct(r.zs_bi.rate)}  (我 {r.zs_bi.n_ours} / 它 {r.zs_bi.n_theirs})")
    print(f"  段中枢 全部 {_pct(r.zs_seg.rate)}  (我 {r.zs_seg.n_ours} / 它 {r.zs_seg.n_theirs})")
    print(f"  买卖点 同根 {r.bsp['same_bar']}  我 {r.bsp['ours']}  它 {r.bsp['theirs']}")
    print(f"  耗时 我 {r.t_ours:.2f}s  它 {r.t_theirs:.2f}s")
    cats = diff_categories([r], "bi")
    if cats:
        print("  笔差异分类: " + ", ".join(f"{k} {v}" for k, v in cats.items()))


def run_verify(code: str, level: str) -> Result:
    """`chan verify` 入口。"""
    from chanlun.codes import normalize
    r = verify(normalize(code).code, level)  # type: ignore[arg-type]
    print_result(r)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="与 chan.py 交叉验证")
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--all", action="store_true", help="自选股池全部")
    ap.add_argument("-l", "--levels", default="D")
    ap.add_argument("--tail", type=int, default=None, help="只取最近 N 根")
    ap.add_argument("--report", type=Path, default=None, help="写 Markdown 报告到该路径")
    ap.add_argument("--detail-dir", type=Path, default=ROOT / "output" / "crossval")
    ap.add_argument("--cross-seg", choices=["default", "true", "false"], default="default", help="覆盖 engine.zs.bi_zs_cross_seg")
    args = ap.parse_args(argv)

    from chanlun import watchlist as wl
    from chanlun.codes import normalize
    from chanlun.config import LEVELS_HK

    cfg = load_config()
    if args.cross_seg != "default":
        cfg.engine.zs.bi_zs_cross_seg = args.cross_seg == "true"
    codes = [normalize(c).code for c in args.codes]
    if args.all or not codes:
        codes += [s["code"] for s in wl.load(cfg.root / "watchlist.yaml") if s["code"] not in codes]
    levels = [x.strip() for x in args.levels.split(",") if x.strip()]
    results: list[Result] = []
    store = Store(cfg.db_path)
    try:
        for code in codes:
            for lv in levels:
                if code.endswith(".HK") and lv not in LEVELS_HK:
                    continue
                try:
                    r = verify(code, lv, cfg, args.tail, store)  # type: ignore[arg-type]
                except Exception as e:  # noqa: BLE001
                    print(f"{code} {lv} 失败: {e}")
                    continue
                print_result(r)
                results.append(r)
    finally:
        store.close()
    if results:
        s = summarize(results)
        print("\n总体  笔(已确认) {}  线段(已确认) {}  笔中枢(已确认) {}  段中枢 {}".format(
            _pct(s["bi_conf"]), _pct(s["seg_conf"]), _pct(s["zs_bi_conf"]), _pct(s["zs_seg_all"])))
    if args.report and results:
        write_report(results, args.report, cfg, args.detail_dir)
        print(f"报告已写入 {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
