"""
turtle.py
=========
海龟交易法则回测引擎。

策略规则（经典海龟交易系统）：
    入场  — 价格突破 N 日最高价（唐奇安通道上轨）→ 买入 1 个单位
    加仓  — 价格上涨 0.5×ATR 后加仓 1 个单位，最多加仓 4 次（共 5 个单位）
    出场  — 价格跌破 M 日最低价（唐奇安通道下轨）→ 平仓
    止损  — 价格跌破平均入场价 − 2×ATR → 止损平仓
    头寸  — 1 个单位 = 账户的 1% / ATR（按初始资金计算）

用法：
    python src/turtle.py [csv_path]
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_data  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# 默认参数（经典海龟系统）
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_ENTRY_PERIOD = 20     # 入场通道周期（唐奇安上轨）
DEFAULT_EXIT_PERIOD = 10      # 出场通道周期（唐奇安下轨）
DEFAULT_ATR_PERIOD = 14       # ATR 周期
DEFAULT_ADD_STEP = 0.5        # 加仓步长（几倍 ATR）
DEFAULT_INITIAL_CAPITAL = 100_000.0
DEFAULT_COMMISSION_RATE = 0.0003  # 万分之三

MAX_UNITS = 5                 # 最大持仓单位数（1 初始 + 4 加仓）
STOP_MULTIPLE = 2.0           # 止损倍数（入场价 − N×ATR）
RISK_PER_UNIT = 0.01          # 每单位风险 1%

DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "688256_SH_20210701_20260701.csv"
)


# ═══════════════════════════════════════════════════════════════════════════
# 指标计算
# ═══════════════════════════════════════════════════════════════════════════

def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = DEFAULT_ATR_PERIOD
) -> pd.Series:
    """
    计算 ATR（Average True Range），使用 Wilder 平滑。

    参数
    ----
    high, low, close : pd.Series
        最高价、最低价、收盘价
    period : int
        ATR 周期（默认 14）

    返回
    ----
    pd.Series — ATR 值
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    atr.name = "ATR"
    return atr


def compute_donchian(
    high: pd.Series, low: pd.Series,
    entry_period: int = DEFAULT_ENTRY_PERIOD,
    exit_period: int = DEFAULT_EXIT_PERIOD,
) -> tuple[pd.Series, pd.Series]:
    """
    计算唐奇安通道（Donchian Channel）。

    入场上轨 = 前 entry_period 日的最高价
    出场下轨 = 前 exit_period 日的最低价

    使用 shift(1) 避免未来函数：今天的信号基于昨天及之前的最高/最低价。

    参数
    ----
    high, low : pd.Series
    entry_period : int — 入场通道周期（默认 20）
    exit_period : int — 出场通道周期（默认 10）

    返回
    ----
    (entry_upper, exit_lower) — 两个 pd.Series
        entry_upper — 突破此价位则买入
        exit_lower  — 跌破此价位则卖出
    """
    entry_upper = high.rolling(window=entry_period).max().shift(1)
    exit_lower = low.rolling(window=exit_period).min().shift(1)
    entry_upper.name = "entry_upper"
    exit_lower.name = "exit_lower"
    return entry_upper, exit_lower


# ═══════════════════════════════════════════════════════════════════════════
# 回测主函数
# ═══════════════════════════════════════════════════════════════════════════

