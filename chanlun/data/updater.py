"""增量更新：日 / 周线全量重拉覆盖（解决前复权整体变化）；分钟线增量拉取，检测到复权变化时全量重算。"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Callable
import pandas as pd
from .base import DataProvider, ProviderError
from .store import Store
from .baostock_provider import BaostockProvider
from .sina_provider import SinaProvider
from .tencent_provider import TencentProvider
from .sina_hk_provider import SinaHKProvider
from .yfinance_provider import YfinanceProvider
from ..codes import Code, normalize
from ..config import AppConfig, Level, LEVELS_CN, LEVELS_HK

log = logging.getLogger("chanlun.data")

_REGISTRY: dict[str, Callable[[], DataProvider]] = {
    "baostock": BaostockProvider, "sina": SinaProvider, "tencent": TencentProvider, "sina_hk": SinaHKProvider, "yfinance": YfinanceProvider,
}

def _history_start(spec: str) -> date | None:
    if spec == "all":
        return None
    n = int(spec[:-1])
    return date.today() - timedelta(days=365 * n if spec.endswith("y") else 30 * n)

class Updater:
    def __init__(self, cfg: AppConfig, store: Store):
        self.cfg = cfg
        self.store = store
        self._providers: dict[str, DataProvider] = {}

    def provider(self, name: str) -> DataProvider:
        if name not in self._providers:
            self._providers[name] = _REGISTRY[name]()
        return self._providers[name]

    def providers_for(self, code: Code, level: Level) -> list[DataProvider]:
        return [self.provider(n) for n in self.cfg.data.providers.get(code.market, []) if self.provider(n).supports(code, level)]

    def levels_for(self, code: Code) -> list[Level]:
        return LEVELS_CN if code.market == "CN" else LEVELS_HK

    def _fetch(self, code: Code, level: Level, start: date | None) -> tuple[pd.DataFrame, str]:
        errs = []
        for p in self.providers_for(code, level):
            try:
                df = p.get_klines(code, level, start, None)
                if not df.empty:
                    return df, p.name
                errs.append(f"{p.name}: 空数据")
            except ProviderError as e:
                errs.append(str(e))
                log.warning("%s %s %s 失败，切换备源: %s", code, level, p.name, e)
        raise ProviderError("; ".join(errs) or "无可用数据源")

    def update(self, raw_code: str, levels: list[Level] | None = None, full: bool = False) -> dict[str, str]:
        code = normalize(raw_code)
        results = {}
        if self.store.get_name(code.code) is None:
            self._update_name(code)
        for level in levels or self.levels_for(code):
            try:
                results[level] = self._update_level(code, level, full)
            except ProviderError as e:
                self.store.log(code.code, level, self.store.last_ts(code.code, level), "error", str(e))
                results[level] = f"失败: {e}"
        return results

    def _update_name(self, code: Code):
        for name in self.cfg.data.providers.get(code.market, []):
            try:
                n = self.provider(name).get_name(code)
            except Exception:  # noqa: BLE001
                n = None
            if n:
                self.store.set_name(code.code, n, code.market)
                return
        # 港股名称统一用腾讯
        try:
            n = self.provider("tencent").get_name(code)
            if n:
                self.store.set_name(code.code, n, code.market)
        except Exception:  # noqa: BLE001
            pass

    def _update_level(self, code: Code, level: Level, full: bool) -> str:
        hist_start = _history_start(self.cfg.data.history.get(level, "all"))
        last = self.store.last_ts(code.code, level)
        minute = level in ("5m", "30m")
        if full or last is None or not minute:
            # 日/周线：全量重拉覆盖；分钟线首次：全量
            df, src = self._fetch(code, level, hist_start)
            n = self.store.replace_klines(code.code, level, df, src)
            self.store.log(code.code, level, df.ts.iloc[-1], "ok", f"全量 {n} 根", src)
            return f"全量 {n} 根 ({src})"
        # 分钟线增量：从最后一根前 5 个交易日开始重拉，重叠部分用于检测复权变化
        start = (last - pd.Timedelta(days=7)).date()
        df, src = self._fetch(code, level, start)
        if df.empty:
            self.store.log(code.code, level, last, "ok", "无新数据", src)
            return "无新数据"
        old = self.store.load_klines(code.code, level)
        overlap = old.merge(df, on="ts", suffixes=("_old", "_new"))
        if len(overlap) and ((overlap.close_old - overlap.close_new).abs() / overlap.close_new > 1e-4).any():
            log.info("%s %s 检测到复权变化，分钟线全量重拉", code, level)
            df, src = self._fetch(code, level, hist_start)
            n = self.store.replace_klines(code.code, level, df, src)
            self.store.log(code.code, level, df.ts.iloc[-1], "ok", f"复权变化，全量 {n} 根", src)
            return f"复权变化，全量重拉 {n} 根 ({src})"
        new = df[df.ts > last]
        n = self.store.upsert_klines(code.code, level, new, src)
        self.store.log(code.code, level, df.ts.iloc[-1], "ok", f"增量 {n} 根", src)
        return f"增量 {n} 根 ({src})"
