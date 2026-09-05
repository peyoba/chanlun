import time, warnings; warnings.filterwarnings("ignore")
import pandas as pd, akshare as ak, yfinance as yf
def t(): return time.perf_counter()
def run(name, fn, tries=3):
    for i in range(tries):
        try:
            t0=t(); r=fn(); print(f"[OK] {name} {t()-t0:.1f}s ->", r); return
        except Exception as e:
            print(f"[retry{i}] {name}: {type(e).__name__}: {str(e)[:120]}"); time.sleep(2)
    print(f"[FAIL] {name}")
def desc(df, datecol=0): return f"rows={len(df)} first={df.iloc[0,datecol]} last={df.iloc[-1,datecol]}"
run("A股日线qfq 600519", lambda: desc(ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="19900101", end_date="20260905", adjust="qfq")))
run("A股5分 600519", lambda: desc(ak.stock_zh_a_hist_min_em(symbol="600519", period="5", adjust="qfq")))
run("A股30分 600519", lambda: desc(ak.stock_zh_a_hist_min_em(symbol="600519", period="30", adjust="qfq")))
run("港股00700日线qfq", lambda: desc(ak.stock_hk_hist(symbol="00700", period="daily", start_date="19900101", end_date="20260905", adjust="qfq")))
run("港股00700周线qfq", lambda: desc(ak.stock_hk_hist(symbol="00700", period="weekly", start_date="19900101", end_date="20260905", adjust="qfq")))
run("港股09988日线qfq", lambda: desc(ak.stock_hk_hist(symbol="09988", period="daily", start_date="19900101", end_date="20260905", adjust="qfq")))
def hk_adj():
    r=ak.stock_hk_hist(symbol="00700", period="daily", start_date="20250101", end_date="20260905", adjust="")
    q=ak.stock_hk_hist(symbol="00700", period="daily", start_date="20250101", end_date="20260905", adjust="qfq")
    m=r.merge(q,on="日期",suffixes=("_raw","_qfq")); m["ratio"]=m["收盘_qfq"]/m["收盘_raw"]
    ch=m[m.ratio.diff().abs()>1e-6]; return "复权因子变动日: "+(ch[["日期","ratio"]].round(4).to_string(index=False).replace("\n"," | ") if len(ch) else "无")
run("港股00700复权对比", hk_adj)
run("港股列表", lambda: f"rows={len(ak.stock_hk_spot_em())}")
run("A股列表", lambda: f"rows={len(ak.stock_info_a_code_name())}")
run("交易日历", lambda: desc(ak.tool_trade_date_hist_sina()))
def yfh():
    y=yf.Ticker("0700.HK").history(period="max", auto_adjust=True); return f"rows={len(y)} first={y.index[0].date()} last={y.index[-1].date()} lastclose={y.Close.iloc[-1]:.2f}"
run("yfinance 0700.HK", yfh)
def em_vs_yf():
    e=ak.stock_hk_hist(symbol="00700", period="daily", start_date="20250601", end_date="20260905", adjust="qfq")
    y=yf.Ticker("0700.HK").history(start="2025-06-01", auto_adjust=True)
    e["d"]=pd.to_datetime(e["日期"]).dt.date; y["d"]=y.index.date
    m=e.merge(y,on="d"); m["diff"]=(m["收盘"]-m["Close"]).abs()/m["Close"]
    return f"重叠 {len(m)} 天, 收盘价相对差 max={m['diff'].max():.4%} mean={m['diff'].mean():.4%}, 东财末根 {m.iloc[-1]['收盘']} vs yf {m.iloc[-1]['Close']:.2f}"
run("港股 东财 vs yfinance", em_vs_yf)
