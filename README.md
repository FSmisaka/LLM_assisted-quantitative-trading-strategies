# LLM-Assisted Quantitative Trading Strategies

BA 工作坊作业

## Repository Structure

```
.
├── data/
│   ├── raw/          # 原始数据（股票日交易数据等）
│   └── processed/    # 清洗/处理后的数据
├── notebooks/        # Jupyter Notebook（探索性分析、策略原型）
├── src/              # 量化策略代码与算法
│   ├── fetch_data.py    # 通过 TuShare 获取 A 股日线数据
│   └── visualize.py     # 绘制收盘价曲线图
├── docs/             # 课程文档、作业（Word/PDF）、报告
├── output/
│   └── figures/      # 生成的图表与图片
└── .claude/          # Claude Code 配置（含 MCP）
```

## Quick Start

### 1. 安装依赖

```bash
pip install tushare pandas matplotlib
```

### 2. 获取 TuShare Token

1. 注册 [TuShare Pro](https://tushare.pro)
2. 登录 → 个人中心 → 接口TOKEN → 复制 token
3. 设置环境变量：

```bash
export TUSHARE_TOKEN="your_token_here"
```

### 3. 获取数据

```bash
python src/fetch_data.py
```

默认获取 **688256.SH（寒武纪）** 过去一年的日线交易数据，保存至 `data/raw/`。

如需更换股票，编辑 `src/fetch_data.py` 中的 `TS_CODE`、`START_DATE`、`END_DATE` 变量。

### 4. 可视化

```bash
python src/visualize.py
```

读取 `data/raw/` 中的 CSV，生成收盘价曲线图并输出至 `output/figures/`。

### 5. MCP 配置（可选）

配置 MCP 后可直接用自然语言调用 TuShare 获取数据：

1. 登录 TuShare → 个人中心 → MCP Server → 复制 JSON 配置
2. 将 `.claude/settings.local.json` 中 `mcpServers.tushareMcp.url` 的 `YOUR_TUSHARE_TOKEN_HERE` 替换为实际 token
3. 重启 Claude Code 会话即可生效
