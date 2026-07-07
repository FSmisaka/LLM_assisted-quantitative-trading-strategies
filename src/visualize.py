"""
visualize.py
============
读取股票日线数据 CSV，绘制每日收盘价曲线图，并导出处理后的数据。

用法：
    python src/visualize.py [csv_path]

    - 不传参数：默认读取 data/raw/688256_daily_qfq.csv
    - 传入路径：读取指定 CSV 文件

输出：
    1. 收盘价曲线图 → output/figures/688256_close_price.png
    2. 处理后的 CSV → data/processed/688256_daily_processed.csv
"""

import os
import sys

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from utils import load_data, save_to_csv


# ============================================================================
# 配置
# ============================================================================

# 中文字体设置（解决 matplotlib 中文乱码）
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题

# 默认输入路径
DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "688256_daily_qfq.csv"
)

# 输出路径
FIGURE_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "output", "figures", "688256_close_price.png"
)
PROCESSED_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", "processed", "688256_daily_processed.csv"
)


# ============================================================================
# 主逻辑
# ============================================================================

def plot_close_price(df: pd.DataFrame, ts_code: str, output_path: str) -> None:
    """绘制每日收盘价曲线图并保存。"""
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.plot(df["trade_date"], df["close"], linewidth=1.2, color="#1f77b4", marker="", alpha=0.9)

    # 标注最高/最低收盘价
    max_idx = df["close"].idxmax()
    min_idx = df["close"].idxmin()
    ax.annotate(
        f"最高: {df['close'][max_idx]:.2f}",
        xy=(df["trade_date"][max_idx], df["close"][max_idx]),
        xytext=(0, 12), textcoords="offset points",
        fontsize=9, color="red", ha="center",
        arrowprops=dict(arrowstyle="->", color="red", lw=0.8),
    )
    ax.annotate(
        f"最低: {df['close'][min_idx]:.2f}",
        xy=(df["trade_date"][min_idx], df["close"][min_idx]),
        xytext=(0, -16), textcoords="offset points",
        fontsize=9, color="green", ha="center",
        arrowprops=dict(arrowstyle="->", color="green", lw=0.8),
    )

    # 格式化 X 轴
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)

    # 标签与标题
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Closing Price (CNY)", fontsize=11)
    ax.set_title(f"{ts_code} — Daily Closing Price ({df['trade_date'].min().strftime('%Y-%m-%d')} to {df['trade_date'].max().strftime('%Y-%m-%d')})", fontsize=13, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"✅ 收盘价曲线图已保存至: {output_path}")
    plt.close(fig)


def save_processed_csv(df: pd.DataFrame, output_path: str) -> None:
    """保存处理后的数据为 CSV（日期还原为 YYYYMMDD 格式）。"""
    df_out = df.copy()
    df_out["trade_date"] = df_out["trade_date"].dt.strftime("%Y%m%d")
    save_to_csv(df_out, output_path)


def print_summary(df: pd.DataFrame) -> None:
    """打印数据摘要统计。"""
    close = df["close"]
    print(f"\n📈 统计摘要：")
    print(f"   交易日数:   {len(df)} 天")
    print(f"   平均收盘价: {close.mean():.2f} 元")
    print(f"   最高收盘价: {close.max():.2f} 元  ({df.loc[close.idxmax(), 'trade_date'].strftime('%Y-%m-%d')})")
    print(f"   最低收盘价: {close.min():.2f} 元  ({df.loc[close.idxmin(), 'trade_date'].strftime('%Y-%m-%d')})")
    print(f"   标准差:     {close.std():.2f}")


def main() -> None:
    # 解析命令行参数
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

    df = load_data(csv_path, required_cols={"trade_date", "close"})

    # 从 CSV 中提取股票代码（如果有 ts_code 列），否则从文件名推断
    if "ts_code" in df.columns:
        ts_code = df["ts_code"].iloc[0]
    else:
        ts_code = os.path.splitext(os.path.basename(csv_path))[0]

    print_summary(df)
    plot_close_price(df, ts_code, FIGURE_OUTPUT)
    save_processed_csv(df, PROCESSED_OUTPUT)


if __name__ == "__main__":
    main()
