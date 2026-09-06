"""交叉验证作为测试层：有 chan.py 基准库与本地数据时才运行，否则跳过。"""
import sys
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _ready():
    if not (HERE / "chan.py" / "Chan.py").exists():
        return "未克隆 chan.py 基准库（见 tests/crossval/BASELINE.md）"
    from chanlun.config import load_config
    if not load_config().db_path.exists():
        return "无本地数据库"
    return None


@pytest.mark.parametrize("code,level,bi_min,zs_min", [("600519.SH", "D", 0.95, 0.80), ("00700.HK", "D", 0.95, 0.80)])
def test_bi_agreement_with_chanpy(code, level, bi_min, zs_min):
    why = _ready()
    if why:
        pytest.skip(why)
    import run as cv
    from chanlun.data.store import Store
    from chanlun.config import load_config
    cfg = load_config()
    st = Store(cfg.db_path)
    try:
        if st.count(code, level) == 0:
            pytest.skip(f"{code} {level} 无本地数据")
        r = cv.verify(code, level, cfg, store=st)
    finally:
        st.close()
    assert r.bi.rate_conf >= bi_min, f"笔端点一致率 {r.bi.rate_conf:.3f} < {bi_min}"
    assert r.zs_bi.rate_conf >= zs_min, f"笔中枢一致率 {r.zs_bi.rate_conf:.3f} < {zs_min}"
