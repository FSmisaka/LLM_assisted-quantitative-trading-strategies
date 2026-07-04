"""
utils.py
========
项目通用工具函数，供 src/ 下各脚本复用。

包含：
    - load_data      加载原始 CSV 日线数据
    - save_to_csv    将 DataFrame 保存为 CSV
    - divider        控制台分隔标题
    - get_token      获取 TuShare API token
"""

import os
import sys

import pandas as pd


# ============================================================================
# 数据 I/O
# ============================================================================

def load_data(csv_path: str, required_cols: set | None = None) -> pd.DataFrame:
    """
    加载原始 CSV 日线数据，自动转换 trade_date 为 datetime 并按日期排序。

    参数
    ----
    csv_path : str
        CSV 文件路径
    required_cols : set | None
        必须存在的列名集合，若缺失则报错退出。默认 None 不检查。
    """
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    if required_cols:
        missing = required_cols - set(df.columns)
        if missing:
            print(f"❌ CSV 缺少必要列: {missing}")
            sys.exit(1)

    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def save_to_csv(df: pd.DataFrame, filepath: str) -> None:
    """将 DataFrame 保存为 CSV 文件（UTF-8 BOM，兼容 Excel）。"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"✅ 数据已保存至: {filepath}")


# ============================================================================
# 显示工具
# ============================================================================

def divider(title: str) -> None:
    """打印带分隔线的标题。"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================================
# TuShare
# ============================================================================

def get_token() -> str:
    """从环境变量 TUSHARE_TOKEN 获取 TuShare API token。"""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ 未找到 TUSHARE_TOKEN 环境变量。")
        print("   请先注册 TuShare Pro（https://tushare.pro），获取 token 后执行：")
        print("   export TUSHARE_TOKEN=\"your_token_here\"")
        sys.exit(1)
    return token
