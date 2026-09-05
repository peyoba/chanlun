"""M0 数据源实测脚本：输出各源可用级别、历史起点、耗时。"""
import time, sys, warnings
warnings.filterwarnings("ignore")
import pandas as pd

def t(): return time.perf_counter()

print("===== baostock =====")
import baostock as bs
lg = bs.login(); print("login:", lg.error_code, lg.error_msg)
def bs_q(code, freq, start, adj="2", fields=None):
    if fields is None:
        fields = "date,time,open,high,low,close,volume,amount" if freq in ("5","15","30","60") else "date,open,high,low,close,volume,amount,adjustflag"
    t0=t(); rs = bs.query_history_k_data_plus(code, fields, start_date=start, end_date="2026-09-05", frequency=freq, adjustflag=adj)
    rows=[]
    while rs.error_code=="0" and rs.next(): rows.append(rs.get_row_data())
    df=pd.DataFrame(rows, columns=rs.fields); return df, t()-t0, rs.error_msg
for code in ["sh.600519","sz.300750"]:
    for freq in ["5","30","d","w"]:
        df,dt,err=bs_q(code,freq,"1990-01-01")
        first = (df.iloc[0]["time"] if "time" in df else df.iloc[0]["date"]) if len(df) else "-"
        last = (df.iloc[-1]["time"] if "time" in df else df.iloc[-1]["date"]) if len(df) else "-"
        print(f"{code} freq={freq:>2} rows={len(df):>6} first={first} last={last} {dt:.1f}s {err}")
# 复权对比：600519 日线 不复权 vs 前复权 最近一次分红前后
d_raw,_,_=bs_q("sh.600519","d","2025-06-01",adj="3"); d_qfq,_,_=bs_q("sh.600519","d","2025-06-01",adj="2")
m=d_raw.merge(d_qfq,on="date",suffixes=("_raw","_qfq"))
m["ratio"]=m.close_qfq.astype(float)/m.close_raw.astype(float)
chg=m[m.ratio.diff().abs()>1e-6]
print("600519 前复权因子变动日(近一年):", chg[["date","ratio"]].to_string(index=False) if len(chg) else "无")
print("最近5根日线 raw vs qfq:\n", m.tail(3)[["date","close_raw","close_qfq"]].to_string(index=False))
bs.logout()

print("\n===== akshare / 东方财富 =====")
import akshare as ak
t0=t(); df=ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="19900101", end_date="20260905", adjust="qfq"); print(f"A股日线qfq rows={len(df)} first={df.iloc[0,0]} last={df.iloc[-1,0]} {t()-t0:.1f}s cols={list(df.columns)[:8]}")
print(df.tail(3).iloc[:, :6].to_string(index=False))
for p in ["5","30"]:
    try:
        t0=t(); dm=ak.stock_zh_a_hist_min_em(symbol="600519", period=p, adjust="qfq"); print(f"A股{p}分 qfq rows={len(dm)} first={dm.iloc[0,0]} last={dm.iloc[-1,0]} {t()-t0:.1f}s")
    except Exception as e: print(f"A股{p}分 失败: {e}")
for code in ["00700","09988"]:
    try:
        t0=t(); dh=ak.stock_hk_hist(symbol=code, period="daily", start_date="19900101", end_date="20260905", adjust="qfq"); print(f"港股{code}日线qfq rows={len(dh)} first={dh.iloc[0,0]} last={dh.iloc[-1,0]} {t()-t0:.1f}s")
        t0=t(); dw=ak.stock_hk_hist(symbol=code, period="weekly", start_date="19900101", end_date="20260905", adjust="qfq"); print(f"港股{code}周线qfq rows={len(dw)} first={dw.iloc[0,0]} last={dw.iloc[-1,0]} {t()-t0:.1f}s")
    except Exception as e: print(f"港股{code} 失败: {e}")
try:
    t0=t(); dhr=ak.stock_hk_hist(symbol="00700", period="daily", start_date="20250101", end_date="20260905", adjust=""); print(f"港股00700 不复权 rows={len(dhr)} {t()-t0:.1f}s")
    dhq=ak.stock_hk_hist(symbol="00700", period="daily", start_date="20250101", end_date="20260905", adjust="qfq")
    mm=dhr.merge(dhq,on="日期",suffixes=("_raw","_qfq")); mm["ratio"]=mm["收盘_qfq"]/mm["收盘_raw"]
    ch=mm[mm.ratio.diff().abs()>1e-6]; print("00700 复权因子变动日:", ch[["日期","ratio"]].to_string(index=False) if len(ch) else "无")
except Exception as e: print("港股复权对比失败:", e)
try:
    t0=t(); lst=ak.stock_hk_spot_em(); print(f"港股列表 rows={len(lst)} {t()-t0:.1f}s")
except Exception as e: print("港股列表失败:", e)
try:
    t0=t(); cal=ak.tool_trade_date_hist_sina(); print(f"A股交易日历 rows={len(cal)} last={cal.iloc[-1,0]} {t()-t0:.1f}s")
except Exception as e: print("交易日历失败:", e)

print("\n===== yfinance =====")
import yfinance as yf
try:
    t0=t(); y=yf.Ticker("0700.HK").history(period="max", auto_adjust=True); print(f"0700.HK rows={len(y)} first={y.index[0].date()} last={y.index[-1].date()} {t()-t0:.1f}s")
    print(y.tail(3)[["Open","High","Low","Close"]].round(2).to_string())
except Exception as e: print("yfinance 失败:", e)
