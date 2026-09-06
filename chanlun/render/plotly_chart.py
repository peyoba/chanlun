"""plotly 图：K 线 + 分型 + 笔 + 线段 + 中枢 + 买卖点 + 高一级投影 + MACD。

横轴用 K 线序号（linear），避免非交易日空隙，线段按几何裁剪而不会被钉到窗口边。
窗口外的中枢 / 投影 / 线段裁到当前渲染区间，避免左侧空白和斜贯整图的假线。
纵轴禁止手拉；缩放/平移横轴后按可见 K 线重新贴价。
"""
from __future__ import annotations
import math
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ..engine.models import AnalysisResult, LevelResult

C = dict(up="#e0453b", down="#2e9e5b", bi="#1f77b4", seg="#111111", zs_bi="rgba(255,165,0,0.9)", zs_seg="rgba(128,0,128,0.9)",
         proj="rgba(30,144,255,0.12)", proj_line="rgba(30,144,255,0.5)", buy="#d62728", sell="#2ca02c", top="#9467bd", bot="#8c564b")

_VIEW_BARS = {"5m": 240, "30m": 320, "D": 252, "W": 156}


def _fmt(ts: pd.Timestamp, level: str) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if level in ("5m", "30m") else ts.strftime("%Y-%m-%d")


def _tick_fmt(ts: pd.Timestamp, level: str) -> str:
    return ts.strftime("%m-%d %H:%M") if level in ("5m", "30m") else ts.strftime("%Y-%m-%d")


def _yrange(high: pd.Series, low: pd.Series, pad: float = 0.04) -> tuple[float, float]:
    lo, hi = float(low.min()), float(high.max())
    if hi <= lo:
        return lo - 1.0, hi + 1.0
    m = (hi - lo) * pad
    return lo - m, hi + m


def clip_span(s_raw: int, s_p: float, e_raw: int, e_p: float, off: int, n: int) -> tuple[float, float, float, float] | None:
    """把一段直线裁到渲染窗口 [0, n)。窗外起点按比例插值，避免钉在左边缘拉出斜线。"""
    if n <= 0 or e_raw < off:
        return None
    ox0, ox1 = float(s_raw - off), float(e_raw - off)
    oy0, oy1 = float(s_p), float(e_p)
    if ox1 < 0:
        return None

    def y_at(x: float) -> float:
        if ox1 == ox0:
            return oy0
        return oy0 + (x - ox0) / (ox1 - ox0) * (oy1 - oy0)

    x0 = max(ox0, 0.0)
    x1 = min(ox1, float(n - 1))
    if x1 < x0:
        return None
    return x0, y_at(x0), x1, y_at(x1)


def _label_alias(ts: pd.Series, level: str) -> dict[str, str]:
    """linear 轴自动刻度用数字，映射成日期；缩放后 Plotly 会自己增减刻度。"""
    return {str(i): _tick_fmt(t, level) for i, t in enumerate(ts)}


def visible_yrange(high: pd.Series, low: pd.Series, x0: float, x1: float, pad: float = 0.04) -> tuple[float, float]:
    """按横轴可见区间取最高最低，留给缩放后贴价。"""
    n = len(high)
    if n == 0:
        return 0.0, 1.0
    i0 = max(0, math.ceil(x0))
    i1 = min(n - 1, math.floor(x1))
    if i1 < i0:
        i0, i1 = 0, n - 1
    return _yrange(high.iloc[i0:i1 + 1], low.iloc[i0:i1 + 1], pad)


CHART_CONFIG = {
    "scrollZoom": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "responsive": True,
}

