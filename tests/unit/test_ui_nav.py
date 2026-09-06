"""导航解析：代码与级别必须分开取，不能互相覆盖。"""
from chanlun.ui.nav import qp_str, resolve_nav


def test_qp_str_accepts_list_or_scalar():
    assert qp_str("30m") == "30m"
    assert qp_str(["30m"]) == "30m"
    assert qp_str(None) is None
    assert qp_str("") is None


def test_level_from_url_survives_missing_code():
    """点级别时 URL 往往只有 level，不能用 session 里的日线把级别盖回去。"""
    code, level = resolve_nav(
        url_code=None,
        url_level="30m",
        session_code="600519.SH",
        session_level="D",
        first_code="600519.SH",
        default_level="D",
    )
    assert code == "600519.SH"
    assert level == "30m"


def test_hk_stock_rejects_intraday():
    code, level = resolve_nav(
        url_code="00700.HK",
        url_level="30m",
        session_code="00700.HK",
        session_level="30m",
        first_code="600519.SH",
        default_level="D",
    )
    assert code == "00700.HK"
    assert level == "D"
