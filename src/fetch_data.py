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
"""

import os
import sys

import pandas as pd
import tushare as ts


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
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "688256_daily.csv")


# ============================================================================
# 主逻辑
# ============================================================================

def get_token() -> str:
    """从环境变量获取 TuShare token。"""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ 未找到 TUSHARE_TOKEN 环境变量。")
        print("   请先注册 TuShare Pro（https://tushare.pro），获取 token 后执行：")
        print("   export TUSHARE_TOKEN=\"your_token_here\"")
        sys.exit(1)
    return token


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


def save_to_csv(df: pd.DataFrame, filepath: str) -> None:
    """将 DataFrame 保存为 CSV 文件。"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"✅ 数据已保存至: {filepath}")


def main() -> None:
    df = fetch_daily(TS_CODE, START_DATE, END_DATE)

    print(f"\n📊 数据概览：")
    print(f"   总交易日: {len(df)} 条")
    print(f"   日期范围: {df['trade_date'].min()} – {df['trade_date'].max()}")
    print(f"   收盘价区间: {df['close'].min():.2f} – {df['close'].max():.2f} 元")
    print(f"\n前 5 条数据：")
    print(df.head().to_string(index=False))

    save_to_csv(df, OUTPUT_FILE)


if __name__ == "__main__":
    main()
