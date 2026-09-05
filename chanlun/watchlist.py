"""自选股池读写。"""
from __future__ import annotations
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
