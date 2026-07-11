"""
fetch_data.py
=============
使用 TuShare 获取沪深股市股票的日线交易数据，并保存为 CSV。

用法：
    python src/fetch_data.py

前置条件：
    1. 注册 TuShare Pro 账号：https://tushare.pro
    2. 获取 token：登录后进入「个人中心」→「接口TOKEN」
    3. 设置环境变量：export TUSHARE_TOKEN="your_token_here"

本脚本默认获取：
    - 股票：688256.SH（寒武纪，AI 芯片龙头，科创板）
    - 时间：过去一年（2025-07-01 至 2026-07-01）
    - 输出 1：data/raw/688256_daily.csv      — 未复权日线数据（daily 接口）
    - 输出 2：data/raw/688256_SH_20210701_20260701.csv  — 前复权日线数据（pro_bar 接口，adj='qfq'）
"""

import os
import sys

import pandas as pd
import tushare as ts

from utils import get_token, save_to_csv


# ============================================================================
# 配置
# ============================================================================

# 股票代码（TuShare 格式：代码 + 交易所后缀）
# 上海证券交易所：.SH  |  深圳证券交易所：.SZ
# 科创板（688xxx）属于上交所，故后缀为 .SH
TS_CODE = "688256.SH"          # 寒武纪 — AI 芯片龙头
START_DATE = "20250701"        # 起始日期 YYYYMMDD
END_DATE = "20260701"          # 结束日期 YYYYMMDD

# 输出路径
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "688256_daily.csv")          # 未复权
OUTPUT_FILE_ADJ = os.path.join(OUTPUT_DIR, "688256_SH_20210701_20260701.csv")  # 前复权


# ============================================================================
# 主逻辑
# ============================================================================

def fetch_daily(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    通过 TuShare Pro API 获取 A 股日线行情。

    参数
    ----
    ts_code : str
        TuShare 股票代码，如 '688256.SH'
    start_date : str
        起始日期，格式 YYYYMMDD
    end_date : str
        结束日期，格式 YYYYMMDD

    返回
    ----
    pd.DataFrame，包含以下字段：
        ts_code     – 股票代码
        trade_date  – 交易日期
        open        – 开盘价（元）
        high        – 最高价（元）
        low         – 最低价（元）
        close       – 收盘价（元）
        pre_close   – 前收盘价（元）
        change      – 涨跌额（元）
        pct_chg     – 涨跌幅（%）
        vol         – 成交量（手）
        amount      – 成交额（千元）
    """
    token = get_token()
    pro = ts.pro_api(token)

    print(f"📡 正在从 TuShare 获取数据…")
    print(f"   股票代码: {ts_code}")
    print(f"   时间范围: {start_date} – {end_date}")

    df = pro.daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )

    if df.empty:
        print("⚠️  未获取到任何数据，请检查：")
        print("   1. 股票代码是否正确")
        print("   2. 日期范围内是否有交易日")
        print("   3. TuShare token 是否有效、积分是否充足")
        sys.exit(1)

    # 按交易日期升序排列
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def fetch_daily_adj(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    通过 TuShare Pro 的 pro_bar 接口获取 A 股前复权日线行情。

    复权方式为"前复权"（qfq）：以 end_date 为基准，保持当前价格不变，
    将历史价格按复权因子比例缩减，使 K 线走势连续。

    与 fetch_daily() 的主要区别：
        - 接口不同：pro_bar() vs daily()
        - open/high/low/close/pre_close 均为前复权后的价格
        - 复权因子来自 TuShare 官方，基于分红、送股、配股等事件计算

    参数
    ----
    ts_code : str
        TuShare 股票代码，如 '688256.SH'
    start_date : str
        起始日期，格式 YYYYMMDD
    end_date : str
        结束日期，格式 YYYYMMDD

    返回
    ----
    pd.DataFrame，字段与 daily() 返回的一致，但价格字段均为前复权值。
    """
    token = get_token()
    ts.set_token(token)

    print(f"\n📡 正在从 TuShare 获取前复权数据（qfq）…")
    print(f"   股票代码: {ts_code}")
    print(f"   时间范围: {start_date} – {end_date}")

    df = ts.pro_bar(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        adj="qfq",
    )

    if df is None or df.empty:
        print("⚠️  未获取到任何前复权数据，请检查：")
        print("   1. 股票代码是否正确")
        print("   2. 日期范围内是否有交易日")
        print("   3. TuShare token 是否有效、积分是否充足")
        sys.exit(1)

    # 按交易日期升序排列
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def main() -> None:
    # 1. 获取未复权数据
    df = fetch_daily(TS_CODE, START_DATE, END_DATE)

    print(f"\n📊 未复权数据概览：")
    print(f"   总交易日: {len(df)} 条")
    print(f"   日期范围: {df['trade_date'].min()} – {df['trade_date'].max()}")
    print(f"   收盘价区间: {df['close'].min():.2f} – {df['close'].max():.2f} 元")
    print(f"\n前 5 条数据：")
    print(df.head().to_string(index=False))

    save_to_csv(df, OUTPUT_FILE)

    # 2. 获取前复权数据
    df_adj = fetch_daily_adj(TS_CODE, START_DATE, END_DATE)

    print(f"\n📊 前复权数据概览：")
    print(f"   总交易日: {len(df_adj)} 条")
    print(f"   日期范围: {df_adj['trade_date'].min()} – {df_adj['trade_date'].max()}")
    print(f"   收盘价区间: {df_adj['close'].min():.2f} – {df_adj['close'].max():.2f} 元")
    print(f"\n前 5 条数据：")
    print(df_adj.head().to_string(index=False))

    save_to_csv(df_adj, OUTPUT_FILE_ADJ)

    # 3. 对比未复权 vs 前复权（同一交易日）
    print(f"\n📈 未复权 vs 前复权收盘价对比（最近 5 个交易日）：")
    merged = df.merge(
        df_adj[["trade_date", "close"]],
        on="trade_date",
        suffixes=("_raw", "_qfq"),
    ).tail(5)
    for _, row in merged.iterrows():
        diff = row["close_qfq"] - row["close_raw"]
        print(f"   {row['trade_date']}  |  未复权: {row['close_raw']:>8.2f}  |  前复权: {row['close_qfq']:>8.2f}  |  差额: {diff:>+8.2f}")


if __name__ == "__main__":
    main()