_FIT_JS = """
<script>
(function () {
  function visHL(high, low, x, x0, x1) {
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i < x.length; i++) {
      var xi = +x[i];
      if (xi < x0 || xi > x1) continue;
      if (high[i] != null && !isNaN(high[i]) && high[i] > hi) hi = high[i];
      if (low[i] != null && !isNaN(low[i]) && low[i] < lo) lo = low[i];
    }
    if (!isFinite(lo) || !isFinite(hi)) return null;
    var p = (hi - lo) * 0.04;
    if (!p) p = Math.abs(hi) * 0.02 || 1;
    return [lo - p, hi + p];
  }
  function visY(y, x, x0, x1) {
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i < x.length; i++) {
      var xi = +x[i], v = +y[i];
      if (xi < x0 || xi > x1 || isNaN(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (!isFinite(lo)) return null;
    var p = (hi - lo) * 0.08;
    if (!p) p = Math.abs(hi) * 0.05 || 1;
    return [lo - p, hi + p];
  }
  function traces(gd) {
    return gd._fullData && gd._fullData.length ? gd._fullData : gd.data;
  }
  function fit(gd) {
    var xr = gd.layout.xaxis && gd.layout.xaxis.range;
    if (!xr || xr.length < 2) return;
    var x0 = +xr[0], x1 = +xr[1];
    var src = traces(gd);
    var patch = {};
    var candle = src.find(function (t) { return t.type === "candlestick"; });
    if (candle) {
      var yr = visHL(candle.high, candle.low, candle.x, x0, x1);
      if (yr) patch["yaxis.range"] = yr;
    }
    var lo = Infinity, hi = -Infinity;
    ["MACD柱", "DIF", "DEA"].forEach(function (name) {
      var t = src.find(function (d) { return d.name === name; });
      if (!t) return;
      var r = visY(t.y, t.x, x0, x1);
      if (r) { lo = Math.min(lo, r[0]); hi = Math.max(hi, r[1]); }
    });
    if (isFinite(lo) && isFinite(hi)) patch["yaxis2.range"] = [lo, hi];
    if (!Object.keys(patch).length) return;
    gd._chanlunFitting = true;
    Plotly.relayout(gd, patch).then(function () { gd._chanlunFitting = false; });
  }
  function install(gd) {
    if (!gd || gd._chanlunFit) return;
    gd._chanlunFit = true;
    gd._chanlunXr = ((gd.layout.xaxis && gd.layout.xaxis.range) || []).join();
    gd.on("plotly_relayout", function (e) {
      if (gd._chanlunFitting) return;
      var xr = ((gd.layout.xaxis && gd.layout.xaxis.range) || []).join();
      if (xr === gd._chanlunXr && !(e && e["yaxis.autorange"])) return;
      gd._chanlunXr = xr;
      fit(gd);
    });
  }
  function boot() {
    var gd = document.querySelector(".js-plotly-plot, .plotly-graph-div");
    if (gd && gd.data && window.Plotly) { install(gd); return; }
    setTimeout(boot, 40);
  }
  boot();
})();
</script>
"""


def show_figure(fig: go.Figure, height: int = 760) -> None:
    """网页出图：缩放横轴时纵轴贴可见 K 线，仍禁止手拉纵轴。"""
    import streamlit.components.v1 as components
    fig.update_layout(autosize=True, width=None, height=height)
    html = fig.to_html(include_plotlyjs="inline", full_html=True, config=CHART_CONFIG)
    html = html.replace("<head>", "<head><style>html,body{margin:0;overflow:hidden}.js-plotly-plot,.plot-container,.svg-container{width:100%!important}</style>", 1)
    html = html.replace("</body>", _FIT_JS + "</body>")
    components.html(html, height=height + 16, scrolling=False)


