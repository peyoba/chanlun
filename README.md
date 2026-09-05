# chanlun · 缠论分析工具

A 股 / 港股多级别缠论分析：笔、线段、中枢、买卖点（严格 / 疑似两档 + 理由）计算与绘图。

文档见 `docs/`（先读 `docs/00-项目总览.md`）。进度见 `docs/reports/进度.md`。

## 快速开始

```bash
# 首次安装（Python 3.11+）
python3 -m venv .venv
.venv/bin/pip install -e ".[ui]"

# 拉数据（自选股池见 watchlist.yaml）
.venv/bin/chan update --all

# 生成静态图 / 总览
.venv/bin/chan plot 600519 -l D --open
.venv/bin/chan pool

# 启动网页（或直接双击 启动缠论工具.command）
.venv/bin/chan ui
```

## 常用命令

- `chan update [代码...] [--all] [-l D,30m] [--full]`：数据入库（日 / 周全量，分钟增量）
- `chan plot 代码 -l D [--bi old|new]`：单股 HTML 图
- `chan pool [-l D]`：自选股池批量出图 + index.html 总览
- `chan ui [--port 8501]`：Streamlit 网页
- `chan import -`：粘贴 / 文件批量导入自选股
- `chan status`：缓存状态

## 测试

```bash
.venv/bin/python -m pytest -q   # unit / golden / replay / crossval
```
