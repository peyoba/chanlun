"""自选股池读写。"""
from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
import re, yaml
from .codes import normalize, CodeError

def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # BaseLoader：所有标量保持字符串，避免 YAML 1.1 把 00700 / 002466 解析成八进制整数
    d = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader) or {}
    out = []
    for s in d.get("stocks", []):
        try:
            c = normalize(str(s["code"]).strip())
        except CodeError:
            continue
        out.append({"code": c.code, "note": s.get("note", "")})
    return out

def save(path: Path, stocks: list[dict]):
    path.write_text(yaml.safe_dump({"stocks": stocks}, allow_unicode=True, sort_keys=False), encoding="utf-8")

def parse_codes(text: str) -> list[str]:
    """从任意文本提取代码：支持逗号 / 空格 / 换行 / 分号分隔。"""
    tokens = re.split(r"[\s,;，；、]+", text)
    out = []
    for t in tokens:
        if not t:
            continue
        try:
            c = normalize(t).code
        except CodeError:
            continue
        if c not in out:
            out.append(c)
    return out


def resolve_query(
    text: str,
    *,
    local: list[tuple[str, str]] | None = None,
    remote: Callable[[str], list[tuple[str, str]]] | None = None,
) -> tuple[list[str], str]:
    """代码或名称 → (代码列表, 错误)。有代码就按代码；否则查本地名称，再查远程联想。"""
    codes = parse_codes(text)
    if codes:
        return codes, ""
    q = (text or "").strip()
    if not q:
        return [], "请输入代码或名称"
    pairs = list(local or [])
    if remote is not None:
        try:
            pairs = pairs + list(remote(q) or [])
        except Exception:  # noqa: BLE001
            pass
    picked, err = _pick_name(q, pairs)
    if picked:
        return picked, ""
    return [], err or f"无法识别「{q}」，请输入代码如 600519 或 00700"


def _pick_name(q: str, pairs: list[tuple[str, str]]) -> tuple[list[str], str]:
    if not pairs:
        return [], ""
    exact = [(c, n) for c, n in pairs if n == q]
    pool = exact or [(c, n) for c, n in pairs if q in n]
    uniq: list[tuple[str, str]] = []
    seen: set[str] = set()
    for c, n in pool:
        if c in seen:
            continue
        seen.add(c)
        uniq.append((c, n))
    if len(uniq) == 1:
        return [uniq[0][0]], ""
    if len(uniq) > 1:
        shown = "、".join(f"{c} {n}" for c, n in uniq[:6])
        return [], f"「{q}」匹配到多只：{shown}，请输入代码"
    return [], ""

def add(path: Path, codes: list[str]) -> list[str]:
    stocks = load(path)
    have = {s["code"] for s in stocks}
    added = []
    for c in codes:
        if c not in have:
            stocks.append({"code": c, "note": ""})
            added.append(c)
    save(path, stocks)
    return added

def remove(path: Path, code: str):
    stocks = [s for s in load(path) if s["code"] != code]
    save(path, stocks)


def next_after_remove(codes: list[str], removed: str, current: str) -> str:
    """移除后还看哪只：没删当前就留下，删了就看列表里的下一只。"""
    remain = [c for c in codes if c != removed]
    if current in remain:
        return current
    return remain[0] if remain else ""
