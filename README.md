# LLM-Assisted Quantitative Trading Strategies

光华 BA 工作坊 · 量化交易策略课程作业

---

## 目录

- [项目概览](#项目概览)
- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [模块说明](#模块说明)
  - [数据获取 — `src/fetch_data.py`](#1-数据获取---srcfetch_datapy)
  - [通用工具 — `src/utils.py`](#2-通用工具---srcutilspy)
  - [数据可视化 — `src/visualize.py`](#3-数据可视化---srcvisualizepy)
  - [数据诊断 — `src/diagnose.py`](#4-数据诊断---srcdiagnosepy)
  - [技术指标 — `src/indicators.py`](#5-技术指标---srcindicatorspy)
- [数据资产](#数据资产)
- [MCP 配置](#mcp-配置)
- [已完成任务清单](#已完成任务清单)

---

## 项目概览

本项目围绕 **寒武纪 (688256.SH)** 过去一年的日线交易数据，完成了从数据获取、诊断分析到技术指标计算与可视化的完整流水线。

| 维度 | 说明 |
|---|---|
| **标的** | 寒武纪 Cambricon (688256.SH) — 中国 AI 芯片龙头，科创板上市 |
| **数据** | 243 个交易日 (2025-07-01 → 2026-07-01)，11 个字段 |
| **技术栈** | Python 3.13 · TuShare Pro · Pandas · Matplotlib · SciPy |
| **代码** | 5 个模块 |

---

## 仓库结构

```
quant/
├── data/
│   ├── raw/                          # 原始数据
│   │   └── 688256_daily.csv          #   TuShare 日线 (243×11)
│   └── processed/                    # 处理后数据
│       ├── 688256_daily_processed.csv #   可视化输出副本
│       └── indicators.csv            #   技术指标全量数据 (243×15)
├── src/                              # 源代码（5 模块，974 行）
│   ├── utils.py                      #   通用工具函数
│   ├── fetch_data.py                 #   数据获取 (TuShare)
│   ├── visualize.py                  #   收盘价可视化
│   ├── diagnose.py                   #   数据诊断分析
│   └── indicators.py                 #   技术指标计算与看板
├── notebooks/                        # Jupyter Notebook（预留）
├── docs/                             # 课程文档与报告
├── output/                           # 输出物
│   └── figures/
│       ├── 688256_close_price.png    #   收盘价曲线图
│       └── indicators_dashboard.png  #   技术指标综合看板
├── .gitignore
└── README.md
```

---

## 快速开始

### 环境准备

```bash
pip install tushare pandas matplotlib scipy numpy
```

### 设置 TuShare Token

```bash
export TUSHARE_TOKEN="your_token_here"
```

> Token 可在 [tushare.pro](https://tushare.pro) 注册后在「个人中心 → 接口TOKEN」获取。
> **至少需要 120 积分**才能调用 `daily` 接口（注册 100 + 完善个人资料 +20）。

### 运行流水线

```bash
# Step 1: 获取数据
python src/fetch_data.py

# Step 2: 收盘价可视化
python src/visualize.py

# Step 3: 数据诊断分析
python src/diagnose.py

# Step 4: 技术指标计算与看板
python src/indicators.py
```

---

## 模块说明

### 1. 数据获取 — `src/fetch_data.py`

通过 TuShare Pro API 获取指定 A 股的日线行情数据。

```
python src/fetch_data.py
```

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `TS_CODE` | `688256.SH` | TuShare 格式：代码+交易所后缀 |
| `START_DATE` | `20250701` | YYYYMMDD 格式 |
| `END_DATE` | `20260701` | 同上 |

**依赖**：`utils.get_token()`、`utils.save_to_csv()`

**输出**：`data/raw/688256_daily.csv` (243 行 × 11 列)

返回字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `change`, `pct_chg`, `vol`, `amount`

---

### 2. 通用工具 — `src/utils.py`

为所有模块提供共享函数，避免代码重复。

| 函数 | 用途 | 被引用方 |
|---|---|---|
| `load_data(csv_path, required_cols=None)` | 加载 CSV 并自动转换日期、排序 | visualize, diagnose, indicators |
| `save_to_csv(df, filepath)` | 保存 UTF-8 BOM CSV | fetch_data, visualize |
| `divider(title)` | 控制台分隔标题 | diagnose |
| `get_token()` | 从环境变量读取 TuShare Token | fetch_data |

---

### 3. 数据可视化 — `src/visualize.py`

读取原始 CSV，绘制收盘价曲线图并标注最高/最低点。

```
python src/visualize.py [csv_path]
```

**依赖**：`utils.load_data()`、`utils.save_to_csv()`

**输出**：
- `output/figures/688256_close_price.png` — 收盘价曲线图 (含最高/最低标注)
- `data/processed/688256_daily_processed.csv` — 处理后的数据副本

**统计摘要示例**：

| 指标 | 数值 |
|---|---|
| 交易日数 | 243 天 |
| 平均收盘价 | ¥1,206.48 |
| 最高收盘价 | ¥1,868.00 (2026-05-07) |
| 最低收盘价 | ¥523.50 (2025-07-10) |
| 标准差 | 268.11 |

---

### 4. 数据诊断 — `src/diagnose.py`

全面的数据质量检查，包含六个维度的分析：

```
python src/diagnose.py [csv_path]
```

**依赖**：`utils.load_data()`、`utils.divider()`

| 维度 | 内容 | 结论 |
|---|---|---|
| ① 缺失值 | 逐列 NaN 检测 | ✅ 全部 11 列零缺失 |
| ② 日期连续性 | 重复检测、自然日覆盖率 | ✅ 243 交易日，无重复 |
| ③ 描述性统计 | 均值/中位数/标准差/偏度/峰度/Q1/Q3/IQR/CV | 价格左偏，涨跌右偏 |
| ④ 数据完整性 | OHLC 逻辑校验 (high≥low 等) | ✅ 全部通过 |
| ⑤ 异常值 | IQR ×1.5 方法逐列检测 | 价格 ~9%异常 (高波动特征) |
| ⑥ 涨跌分布 | 涨跌天数比、平均涨跌幅 | 涨 53.9%，盈亏比 1.26 |

**描述性统计覆盖全部 9 个数值变量**：

- 价格类 (5)：`open`, `high`, `low`, `close`, `pre_close`
- 变动类 (2)：`change`, `pct_chg`
- 量额类 (2)：`vol`, `amount`

---

### 5. 技术指标 — `src/indicators.py`

一站式技术指标计算、可视化看板与信号摘要。架构设计为**可扩展**——新增指标仅需添加计算函数并注册。

```
python src/indicators.py [csv_path]
```

**依赖**：`utils.load_data()`

#### 已实现指标

| 指标 | 参数 | 公式 | 参考 |
|---|---|---|---|
| **MA** (移动平均线) | 5/10/20/60/120 日 | SMA(P) = ΣClose / P | — |
| **RSI** (相对强弱指数) | 14 日 | RSI = 100 − 100/(1+RS), RS = AvgGain/AvgLoss | Wilder 1978 |
| **MACD** (指数平滑异同) | 12/26/9 | DIF=EMA12−EMA26, DEA=EMA9(DIF), Hist=2×(DIF−DEA) | Appel 1970s |
| **BB** (布林带) | 20 日, ±2σ | Mid=SMA20, Upper=Mid+2σ, Lower=Mid−2σ | Bollinger 1980s |

#### 可视化看板

三面板综合视图（`output/figures/indicators_dashboard.png`）：

```
┌─────────────────────────────────────────┐
│ Panel A: 收盘价 + 布林带 + 5条 MA线      │  价格趋势 + 波动范围
├─────────────────────────────────────────┤
│ Panel B: RSI (14) + 超买70/超卖30区域    │  动量强弱信号
├─────────────────────────────────────────┤
│ Panel C: MACD 柱状图 + DIF/DEA 曲线      │  趋势方向 + 动能变化
└─────────────────────────────────────────┘
```

#### 最新信号摘要

执行后自动打印，例如：

```
📡 最新交易日信号摘要 (2026-07-01)
  RSI(14):      中性 (55.7)
  MACD:         多头金叉区域 📈
  布林带:       通道内 (74% 带宽)
  MA 排列:      多头排列 MA5>MA10>...>MA120
```

#### 扩展新指标

在 `indicators.py` 中三步完成：

```python
# 1. 添加计算函数
def compute_xxx(close: pd.Series) -> pd.DataFrame:
    ...

# 2. 在 compute_all_indicators() 中注册
xxx = compute_xxx(close)
result = pd.concat([..., xxx], axis=1)

# 3. 在 plot_dashboard() 中添加子图
```

---

## 数据资产

| 文件 | 维度 | 大小 | 内容 |
|---|---|---|---|
| `data/raw/688256_daily.csv` | 243 × 11 | 22 KB | TuShare 日线原始数据 |
| `data/processed/indicators.csv` | 243 × 15 | — | 全部技术指标 (close + 5MA + RSI + DIF/DEA/MACD + 4BB) |
| `output/figures/688256_close_price.png` | — | 130 KB | 收盘价曲线图 |
| `output/figures/indicators_dashboard.png` | — | — | 三面板技术指标看板 |

---

## MCP 配置

本项目已配置 TuShare MCP Server（`.claude/settings.local.json`），重启 Claude Code 后可直接使用自然语言调用 TuShare 获取数据。

配置格式：
```json
{
  "mcpServers": {
    "tushareMcp": {
      "type": "url",
      "url": "https://api.tushare.pro/mcp/token=<YOUR_TOKEN>"
    }
  }
}
```

---

## 已完成任务清单

| 序号 | 任务 | 对应模块 | 状态 |
|---|---|---|---|
| TASK 1 | 获取 A 股日线数据 (寒武纪 688256.SH) | `fetch_data.py` | ✅ |
| | 收盘价曲线图 + CSV 保存 | `visualize.py` | ✅ |
| | MCP 协议配置 | `.claude/settings.local.json` | ✅ |
| | 仓库架构搭建 | 全部目录 + `.gitignore` | ✅ |
| | 通用函数抽取 | `utils.py` (4 个共享函数) | ✅ |
| TASK 2 | 数据诊断 — 缺失值 / 描述性统计 / 完整性 / 异常值 | `diagnose.py` | ✅ |
| | 技术指标 RSI (14日) | `indicators.py` | ✅ |
| | 技术指标 MACD (12/26/9) | `indicators.py` | ✅ |
| | 技术指标布林带 (20日, ±2σ) | `indicators.py` | ✅ |
| | 技术指标 MA (5/10/20/60/120) | `indicators.py` | ✅ |
| | 技术指标综合看板 | `indicators.py` | ✅ |
