"""
diagnose.py
===========
对原始日线数据进行基础诊断分析：缺失值检查、描述性统计、数据完整性校验。

用法：
    python src/diagnose.py [csv_path]

    - 不传参数：默认读取 data/raw/688256_daily.csv
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from utils import load_data, divider


# ============================================================================
# 配置
# ============================================================================

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "688256_daily.csv")

# 数值列分组
PRICE_COLS = ["open", "high", "low", "close", "pre_close"]
CHANGE_COLS = ["change", "pct_chg"]
VOLUME_COLS = ["vol", "amount"]
ALL_NUMERIC = PRICE_COLS + CHANGE_COLS + VOLUME_COLS


# ============================================================================
# 1. 缺失值检查
# ============================================================================

def check_missing(df: pd.DataFrame) -> pd.DataFrame:
    """检查每列的缺失值情况。返回缺失值汇总表。"""
    missing = pd.DataFrame({
        "column": df.columns,
        "missing_count": df.isnull().sum().values,
        "missing_pct": (df.isnull().sum() / len(df) * 100).round(3).values,
    })
    missing = missing[missing["missing_count"] > 0].reset_index(drop=True)

    if missing.empty:
        print("✅ 所有列均无缺失值。")
    else:
        print("⚠️  发现缺失值：")
        for _, row in missing.iterrows():
            print(f"   {row['column']:12s} — {row['missing_count']:4d} 个缺失 ({row['missing_pct']:.2f}%)")
    return missing


# ============================================================================
# 2. 日期连续性检查
# ============================================================================

def check_date_continuity(df: pd.DataFrame) -> None:
    """检查交易日期的连续性和覆盖范围。"""
    dates = df["trade_date"].sort_values()
    n_days = len(dates)
    date_range = (dates.iloc[-1] - dates.iloc[0]).days
    weekdays = sum(1 for d in dates if d.dayofweek < 5)

    # 自然日 vs 实际交易日
    print(f"   日期范围:     {dates.iloc[0].strftime('%Y-%m-%d')} → {dates.iloc[-1].strftime('%Y-%m-%d')}")
    print(f"   自然日跨度:   {date_range} 天")
    print(f"   实际交易日:   {n_days} 天")
    print(f"   其中工作日:   {weekdays} 天")
    print(f"   数据覆盖率:   {n_days / date_range * 100:.1f}% (自然日)")

    # 检查是否有重复日期
    dup_dates = dates[dates.duplicated()]
    if len(dup_dates):
        print(f"   ⚠️  重复日期: {len(dup_dates)} 条")
    else:
        print(f"   ✅ 无重复日期")

    # 检查期间内是否有休市日缺失（粗略：周末除外）
    expected_trading_days = len(pd.bdate_range(dates.iloc[0], dates.iloc[-1]))
    gap = expected_trading_days - n_days
    if gap > 0:
        print(f"   ℹ️  相比工作日历少 {gap} 天（含法定节假日休市，属正常现象）")


# ============================================================================
# 3. 描述性统计
# ============================================================================

def descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有数值列的扩展描述性统计量。"""
    data = df[ALL_NUMERIC].copy()

    stats = pd.DataFrame(index=ALL_NUMERIC)

    # 基本统计量
    stats["count"] = data.count()
    stats["mean"] = data.mean().round(4)
    stats["median"] = data.median().round(4)
    stats["std"] = data.std().round(4)
    stats["min"] = data.min().round(4)
    stats["max"] = data.max().round(4)
    stats["range"] = (data.max() - data.min()).round(4)
    stats["Q1"] = data.quantile(0.25).round(4)
    stats["Q3"] = data.quantile(0.75).round(4)
    stats["IQR"] = (stats["Q3"] - stats["Q1"]).round(4)

    # 分布形态
    stats["skewness"] = data.skew().round(4)
    stats["kurtosis"] = data.kurtosis().round(4)

    # 变异系数 CV = std/|mean| (仅当 mean ≠ 0)
    stats["CV"] = (data.std() / data.mean().abs()).round(4)

    # 特殊统计量 — 涨跌
    if "change" in data.columns:
        stats.loc["change", "positive_days"] = (data["change"] > 0).sum()
        stats.loc["change", "negative_days"] = (data["change"] < 0).sum()
        stats.loc["change", "zero_days"] = (data["change"] == 0).sum()

    return stats


def print_stats_table(stats: pd.DataFrame, title: str, cols: list) -> None:
    """按列分组打印统计表。"""
    sub = stats.loc[cols]
    print(f"\n  {title}")
    print(sub.to_string())


