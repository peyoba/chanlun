"""把本级别引擎结果写成可读的缠论结构说明。只陈述已算出的结构，不给交易建议。"""
from __future__ import annotations
import html
import re
from typing import Any

from ..engine.models import Bi, BSP, LevelResult, Seg, ZhongShu

_LEVEL = {"5m": "5分钟", "30m": "30分钟", "D": "日线", "W": "周线"}
_DIR = {"up": "向上", "down": "向下"}
_STAIR = {"up": "上台阶", "down": "下台阶"}
_CASE = {"case1": "第一种情况", "case2": "第二种情况", "pending": "未完成"}
_BSP = {
    "1b": "一买", "1s": "一卖", "2b": "二买", "2s": "二卖", "3b": "三买", "3s": "三卖",
    "2b_like": "类二买", "2s_like": "类二卖",
}


def analysis_markdown(res: LevelResult) -> str:
    return "\n\n".join(analysis_paragraphs(res))


def analysis_html(res: LevelResult) -> str:
    parts: list[str] = []
    for raw in analysis_paragraphs(res):
        if raw.startswith("### "):
            parts.append(f"<h3>{html.escape(raw[4:])}</h3>")
            continue
        escaped = html.escape(raw)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        parts.append(f"<p>{escaped}</p>")
    return '<section class="analysis">' + "".join(parts) + "</section>"


def analysis_paragraphs(res: LevelResult) -> list[str]:
    meta = res.meta or {}
    level = str(meta.get("level") or "")
    code = str(meta.get("code") or "")
    name = str(meta.get("name") or "")
    title = " ".join(x for x in (name, code) if x) or "未命名"
    paras = [f"### {title} · {_LEVEL.get(level, level or '本级别')}"]

    if res.bars is None or len(res.bars) == 0:
        paras.append("本级别没有 K 线，无法写结构。")
        return paras

    last_ts = res.bars.ts.iloc[-1]
    close = float(res.bars.close.iloc[-1])
    paras.append(f"数据截至 {_fmt_ts(last_ts, level)}。以下只陈述本级别已算出的结构，不是买卖建议。")
    paras.append(_now_para(res, close))
    paras.append(_trend_para(res))
    if res.segs or res.bis:
        paras.append(_path_para(res))
    paras.append(_zs_para(res))
    paras.append(_bsp_para(res, last_ts, level))
    proj = getattr(res, "projection", None) or {}
    if proj:
        paras.append(_proj_para(proj))
    return paras


def _now_para(res: LevelResult, close: float) -> str:
    bits = [f"收 {_px(close)}"]
    zs = res.zs_seg[-1] if res.zs_seg else (res.zs_bi[-1] if res.zs_bi else None)
    if zs is not None:
        kind = "段" if zs.kind == "seg" else "笔"
        bits.append(f"在{kind}中枢#{zs.id} [{_px(zs.zd)}, {_px(zs.zg)}] {_where(close, zs)}")
    if res.segs:
        s = res.segs[-1]
        bits.append(f"当前线段#{s.id} {_DIR[s.dir]} {_px(s.start_price)} → {_px(s.end_price)}，{_CASE.get(s.end_case, s.end_case)}、{_conf(s.confirmed)}")
    if res.bis:
        bits.append(_bi_now(res.bis[-1]))
    return "**当下**：" + "；".join(bits) + "。"


def _bi_now(b: Bi) -> str:
    head = f"末笔{_DIR[b.dir]} {_px(b.start_price)} → {_px(b.end_price)}"
    if b.candidate:
        return head + "（候选，可能作废）"
    if not b.confirmed:
        return head + "（未确认，后续可能重画）"
    return head + "（已确认）"


def _trend_para(res: LevelResult) -> str:
    trend = res.trend or {}
    seg = _trend_seg(trend.get("seg") or {}, res.zs_seg, res.segs[-1] if res.segs else None)
    bi = _trend_bi(trend.get("bi") or {}, res.zs_bi)
    return f"**走势**：{seg}；{bi}。"


def _trend_seg(t: dict[str, Any], zss: list[ZhongShu], cur: Seg | None) -> str:
    kind = t.get("type")
    if not kind or kind == "none":
        return "段级别尚不足以判定走势类型"
    last = zss[-1] if zss else None
    if kind == "range":
        if len(zss) >= 2:
            return "段级别最近两个中枢重叠，按盘整计"
        return "段级别按盘整计（目前只有 1 个段中枢）"
    n = t.get("zs_count") or 0
    stair = _STAIR.get(t.get("dir") or "", "台阶")
    text = f"段中枢连成 {n} 级{stair}"
    if last is not None and last.leave_id is None:
        text += "，最后一级还在延伸"
        extra = _leave_why(last, cur, "段")
        if extra:
            text += f"（{extra}）"
    return text


def _trend_bi(t: dict[str, Any], zss: list[ZhongShu]) -> str:
    kind = t.get("type")
    if not kind or kind == "none":
        return "笔级别尚不足以判定"
    if kind == "range":
        if len(zss) >= 2:
            return "笔级别最近两个中枢重叠，按盘整计"
        return "笔级别按盘整计（目前只有 1 个笔中枢）"
    n = t.get("zs_count") or 0
    stair = _STAIR.get(t.get("dir") or "", "台阶")
    return f"笔中枢连成 {n} 级{stair}"


