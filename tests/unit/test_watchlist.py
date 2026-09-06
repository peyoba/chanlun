"""自选股池：移除后还看哪一只；代码 / 名称解析。"""
from chanlun.watchlist import next_after_remove, parse_codes, resolve_query


def test_remove_other_keeps_current():
    assert next_after_remove(["A", "B", "C"], "B", "A") == "A"


def test_remove_current_goes_to_next():
    assert next_after_remove(["A", "B", "C"], "A", "A") == "B"


def test_remove_last_remaining_is_empty():
    assert next_after_remove(["A"], "A", "A") == ""


def test_parse_codes_ignores_name():
    assert parse_codes("指南针") == []
    assert parse_codes("600519 00700") == ["600519.SH", "00700.HK"]


def test_resolve_prefers_code():
    codes, err = resolve_query("600519", local=[("000858.SZ", "五粮液")])
    assert err == ""
    assert codes == ["600519.SH"]


def test_resolve_local_name():
    local = [("600519.SH", "贵州茅台"), ("00700.HK", "腾讯控股")]
    codes, err = resolve_query("贵州茅台", local=local, remote=lambda q: [])
    assert err == ""
    assert codes == ["600519.SH"]


def test_resolve_remote_name():
    def remote(q: str):
        assert q == "指南针"
        return [("300803.SZ", "指南针")]
    codes, err = resolve_query("指南针", local=[], remote=remote)
    assert err == ""
    assert codes == ["300803.SZ"]


def test_resolve_ambiguous_name():
    local = [("688981.SH", "中芯国际"), ("00981.HK", "中芯国际")]
    codes, err = resolve_query("中芯国际", local=local, remote=lambda q: [])
    assert codes == []
    assert "688981.SH" in err and "00981.HK" in err


def test_resolve_unknown_name():
    codes, err = resolve_query("不存在的股票", local=[], remote=lambda q: [])
    assert codes == []
    assert "无法识别" in err
