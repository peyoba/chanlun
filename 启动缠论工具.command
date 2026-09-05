#!/bin/bash
# 双击启动缠论工具网页（Streamlit）。首次运行会自动建虚拟环境。
cd "$(dirname "$0")"

if [ ! -x .venv/bin/chan ]; then
  echo "首次运行：正在初始化环境…"
  python3 -m venv .venv
  .venv/bin/python -m pip install -e ".[ui]" -q
fi

echo "启动中… 浏览器将自动打开 http://localhost:8501 （关闭本窗口即退出）"
.venv/bin/chan ui &
PID=$!
sleep 4
open "http://localhost:8501"
wait $PID