def run_turtle_backtest(
    df: pd.DataFrame,
    entry_period: int = DEFAULT_ENTRY_PERIOD,
    exit_period: int = DEFAULT_EXIT_PERIOD,
    atr_period: int = DEFAULT_ATR_PERIOD,
    add_step: float = DEFAULT_ADD_STEP,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    commission_rate: float = 0.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    运行海龟交易法则回测。

    参数
    ----
    df : pd.DataFrame
        原始日线数据，需包含 trade_date, open, high, low, close 列
    entry_period : int — 入场通道周期（唐奇安上轨，默认 20）
    exit_period : int  — 出场通道周期（唐奇安下轨，默认 10）
    atr_period : int   — ATR 周期（默认 14）
    add_step : float   — 加仓步长（几倍 ATR，默认 0.5）
    initial_capital : float — 初始资金
    commission_rate : float — 手续费率（0.0003 = 万分之三）
    start_date, end_date : str | None — 回测日期范围

    返回
    ----
    dict — data（图表数据） + metrics（绩效指标）
    """
    # ── 数据准备 ──────────────────────────────────────────────────────────
    df = df.copy()
    if "trade_date" in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df["trade_date"]):
            df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)

    # 日期过滤
    if start_date is not None:
        start_dt = pd.to_datetime(start_date)
        df = df[df["trade_date"] >= start_dt]
    if end_date is not None:
        end_dt = pd.to_datetime(end_date)
        df = df[df["trade_date"] <= end_dt]

    df = df.reset_index(drop=True)
    n = len(df)
    if n == 0:
        raise ValueError("指定的日期范围内无交易数据")

    max_period = max(entry_period, exit_period, atr_period)
    if n < max_period + 2:
        raise ValueError(
            f"数据不足：回测区间仅 {n} 个交易日，"
            f"至少需要 {max_period + 2} 天"
        )

    dates = df["trade_date"]
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # ── 计算指标 ──────────────────────────────────────────────────────────
    atr = compute_atr(high, low, close, atr_period)
    entry_upper, exit_lower = compute_donchian(high, low, entry_period, exit_period)

    # ── 模拟交易 ──────────────────────────────────────────────────────────
    buy_factor = 1.0 + commission_rate
    sell_factor = 1.0 - commission_rate
    stop_multiple = STOP_MULTIPLE
    max_units = MAX_UNITS

    cash = float(initial_capital)
    total_shares = 0.0
    unit_prices = []          # 每单位入场价
    last_add_price = 0.0
    portfolio_values = np.zeros(n)
    trades = []

    # 信号记录
    buy_signals = []          # 首次入场
    add_signals = []          # 加仓
    sell_signals = []         # 通道出场
    stop_signals = []         # 止损出场

    # 止损线（用于绘图）
    stop_line = np.full(n, np.nan)

    for i in range(n):
        price_c = float(close.iloc[i])
        atr_val = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else None
        date_str = str(dates.iloc[i].date())

        # 计算单位头寸（基于当前 ATR 和初始资金）
        if atr_val and atr_val > 0:
            unit_shares = (initial_capital * RISK_PER_UNIT) / atr_val
        else:
            unit_shares = 0.0

        # 当前持仓状态
        holding = total_shares > 0
        num_units = len(unit_prices)

        # ── 入场信号：突破上轨 ─────────────────────────────────────────
        upper = float(entry_upper.iloc[i]) if pd.notna(entry_upper.iloc[i]) else None
        if not holding and upper is not None and price_c > upper and unit_shares > 0:
            cost = unit_shares * price_c * buy_factor
            if cost <= cash:
                cash -= cost
                total_shares += unit_shares
                unit_prices.append(price_c)
                last_add_price = price_c
                buy_signals.append({"date": date_str, "price": round(price_c, 2)})

        # ── 加仓信号：价格上涨 add_step × ATR ──────────────────────────
        elif (holding and num_units < max_units
              and atr_val and atr_val > 0
              and last_add_price > 0
              and price_c >= last_add_price + add_step * atr_val
              and unit_shares > 0):
            cost = unit_shares * price_c * buy_factor
            if cost <= cash:
                cash -= cost
                total_shares += unit_shares
                unit_prices.append(price_c)
                last_add_price = price_c
                add_signals.append({"date": date_str, "price": round(price_c, 2)})

        # ── 出场 / 止损 ─────────────────────────────────────────────────
        if holding and num_units > 0:
            avg_entry = sum(unit_prices) / num_units
            stop_price = avg_entry - stop_multiple * atr_val if atr_val else avg_entry * 0.85

            # 记录止损线
            stop_line[i] = stop_price if atr_val else np.nan

            should_exit = False
            exit_type = None
            lower = float(exit_lower.iloc[i]) if pd.notna(exit_lower.iloc[i]) else None

            # 通道出场：跌破下轨
            if lower is not None and price_c < lower:
                should_exit = True
                exit_type = "channel"
            # 止损出场
            elif atr_val and price_c < stop_price:
                should_exit = True
                exit_type = "stop_loss"

            if should_exit:
                proceeds = total_shares * price_c * sell_factor
                cash += proceeds

                total_cost = sum(
                    unit_shares * up * buy_factor for up in unit_prices
                )
                if total_cost > 0:
                    trade_return = (proceeds - total_cost) / total_cost
                else:
                    trade_return = 0.0

                trades.append({
                    "buy_date": str(dates.iloc[0]).split(" ")[0] if unit_prices else "",
                    "sell_date": date_str,
                    "sell_price": round(price_c, 2),
                    "return": round(float(trade_return), 6),
                    "win": trade_return > 0,
                    "units": num_units,
                    "exit_type": exit_type,
                })

                if exit_type == "channel":
                    sell_signals.append({"date": date_str, "price": round(price_c, 2)})
                elif exit_type == "stop_loss":
                    stop_signals.append({"date": date_str, "price": round(price_c, 2)})

                total_shares = 0.0
                unit_prices = []
                last_add_price = 0.0

        # 当日组合净值
        portfolio_values[i] = cash + total_shares * price_c

    # ── 强制平仓 ──────────────────────────────────────────────────────────
    if total_shares > 0 and n > 0:
        last_price = float(close.iloc[-1])
        last_date_str = str(dates.iloc[-1].date())
        proceeds = total_shares * last_price * sell_factor
        cash += proceeds

        unit_shares_last = (initial_capital * RISK_PER_UNIT) / float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) and float(atr.iloc[-1]) > 0 else 0
        # Recalculate cost with the unit shares used at the time
        total_cost = 0
        for up in unit_prices:
            if unit_shares_last > 0:
                total_cost += unit_shares_last * up * buy_factor
            else:
                # fallback: use same shares across units
                pass

        if total_cost > 0:
            trade_return = (proceeds - total_cost) / total_cost
        elif unit_shares_last > 0 and unit_prices:
            # recalculate properly
            total_cost = sum(unit_shares_last * up * buy_factor for up in unit_prices)
            trade_return = (proceeds - total_cost) / total_cost if total_cost > 0 else 0.0
        else:
            trade_return = 0.0

        trades.append({
            "buy_date": "",
            "sell_date": last_date_str,
            "sell_price": round(last_price, 2),
            "return": round(float(trade_return), 6),
            "win": trade_return > 0,
            "units": len(unit_prices),
            "exit_type": "force_close",
        })
        total_shares = 0.0
        unit_prices = []
        portfolio_values[-1] = cash

    # ── 组合净值序列 ──────────────────────────────────────────────────────
    pv_series = pd.Series(portfolio_values, index=dates)

    # ── 基准（买入持有）───────────────────────────────────────────────────
    benchmark_shares = initial_capital / float(close.iloc[0]) if float(close.iloc[0]) > 0 else 0
    benchmark_values = close.values * benchmark_shares

    # ── 回撤 ──────────────────────────────────────────────────────────────
    running_max = np.maximum.accumulate(portfolio_values)
    drawdown_pct = (portfolio_values / np.where(running_max > 0, running_max, 1.0) - 1.0) * 100.0

    # ── 每日收益率 ────────────────────────────────────────────────────────
    daily_returns = pv_series.pct_change().dropna()

    # ── 指标计算 ──────────────────────────────────────────────────────────
    total_days = (dates.iloc[-1] - dates.iloc[0]).days
    n_years = total_days / 365.25 if total_days > 0 else 0.0
    final_value = float(portfolio_values[-1])
    total_return = (final_value / initial_capital - 1.0) * 100.0

    if n_years > 0 and final_value > 0:
        annual_return = ((final_value / initial_capital) ** (1.0 / n_years) - 1.0) * 100.0
    else:
        annual_return = None

    if len(daily_returns) > 1:
        std_ret = float(daily_returns.std())
        sharpe = float(daily_returns.mean() / max(std_ret, 1e-12) * np.sqrt(252))
    else:
        sharpe = None

    max_dd = float(np.min(drawdown_pct))
    max_dd_idx = int(np.argmin(drawdown_pct))
    max_dd_date = str(dates.iloc[max_dd_idx].date())

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

    benchmark_final = float(benchmark_values[-1])
    benchmark_return = (benchmark_final / initial_capital - 1.0) * 100.0

    # ── 序列化辅助 ────────────────────────────────────────────────────────
    def safe_list(series_like):
        if hasattr(series_like, "fillna"):
            return [
                round(float(x), 4) if pd.notna(x) and np.isfinite(x) else None
                for x in series_like
            ]
        return [
            round(float(x), 4) if (x is not None and pd.notna(x) and np.isfinite(x)) else None
            for x in series_like
        ]

    dates_str = [str(d.date()) for d in dates]

    return {
        "data": {
            "dates": dates_str,
            "close": safe_list(close),
            "entry_upper": safe_list(entry_upper),
            "exit_lower": safe_list(exit_lower),
            "stop_line": safe_list(stop_line),
            "buy_signals": buy_signals,
            "add_signals": add_signals,
            "sell_signals": sell_signals,
            "stop_signals": stop_signals,
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
    print("  🐢 海龟交易法则回测报告")
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
    print(f"  入场信号:       {len(d['buy_signals'])}")
    print(f"  加仓信号:       {len(d['add_signals'])}")
    print(f"  出场信号:       {len(d['sell_signals'])}")
    print(f"  止损信号:       {len(d['stop_signals'])}")
    print(f"{'=' * 60}\n")


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    df = load_data(csv_path)
    ts_code = df["ts_code"].iloc[0] if "ts_code" in df.columns else "N/A"
    print(f"🐢 运行海龟交易回测…")
    print(f"   股票: {ts_code}  |  数据量: {len(df)} 条")
    print(f"   参数: 入场 {DEFAULT_ENTRY_PERIOD}日 / 出场 {DEFAULT_EXIT_PERIOD}日 / "
          f"ATR({DEFAULT_ATR_PERIOD}) / 加仓步长 {DEFAULT_ADD_STEP}×ATR")
    print(f"   初始资金 ¥{DEFAULT_INITIAL_CAPITAL:,.0f}  |  最大 {MAX_UNITS} 单位  |  "
          f"止损 {STOP_MULTIPLE}×ATR")

    result = run_turtle_backtest(
        df,
        entry_period=DEFAULT_ENTRY_PERIOD,
        exit_period=DEFAULT_EXIT_PERIOD,
        atr_period=DEFAULT_ATR_PERIOD,
        add_step=DEFAULT_ADD_STEP,
        initial_capital=DEFAULT_INITIAL_CAPITAL,
        commission_rate=DEFAULT_COMMISSION_RATE,
    )
    print_summary(result)


if __name__ == "__main__":
    main()
