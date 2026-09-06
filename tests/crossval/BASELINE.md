# 交叉验证基准（chan.py）

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/Vespa314/chan.py.git |
| 固定 commit | `429d6ed3043e27c93a003ba2b10e70a05575e1f5`（2026-06-25） |
| 本地位置 | `tests/crossval/chan.py/`（已 .gitignore，需自行克隆） |
| 运行脚本 | `tests/crossval/run.py`（`chan verify` 命令即调用它） |
| 数据 | 与本项目同一份 `data/market.db` K 线，逐根喂给 chan.py；报告中每行带 `data_hash`，数据变了哈希就变 |
| 依赖 | chan.py 核心计算只需标准库；本项目 venv 已含 numpy / pandas。绘图 / 策略模块（matplotlib、xgboost、PyQt）不需要 |

## 准备

```bash
git clone https://github.com/Vespa314/chan.py.git tests/crossval/chan.py
git -C tests/crossval/chan.py checkout 429d6ed3043e27c93a003ba2b10e70a05575e1f5
```

## 运行

```bash
.venv/bin/chan verify 600519 -l D                       # 单股单级别，打印一致率
.venv/bin/python tests/crossval/run.py --all -l D,W,30m,5m --report docs/reports/交叉验证报告.md
.venv/bin/python -m pytest -q tests/crossval            # 作为测试层：600519 日线笔端点一致率 ≥ 95%
```

## 配置对照（02 文档第 12 节）

| 本项目 | chan.py | 说明 |
|---|---|---|
| `bi.mode = old` | `bi_strict = True` | 老笔：顶底合并 K 线索引差 ≥ 4 |
| `bi.mode = new` | `bi_strict = False` | 新笔 |
| `bi.fx_check = strict` | `bi_fx_check = "strict"` | 分型价格条件 |
| 不计缺口 | `gap_as_kl = False` | |
| 笔端点为笔内极值（02 §3.4 补充） | `bi_end_is_peak = True` | 2026-09-05 交叉验证后补入我方 |
| 候选笔作废、前一笔延伸（02 §3.4.3） | `bi_allow_sub_peak = False` | 两边都不允许"次高低点成笔" |
| `seg.algo = feature_seq` | `seg_algo = "chan"`，`left_seg_method = "peak"` | 特征序列法 |
| `zs.bi_zs_cross_seg = false` | `zs_algo = "normal"` | 笔中枢不跨线段 |
| 不合并中枢 | `zs_combine = False` | |
| 买卖点 | `bs_type = "1,2,3a,3b"`，`macd_algo = "area"` | 仅参考对照 |

## 比较口径

- 笔 / 线段：端点 =（极值所在原始 K 线时间, 价格）；时间相同且价格相对误差 ≤ 1e-6 记为匹配。
- 中枢：ZG、ZD 都在 1e-6 相对误差内且时间区间有重叠。
- 一致率 = 2 × 匹配 / (我方数 + chan.py 数)。「已确认」只算我方 `confirmed` / chan.py `is_sure` 的结构。
- 差异自动归类：序列开头 / 末端未确认 / 同价异根 / 同根异价 / 端点位置差异 / 多少一笔一段 / 中枢无对应；逐条明细写到 `output/crossval/{code}_{level}.json`。

## 已知口径差异（详见 docs/reports/交叉验证报告.md）

1. **线段第二种情况**：我方按第 67 课——特征序列有缺口时，须反向线段成型才结束；成型前同向笔越过端点则原线段延续。chan.py 在 issue #272 中删掉了"越过端点则延续"的检查，因此强趋势中 chan.py 线段更多更短。
2. **线段末端**：chan.py 用 `collect_left_seg`（peak 法）把尾部笔强行收成未确认线段；我方末段标 `pending`。
3. **序列开头**：我方丢弃开头包含的 K 线并从第一个分型起算；chan.py 从第一根 K 线起并有专门的第一笔 / 第一段逻辑。只影响历史最前端。