def build_figure(res: LevelResult | AnalysisResult, max_bars: int = 3000, show_fx: bool = False, show_merged: bool = False, title: str | None = None) -> go.Figure:
    bars = res.bars
    level = res.meta.get("level", "D")
    off = max(0, len(bars) - max_bars)
    b = bars.iloc[off:].reset_index(drop=True)
    n = len(b)
    x = list(range(n))
    labels = [_fmt(t, level) for t in b.ts]
    view_n = min(n, _VIEW_BARS.get(level, 300))
    view0 = max(0, n - view_n)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.10)
    fig.add_trace(go.Candlestick(x=x, open=b.open, high=b.high, low=b.low, close=b.close, name="K线",
                                 increasing_line_color=C["up"], decreasing_line_color=C["down"],
                                 increasing_fillcolor=C["up"], decreasing_fillcolor=C["down"], line_width=1,
                                 text=labels, hoverinfo="text+y"), row=1, col=1)

    def X(raw: int) -> int:
        return raw - off

    def clip_i(i: int) -> int:
        return 0 if i < 0 else (n - 1 if i >= n else i)

    if show_merged:
        for m in res.merged:
            if m.raw_end < off: continue
            fig.add_shape(type="rect", x0=clip_i(X(m.raw_start)), x1=clip_i(X(m.raw_end)), y0=m.low, y1=m.high,
                          line=dict(color="rgba(0,0,0,0.25)", width=1), row=1, col=1)

    if show_fx:
        for k, color, sym in (("top", C["top"], "triangle-down"), ("bottom", C["bot"], "triangle-up")):
            pts = [f for f in res.fractals if f.kind == k and f.raw_idx >= off]
            fig.add_trace(go.Scatter(x=[X(f.raw_idx) for f in pts], y=[f.price for f in pts], mode="markers",
                                     name=f"{'顶' if k=='top' else '底'}分型",
                                     marker=dict(symbol=sym, size=7, color=color), hoverinfo="skip", visible="legendonly"), row=1, col=1)

    def _line(items, name, color, width, getter):
        for conf in (True, False):
            xs, ys, txt = [], [], []
            for it in items:
                if it.confirmed != conf or it.end_raw < off: continue
                s_raw, s_p, e_raw, e_p = getter(it)
                span = clip_span(s_raw, s_p, e_raw, e_p, off, n)
                if span is None: continue
                x0, y0, x1, y1 = span
                xs += [x0, x1, None]; ys += [y0, y1, None]
                info = f"{name}#{it.id} {it.dir} {s_p:.2f}→{e_p:.2f}<br>端点 {_fmt(bars.ts.iloc[e_raw], level)}"
                info += f"<br>确认于 {_fmt(it.confirmed_at, level)}" if it.confirmed and it.confirmed_at is not None else "<br>未确认（可能重画）"
                txt += [info, info, None]
            if xs:
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"{name}{'' if conf else '(未确认)'}",
                                         line=dict(color=color, width=width, dash="solid" if conf else "dot"),
                                         text=txt, hoverinfo="text", legendgroup=name, showlegend=conf), row=1, col=1)
    _line(res.bis, "笔", C["bi"], 1.4, lambda it: (it.start_raw, it.start_price, it.end_raw, it.end_price))
    _line(res.segs, "线段", C["seg"], 2.6, lambda it: (it.start_raw, it.start_price, it.end_raw, it.end_price))

    def _zs(zss, name, color):
        for z in zss:
            if z.end_raw < off: continue
            x0, x1 = clip_i(X(z.start_raw)), clip_i(X(z.end_raw))
            dash = "solid" if z.range_confirmed else "dot"
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=z.zd, y1=z.zg, line=dict(color=color, width=1.5 if name == "段中枢" else 1, dash=dash),
                          fillcolor=color.replace("0.9", "0.06"), row=1, col=1)
            if z.ended and not z.end_confirmed:
                fig.add_shape(type="line", x0=x1, x1=x1, y0=z.zd, y1=z.zg, line=dict(color=color, width=2, dash="dot"), row=1, col=1)
            hint = ("；".join(z.hints)) if z.hints else ""
            fig.add_annotation(x=x0, y=z.zg, text=f"{name}#{z.id} [{z.zd:.2f},{z.zg:.2f}] n={len(z.elems)}{' ' + hint if hint else ''}",
                               showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=9, color=color), row=1, col=1)
    _zs(res.zs_bi, "笔中枢", C["zs_bi"]); _zs(res.zs_seg, "段中枢", C["zs_seg"])

    proj = getattr(res, "projection", None) or {}
    if proj.get("zs"):
        ts_index = pd.Series(range(len(bars)), index=bars.ts)
        def _pos(t) -> int:
            i = int(ts_index.index.searchsorted(t))
            return X(min(max(i, 0), len(bars) - 1))
        for z in proj["zs"]:
            i0, i1 = _pos(z["start_ts"]), _pos(z["end_ts"])
            if i1 < 0: continue
            x0, x1 = clip_i(i0), clip_i(i1)
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=z["zd"], y1=z["zg"], line=dict(color=C["proj_line"], width=1, dash="dash"),
                          fillcolor=C["proj"], layer="below", row=1, col=1)
            fig.add_annotation(x=x1, y=z["zd"], text=f"{proj['level']}级中枢", showarrow=False, xanchor="right", yanchor="top",
                               font=dict(size=9, color=C["proj_line"]), row=1, col=1)
        pts = [(p["ts"], p["price"]) for p in proj.get("bi_points", []) if _pos(p["ts"]) >= 0]
        if pts:
            fig.add_trace(go.Scatter(x=[clip_i(_pos(t)) for t, _ in pts], y=[p for _, p in pts], mode="markers",
                                     name=f"{proj['level']}级笔端点",
                                     marker=dict(symbol="diamond-open", size=8, color=C["proj_line"]), hoverinfo="y", visible="legendonly"), row=1, col=1)

    for side, color, sym, dy in (("b", C["buy"], "triangle-up", -1), ("s", C["sell"], "triangle-down", 1)):
        for grade in ("strict", "suspect"):
            pts = [p for p in res.bsps if p.raw_idx >= off and p.grade == grade and any(t.endswith(side) or t.endswith(side + "_like") for t in p.type.split("+"))]
            if not pts: continue
            fig.add_trace(go.Scatter(x=[X(p.raw_idx) for p in pts], y=[p.price * (1 + dy * 0.012) for p in pts], mode="markers+text",
                                     name=f"{'买' if side=='b' else '卖'}点({'严格' if grade=='strict' else '疑似'})",
                                     text=[p.type.replace("_like", "*") for p in pts], textposition="bottom center" if side == "b" else "top center",
                                     textfont=dict(size=9, color=color),
                                     marker=dict(symbol=sym if grade == "strict" else sym + "-open", size=11, color=color, line=dict(width=1.5, color=color)),
                                     hovertext=[f"{p.reason_short}<br>{'已确认' if p.confirmed else '当下候选'}" for p in pts], hoverinfo="text"), row=1, col=1)

    if res.macd is not None:
        m = res.macd.iloc[off:].reset_index(drop=True)
        fig.add_trace(go.Bar(x=x, y=m["hist"], name="MACD柱", marker_color=[C["up"] if v >= 0 else C["down"] for v in m["hist"]],
                             marker_line_width=0, width=0.85, hoverinfo="y"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=m["dif"], name="DIF", line=dict(color="#ff7f0e", width=1), hoverinfo="y"), row=2, col=1)
        fig.add_trace(go.Scatter(x=x, y=m["dea"], name="DEA", line=dict(color="#1f77b4", width=1), hoverinfo="y"), row=2, col=1)

    xrng = [view0 - 0.5, n - 0.5]
    y0, y1 = visible_yrange(b.high, b.low, xrng[0], xrng[1])
    alias = _label_alias(b.ts, level)
    xkw = dict(type="linear", range=xrng, minallowed=-0.5, maxallowed=n - 0.5,
               rangeslider_visible=False, fixedrange=False, showgrid=False,
               tickmode="auto", nticks=8, tickformat="d", separatethousands=False,
               labelalias=alias, ticklabeloverflow="allow", automargin=False,
               tickangle=0, tickfont=dict(size=11, color="#333"))
    # 日期画在主图和 MACD 之间，避免落在容器底边被裁掉
    fig.update_xaxes(**xkw, showticklabels=True, ticks="outside", side="bottom", row=1, col=1)
    fig.update_xaxes(**xkw, showticklabels=False, ticks="", row=2, col=1)
    fig.update_yaxes(fixedrange=True, autorange=False, range=[y0, y1], row=1, col=1)
    fig.update_yaxes(fixedrange=True, zeroline=True, zerolinecolor="rgba(0,0,0,0.25)", title_text="MACD",
                     title_font=dict(size=11), row=2, col=1)
    name = res.meta.get("name", ""); code = res.meta.get("code", "")
    upd = res.meta.get("data_updated_at") or ""
    tr = res.trend.get("seg", {}); trend_txt = {"trend": f"{'上涨' if tr.get('dir')=='up' else '下跌'}趋势({tr.get('zs_count')}中枢)", "range": "盘整", "none": "无中枢"}.get(tr.get("type"), "")
    fig.update_layout(title=title or f"{code} {name} · {level} · 段级走势：{trend_txt} · 数据更新 {upd[:16]}{' · 数据非最新' if res.meta.get('stale') else ''}",
                      height=760, margin=dict(l=52, r=16, t=52, b=28), legend=dict(orientation="h", y=1.02, x=0), dragmode="pan",
                      hovermode="x unified", bargap=0, template="plotly_white")
    return fig
