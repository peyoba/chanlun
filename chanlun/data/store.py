"""SQLite 本地缓存。"""
from __future__ import annotations
import hashlib, sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
from .base import COLUMNS
from ..config import Level

_SCHEMA = """
CREATE TABLE IF NOT EXISTS klines(
  code TEXT NOT NULL, level TEXT NOT NULL, ts TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, source TEXT,
  PRIMARY KEY(code, level, ts));
CREATE TABLE IF NOT EXISTS stocks(code TEXT PRIMARY KEY, name TEXT, market TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS update_log(
  code TEXT NOT NULL, level TEXT NOT NULL, last_ts TEXT, updated_at TEXT, status TEXT, message TEXT, source TEXT,
  PRIMARY KEY(code, level));
"""

class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Streamlit 多会话会跨线程复用缓存的 Store，允许跨线程；并发写入由 SQLite 自身加锁保护
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.executescript(_SCHEMA)

    def close(self):
        self.conn.close()

    # ---- klines ----
    def upsert_klines(self, code: str, level: Level, df: pd.DataFrame, source: str) -> int:
        if df.empty:
            return 0
        rows = [(code, level, r.ts.strftime("%Y-%m-%d %H:%M:%S"), r.open, r.high, r.low, r.close,
                 None if pd.isna(r.volume) else float(r.volume), None if pd.isna(r.amount) else float(r.amount), source)
                for r in df.itertuples(index=False)]
        with self.conn:
            self.conn.executemany("INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def replace_klines(self, code: str, level: Level, df: pd.DataFrame, source: str) -> int:
        with self.conn:
            self.conn.execute("DELETE FROM klines WHERE code=? AND level=?", (code, level))
        return self.upsert_klines(code, level, df, source)

    def load_klines(self, code: str, level: Level, as_of: datetime | None = None, limit: int | None = None) -> pd.DataFrame:
        q = "SELECT ts, open, high, low, close, volume, amount FROM klines WHERE code=? AND level=?"
        args: list = [code, level]
        if as_of is not None:
            q += " AND ts<=?"
            args.append(pd.Timestamp(as_of).strftime("%Y-%m-%d %H:%M:%S"))
        q += " ORDER BY ts"
        df = pd.read_sql_query(q, self.conn, params=args)
        df["ts"] = pd.to_datetime(df["ts"])
        if limit:
            df = df.tail(limit).reset_index(drop=True)
        return df[COLUMNS]

    def last_ts(self, code: str, level: Level) -> pd.Timestamp | None:
        r = self.conn.execute("SELECT MAX(ts) FROM klines WHERE code=? AND level=?", (code, level)).fetchone()
        return pd.Timestamp(r[0]) if r and r[0] else None

    def count(self, code: str, level: Level) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM klines WHERE code=? AND level=?", (code, level)).fetchone()[0]

    # ---- stocks ----
    def set_name(self, code: str, name: str, market: str):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO stocks VALUES (?,?,?,?)", (code, name, market, datetime.now().isoformat(timespec="seconds")))

    def get_name(self, code: str) -> str | None:
        r = self.conn.execute("SELECT name FROM stocks WHERE code=?", (code,)).fetchone()
        return r[0] if r else None

    def list_names(self) -> list[tuple[str, str]]:
        return list(self.conn.execute("SELECT code, name FROM stocks WHERE name IS NOT NULL AND name != ''"))

    # ---- log ----
    def log(self, code: str, level: Level, last_ts, status: str, message: str = "", source: str = ""):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO update_log VALUES (?,?,?,?,?,?,?)",
                              (code, level, None if last_ts is None else pd.Timestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S"),
                               datetime.now().isoformat(timespec="seconds"), status, message, source))

    def get_log(self, code: str, level: Level) -> dict | None:
        r = self.conn.execute("SELECT last_ts, updated_at, status, message, source FROM update_log WHERE code=? AND level=?", (code, level)).fetchone()
        return None if r is None else dict(zip(["last_ts", "updated_at", "status", "message", "source"], r))

    def all_logs(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM update_log ORDER BY code, level", self.conn)


def data_hash(df: pd.DataFrame) -> str:
    """K 线内容哈希，用于缓存键。"""
    if df.empty:
        return "empty"
    h = hashlib.sha1()
    h.update(pd.util.hash_pandas_object(df[["ts", "open", "high", "low", "close"]], index=False).values.tobytes())
    return h.hexdigest()[:12]