# ============================================================================
# 4. 数据完整性校验
# ============================================================================

def check_integrity(df: pd.DataFrame) -> dict:
    """检查价格数据的逻辑一致性。"""
    issues = {}

    # OHLC 关系: high >= max(open, close), low <= min(open, close)
    bad_high = (df["high"] < df[["open", "close"]].max(axis=1)).sum()
    bad_low = (df["low"] > df[["open", "close"]].min(axis=1)).sum()
    bad_hl = (df["high"] < df["low"]).sum()

    issues["high < max(open,close)"] = bad_high
    issues["low > min(open,close)"] = bad_low
    issues["high < low"] = bad_hl

    if all(v == 0 for v in issues.values()):
        print("✅ OHLC 价格逻辑一致性检查通过（high≥low, high≥open/close, low≤open/close）。")
    else:
        for desc, count in issues.items():
            if count > 0:
                print(f"⚠️  {desc}: {count} 条异常记录")

    return issues


# ============================================================================
# 5. 异常值检测 (IQR 方法)
# ============================================================================

def detect_outliers_iqr(df: pd.DataFrame, cols: list, multiplier: float = 1.5) -> pd.Series:
    """用 IQR 方法检测异常值，返回每列的异常值数量。"""
    outliers = {}
    for col in cols:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr
        n_out = ((df[col] < lower) | (df[col] > upper)).sum()
        outliers[col] = n_out
    return pd.Series(outliers, name="outlier_count")


# ============================================================================
# 6. 综合报告
# ============================================================================

def print_overview(df: pd.DataFrame) -> None:
    """打印数据集整体概览。"""
    print(f"   股票代码:     {df['ts_code'].iloc[0]}")
    print(f"   总记录数:     {len(df)} 条")
    print(f"   总列数:       {len(df.columns)} 列")
    print(f"   内存占用:     {df.memory_usage(deep=True).sum() / 1024:.1f} KB")


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    df = load_data(csv_path)

    # ── 概览 ──
    divider("数据概览")
    print_overview(df)

    # ── 缺失值 ──
    divider("1. 缺失值检查")
    missing = check_missing(df)

    # ── 日期连续性 ──
    divider("2. 日期连续性检查")
    check_date_continuity(df)

    # ── 描述性统计 ──
    divider("3. 描述性统计")

    stats = descriptive_stats(df)

    # 分别展示三类变量
    print_stats_table(stats, "📌 价格变量 (open / high / low / close / pre_close)", PRICE_COLS)
    print_stats_table(stats, "📌 变动变量 (change / pct_chg)", CHANGE_COLS)
    print_stats_table(stats, "📌 量额变量 (vol / amount)", VOLUME_COLS)

    # ── 数据完整性 ──
    divider("4. 数据完整性校验")
    check_integrity(df)

    # ── 异常值 ──
    divider("5. 异常值检测 (IQR × 1.5)")
    outliers = detect_outliers_iqr(df, ALL_NUMERIC)
    if outliers.sum() > 0:
        print("   各列异常值数量（超出 Q1-1.5×IQR ~ Q3+1.5×IQR 范围）：")
        for col, n in outliers.items():
            marker = " ⚠️" if n > len(df) * 0.05 else ""
            print(f"     {col:12s}: {n:3d} / {len(df)} ({n/len(df)*100:5.1f}%){marker}")
    else:
        print("   ✅ 未检测到 IQR 异常值。")

    # ── 涨跌概览 ──
    divider("6. 涨跌分布概览")
    up = (df["change"] > 0).sum()
    down = (df["change"] < 0).sum()
    flat = (df["change"] == 0).sum()
    print(f"   上涨天数: {up:4d}  ({up/len(df)*100:5.1f}%)")
    print(f"   下跌天数: {down:4d}  ({down/len(df)*100:5.1f}%)")
    print(f"   持平天数: {flat:4d}  ({flat/len(df)*100:5.1f}%)")
    avg_gain = df.loc[df["pct_chg"] > 0, "pct_chg"].mean()
    avg_loss = df.loc[df["pct_chg"] < 0, "pct_chg"].mean()
    print(f"   平均涨幅: {avg_gain:+.2f}%")
    print(f"   平均跌幅: {avg_loss:+.2f}%")

    print("\n" + "=" * 70)
    print("  诊断分析完成 ✅")
    print("=" * 70)


if __name__ == "__main__":
    main()
