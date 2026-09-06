"""单股 HTML（含买卖点详情表）与 index.html 总览。"""
from __future__ import annotations
import html
from pathlib import Path
from ..engine.models import AnalysisResult
from ..config import AppConfig
from .plotly_chart import build_figure

_CSS = """<style>body{font-family:-apple-system,'PingFang SC',sans-serif;margin:0;padding:0 12px}table{border-collapse:collapse;font-size:13px;width:100%}
td,th{border:1px solid #ddd;padding:4px 8px;vertical-align:top}th{background:#f5f5f5;text-align:left}.strict{color:#d62728;font-weight:600}.suspect{color:#888}
details{margin:2px 0}summary{cursor:pointer}.pass{color:#2ca02c}.fail{color:#d62728}.weak{color:#ff7f0e}small{color:#666}
#nav{position:fixed;top:0;left:0;bottom:0;width:200px;overflow-y:auto;background:#fafafa;border-right:1px solid #e0e0e0;padding:10px;box-sizing:border-box;font-size:13px}
#nav a{display:inline-block;margin:1px 4px 1px 0;text-decoration:none;color:#1f77b4}
#nav a.cur{font-weight:700;color:#d62728}
#nav .nm{color:#444;margin-right:2px}
#main{margin-left:212px;padding:0 12px}
a.back{display:inline-block;margin:8px 0;color:#1f77b4;text-decoration:none;font-size:14px}
@media (max-width:800px){#nav{display:none}#main{margin-left:0}}</style>"""

def bsp_table(res: AnalysisResult) -> str:
    rows = []
    for p in reversed(res.bsps):
        checks = "".join(f"<li class='{c.status}'>{'✅' if c.status=='pass' else '❌' if c.status=='fail' else '⚠️'} {html.escape(c.cond)} <small>{html.escape(c.value)}</small></li>" for c in p.checklist)
        risks = "".join(f"<li>{html.escape(r)}</li>" for r in p.risks)
        rows.append(f"<tr><td>{p.ts.strftime('%Y-%m-%d %H:%M') if res.meta.get('level') in ('5m','30m') else p.ts.date()}</td><td>{p.type}</td>"
                    f"<td class='{p.grade}'>{'严格成立' if p.grade=='strict' else '疑似/待确认'}</td><td>{'已确认' if p.confirmed else '当下候选'}"
                    f"{('<br><small>确认于 ' + str(p.confirmed_at.date()) + '</small>') if p.confirmed_at is not None else ''}</td>"
                    f"<td>{html.escape(p.reason_short)}<details><summary>详情</summary><b>判定清单</b><ul>{checks}</ul><b>教学说明</b><p>{html.escape(p.teaching)}</p>"
                    f"<b>薄弱环节与风险</b><ul>{risks or '<li>无</li>'}</ul></details></td></tr>")
    return "<table><tr><th>时间</th><th>类型</th><th>规则满足度</th><th>状态</th><th>理由</th></tr>" + "".join(rows) + "</table>" if rows else "<p>本级别无买卖点</p>"

def nav_html(rows: list[dict], cur_code: str, cur_level: str, index_name: str = "index.html") -> str:
    """左侧自选股池导航：所有股票 × 级别的链接，当前页高亮。"""
    by_code: dict[str, list[dict]] = {}
    for r in rows:
        by_code.setdefault(r["code"], []).append(r)
    items = []
    for code, its in by_code.items():
        name = its[0]["name"]
        links = " ".join(
            "<a href='%s'%s>%s</a>" % (i["file"], " class='cur'" if i["code"] == cur_code and i["level"] == cur_level else "", i["level"])
            for i in its)
        badge = "<small>🔴</small>" if any("买" in (i["last_bsp"] or "") for i in its) else ("<small>🟢</small>" if any("卖" in (i["last_bsp"] or "") for i in its) else "")
        items.append(f"<div><span class='nm'>{html.escape(name)}</span>{badge} {links}</div>")
    return f"<div id='nav'><a class='back' href='{index_name}'>← 总览 / 自选股池</a>{''.join(items)}</div><div id='main'>"


def render_stock(res: AnalysisResult, path: Path, cfg: AppConfig, show_fx: bool = True, nav_rows: list[dict] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = build_figure(res, cfg.ui.max_render_bars, show_fx=show_fx)
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn", config={"scrollZoom": True, "displaylogo": False})
    hi = res.projection.get("level") if res.projection else None
    note = (f"<p><small>蓝色细线=笔，黑色粗线=线段，橙框=笔中枢（按所属线段切分），紫框=段中枢，浅蓝色块={hi}级别中枢投影；虚线=未确认（可能重画）。"
            f"实心三角=严格成立，空心=疑似。笔模式：{cfg.engine.bi.mode}。</small></p>")
    nav = nav_html(nav_rows, res.meta.get("code", ""), str(res.meta.get("level")), path.name if path.name != "index.html" else "index.html") if nav_rows else ""
    close = "</div>" if nav else ""
    body = (f"<!doctype html><html><head><meta charset='utf-8'><title>{res.meta.get('code')} {res.meta.get('name')} {res.meta.get('level')}</title>{_CSS}</head><body>"
            f"{nav}{chart}{note}<h3>买卖点（{res.meta.get('level')}）</h3>{bsp_table(res)}{close}</body></html>")
    path.write_text(body, encoding="utf-8")
    return path

def render_index(rows: list[dict], path: Path) -> Path:
    by_code: dict[str, list[dict]] = {}
    for r in rows:
        by_code.setdefault(r["code"], []).append(r)
    trs = []
    for code, items in by_code.items():
        name = items[0]["name"]
        links = " ".join(f"<a href='{i['file']}'>{i['level']}</a>" for i in items)
        last = "<br>".join(f"<small>{i['level']}: {html.escape(i['last_bsp'])}</small>" for i in items if i["last_bsp"])
        trs.append(f"<tr><td>{code}</td><td>{name}</td><td>{links}</td><td>{last}</td></tr>")
    path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>缠论工具 · 总览</title>{_CSS}</head><body><h2>自选股池</h2>"
                    f"<table><tr><th>代码</th><th>名称</th><th>级别</th><th>最新信号</th></tr>{''.join(trs)}</table></body></html>", encoding="utf-8")
    return path
