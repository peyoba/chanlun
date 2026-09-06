"""chan 命令行入口。"""
from __future__ import annotations
import logging, sys, webbrowser
from pathlib import Path
from typing import Optional
import typer
from .config import load_config, Level, LEVELS_CN, LEVELS_HK
from .codes import normalize, CodeError
from . import watchlist as wl

app = typer.Typer(help="缠论分析工具", no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

def _levels(arg: Optional[str]) -> Optional[list[Level]]:
    return [x.strip() for x in arg.split(",")] if arg else None  # type: ignore

@app.command()
def update(codes: list[str] = typer.Argument(None, help="代码，可多个；不填则用 --all"),
           all: bool = typer.Option(False, "--all", help="更新自选股池全部"),
           levels: Optional[str] = typer.Option(None, "--levels", "-l", help="逗号分隔，如 D,30m"),
           full: bool = typer.Option(False, "--full", help="分钟线也全量重拉")):
    """拉取数据入库（日 / 周全量覆盖，分钟增量）。"""
    from .data.store import Store
    from .data.updater import Updater
    cfg = load_config()
    targets = list(codes or [])
    if all or not targets:
        targets += [s["code"] for s in wl.load(cfg.root / "watchlist.yaml")]
    if not targets:
        typer.echo("没有目标：请给代码或先建 watchlist.yaml"); raise typer.Exit(1)
    store = Store(cfg.db_path)
    up = Updater(cfg, store)
    for c in targets:
        try:
            res = up.update(c, _levels(levels), full)
        except CodeError as e:
            typer.echo(f"{c}: {e}"); continue
        name = store.get_name(normalize(c).code) or ""
        for lv, msg in res.items():
            typer.echo(f"{normalize(c).code} {name} {lv:>3}: {msg}")
    store.close()

@app.command()
def plot(code: str, level: str = typer.Option("D", "--level", "-l"),
         bi: Optional[str] = typer.Option(None, "--bi", help="old | new"),
         open_: bool = typer.Option(False, "--open", help="生成后用浏览器打开"),
         out: Optional[Path] = typer.Option(None, "--out")):
    """生成单股静态 HTML 图。"""
    from .engine.assemble import assemble
    from .render.html_report import render_stock
    cfg = load_config()
    if bi:
        cfg.engine.bi.mode = bi  # type: ignore
    c = normalize(code)
    res = assemble(c.code, level, cfg)  # type: ignore
    path = out or cfg.root / "output" / f"{c.code}_{level}.html"
    render_stock(res, path, cfg)
    typer.echo(f"已生成 {path}")
    if open_:
        webbrowser.open(path.as_uri())

@app.command()
def pool(levels: Optional[str] = typer.Option("D", "--levels", "-l")):
    """自选股池批量生成 + index.html 总览。"""
    from .engine.assemble import assemble
    from .render.html_report import render_stock, render_index
    cfg = load_config()
    stocks = wl.load(cfg.root / "watchlist.yaml")
    out_dir = cfg.root / "output"; out_dir.mkdir(exist_ok=True)
    rows = []
    for s in stocks:
        c = normalize(s["code"])
        lvs = _levels(levels) or (LEVELS_CN if c.market == "CN" else LEVELS_HK)
        for lv in lvs:
            if c.market == "HK" and lv not in LEVELS_HK:
                continue
            try:
                res = assemble(c.code, lv, cfg)
                p = out_dir / f"{c.code}_{lv}.html"
                render_stock(res, p, cfg)
                rows.append({"code": c.code, "name": res.meta.get("name", ""), "level": lv, "file": p.name,
                             "last_bsp": res.bsps[-1].summary() if res.bsps else "", "bars": len(res.bars)})
                typer.echo(f"{c.code} {lv} ok")
            except Exception as e:  # noqa: BLE001
                typer.echo(f"{c.code} {lv} 失败: {e}")
    render_index(rows, out_dir / "index.html")
    typer.echo(f"总览: {out_dir / 'index.html'}")

@app.command("import")
def import_(file: str = typer.Argument("-", help="文件路径，或 - 读 stdin")):
    """批量导入代码到自选股池。"""
    cfg = load_config()
    text = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
    codes = wl.parse_codes(text)
    added = wl.add(cfg.root / "watchlist.yaml", codes)
    typer.echo(f"识别 {len(codes)} 个，新增 {len(added)} 个: {' '.join(added)}")

@app.command()
def verify(code: str, level: str = typer.Option("D", "--level", "-l")):
    """与 chan.py 交叉验证（开发环境：需克隆 tests/crossval/chan.py，见 tests/crossval/BASELINE.md）。"""
    import importlib.util
    cfg = load_config()
    script = cfg.root / "tests" / "crossval" / "run.py"
    if not script.exists():
        typer.echo(f"未找到 {script}：交叉验证脚本只在代码库开发环境中可用"); raise typer.Exit(1)
    spec = importlib.util.spec_from_file_location("chanlun_crossval_run", script)
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod  # 注册后再执行，dataclass 需要能找到模块
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    try:
        mod.run_verify(code, level)
    except RuntimeError as e:
        typer.echo(str(e)); raise typer.Exit(1)

@app.command()
def ui(port: Optional[int] = typer.Option(None, "--port")):
    """启动 Streamlit 网页。"""
    import subprocess
    cfg = load_config()
    app_path = Path(__file__).parent / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port or cfg.ui.port),
                    "--browser.gatherUsageStats", "false"], cwd=cfg.root)

@app.command()
def status():
    """显示缓存状态。"""
    from .data.store import Store
    cfg = load_config()
    store = Store(cfg.db_path)
    df = store.all_logs()
    typer.echo(df.to_string(index=False) if len(df) else "空")

if __name__ == "__main__":
    app()
