"""
backtest.py
===========
双均线策略回测引擎。

策略规则：
    - 短周期 SMA 上穿长周期 SMA → 买入信号（金叉）
    - 短周期 SMA 下穿长周期 SMA → 卖出信号（死叉）
    - 同一时间最多持有一个仓位（全仓进出）
    - 交易以当日收盘价执行

用法：
    python src/backtest.py [csv_path]

    不带参数：使用默认 CSV 文件
    带参数：对指定 CSV 运行回测并打印摘要
"""

import os
import sys

import numpy as np
import pandas as pd

# ── 确保 src/ 在 import 路径中 ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from utils import load_data  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# 默认参数
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_SHORT_SMA = 5
DEFAULT_LONG_SMA = 20
DEFAULT_INITIAL_CAPITAL = 100_000.0
DEFAULT_COMMISSION_RATE = 0.0003  # 万分之三

DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "688256_SH_20210701_20260701.csv"
)


# ═══════════════════════════════════════════════════════════════════════════
# 核心计算函数
# ═══════════════════════════════════════════════════════════════════════════

def compute_signals(
    close: pd.Series,
    short_period: int = DEFAULT_SHORT_SMA,
    long_period: int = DEFAULT_LONG_SMA,
) -> pd.DataFrame:
    """
    计算双均线交叉信号。

    参数
    ----
    close : pd.Series
        收盘价序列（以日期为索引）
    short_period : int
        短周期 SMA 窗口
    long_period : int
        长周期 SMA 窗口

    返回
    ----
    pd.DataFrame，包含三列：
        short_ma  — 短周期移动平均线
        long_ma   — 长周期移动平均线
        signal    — 1 = 金叉买入, -1 = 死叉卖出, 0 = 无信号
    """
    short_ma = close.rolling(window=short_period).mean()
    long_ma = close.rolling(window=long_period).mean()

    # 金叉：短线上穿长线
    golden_cross = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
    # 死叉：短线下穿长线
    death_cross = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[golden_cross] = 1
    signal[death_cross] = -1

    return pd.DataFrame({
        "short_ma": short_ma,
        "long_ma": long_ma,
        "signal": signal,
    }, index=close.index)


