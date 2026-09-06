"""golden 测试：样本股冻结期望输出（笔 / 线段 / 中枢 / 背驰 / 买卖点），防回归。

基线由 make_golden.py 生成；引擎口径有意变更后用 `make_golden.py --update` 刷新，并在报告中说明差异。
"""
import json, sys
from pathlib import Path
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_golden import snapshot  # noqa: E402
from chanlun.config import AppConfig  # noqa: E402

CASES = sorted(p.stem for p in (HERE / "expected").glob("*.json"))


def _diff(name, a, b, limit=5):
    if a == b:
        return []
    out = [f"{name}: 数量 {len(a)} vs 基线 {len(b)}"] if len(a) != len(b) else []
    n = 0
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            out.append(f"{name}[{i}]: 现在 {x} | 基线 {y}"); n += 1
            if n >= limit:
                break
    return out


@pytest.mark.parametrize("case", CASES)
def test_golden(case):
    exp = json.loads((HERE / "expected" / f"{case}.json").read_text(encoding="utf-8"))
    bars = pd.read_csv(HERE / "fixtures" / f"{case}.csv", parse_dates=["ts"])
    cfg = AppConfig()
    assert cfg.engine.hash() == exp["engine_config_hash"], "引擎默认配置已变化：确认口径变更后运行 make_golden.py --update"
    cur = snapshot(bars, cfg)
    assert cur["data_hash"] == exp["data_hash"], "fixture 数据与基线不一致"
    problems = []
    for key in ("bi", "seg", "zs_bi", "zs_seg", "divergences", "bsp"):
        problems += _diff(key, cur[key], exp[key])
    for key in ("merged", "fractals", "trend"):
        if cur[key] != exp[key]:
            problems.append(f"{key}: 现在 {cur[key]} | 基线 {exp[key]}")
    assert not problems, "\n".join(problems)
