"""Streamlit 网页入口：自选股池 + 级别切换 + 图层开关 + 买卖点详情。由 `chan ui` 启动。"""
from __future__ import annotations
import copy
import sys
import time
from datetime import datetime

import streamlit as st

try:
    from ..config import load_config, Level
    from ..codes import normalize, CodeError
    from .. import watchlist as wl
    from .nav import allowed_levels, qp_str, resolve_nav
except ImportError:  # streamlit 直接执行本文件，无包上下文
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from chanlun.config import load_config, Level
    from chanlun.codes import normalize, CodeError
    from chanlun import watchlist as wl
    from chanlun.ui.nav import allowed_levels, qp_str, resolve_nav

st.set_page_config(page_title="缠论分析工具", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

cfg = load_config()
QP = st.query_params
_stocks = wl.load(cfg.root / "watchlist.yaml")
_codes = [s["code"] for s in _stocks]
_first = _codes[0] if _codes else ""


def _norm(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return normalize(raw).code
    except (CodeError, ValueError):
        return ""


# 首次进入才读 URL；之后以控件/session 为准，避免「只写了 level、没写 code」时被日线盖回去。
if "code" not in st.session_state or "level" not in st.session_state:
    raw_code, raw_level = resolve_nav(
        url_code=_norm(qp_str(QP.get("code"))),
        url_level=qp_str(QP.get("level")),
        session_code=st.session_state.get("code"),
        session_level=st.session_state.get("level"),
        first_code=_first,
        default_level=cfg.ui.default_level,
        remember=cfg.ui.remember_last,
    )
    st.session_state.code = raw_code
    st.session_state.level = raw_level

if _codes and st.session_state.get("code") not in _codes:
    st.session_state.code = _first
_allowed = allowed_levels(st.session_state.get("code") or "")
if st.session_state.get("level") not in _allowed:
    st.session_state.level = cfg.ui.default_level if cfg.ui.default_level in _allowed else _allowed[0]

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
    """每只自选股日线最新一条信号（按时间，不挑严格档）。"""
    out = {}
    for s in wl.load(cfg.root / "watchlist.yaml"):
        try:
            res = _assemble(s["code"], "D", cfg.engine.bi.mode, ver)
            b = max(res.bsps, key=lambda x: x.ts) if res.bsps else None
            out[s["code"]] = (
                f"{'🔴' if b.type.endswith('b') else '🟢'}{b.type}"
                f"{'·严格' if b.grade == 'strict' else ''} {b.ts.date()}"
            ) if b else ""
        except Exception:  # noqa: BLE001
            out[s["code"]] = ""
    return out

def _rerun(*, code: str | None = None, level: Level | None = None):
    c = st.session_state.get("code") if code is None else code
    lv = st.session_state.get("level") if level is None else level
    st.session_state.code = c or ""
    if c:
        QP["code"] = c
    elif "code" in QP:
        del QP["code"]
    if lv:
        st.session_state.level = lv
        QP["level"] = lv
    st.rerun()

# ---- 侧栏 ----
with st.sidebar:
    st.title("📈 缠论工具")
    stocks = _stocks
    badges = _badges(_version())
    cur = st.session_state.get("code") or ""
    with st.form("add_stock", clear_on_submit=True, border=False):
        add_box, add_btn = st.columns([0.72, 0.28], vertical_alignment="bottom")
        with add_box:
            add_raw = st.text_input("加入自选", placeholder="600519、00700 或 指南针", label_visibility="collapsed")
        with add_btn:
            add_clicked = st.form_submit_button("加入", width="stretch")
    if add_clicked:
        from chanlun.data.sina_provider import suggest_equities
        codes, err = wl.resolve_query(add_raw or "", local=_store().list_names(), remote=suggest_equities)
        if err:
            st.toast(err)
        else:
            added = wl.add(cfg.root / "watchlist.yaml", codes)
            target = (added or codes)[0]
            if added:
                if _store().count(target, "D") == 0:
                    from chanlun.data.updater import Updater
                    with st.spinner(f"正在拉取 {target} …"):
                        Updater(cfg, _store()).update(target)
                _badges.clear()
                _assemble.clear()
                _version.clear()
                st.toast(f"已加入 {' '.join(added)}")
            else:
                st.toast(f"{target} 已在自选")
            if target != cur:
                _rerun(code=target)
            else:
                st.rerun()
    if stocks:
        for s in stocks:
            c = s["code"]
            name = _store().get_name(c) or ""
            label = f"{c} {name}  {badges.get(c, '')}".rstrip()
            pick, drop = st.columns([0.86, 0.14], vertical_alignment="center")
            with pick:
                if st.button(label, key=f"pick_{c}", type="primary" if c == cur else "secondary", width="stretch"):
                    if c != cur:
                        _rerun(code=c)
            with drop:
                if st.button("删", key=f"rm_{c}", help=f"移出 {c}", width="stretch"):
                    wl.remove(cfg.root / "watchlist.yaml", c)
                    _badges.clear()
                    st.toast(f"已移除 {c}")
                    _rerun(code=wl.next_after_remove(_codes, c, cur))
    else:
        st.caption("自选股池为空")
    _allowed = allowed_levels(st.session_state.get("code") or "")
    if st.session_state.get("level") not in _allowed:
        st.session_state.level = cfg.ui.default_level if cfg.ui.default_level in _allowed else _allowed[0]

    if st.button("↻ 更新数据", width="stretch"):
            from chanlun.data.updater import Updater
            t0 = time.time()
            up = Updater(cfg, _store())
            msgs = up.update(cur)
            _assemble.clear(); _badges.clear(); _version.clear()
            st.toast(f"{cur} 更新完成（{time.time() - t0:.1f}s）: " + "; ".join(f"{k} {v.split(' ')[0]}" for k, v in msgs.items()))

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
            engine = d.setdefault("engine", {})
            bi = engine.get("bi")
            if not isinstance(bi, dict):
                bi = {}
                engine["bi"] = bi
            bi["mode"] = bi_mode
            d.setdefault("ui", {})["default_level"] = st.session_state.get("level")
            p.write_text(_yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            st.toast("已保存到 config.yaml")

# ---- 主区 ----
code = st.session_state.get("code") or ""
level = st.session_state.get("level")
allowed = allowed_levels(code)
if level not in allowed:
    level = cfg.ui.default_level if cfg.ui.default_level in allowed else allowed[0]
    st.session_state.level = level
if qp_str(QP.get("code")) != code and code:
    QP["code"] = code
if qp_str(QP.get("level")) != level and level:
    QP["level"] = level

if not code:
    st.warning("自选股池为空：请在左侧输入代码后点「加入」，或命令行 `chan import`。")
    st.stop()

st.segmented_control("级别", options=allowed, key="level")
level = st.session_state.level

t0 = time.time()
try:
    res = _assemble(code, level, bi_mode, _version())
except ValueError as e:
    st.error(str(e))
    st.stop()
calc_ms = (time.time() - t0) * 1000

from chanlun.render.narrative import analysis_markdown
from chanlun.render.plotly_chart import build_figure, show_figure
view = copy.copy(res)
if not show_zs_bi:
    view.zs_bi = []
if not show_zs_seg:
    view.zs_seg = []
if not show_proj:
    view.projection = {}
with st.container(border=True):
    st.markdown(analysis_markdown(res))
fig = build_figure(view, cfg.ui.max_render_bars, show_fx=show_fx, show_merged=show_merged)
show_figure(fig)

meta_bits = [f"计算 {calc_ms:.0f} ms", f"K线 {len(res.bars)} 根"]
if res.meta.get("stale"):
    meta_bits.append("⚠️ 数据上次更新失败，非最新")
st.caption(" · ".join(meta_bits))
st.caption("图例：蓝细线=笔，黑粗线=线段，橙框=笔中枢，紫框=段中枢，浅蓝色块=高一级中枢投影，虚线=未确认（可能重画）")

# 盘中未收盘提示
last_ts = res.bars.ts.iloc[-1]
now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo else datetime.now()
if (now - last_ts).total_seconds() < 8 * 3600 and now.weekday() < 5:
    st.caption("🕐 可能包含盘中数据，收盘后请点「更新数据」刷新")

# 买卖点（默认只列最近 12 条，避免满屏历史信号）
shown = sorted(res.bsps, key=lambda x: x.ts, reverse=True)
filt = st.radio("买卖点筛选", ["最近 12 条", "仅严格", "全部"], horizontal=True)
if filt == "仅严格":
    shown = [p for p in shown if p.grade == "strict"]
elif filt == "最近 12 条":
    shown = shown[:12]
st.subheader(f"买卖点（{level}，{len(shown)}/{len(res.bsps)}）")
if not res.bsps:
    st.info("本级别暂无买卖点")
elif not shown:
    st.info("当前筛选下没有买卖点")
for p in shown:
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
