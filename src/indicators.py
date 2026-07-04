"""
indicators.py
=============
技术指标计算与可视化。

支持的指标：
    - MA     移动平均线 (5/10/20/60/120 日)
    - RSI    相对强弱指数 (14 日)
    - MACD   指数平滑异同移动平均线 (12/26/9)
    - BB     布林带 (20 日, 2σ)

扩展新指标：
    1. 在 # ---- 计算函数 ---- 区域添加计算函数
    2. 在 compute_all_indicators() 中调用
    3. 在 plot_dashboard() 中添加绘图逻辑

用法：
    python src/indicators.py [csv_path]
"""

import os
import sys

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from utils import load_data

# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "688256_daily.csv")

# ── 指标参数（集中管理，便于调参）────────────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2

MA_PERIODS = [5, 10, 20, 60, 120]
MA_COLORS = ["#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
MA_ALPHAS = [0.9, 0.8, 0.7, 0.5, 0.4]
MA_WIDTHS = [1.0, 1.0, 1.2, 1.5, 1.5]


# ═══════════════════════════════════════════════════════════════════════════
# 计算函数
# ═══════════════════════════════════════════════════════════════════════════

def compute_ma(close: pd.Series) -> pd.DataFrame:
    """
    计算多周期简单移动平均线 (SMA)。

    返回 DataFrame，列名为 MA5, MA10, MA20, MA60, MA120。
    """
    result = pd.DataFrame(index=close.index)
    for p in MA_PERIODS:
        result[f"MA{p}"] = close.rolling(window=p).mean()
    return result


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """
    计算相对强弱指数 RSI (Wilder's smoothing)。

    RSI = 100 - 100 / (1 + RS)
    其中 RS = 平均涨幅 / 平均跌幅
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder's EMA: 初始值为简单平均，后续用平滑公式
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi.name = "RSI"
    return rsi


def compute_macd(close: pd.Series) -> pd.DataFrame:
    """
    计算 MACD 指标。

    返回 DataFrame：
        DIF  — 快慢 EMA 差值 (EMA_fast - EMA_slow)
        DEA  — DIF 的信号线 (EMA of DIF)
        MACD — 柱状图 = 2 × (DIF - DEA)
    """
    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()

    dif = ema_fast - ema_slow
    dif.name = "DIF"
    dea = dif.ewm(span=MACD_SIGNAL, adjust=False).mean()
    dea.name = "DEA"
    macd_hist = 2.0 * (dif - dea)  # 国内常用 ×2 柱
    macd_hist.name = "MACD"

    return pd.concat([dif, dea, macd_hist], axis=1)


def compute_bollinger(close: pd.Series) -> pd.DataFrame:
    """
    计算布林带 Bollinger Bands。

    返回 DataFrame：
        BB_MID   — 中轨 (SMA)
        BB_UPPER — 上轨 (中轨 + K × σ)
        BB_LOWER — 下轨 (中轨 − K × σ)
        BB_WIDTH — 带宽百分比 = (上轨 − 下轨) / 中轨 × 100
    """
    mid = close.rolling(window=BB_PERIOD).mean()
    std = close.rolling(window=BB_PERIOD).std()

    upper = mid + BB_STD * std
    lower = mid - BB_STD * std
    width = (upper - lower) / mid * 100

    return pd.DataFrame({
        "BB_MID": mid,
        "BB_UPPER": upper,
        "BB_LOWER": lower,
        "BB_WIDTH": width,
    }, index=close.index)


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    一站式计算全部技术指标，返回合并后的 DataFrame。
    新增指标时在此函数中追加即可。
    """
    close = df.set_index("trade_date")["close"]

    # ── 计算各指标 ─────────────────────────────────────────────────────
    ma = compute_ma(close)
    rsi = compute_rsi(close)
    macd = compute_macd(close)
    bb = compute_bollinger(close)

    # ── 合并 ───────────────────────────────────────────────────────────
    result = pd.concat([close, ma, rsi, macd, bb], axis=1)
    result.index.name = "trade_date"
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 可视化
# ═══════════════════════════════════════════════════════════════════════════

def plot_dashboard(df_raw: pd.DataFrame, indicators: pd.DataFrame, ts_code: str) -> None:
    """
    绘制技术指标综合看板，包含四个面板：
        Panel A — K线（收盘价） + 布林带 + 多周期 MA
        Panel B — RSI（含超买超卖区域）
        Panel C — MACD（DIF / DEA / 柱状图）
    """
    close = indicators["close"]
    n = len(close)

    # ── 布局 ────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 13))
    gs = fig.add_gridspec(3, 1, height_ratios=[2.5, 1, 1], hspace=0.12)

    ax_price = fig.add_subplot(gs[0])
    ax_rsi = fig.add_subplot(gs[1], sharex=ax_price)
    ax_macd = fig.add_subplot(gs[2], sharex=ax_price)

    date_range_str = (
        f"{close.index[0].strftime('%Y-%m-%d')} — "
        f"{close.index[-1].strftime('%Y-%m-%d')}"
    )
    fig.suptitle(
        f"{ts_code} 寒武纪 · 技术指标看板    |    {date_range_str}    |    {n} 个交易日",
        fontsize=15, fontweight="bold", y=0.98,
    )

    # ── Panel A: 价格 + 布林带 + MA ──────────────────────────────────────
    ax_price.fill_between(
        indicators.index,
        indicators["BB_UPPER"], indicators["BB_LOWER"],
        color="steelblue", alpha=0.08, label="Bollinger Band (±2σ)",
    )
    ax_price.plot(indicators.index, indicators["BB_UPPER"],
                  color="steelblue", linewidth=0.6, alpha=0.7, linestyle="--")
    ax_price.plot(indicators.index, indicators["BB_MID"],
                  color="steelblue", linewidth=0.6, alpha=0.9, linestyle="-.")
    ax_price.plot(indicators.index, indicators["BB_LOWER"],
                  color="steelblue", linewidth=0.6, alpha=0.7, linestyle="--")

    # MA 线
    for i, p in enumerate(MA_PERIODS):
        col = f"MA{p}"
        ax_price.plot(indicators.index, indicators[col],
                      color=MA_COLORS[i], linewidth=MA_WIDTHS[i],
                      alpha=MA_ALPHAS[i], label=f"MA{p}")

    # 收盘价 (最后画，在最上层)
    ax_price.plot(indicators.index, close,
                  color="#1f2937", linewidth=1.2, label="Close", zorder=3)

    ax_price.set_ylabel("Price (CNY)", fontsize=10)
    ax_price.legend(loc="upper left", ncol=8, fontsize=7.5,
                    framealpha=0.6, edgecolor="gray")
    ax_price.grid(True, linestyle="--", alpha=0.25)
    ax_price.tick_params(labelbottom=False)

    # ── Panel B: RSI ─────────────────────────────────────────────────────
    ax_rsi.fill_between(indicators.index, RSI_OVERBOUGHT, 100,
                         color="red", alpha=0.06)
    ax_rsi.fill_between(indicators.index, 0, RSI_OVERSOLD,
                         color="green", alpha=0.06)
    ax_rsi.axhline(RSI_OVERBOUGHT, color="red", linewidth=0.8,
                    linestyle="--", alpha=0.5, label=f"Overbought ({RSI_OVERBOUGHT})")
    ax_rsi.axhline(50, color="gray", linewidth=0.5, alpha=0.4)
    ax_rsi.axhline(RSI_OVERSOLD, color="green", linewidth=0.8,
                    linestyle="--", alpha=0.5, label=f"Oversold ({RSI_OVERSOLD})")

    ax_rsi.plot(indicators.index, indicators["RSI"],
                color="#6d28d9", linewidth=0.9, label=f"RSI({RSI_PERIOD})")
    ax_rsi.fill_between(indicators.index, 50, indicators["RSI"],
                         where=(indicators["RSI"] >= 50),
                         color="#6d28d9", alpha=0.08)
    ax_rsi.fill_between(indicators.index, indicators["RSI"], 50,
                         where=(indicators["RSI"] < 50),
                         color="#dc2626", alpha=0.08)

    ax_rsi.set_ylabel("RSI", fontsize=10)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_yticks([0, 30, 50, 70, 100])
    ax_rsi.legend(loc="upper left", fontsize=7.5, framealpha=0.6)
    ax_rsi.grid(True, linestyle="--", alpha=0.25)
    ax_rsi.tick_params(labelbottom=False)

    # ── Panel C: MACD ─────────────────────────────────────────────────────
    dif = indicators["DIF"]
    dea = indicators["DEA"]
    macd_hist = indicators["MACD"]

    # 柱状图 — 涨红跌绿
    colors_hist = ["#dc2626" if v >= 0 else "#16a34a" for v in macd_hist]
    ax_macd.bar(indicators.index, macd_hist, width=0.8,
                color=colors_hist, alpha=0.5, label="MACD Histogram")

    ax_macd.plot(indicators.index, dif, color="#2563eb",
                 linewidth=0.9, label=f"DIF (EMA{MACD_FAST}−EMA{MACD_SLOW})")
    ax_macd.plot(indicators.index, dea, color="#ea580c",
                 linewidth=0.9, label=f"DEA (EMA{MACD_SIGNAL})")
    ax_macd.axhline(0, color="gray", linewidth=0.5, alpha=0.4)

    ax_macd.set_ylabel("MACD", fontsize=10)
    ax_macd.legend(loc="upper left", fontsize=7.5, framealpha=0.6)
    ax_macd.grid(True, linestyle="--", alpha=0.25)

    # ── X 轴格式化 ──────────────────────────────────────────────────────
    for ax in [ax_price, ax_rsi, ax_macd]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax_macd.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    plt.setp(ax_price.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    plt.setp(ax_rsi.get_xticklabels(), rotation=45, ha="right", fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])

    # ── 保存 ────────────────────────────────────────────────────────────
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output", "figures")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "indicators_dashboard.png")
    fig.savefig(output_path, dpi=180, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    print(f"✅ 技术指标看板已保存至: {output_path}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════════════════════════════════════

def print_signal_summary(indicators: pd.DataFrame) -> None:
    """打印当前最新交易日的指标信号摘要。"""
    latest = indicators.iloc[-1]
    close_val = latest["close"]
    rsi_val = latest["RSI"]

    print(f"\n{'='*60}")
    print("  📡 最新交易日信号摘要")
    print(f"{'='*60}")
    print(f"  日期: {indicators.index[-1].strftime('%Y-%m-%d')}")
    print(f"  收盘价: {close_val:.2f} 元")
    print()

    # RSI
    if rsi_val > RSI_OVERBOUGHT:
        rsi_signal = f"超买 ⚠️ ({rsi_val:.1f})"
    elif rsi_val < RSI_OVERSOLD:
        rsi_signal = f"超卖 🔔 ({rsi_val:.1f})"
    else:
        rsi_signal = f"中性 ({rsi_val:.1f})"
    print(f"  RSI({RSI_PERIOD}):      {rsi_signal}")

    # MACD
    dif, dea, macd_h = latest["DIF"], latest["DEA"], latest["MACD"]
    if dif > dea and macd_h > 0:
        macd_signal = "多头金叉区域 📈"
    elif dif < dea and macd_h < 0:
        macd_signal = "空头死叉区域 📉"
    elif dif > dea:
        macd_signal = "DIF > DEA（多头但柱缩）"
    else:
        macd_signal = "DIF < DEA（空头但柱收）"
    print(f"  MACD:           {macd_signal}")
    print(f"    DIF={dif:.2f}  DEA={dea:.2f}  Hist={macd_h:.2f}")

    # Bollinger
    bb_upper, bb_lower, bb_mid = latest["BB_UPPER"], latest["BB_LOWER"], latest["BB_MID"]
    bb_pos = (close_val - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper != bb_lower else 50
    if bb_pos > 100:
        bb_signal = f"突破上轨 🚀"
    elif bb_pos < 0:
        bb_signal = f"跌破下轨 🔻"
    elif bb_pos > 80:
        bb_signal = f"接近上轨 ({bb_pos:.0f}% 带宽)"
    elif bb_pos < 20:
        bb_signal = f"接近下轨 ({bb_pos:.0f}% 带宽)"
    else:
        bb_signal = f"通道内 ({bb_pos:.0f}% 带宽)"
    print(f"  布林带:         {bb_signal}")
    print(f"    Upper={bb_upper:.2f}  Mid={bb_mid:.2f}  Lower={bb_lower:.2f}")

    # MA 排列
    ma_vals = [(p, latest[f"MA{p}"]) for p in MA_PERIODS if not pd.isna(latest[f"MA{p}"])]
    if len(ma_vals) >= 3:
        sorted_mas = sorted(ma_vals, key=lambda x: x[1], reverse=True)
        periods_sorted = [f"MA{p}" for p, _ in sorted_mas]
        if [f"MA{p}" for p, _ in ma_vals] == periods_sorted:
            if close_val > sorted_mas[0][1]:
                ma_signal = "多头排列（短>长，价在均线上方）📈"
            else:
                ma_signal = "多头排列但价在均线下方"
        elif [f"MA{p}" for p, _ in ma_vals][::-1] == periods_sorted:
            ma_signal = "空头排列（长>短）📉"
        else:
            ma_signal = "均线交织（震荡）"
    else:
        ma_signal = "数据不足"
    print(f"  MA 排列:        {ma_signal}")

    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    df_raw = load_data(csv_path)

    ts_code = df_raw["ts_code"].iloc[0] if "ts_code" in df_raw.columns else "688256.SH"

    print(f"📐 计算技术指标中…")
    print(f"   股票: {ts_code}  |  数据量: {len(df_raw)} 条")

    indicators = compute_all_indicators(df_raw)

    # 保存指标数据
    output_csv = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "indicators.csv")
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    indicators.to_csv(output_csv, encoding="utf-8-sig", float_format="%.4f")
    print(f"✅ 指标数据已保存至: {output_csv}")

    # 可视化
    plot_dashboard(df_raw, indicators, ts_code)

    # 信号摘要
    print_signal_summary(indicators)


if __name__ == "__main__":
    main()
