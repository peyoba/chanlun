import pytest
from chanlun.codes import normalize, CodeError

@pytest.mark.parametrize("raw,exp", [
    ("600519", "600519.SH"), ("sh600519", "600519.SH"), ("600519.SH", "600519.SH"), ("SH.600519", "600519.SH"),
    ("000858", "000858.SZ"), ("sz000858", "000858.SZ"), ("300750", "300750.SZ"), ("688981", "688981.SH"),
    ("00700", "00700.HK"), ("0700.HK", "00700.HK"), ("700.HK", "00700.HK"), ("hk00700", "00700.HK"), ("9988", "09988.HK"),
])
def test_normalize(raw, exp):
    assert normalize(raw).code == exp

def test_bse_rejected():
    with pytest.raises(CodeError):
        normalize("430047")
    with pytest.raises(CodeError):
        normalize("830799")

def test_provider_formats():
    c = normalize("600519")
    assert c.baostock == "sh.600519" and c.sina == "sh600519" and c.tencent == "sh600519"
    h = normalize("00700")
    assert h.tencent == "hk00700" and h.yfinance == "0700.HK"
