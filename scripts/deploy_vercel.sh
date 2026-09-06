#!/bin/bash
# 更新数据 → 生成静态页 → 部署到 Vercel。先 vercel login 一次。
set -e
cd "$(dirname "$0")/.."
.venv/bin/chan update --all
.venv/bin/chan pool -l 5m,30m,D,W
cp vercel.json output/vercel.json 2>/dev/null; vercel deploy output --prod --yes
