"""腾讯：股票名称（A 股 / 港股）。K 线接口保留但默认不启用：实测其港股 qfq 未处理 2014 年前的拆股。"""
from __future__ import annotations
from datetime import date
import pandas as pd, requests
from .base import ProviderError, finalize, COLUMNS
from ..codes import Code
from ..config import Level

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}

class TencentProvider:
    name = "tencent"

    def supports(self, code: Code, level: Level) -> bool:
        return code.market == "HK" and level in ("D", "W")

    def get_klines(self, code: Code, level: Level, start: date | None, end: date | None) -> pd.DataFrame:
        kind = "day" if level == "D" else "week"
        s = (start or date(2000, 1, 1)).isoformat()
        e = (end or date.today()).isoformat()
        frames = []
        # 接口单次最多约 2000 根左右，按年分段拉，前复权用 qfq
        cur_end = e
        seen = set()
        for _ in range(40):
            param = f"{code.tencent},{kind},{s},{cur_end},640,qfq"
            try:
                r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params={"param": param}, headers=_UA, timeout=15)
                data = r.json()["data"][code.tencent]
            except Exception as ex:  # noqa: BLE001
                raise ProviderError(f"tencent 拉取失败: {ex}") from ex
            k = data.get(f"qfq{kind}") or data.get(kind) or []
            rows = [x for x in k if x[0] not in seen]
            if not rows:
                break
            for x in rows:
                seen.add(x[0])
            frames.append(pd.DataFrame([x[:6] for x in rows], columns=["ts", "open", "close", "high", "low", "volume"]))
            first = rows[0][0]
            if len(k) < 640 or first <= s:
                break
            cur_end = (pd.Timestamp(first) - pd.Timedelta(days=1)).date().isoformat()
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.concat(frames)
        df["amount"] = float("nan")
        df["ts"] = pd.to_datetime(df["ts"])
        return finalize(df)

    def get_name(self, code: Code) -> str | None:
        try:
            r = requests.get(f"https://qt.gtimg.cn/q={code.tencent}", headers=_UA, timeout=8)
            txt = r.content.decode("gbk", errors="ignore")
            parts = txt.split("~")
            return parts[1] if len(parts) > 2 else None
        except Exception:  # noqa: BLE001
            return None
