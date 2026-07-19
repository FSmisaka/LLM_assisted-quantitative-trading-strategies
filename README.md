# LLM-Assisted Quantitative Trading Strategies

BA 工作坊 · 量化交易策略课程作业

---

## 快速开始

```bash
pip install flask tushare pandas matplotlib scipy numpy scikit-learn xgboost

export TUSHARE_TOKEN="your_token_here"   # https://tushare.pro 注册获取，需 ≥120 积分

python app/server.py                      # 启动看板 → http://localhost:8080
```

---

## 项目结构

```
quant/
├── app/                          # 交互式看板 (Flask + Plotly.js)
├── src/
│   ├── fetch_data.py             # TuShare 数据获取
│   ├── visualize.py              # 收盘价曲线图
│   ├── diagnose.py               # 数据诊断（缺失值/描述统计/异常值/分布）
│   ├── indicators.py             # 技术指标计算 (RSI/MACD/BB/MA)
│   ├── backtest.py               # 双均线交叉策略回测
│   ├── turtle.py                 # 海龟交易法则回测
│   ├── ml_classifiers.py         # ML 分类模型通用模块（LR/DT/RF/XGBoost）
│   ├── ml_quant.py               # ML 量化选股系统（因子加载→特征工程→滚动训练→回测）
│   └── utils.py                  # 通用工具函数
├── data/raw/                     # 原始行情数据
├── data/processed/               # 处理后数据
├── output/figures/               # 图表输出
└── docs/                         # 课程报告 (TASK1–6)
```

---

## 已完成任务

| 任务 | 内容 | 核心文件 |
|------|------|----------|
| **TASK 1** | TuShare 数据获取 · 收盘价可视化 · 仓库搭建 | `fetch_data.py`, `visualize.py`, `utils.py` |
| **TASK 2** | 数据诊断 · RSI/MACD/布林带/均线计算与可视化 | `diagnose.py`, `indicators.py` |
| **TASK 3** | 双均线交叉策略回测（金叉买入/死叉卖出） | `backtest.py` |
| **TASK 4** | 海龟交易法则回测（唐奇安通道+ATR+金字塔加仓+止损） | `turtle.py` |
| **TASK 5** | ML 分类器通用模块（LR/DT/RF/XGBoost + AUC/ROC） | `ml_classifiers.py` |
| **TASK 6** | ML 量化选股系统（因子数据+特征工程+滚动训练+季度回测） | `ml_quant.py` |

---

## 交互式看板

`python app/server.py` 启动后，浏览器打开 `http://localhost:8080`：

- 左侧控制面板：选择本地文件或输入股票代码从 TuShare 拉取数据，调节指标参数
- 右侧图表区：价格+布林带+均线、RSI、MACD 三个 Panel，Plotly 交互式渲染
- 支持缩放/平移、悬停查看数值、导出 PNG

---

## 各模块用法

| 模块 | 运行方式 |
|------|----------|
| 数据获取 | `python src/fetch_data.py` |
| 收盘价图 | `python src/visualize.py [csv_path]` |
| 数据诊断 | `python src/diagnose.py [csv_path]` |
| 技术指标 | `python src/indicators.py [csv_path]` |
| 双均线回测 | `python src/backtest.py [csv_path]` |
| 海龟回测 | `python src/turtle.py [csv_path]` |
| ML 分类器 | `python src/ml_classifiers.py` |
| ML 量化选股 | `python src/ml_quant.py [csv_path]` |

---

## 数据说明

- 默认标的：688256.SH（寒武纪），时间范围 2021-07 至 2026-07
- 数据源：TuShare Pro API（`daily` 接口原始数据 + `pro_bar` 接口前复权数据）
- 支持替换任意 CSV，ML 模块支持中英文列名自动识别
