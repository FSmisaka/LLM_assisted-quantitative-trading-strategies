# LLM-Assisted Quantitative Trading Strategies

光华 BA 工作坊 · 量化交易策略课程作业

---

## 快速开始

```bash
# 1. 安装依赖
pip install flask tushare pandas matplotlib scipy numpy

# 2. 设置 TuShare Token（需 ≥120 积分）
export TUSHARE_TOKEN="your_token_here"

# 3. 启动交互式看板
python app/server.py
# 浏览器打开 http://localhost:8080
```

> Token 在 [tushare.pro](https://tushare.pro) 注册后在「个人中心 → 接口TOKEN」获取。注册 100 积分 + 完善资料 +20 = 120，刚好解锁 `daily` 接口。

---

## 📊 交互式看板

```
┌──────────────────────────────────────────────────────┐
│  📊 Quant Dashboard                    [状态指示灯]   │
├──────────────┬───────────────────────────────────────┤
│  控制面板     │                                       │
│              │         📈 Plotly 交互式图表           │
│  📡 数据源   │   ┌───────────────────────────────┐   │
│  文件选择/获取│   │ Panel A: 价格 + BB + MA       │   │
│  股票代码    │   ├───────────────────────────────┤   │
│  日期范围    │   │ Panel B: RSI + 超买/超卖线    │   │
│  [获取数据]  │   ├───────────────────────────────┤   │
│              │   │ Panel C: MACD 柱 + DIF/DEA    │   │
│  ⚙️ 指标参数 │   └───────────────────────────────┘   │
│  RSI 周期    │                                       │
│  MACD 参数   │                                       │
│  布林带参数  │                                       │
│  MA 勾选     │                                       │
│  [应用&刷新] │                                       │
│              │                                       │
│  📡 信号摘要 │                                       │
└──────────────┴───────────────────────────────────────┘
```

**启动方式**：`python app/server.py`，浏览器打开 `http://localhost:8080`。

**交互功能**：
- 📡 选择本地文件 / 输入代码 + 日期从 TuShare 拉取新数据
- ⚙️ 实时调节 RSI 周期、MACD 三参数、布林带周期与带宽、MA 多周期勾选
- 🖱️ 鼠标悬停图表显示精确数值；悬停参数控件显示说明提示
- 📡 右侧面板实时展示最新交易日信号摘要
- 💾 图表可缩放/平移，支持导出 PNG

**布局**：左侧控制面板 (340px) + 右侧 Plotly 面板图表，响应式适配。

---

## 仓库结构

```
quant/
├── app/                              # 交互式看板 (Flask + Plotly.js)
│   ├── server.py                     #   Flask 后端 API
│   ├── templates/index.html          #   仪表盘 HTML
│   └── static/
│       ├── css/style.css             #   样式
│       └── js/dashboard.js           #   前端逻辑 + Plotly 渲染
├── src/                              # 核心模块
│   ├── utils.py                      #   通用工具 (load_data, save_to_csv, …)
│   ├── fetch_data.py                 #   TuShare 数据获取
│   ├── visualize.py                  #   收盘价可视化 (静态 PNG)
│   ├── diagnose.py                   #   数据诊断 (缺失值/描述性统计/完整性)
│   └── indicators.py                 #   技术指标计算 (RSI/MACD/BB/MA)
├── data/
│   ├── raw/                          # 原始日线数据
│   └── processed/                    # 处理后数据 + 指标 CSV
├── output/figures/                   # 图表输出
├── docs/                             # 课程文档 (Word/PDF)
├── .claude/settings.local.json       # MCP 配置
└── .gitignore
```

---

## 模块速览

| 模块 | 功能 | 用法 |
|---|---|---|
| `app/server.py` | 交互式看板后端 (Flask API) | `python app/server.py` → `localhost:8080` |
| `src/fetch_data.py` | TuShare 获取日线数据 → CSV | `python src/fetch_data.py` |
| `src/visualize.py` | 收盘价曲线图 + 统计摘要 | `python src/visualize.py` |
| `src/diagnose.py` | 缺失值 / 描述性统计 / 完整性 / 异常值 / 涨跌分布 | `python src/diagnose.py` |
| `src/indicators.py` | RSI + MACD + BB + MA 计算 & 静态看板 | `python src/indicators.py` |
| `src/utils.py` | `load_data`, `save_to_csv`, `divider`, `get_token` | 被上述模块引用 |

### API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/` | 仪表盘页面 |
| `GET` | `/api/files` | 列出 `data/raw/` 下可用 CSV |
| `POST` | `/api/fetch` | 通过 TuShare 获取新数据 |
| `POST` | `/api/indicators` | 计算指标，返回 JSON 供前端渲染 |

---

## 技术指标参数

| 指标 | 默认参数 | 可调范围 |
|---|---|---|
| RSI | 周期 N=14 | 2–50 |
| MACD | EMA(12, 26), Signal=9 | 快线 2–50, 慢线 5–100, 信号线 2–50 |
| 布林带 | SMA20, K=2.0σ | 周期 5–100, 带宽 0.5–5.0 |
| MA | 5, 10, 20, 60, 120 日 | 多选 (可增选 250 日) |

---

## MCP 配置

TuShare MCP Server 已配置在 `.claude/settings.local.json`，重启 Claude Code 后可用自然语言直接调用 TuShare 获取数据。

---

## 已完成任务

| 阶段 | 内容 |
|---|---|
| **TASK 1** | TuShare 数据获取 (688256.SH) · 收盘价曲线图 · MCP 配置 · 仓库架构 · utils 抽取 |
| **TASK 2** | 数据诊断 (缺失值/描述统计/完整性/异常值/涨跌分布) · RSI · MACD · 布林带 · MA · 技术指标看板 |
