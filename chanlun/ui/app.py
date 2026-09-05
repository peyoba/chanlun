"""Streamlit 网页入口：自选股池 + 级别切换 + 图层开关 + 买卖点详情。由 `chan ui` 启动。"""
from __future__ import annotations
import copy
import sys
import time
from datetime import datetime

import streamlit as st

try:
    from ..config import load_config, Level, LEVELS_CN, LEVELS_HK
    from ..codes import normalize, CodeError
    from .. import watchlist as wl
except ImportError:  # streamlit 直接执行本文件，无包上下文
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from chanlun.config import load_config, Level, LEVELS_CN, LEVELS_HK
    from chanlun.codes import normalize, CodeError
    from chanlun import watchlist as wl

st.set_page_config(page_title="缠论分析工具", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

cfg = load_config()
QP = st.query_params

# ---- 状态记忆与 URL 参数 ----
def _initial() -> tuple[str, Level]:
    code = QP.get("code")
    level = QP.get("level")
    if not code and cfg.ui.remember_last and "code" in st.session_state:
        code, level = st.session_state.get("code"), st.session_state.get("level")
    stocks = wl.load(cfg.root / "watchlist.yaml")
    code = code or (stocks[0]["code"] if stocks else "")
    try:
        code = normalize(code).code
    except (CodeError, ValueError):
        code = ""
    market = code.endswith(".HK") if code else False
    allowed = LEVELS_HK if market else LEVELS_CN
    if level not in allowed:
        level = cfg.ui.default_level if cfg.ui.default_level in allowed else allowed[-2]
    return code, level  # type: ignore

code, level = _initial()

# ---- 引擎与数据（缓存） ----
@st.cache_resource
def _store():
    from chanlun.data.store import Store
    return Store(cfg.db_path)

@st.cache_data(ttl=300, show_spinner=False)
def _version() -> str:
    s = _store()
    df = s.all_logs()
    return "" if df.empty else str(df["updated_at"].max())

@st.cache_data(ttl=300, show_spinner="计算缠论结构…")
def _assemble(code: str, level: str, bi_mode: str, ver: str):
    from chanlun.engine.assemble import assemble
    c = copy.deepcopy(cfg)
    c.engine.bi.mode = bi_mode  # type: ignore
    return assemble(code, level, c, store=_store())  # type: ignore

@st.cache_data(ttl=600, show_spinner=False)
def _badges(ver: str) -> dict[str, str]:
    """每只自选股日线最新信号徽标。"""
    out = {}
    for s in wl.load(cfg.root / "watchlist.yaml"):
        try:
            res = _assemble(s["code"], "D", cfg.engine.bi.mode, ver)
            strict = [b for b in res.bsps if b.grade == "strict"]
            b = (strict or res.bsps)[-1] if res.bsps else None
            out[s["code"]] = f"{'🔴' if b and b.type.endswith('b') else '🟢' if b else ''}{b.type}{'·严格' if b and b.grade == 'strict' else ''} {b.ts.date()}" if b else ""
        except Exception:  # noqa: BLE001
            out[s["code"]] = ""
    return out

def _rerun(code: str | None = None, level: Level | None = None):
    if code:
        QP["code"] = code
    if level:
        QP["level"] = level
    st.rerun()

# ---- 侧栏 ----
with st.sidebar:
    st.title("📈 缠论工具")
    stocks = wl.load(cfg.root / "watchlist.yaml")
    badges = _badges(_version())
    sel = st.radio("自选股池", options=[s["code"] for s in stocks],
                   format_func=lambda c: f"{c} {(_store().get_name(c) or '')}  {badges.get(c, '')}",
                   index=[s["code"] for s in stocks].index(code) if code in [s["code"] for s in stocks] else 0,
                   label_visibility="collapsed")
    if sel != code:
        _rerun(code=sel)

    if st.button("↻ 更新数据", width="stretch"):
            from chanlun.data.updater import Updater
            t0 = time.time()
            up = Updater(cfg, _store())
            msgs = up.update(code)
            _assemble.clear(); _badges.clear(); _version.clear()
            st.toast(f"{code} 更新完成（{time.time() - t0:.1f}s）: " + "; ".join(f"{k} {v.split(' ')[0]}" for k, v in msgs.items()))

    with st.expander("➕ 加入 / 移除自选股"):
        txt = st.text_area("粘贴代码（支持逗号 / 空格 / 换行，如 600519 或 00700）", height=80)
        if st.button("加入股池", width="stretch"):
            added = wl.add(cfg.root / "watchlist.yaml", wl.parse_codes(txt))
            st.toast(f"新增 {len(added)} 个: {' '.join(added) or '无'}")
            if added:
                _badges.clear(); _rerun(code=added[0])
        targets = [s["code"] for s in stocks if s["code"] != code]
        rm = st.selectbox("移除", ["（选择）"] + targets)
        if st.button("移除所选", width="stretch") and rm != "（选择）":
            wl.remove(cfg.root / "watchlist.yaml", rm)
            _badges.clear()
            st.toast(f"已移除 {rm}")
            _rerun(code=stocks[0]["code"] if stocks and stocks[0]["code"] != rm else (targets[0] if targets else None))

    with st.expander("⚙️ 参数"):
        bi_mode = st.radio("笔模式", ["old", "new"], horizontal=True,
                           help="老笔=顶底间至少1根独立K线；新笔=分型不共用K线")
        show_fx = st.toggle("分型标记", value=False)
        show_merged = st.toggle("合并K线", value=False)
        show_zs_bi = st.toggle("笔中枢", value=True)
        show_zs_seg = st.toggle("段中枢", value=True)
        show_proj = st.toggle("高一级投影", value=True)
        if st.button("保存为默认（写入 config.yaml）", width="stretch"):
            import yaml as _yaml
            p = cfg.root / "config.yaml"
            d = _yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
            d.setdefault("engine", {})["bi"] = {"mode": bi_mode}
            d.setdefault("ui", {})["default_level"] = level
            p.write_text(_yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            st.toast("已保存到 config.yaml")

# ---- 主区 ----
st.session_state["code"], st.session_state["level"] = code, level

if not code:
    st.warning("自选股池为空：请在左侧「加入 / 移除自选股」中粘贴代码，或命令行 `chan import`。")
    st.stop()

# 级别切换
allowed = LEVELS_HK if code.endswith(".HK") else LEVELS_CN
cols = st.columns([1] + [1] * len(allowed) + [5])
with cols[0]:
    st.markdown("**级别**")
for i, lv in enumerate(allowed):
    with cols[i + 1]:
        if st.button(f"**{lv}**" if lv == level else lv, width="stretch",
                     type="primary" if lv == level else "secondary"):
            _rerun(level=lv)

t0 = time.time()
res = _assemble(code, level, bi_mode, _version())
calc_ms = (time.time() - t0) * 1000

from chanlun.render.plotly_chart import build_figure
view = copy.copy(res)
if not show_zs_bi:
    view.zs_bi = []
if not show_zs_seg:
    view.zs_seg = []
if not show_proj:
    view.projection = {}
fig = build_figure(view, cfg.ui.max_render_bars, show_fx=show_fx, show_merged=show_merged)
st.plotly_chart(fig, width="stretch", config={"scrollZoom": True, "displaylogo": False})

meta_bits = [f"计算 {calc_ms:.0f} ms", f"K线 {len(res.bars)} 根"]
if res.meta.get("stale"):
    meta_bits.append("⚠️ 数据上次更新失败，非最新")
st.caption(" · ".join(meta_bits) + "　图例：蓝细线=笔，黑粗线=线段，橙框=笔中枢，紫框=段中枢，浅蓝色块=高一级中枢投影，虚线=未确认（可能重画）")

# 盘中未收盘提示
last_ts = res.bars.ts.iloc[-1]
now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo else datetime.now()
if (now - last_ts).total_seconds() < 8 * 3600 and now.weekday() < 5:
    st.caption("🕐 可能包含盘中数据，收盘后请点「更新数据」刷新")

# 买卖点
st.subheader(f"买卖点（{level}，共 {len(res.bsps)} 个）")
if not res.bsps:
    st.info("本级别暂无买卖点")
for p in reversed(res.bsps):
    grade_badge = "🔴 严格成立" if p.grade == "strict" else "🟡 疑似/待确认"
    state = "已确认" if p.confirmed else "当下候选"
    with st.expander(f"{'🟢' if p.type.endswith('b') else '🔻'} {p.type}　{p.ts:%Y-%m-%d %H:%M}　{grade_badge}　{state}"):
        st.markdown(f"**理由**：{p.reason_short}")
        st.markdown("**判定清单**")
        for c in p.checklist:
            icon = {"pass": "✅", "fail": "❌", "weak": "⚠️"}.get(c.status, "")
            st.markdown(f"- {icon} **{c.cond}**：{c.value}")
        if p.risks:
            st.markdown("**薄弱环节与风险**")
            for r in p.risks:
                st.markdown(f"- {r}")
        st.caption(p.teaching)