def _leave_why(zs: ZhongShu, cur: Seg | None, unit: str) -> str:
    if zs.leave_id is not None:
        return ""
    if cur is not None and _overlaps(cur.high, cur.low, zs):
        return f"当前{unit}#{cur.id} 仍与中枢有交集，按规则不算离开"
    return "还没有完全在区间外的下一段"


def _path_para(res: LevelResult) -> str:
    if not res.segs:
        return f"**线段**：尚无成段，共 {len(res.bis)} 笔。"
    cur = res.segs[-1]
    bits = [f"当前#{cur.id} {_DIR[cur.dir]} {_px(cur.start_price)} → {_px(cur.end_price)}（{_CASE.get(cur.end_case, cur.end_case)}，{_conf(cur.confirmed)}）"]
    if len(res.segs) > 1:
        prev = res.segs[-2]
        bits.append(f"上一#{prev.id} {_DIR[prev.dir]} {_px(prev.start_price)} → {_px(prev.end_price)}（{_CASE.get(prev.end_case, prev.end_case)}，{_conf(prev.confirmed)}）")
    return "**线段**：" + "；".join(bits) + "。"


def _zs_para(res: LevelResult) -> str:
    parts: list[str] = []
    if res.zs_seg:
        parts.append(_zs_brief(res.zs_seg[-1], res.segs[-1] if res.segs else None))
    else:
        parts.append("尚无段中枢")
    if res.zs_bi:
        parts.append(_zs_brief(res.zs_bi[-1], None))
    else:
        parts.append("尚无笔中枢")
    return "**中枢**：" + "；".join(parts) + "。"


def _zs_brief(z: ZhongShu, cur: Seg | None) -> str:
    unit = "段" if z.kind == "seg" else "笔"
    n = len(z.elems)
    rng = "区间已确认" if z.range_confirmed else "区间未确认"
    if z.ended or z.end_confirmed:
        ended = f"已结束，离开{unit}#{z.leave_id}" if z.leave_id is not None else "已结束"
    elif z.leave_id is None:
        why = _leave_why(z, cur, unit) if z.kind == "seg" else "还在延伸"
        ended = why or "还在延伸"
    else:
        ended = f"离开{unit}#{z.leave_id}，回抽未确认结束"
    return f"{unit}中枢#{z.id} [{_px(z.zd)}, {_px(z.zg)}]（共 {n} {unit}，{rng}，{ended}）"


def _bsp_para(res: LevelResult, last_ts, level: str) -> str:
    if not res.bsps:
        return "**买卖点**：本级别暂无买卖点。下方列表可逐条看判定清单。"
    p = max(res.bsps, key=lambda x: x.ts)
    name = _bsp_name(p.type)
    grade = "严格" if p.grade == "strict" else "疑似"
    state = "已确认" if p.confirmed else "当下候选"
    age = ""
    try:
        days = (last_ts - p.ts).days
        if days > 60:
            age = f"距今 {days} 天，较远，当下以结构位置为主。"
    except TypeError:
        age = ""
    reason = (p.reason_short or "").rstrip("。")
    tail = f"{reason}。" if reason else ""
    anchor = _bsp_anchor(p, res)
    return (
        f"**买卖点**：时间最近一条是 {_fmt_ts(p.ts, level)} 的{grade}{name}（{state}）。"
        f"{age}{anchor}{tail}下方列表可逐条看判定清单。"
    ).replace("。。", "。")


def _bsp_name(t: str) -> str:
    if t in _BSP:
        return _BSP[t]
    return "+".join(_BSP.get(p, p) for p in t.split("+"))


def _bsp_anchor(p: BSP, res: LevelResult) -> str:
    zs_id = p.refs.get("zs")
    if zs_id is None:
        return ""
    pool = res.zs_seg if p.zs_kind == "seg" else res.zs_bi
    z = next((x for x in pool if x.id == zs_id), None)
    if z is None:
        return ""
    unit = "段" if z.kind == "seg" else "笔"
    text = f"对应{'已结束的' if z.ended or z.end_confirmed else ''}{unit}中枢#{z.id} [{_px(z.zd)}, {_px(z.zg)}]"
    last = pool[-1] if pool else None
    if last is not None and last.id != z.id:
        text += f"，不是当下这{unit}中枢#{last.id}"
    return text + "。"


def _proj_para(proj: dict[str, Any]) -> str:
    hi = proj.get("level") or "高一级"
    if proj.get("missing"):
        return f"**高一级**：{_LEVEL.get(hi, hi)}数据缺失，本图无投影。"
    zss = proj.get("zs") or []
    if not zss:
        return f"**高一级**：已叠加 {_LEVEL.get(hi, hi)} 投影，当前无中枢。"
    last = zss[-1]
    return (
        f"**高一级**：{_LEVEL.get(hi, hi)}中枢投影 {len(zss)} 个；"
        f"最近一个 [{_px(last.get('zd'))}, {_px(last.get('zg'))}]。"
    )


def _where(close: float, zs: ZhongShu) -> str:
    if close > zs.zg:
        return "上方"
    if close < zs.zd:
        return "下方"
    return "内部"


def _overlaps(high: float, low: float, zs: ZhongShu) -> bool:
    return high >= zs.zd and low <= zs.zg


def _conf(ok: bool) -> str:
    return "已确认" if ok else "未确认"


def _px(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_ts(ts, level: str) -> str:
    try:
        if level in ("5m", "30m"):
            return ts.strftime("%Y-%m-%d %H:%M")
        return ts.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return str(ts)
