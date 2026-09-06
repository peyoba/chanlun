"""网页导航：股票代码与级别各自解析，互不覆盖。"""
from __future__ import annotations

from chanlun.config import LEVELS_CN, LEVELS_HK, Level


def qp_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    s = str(value).strip() if value is not None else ""
    return s or None


def allowed_levels(code: str) -> list[Level]:
    return list(LEVELS_HK if str(code).endswith(".HK") else LEVELS_CN)


def resolve_nav(
    *,
    url_code: str | None,
    url_level: str | None,
    session_code: str | None,
    session_level: str | None,
    first_code: str,
    default_level: str,
    remember: bool = True,
) -> tuple[str, Level]:
    """代码、级别分开取：URL 缺代码时不得把 URL 里的级别一并丢掉。"""
    code = url_code or (session_code if remember else None) or first_code
    allowed = allowed_levels(code)
    if url_level in allowed:
        level: str = url_level
    elif remember and session_level in allowed:
        level = session_level
    elif default_level in allowed:
        level = default_level
    else:
        level = allowed[-2] if len(allowed) > 1 else allowed[0]
    return code, level  # type: ignore[return-value]
