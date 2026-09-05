"""跨级别组装：先各级别独立 analyze_level，再做高一级投影与二买的次级别验证。依赖单向。"""
from __future__ import annotations
from datetime import datetime
from ..config import AppConfig, Level, higher_level, lower_level, LEVELS_HK
from ..data.store import Store
from .models import AnalysisResult, Check
from .analyze import analyze_level

def assemble(code: str, level: Level, cfg: AppConfig, *, as_of: datetime | None = None, store: Store | None = None) -> AnalysisResult:
    own = store is None
    store = store or Store(cfg.db_path)
    try:
        base = analyze_level(code, level, cfg, as_of=as_of, store=store)
        res = AnalysisResult(**base.__dict__)
        market_levels = LEVELS_HK if code.endswith(".HK") else None
        # 高一级投影
        hi = higher_level(level)
        if hi and (market_levels is None or hi in market_levels):
            try:
                h = analyze_level(code, hi, cfg, as_of=as_of, store=store)
                res.projection = {
                    "level": hi,
                    "zs": [{"zg": z.zg, "zd": z.zd, "start_ts": h.bars.ts.iloc[z.start_raw], "end_ts": h.bars.ts.iloc[z.end_raw], "kind": z.kind, "confirmed": z.range_confirmed}
                           for z in (h.zs_seg or h.zs_bi)],
                    "bi_points": [{"ts": h.bars.ts.iloc[b.end_raw], "price": b.end_price, "dir": b.dir} for b in h.bis],
                }
            except ValueError:
                res.projection = {"level": hi, "zs": [], "bi_points": [], "missing": True}
        # 次级别验证（仅二买 / 二卖）
        lo = lower_level(level)
        lo_ok = lo is not None and (market_levels is None or lo in market_levels)
        lo_res = None
        if lo_ok and cfg.engine.bsp.sub_level_check:
            try:
                lo_res = analyze_level(code, lo, cfg, as_of=as_of, store=store)
            except ValueError:
                lo_res = None
        for b in res.bsps:
            if not b.type.startswith("2"):
                continue
            idx = next((i for i, c in enumerate(b.checklist) if c.cond == "次级别验证"), None)
            if lo_res is None:
                msg = "港股无分钟级数据" if code.endswith(".HK") else ("本级别已是最低级别" if lo is None else "低一级数据缺失")
                if idx is not None:
                    b.checklist[idx] = Check("次级别验证", "weak", f"{msg}，用本级别元素近似")
                b.grade = "suspect"
                continue
            # 低一级在一买之后到二买之间，是否存在至少一笔完整的向上笔（买）/向下笔（卖）
            t1 = res.bars.ts.iloc[res.bsps[b.refs["bsp1"]].raw_idx] if "bsp1" in b.refs and b.refs["bsp1"] < len(res.bsps) else None
            t2 = b.ts
            want = "up" if b.type.startswith("2b") else "down"
            ok = t1 is not None and any(x.dir == want and lo_res.bars.ts.iloc[x.start_raw] >= t1 and lo_res.bars.ts.iloc[x.end_raw] <= t2 and x.confirmed for x in lo_res.bis)
            if idx is not None:
                b.checklist[idx] = Check("次级别验证", "pass" if ok else "weak", f"{lo} 级别{'存在' if ok else '未见'}完整反向笔")
            if not ok:
                b.grade = "suspect"
            b.risks = [r for r in b.risks if not r.startswith("勉强满足：次级别")] + ([] if ok else ["勉强满足：次级别验证"])
        return res
    finally:
        if own:
            store.close()
