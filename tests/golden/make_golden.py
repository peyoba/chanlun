"""生成 / 刷新 golden 基线（样本股冻结期望输出，防回归）。

用法：
  .venv/bin/python tests/golden/make_golden.py            # 只在没有基线时生成
  .venv/bin/python tests/golden/make_golden.py --update   # 引擎口径有意变更后刷新全部基线（须在自检报告 / 05 决策记录里说明）
数据快照来自本地 data/market.db（取每个样本最近 N 根），写入 fixtures/*.csv；期望输出写入 expected/*.json。
引擎配置用 AppConfig() 默认值（不读 config.yaml），基线里记录 engine_config_hash 与 data_hash。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from chanlun.config import AppConfig, load_config  # noqa: E402
from chanlun.data.store import Store, data_hash  # noqa: E402
from chanlun.engine.analyze import analyze_bars  # noqa: E402

# (代码, 级别, 最近 N 根)：覆盖 A 股日线 / 30 分 / 周线与港股日线，长度以 CSV ≤ 150KB 为限
CASES = [("600519.SH", "D", 1500), ("300750.SZ", "30m", 1500), ("000001.SZ", "W", 800), ("00700.HK", "D", 1500), ("002466.SZ", "5m", 1500)]


def snapshot(bars: pd.DataFrame, cfg: AppConfig) -> dict:
    r = analyze_bars(bars, cfg)
    R = lambda x: round(float(x), 6)  # noqa: E731
    return {
        "engine_config_hash": cfg.engine.hash(),
        "data_hash": data_hash(bars),
        "bars": len(bars),
        "merged": len(r.merged),
        "fractals": len(r.fractals),
        "bi": [[b.start_raw, R(b.start_price), b.end_raw, R(b.end_price), b.dir, b.confirmed, b.candidate] for b in r.bis],
        "seg": [[s.start_raw, R(s.start_price), s.end_raw, R(s.end_price), s.dir, s.end_case, s.confirmed] for s in r.segs],
        "zs_bi": [[R(z.zg), R(z.zd), z.start_raw, z.end_raw, list(z.elems), z.range_confirmed, z.ended, z.end_confirmed] for z in r.zs_bi],
        "zs_seg": [[R(z.zg), R(z.zd), z.start_raw, z.end_raw, list(z.elems), z.range_confirmed, z.ended, z.end_confirmed] for z in r.zs_seg],
        "divergences": [[d.kind, d.dir, d.seg_a, d.seg_c, d.zs_id, d.grade, d.raw_idx] for d in r.divergences],
        "bsp": [[b.raw_idx, b.type, b.zs_kind, b.grade, b.confirmed, R(b.price)] for b in r.bsps],
        "trend": r.trend,
    }


def main(argv: list[str]) -> int:
    update = "--update" in argv
    cfg = AppConfig(root=ROOT)
    db = load_config().db_path
    store = Store(db) if db.exists() else None
    for code, level, n in CASES:
        fx = HERE / "fixtures" / f"{code}_{level}.csv"
        ex = HERE / "expected" / f"{code}_{level}.json"
        if not fx.exists():
            if store is None or store.count(code, level) == 0:
                print(f"跳过 {code} {level}：无本地数据，无法生成 fixture"); continue
            df = store.load_klines(code, level).tail(n).reset_index(drop=True)
            df.assign(ts=df.ts.dt.strftime("%Y-%m-%d %H:%M:%S")).to_csv(fx, index=False)
            print(f"写入 fixture {fx.name} ({len(df)} 根)")
        if ex.exists() and not update:
            print(f"保留 {ex.name}（已存在；用 --update 刷新）"); continue
        bars = pd.read_csv(fx, parse_dates=["ts"])
        snap = snapshot(bars, cfg)
        ex.write_text(json.dumps(snap, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"写入 expected {ex.name}: 笔 {len(snap['bi'])} 段 {len(snap['seg'])} 笔中枢 {len(snap['zs_bi'])} 段中枢 {len(snap['zs_seg'])} 买卖点 {len(snap['bsp'])}")
    if store:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
