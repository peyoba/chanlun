"""plotly 图：K 线 + 分型 + 笔 + 线段 + 中枢 + 买卖点 + 高一级投影 + MACD。x 轴用序号避免非交易日空隙。"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ..engine.models import AnalysisResult, LevelResult

C = dict(up="#e0453b", down="#2e9e5b", bi="#1f77b4", seg="#111111", zs_bi="rgba(255,165,0,0.9)", zs_seg="rgba(128,0,128,0.9)",
         proj="rgba(30,144,255,0.12)", proj_line="rgba(30,144,255,0.5)", buy="#d62728", sell="#2ca02c", top="#9467bd", bot="#8c564b")

def _fmt(ts: pd.Timestamp, level: str) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if level in ("5m", "30m") else ts.strftime("%Y-%m-%d")

def build_figure(res: LevelResult | AnalysisResult, max_bars: int = 3000, show_fx: bool = False, show_merged: bool = False, title: str | None = None) -> go.Figure:
    bars = res.bars
    level = res.meta.get("level", "D")
    off = max(0, len(bars) - max_bars)          # 只渲染最近 max_bars 根
    b = bars.iloc[off:].reset_index(drop=True)
    x = list(range(len(b)))
    labels = [_fmt(t, level) for t in b.ts]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(x=x, open=b.open, high=b.high, low=b.low, close=b.close, name="K线",
                                 increasing_line_color=C["up"], decreasing_line_color=C["down"],
                                 increasing_fillcolor=C["up"], decreasing_fillcolor=C["down"], line_width=1,
                                 text=labels, hoverinfo="x+y+text"), row=1, col=1)

    def X(raw: int) -> int:
        return raw - off

    # 合并 K 线（可选）
    if show_merged:
        for m in res.merged:
            if m.raw_end < off: continue
            fig.add_shape(type="rect", x0=X(m.raw_start) - 0.4, x1=X(m.raw_end) + 0.4, y0=m.low, y1=m.high, line=dict(color="rgba(0,0,0,0.25)", width=1), row=1, col=1)

    # 分型
    if show_fx:
        for k, color, sym in (("top", C["top"], "triangle-down"), ("bottom", C["bot"], "triangle-up")):
            pts = [f for f in res.fractals if f.kind == k and f.raw_idx >= off]
            fig.add_trace(go.Scatter(x=[X(f.raw_idx) for f in pts], y=[f.price for f in pts], mode="markers", name=f"{'顶' if k=='top' else '底'}分型",
                                     marker=dict(symbol=sym, size=7, color=color), hoverinfo="skip", visible="legendonly"), row=1, col=1)

    # 笔
    def _line(items, name, color, width, getter):
        for conf in (True, False):
            xs, ys, txt = [], [], []
            for it in items:
                if it.confirmed != conf or it.end_raw < off: continue
                s_raw, s_p, e_raw, e_p = getter(it)
                xs += [X(s_raw), X(e_raw), None]; ys += [s_p, e_p, None]
                info = f"{name}#{it.id} {it.dir} {s_p:.2f}→{e_p:.2f}<br>端点 {_fmt(bars.ts.iloc[e_raw], level)}"
                info += f"<br>确认于 {_fmt(it.confirmed_at, level)}" if it.confirmed and it.confirmed_at is not None else "<br>未确认（可能重画）"
                txt += [info, info, None]
            if xs:
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"{name}{'' if conf else '(未确认)'}",
                                         line=dict(color=color, width=width, dash="solid" if conf else "dot"),
                                         text=txt, hoverinfo="text", legendgroup=name, showlegend=conf), row=1, col=1)
    _line(res.bis, "笔", C["bi"], 1.4, lambda it: (it.start_raw, it.start_price, it.end_raw, it.end_price))
    _line(res.segs, "线段", C["seg"], 2.6, lambda it: (it.start_raw, it.start_price, it.end_raw, it.end_price))

    # 中枢
    def _zs(zss, name, color):
        for z in zss:
            if z.end_raw < off: continue
            x0, x1 = X(z.start_raw), X(z.end_raw)
            dash = "solid" if z.range_confirmed else "dot"
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=z.zd, y1=z.zg, line=dict(color=color, width=1.5 if name == "段中枢" else 1, dash=dash),
                          fillcolor=color.replace("0.9", "0.06"), row=1, col=1)
            if z.ended and not z.end_confirmed:
                fig.add_shape(type="line", x0=x1, x1=x1, y0=z.zd, y1=z.zg, line=dict(color=color, width=2, dash="dot"), row=1, col=1)
            hint = ("；".join(z.hints)) if z.hints else ""
            fig.add_annotation(x=x0, y=z.zg, text=f"{name}#{z.id} [{z.zd:.2f},{z.zg:.2f}] n={len(z.elems)}{' ' + hint if hint else ''}",
                               showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=9, color=color), row=1, col=1)
    _zs(res.zs_bi, "笔中枢", C["zs_bi"]); _zs(res.zs_seg, "段中枢", C["zs_seg"])

    # 高一级投影
    proj = getattr(res, "projection", None) or {}
    if proj.get("zs"):
        ts_index = pd.Series(range(len(bars)), index=bars.ts)
        def _pos(t):
            i = ts_index.index.searchsorted(t)
            return X(min(max(i, 0), len(bars) - 1))
        for z in proj["zs"]:
            x0, x1 = _pos(z["start_ts"]), _pos(z["end_ts"])
            if x1 < 0: continue
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=z["zd"], y1=z["zg"], line=dict(color=C["proj_line"], width=1, dash="dash"), fillcolor=C["proj"], layer="below", row=1, col=1)
            fig.add_annotation(x=x1, y=z["zd"], text=f"{proj['level']}级中枢", showarrow=False, xanchor="right", yanchor="top", font=dict(size=9, color=C["proj_line"]), row=1, col=1)
        pts = [(p["ts"], p["price"]) for p in proj.get("bi_points", []) if _pos(p["ts"]) >= 0]
        if pts:
            fig.add_trace(go.Scatter(x=[_pos(t) for t, _ in pts], y=[p for _, p in pts], mode="markers", name=f"{proj['level']}级笔端点",
                                     marker=dict(symbol="diamond-open", size=8, color=C["proj_line"]), hoverinfo="y", visible="legendonly"), row=1, col=1)

    # 买卖点
    for side, color, sym, dy in (("b", C["buy"], "triangle-up", -1), ("s", C["sell"], "triangle-down", 1)):
        for grade in ("strict", "suspect"):
            pts = [p for p in res.bsps if p.raw_idx >= off and p.grade == grade and any(t.endswith(side) or t.endswith(side + "_like") for t in p.type.split("+"))]
            if not pts: continue
            fig.add_trace(go.Scatter(x=[X(p.raw_idx) for p in pts], y=[p.price * (1 + dy * 0.012) for p in pts], mode="markers+text",
                                     name=f"{'买' if side=='b' else '卖'}点({'严格' if grade=='strict' else '疑似'})",
                                     text=[p.type.replace("_like", "*") for p in pts], textposition="bottom center" if side == "b" else "top center", textfont=dict(size=9, color=color),
                                     marker=dict(symbol=sym if grade == "strict" else sym + "-open", size=11, color=color, line=dict(width=1.5, color=color)),
                                     hovertext=[f"{p.reason_short}<br>{'已确认' if p.confirmed else '当下候选'}" for p in pts], hoverinfo="text"), row=1, col=1)

    # MACD
    if res.macd is not None:
        m = res.macd.iloc[off:].reset_index(drop=True)
        fig.add_trace(go.Bar(x=x, y=m["hist"], name="MACD柱", marker_color=[C["up"] if v >= 0 else C["down"] for v in m["hist"]], hoverinfo="y"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=m["dif"], name="DIF", line=dict(color="#ff7f0e", width=1), hoverinfo="y"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=m["dea"], name="DEA", line=dict(color="#1f77b4", width=1), hoverinfo="y"), row=2, col=1)

    step = max(1, len(x) // 12)
    fig.update_xaxes(tickvals=x[::step], ticktext=labels[::step], rangeslider_visible=False, row=1, col=1)
    fig.update_xaxes(tickvals=x[::step], ticktext=labels[::step], row=2, col=1)
    fig.update_yaxes(fixedrange=False, row=1, col=1)
    name = res.meta.get("name", ""); code = res.meta.get("code", "")
    upd = res.meta.get("data_updated_at") or ""
    tr = res.trend.get("seg", {}); trend_txt = {"trend": f"{'上涨' if tr.get('dir')=='up' else '下跌'}趋势({tr.get('zs_count')}中枢)", "range": "盘整", "none": "无中枢"}.get(tr.get("type"), "")
    fig.update_layout(title=title or f"{code} {name} · {level} · 段级走势：{trend_txt} · 数据更新 {upd[:16]}{' · 数据非最新' if res.meta.get('stale') else ''}",
                      height=820, margin=dict(l=40, r=20, t=50, b=30), legend=dict(orientation="h", y=1.02, x=0), dragmode="pan",
                      hovermode="x unified", template="plotly_white")
    return fig