def run_backtest(
    df: pd.DataFrame,
    short_period: int = DEFAULT_SHORT_SMA,
    long_period: int = DEFAULT_LONG_SMA,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    commission_rate: float = 0.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    运行双均线策略回测。

    参数
    ----
    df : pd.DataFrame
        原始日线数据，需包含 trade_date 和 close 列
    short_period : int
        短周期 SMA
    long_period : int
        长周期 SMA
    initial_capital : float
        初始资金（元）
    commission_rate : float
        手续费率（例如 0.0003 表示万分之三）。
        买入时：每股成本 = 价格 × (1 + rate)
        卖出时：每股收入 = 价格 × (1 − rate)
        设为 0 则不计手续费。
    start_date : str | None
        回测起始日期（YYYYMMDD 或 YYYY-MM-DD），None 表示数据最早日期
    end_date : str | None
        回测结束日期（YYYYMMDD 或 YYYY-MM-DD），None 表示数据最晚日期

    返回
    ----
    dict 包含：
        data : dict
            dates, close, short_ma, long_ma,
            buy_signals [{date, price}], sell_signals [{date, price}],
            portfolio_value, benchmark_value, drawdown
        metrics : dict
            total_return, annual_return, sharpe_ratio,
            max_drawdown, max_drawdown_date,
            win_rate, trade_count, profit_loss_ratio
    """
    # ── 数据准备 ──────────────────────────────────────────────────────────
    df = df.copy()
    if "trade_date" in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df["trade_date"]):
            df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)

    close_series = df.set_index("trade_date")["close"]

    # 日期过滤
    if start_date is not None:
        start_dt = pd.to_datetime(start_date)
        close_series = close_series[close_series.index >= start_dt]
    if end_date is not None:
        end_dt = pd.to_datetime(end_date)
        close_series = close_series[close_series.index <= end_dt]

    n = len(close_series)
    if n == 0:
        raise ValueError("指定的日期范围内无交易数据")

    min_required = max(short_period, long_period) + 1
    if n < min_required:
        raise ValueError(
            f"数据不足：回测区间仅 {n} 个交易日，"
            f"至少需要 {min_required} 天（max(SMA周期) + 1）"
        )

    # ── 计算信号 ──────────────────────────────────────────────────────────
    sig_df = compute_signals(close_series, short_period, long_period)
    short_ma = sig_df["short_ma"]
    long_ma = sig_df["long_ma"]
    signals = sig_df["signal"]

    # ── 模拟交易 ──────────────────────────────────────────────────────────
    buy_cost_factor = 1.0 + commission_rate   # 买入成本系数
    sell_proceed_factor = 1.0 - commission_rate  # 卖出收入系数

    cash = float(initial_capital)
    shares = 0.0
    portfolio_values = np.zeros(n)
    trades = []  # 记录每笔完整交易

    current_buy_date = None
    current_buy_price = None
    current_buy_cost = None  # 本次买入总成本

    for i in range(n):
        price = float(close_series.iloc[i])
        sig = signals.iloc[i]

        # 金叉买入
        if sig == 1 and shares == 0.0 and cash > 0.0:
            cost_per_share = price * buy_cost_factor
            if cost_per_share > 0:
                shares = cash / cost_per_share
                cash = 0.0
                current_buy_date = close_series.index[i]
                current_buy_price = price
                current_buy_cost = shares * cost_per_share

        # 死叉卖出
        elif sig == -1 and shares > 0.0:
            proceeds = shares * price * sell_proceed_factor
            cash = proceeds
            if current_buy_date is not None and current_buy_cost is not None and current_buy_cost > 0:
                trade_return = (proceeds - current_buy_cost) / current_buy_cost
                trades.append({
                    "buy_date": str(current_buy_date.date()),
                    "buy_price": round(current_buy_price, 2),
                    "sell_date": str(close_series.index[i].date()),
                    "sell_price": round(price, 2),
                    "return": round(float(trade_return), 6),
                    "win": trade_return > 0,
                })
            shares = 0.0
            current_buy_date = None
            current_buy_price = None
            current_buy_cost = None

        # 当日组合净值
        portfolio_values[i] = cash + shares * price

    # 回测结束时强制平仓
    if shares > 0.0:
        last_price = float(close_series.iloc[-1])
        last_date = close_series.index[-1]
        proceeds = shares * last_price * sell_proceed_factor
        cash = proceeds
        if current_buy_date is not None and current_buy_cost is not None and current_buy_cost > 0:
            trade_return = (proceeds - current_buy_cost) / current_buy_cost
            trades.append({
                "buy_date": str(current_buy_date.date()),
                "buy_price": round(current_buy_price, 2) if current_buy_price else 0,
                "sell_date": str(last_date.date()),
                "sell_price": round(last_price, 2),
                "return": round(float(trade_return), 6),
                "win": trade_return > 0,
            })
        shares = 0.0
        portfolio_values[-1] = cash

    pv_series = pd.Series(portfolio_values, index=close_series.index)

    # ── 基准（买入持有） ──────────────────────────────────────────────────
    benchmark_shares = initial_capital / float(close_series.iloc[0])
    benchmark_values = close_series.values * benchmark_shares

    # ── 回撤 ──────────────────────────────────────────────────────────────
    running_max = np.maximum.accumulate(portfolio_values)
    drawdown_pct = (portfolio_values / running_max - 1.0) * 100.0  # 负值

    # ── 每日收益率 ────────────────────────────────────────────────────────
    daily_returns = pv_series.pct_change().dropna()

    # ── 指标计算 ──────────────────────────────────────────────────────────
    total_days = (close_series.index[-1] - close_series.index[0]).days
    n_years = total_days / 365.25 if total_days > 0 else 0.0

    final_value = float(portfolio_values[-1])
    total_return = (final_value / initial_capital - 1.0) * 100.0  # 百分比

    # 年化收益率
    if n_years > 0 and final_value > 0:
        annual_return = ((final_value / initial_capital) ** (1.0 / n_years) - 1.0) * 100.0
    else:
        annual_return = None

    # 夏普比率（无风险利率设为 0）
    if len(daily_returns) > 1:
        std_ret = float(daily_returns.std())
        if std_ret > 1e-12:
            sharpe = float(daily_returns.mean() / std_ret * np.sqrt(252))
        else:
            sharpe = 0.0
    else:
        sharpe = None

    # 最大回撤
    max_dd = float(np.min(drawdown_pct))
    max_dd_idx = int(np.argmin(drawdown_pct))
    max_dd_date = str(close_series.index[max_dd_idx].date())

    # 胜率 & 盈亏比
    if trades:
        wins = [t for t in trades if t["win"]]
        losses = [t for t in trades if not t["win"]]
        win_rate = len(wins) / len(trades) * 100.0
        avg_win = float(np.mean([t["return"] for t in wins])) if wins else 0.0
        avg_loss = abs(float(np.mean([t["return"] for t in losses]))) if losses else 0.0
        pl_ratio = avg_win / avg_loss if avg_loss > 1e-12 else None
    else:
        win_rate = 0.0
        pl_ratio = None

    # 基准最终收益
    benchmark_final = float(benchmark_values[-1])
    benchmark_return = (benchmark_final / initial_capital - 1.0) * 100.0

    # ── 收集买卖信号点 ────────────────────────────────────────────────────
    buy_signals = []
    sell_signals = []
    for i in range(n):
        sig = signals.iloc[i]
        if sig == 1:
            buy_signals.append({
                "date": str(close_series.index[i].date()),
                "price": round(float(close_series.iloc[i]), 2),
            })
        elif sig == -1:
            sell_signals.append({
                "date": str(close_series.index[i].date()),
                "price": round(float(close_series.iloc[i]), 2),
            })

    # ── 安全序列化 ────────────────────────────────────────────────────────
    def safe_list(series_like):
        """将 Series/array 转为 Python list，NaN → None。"""
        if hasattr(series_like, "fillna"):
            return [
                round(float(x), 4) if pd.notna(x) and np.isfinite(x) else None
                for x in series_like
            ]
        return [
            round(float(x), 4) if pd.notna(x) and np.isfinite(x) else None
            for x in series_like
        ]

    dates_str = [str(d.date()) for d in close_series.index]

    return {
        "data": {
            "dates": dates_str,
            "close": safe_list(close_series),
            "short_ma": safe_list(short_ma),
            "long_ma": safe_list(long_ma),
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "portfolio_value": safe_list(pv_series),
            "benchmark_value": safe_list(benchmark_values),
            "drawdown": safe_list(drawdown_pct),
        },
        "metrics": {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2) if annual_return is not None else None,
            "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_date": max_dd_date,
            "win_rate": round(win_rate, 1),
            "trade_count": len(trades),
            "profit_loss_ratio": round(pl_ratio, 2) if pl_ratio is not None else None,
            "benchmark_return": round(benchmark_return, 2),
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "n_days": n,
            "n_years": round(n_years, 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════════════════

def print_summary(result: dict) -> None:
    """打印回测结果摘要。"""
    m = result["metrics"]
    d = result["data"]

    print(f"\n{'=' * 60}")
    print("  📊 双均线策略回测报告")
    print(f"{'=' * 60}")
    print(f"  交易日数:       {m['n_days']} 天 ({m['n_years']} 年)")
    print(f"  初始资金:       ¥{m['initial_capital']:,.2f}")
    print(f"  最终净值:       ¥{m['final_value']:,.2f}")
    print(f"  总收益率:       {m['total_return']:+.2f}%")
    print(f"  年化收益率:     {m['annual_return']:+.2f}%" if m["annual_return"] is not None else "  年化收益率:     N/A")
    print(f"  夏普比率:       {m['sharpe_ratio']:.3f}" if m["sharpe_ratio"] is not None else "  夏普比率:       N/A")
    print(f"  最大回撤:       {m['max_drawdown']:.2f}%  (日期: {m['max_drawdown_date']})")
    print(f"  基准收益:       {m['benchmark_return']:+.2f}% (买入持有)")
    print(f"  {'-' * 40}")
    print(f"  交易次数:       {m['trade_count']}")
    print(f"  胜率:           {m['win_rate']:.1f}%")
    print(f"  盈亏比:         {m['profit_loss_ratio']:.2f}" if m["profit_loss_ratio"] is not None else "  盈亏比:         N/A")
    print(f"  {'-' * 40}")
    print(f"  买入信号数:     {len(d['buy_signals'])}")
    print(f"  卖出信号数:     {len(d['sell_signals'])}")
    print(f"{'=' * 60}\n")


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    df = load_data(csv_path)
    ts_code = df["ts_code"].iloc[0] if "ts_code" in df.columns else "N/A"
    print(f"📐 运行双均线回测…")
    print(f"   股票: {ts_code}  |  数据量: {len(df)} 条")
    print(f"   参数: SMA({DEFAULT_SHORT_SMA}) / SMA({DEFAULT_LONG_SMA})  |  "
          f"初始资金 ¥{DEFAULT_INITIAL_CAPITAL:,.0f}  |  手续费率 {DEFAULT_COMMISSION_RATE*10000:.0f}‱")

    result = run_backtest(
        df,
        short_period=DEFAULT_SHORT_SMA,
        long_period=DEFAULT_LONG_SMA,
        initial_capital=DEFAULT_INITIAL_CAPITAL,
        commission_rate=DEFAULT_COMMISSION_RATE,
    )
    print_summary(result)


if __name__ == "__main__":
    main()
