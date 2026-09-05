"""配置加载。所有引擎阈值都在这里，不写死在代码里。"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field

Level = Literal["5m", "30m", "D", "W"]
LEVELS_CN: list[Level] = ["5m", "30m", "D", "W"]
LEVELS_HK: list[Level] = ["D", "W"]
LEVEL_ORDER: list[Level] = ["5m", "30m", "D", "W"]

def higher_level(level: Level) -> Level | None:
    i = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[i + 1] if i + 1 < len(LEVEL_ORDER) else None

def lower_level(level: Level) -> Level | None:
    i = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[i - 1] if i > 0 else None

class BiConfig(BaseModel):
    mode: Literal["old", "new"] = "old"
    fx_check: Literal["strict", "loss", "half", "totally"] = "strict"

class SegConfig(BaseModel):
    algo: Literal["feature_seq"] = "feature_seq"

class ZsConfig(BaseModel):
    kinds: list[Literal["bi", "seg"]] = ["bi", "seg"]
    bi_zs_cross_seg: bool = True   # M1 初版不加不跨线段约束；M2 改 False
    upgrade_hint_after: int = 9

class MacdConfig(BaseModel):
    fast: int = 12
    slow: int = 26
    signal: int = 9

class DivergenceConfig(BaseModel):
    metrics: list[Literal["area", "dif_peak"]] = ["area", "dif_peak"]
    zero_band: float | None = None   # M3 标定；None 时用 DIF 峰值的 20% 作相对带宽
    zero_band_ratio: float = 0.2

class BspConfig(BaseModel):
    types: list[int] = [1, 2, 3]
    sub_level_check: bool = True

class EngineConfig(BaseModel):
    bi: BiConfig = BiConfig()
    seg: SegConfig = SegConfig()
    zs: ZsConfig = ZsConfig()
    macd: MacdConfig = MacdConfig()
    divergence: DivergenceConfig = DivergenceConfig()
    bsp: BspConfig = BspConfig()

    def hash(self) -> str:
        return hashlib.sha1(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:12]

class DataConfig(BaseModel):
    providers: dict[str, list[str]] = {"CN": ["baostock", "sina"], "HK": ["sina_hk", "yfinance"]}
    db_path: str = "data/market.db"
    intraday_supplement: bool = True
    history: dict[str, str] = {"5m": "2y", "30m": "3y", "D": "all", "W": "all"}

class UiConfig(BaseModel):
    default_level: Level = "D"
    remember_last: bool = True
    port: int = 8501
    max_render_bars: int = 3000

class AppConfig(BaseModel):
    data: DataConfig = DataConfig()
    engine: EngineConfig = EngineConfig()
    ui: UiConfig = UiConfig()
    root: Path = Field(default_factory=lambda: Path.cwd())

    @property
    def db_path(self) -> Path:
        p = Path(self.data.db_path)
        return p if p.is_absolute() else self.root / p

def project_root() -> Path:
    """向上找 pyproject.toml，找不到用 cwd。"""
    p = Path(__file__).resolve().parent
    for cand in [p, *p.parents]:
        if (cand / "pyproject.toml").exists():
            return cand
    return Path.cwd()

def load_config(path: str | Path | None = None) -> AppConfig:
    root = project_root()
    cfg_path = Path(path) if path else root / "config.yaml"
    data = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = AppConfig(**data)
    cfg.root = root
    return cfg
