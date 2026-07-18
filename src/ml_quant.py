"""
ml_quant.py
===========
通用机器学习量化交易分析系统。

提供完整的 ML 选股/择时流水线：
    1. 可配置的数据加载与列名自动识别
    2. 特征工程（去极值、标准化、缺失值处理、衍生特征）
    3. 可插拔模型注册（线性/树/森林/XGBoost × 回归/分类）
    4. 按时间顺序的 walk-forward 训练与验证
    5. 基于预测排序的季度选股回测
    6. 绩效指标计算（IC/RankIC/收益率/夏普/最大回撤等）

设计原则：
    - 不绑定特定数据文件，支持替换 CSV
    - 中英文列名兼容
    - 模块化，每个环节可独立替换
    - 严格避免未来函数与数据泄漏

用法:
    python src/ml_quant.py                          # 使用默认数据
    python src/ml_quant.py /path/to/other_data.csv  # 指定文件
"""

import os
import sys
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier as SkRFC
from sklearn.ensemble import RandomForestRegressor as SkRFR
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
    r2_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier as SkDTC
from sklearn.tree import DecisionTreeRegressor as SkDTR

warnings.filterwarnings("ignore")

# ── 确保 src/ 在 import 路径中 ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ═══════════════════════════════════════════════════════════════════════════════
# 0. 配置
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "stock_factor_panel_data.csv.csv"
)


@dataclass
class MLQuantConfig:
    """ML 量化系统的全局配置。

    所有参数都有合理默认值，可通过构造时传入覆盖。
    """

    # ── 数据 ──────────────────────────────────────────────────────────────
    data_path: str = DEFAULT_DATA_PATH
    date_col: str = ""                # 空字符串 = 自动检测
    code_col: str = ""                # 空字符串 = 自动检测
    target_col: str = ""              # 空字符串 = 自动检测

    # ── 模型 ──────────────────────────────────────────────────────────────
    model_type: str = "random_forest"  # linear | decision_tree | random_forest | xgboost
    task_type: str = "regression"      # regression | classification
    model_kwargs: dict = field(default_factory=dict)

    # ── 训练/验证划分 ─────────────────────────────────────────────────────
    train_ratio: float = 0.6          # 前 60% 时间用于训练
    val_ratio: float = 0.2            # 中间 20% 用于验证
    test_ratio: float = 0.2           # 最后 20% 用于测试
    # 如果数据有 quarter 列，也可以按季度数切分
    train_quarters: int = 0           # 0 = 使用比例切分

    # ── 特征工程 ──────────────────────────────────────────────────────────
    winsorize_pct: float = 0.01       # 去极值分位数（双侧）
    fill_na_method: str = "cross_sectional_median"  # cross_sectional_median | zero | drop
    standardize: bool = True
    feature_groups: list = field(default_factory=lambda: ["all"])
    # 可用分组: value, growth, profitability, all

    # ── 回测 ──────────────────────────────────────────────────────────────
    top_n: int = 30                   # 每期选多少只股票
    rebalance_freq: str = "quarter"   # quarter（季度调仓）
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003   # 万分之三
    benchmark_type: str = "equal_weight"  # equal_weight | market_cap

    # ── 输出 ──────────────────────────────────────────────────────────────
    verbose: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 列名自动识别
# ═══════════════════════════════════════════════════════════════════════════════

# 语义列名 → 候选匹配关键词的映射
COLUMN_SEMANTICS: dict[str, list[str]] = {
    "date": [
        "date", "trade_date", "日期", "时间", "quarter", "report_date",
        "datetime", "period", "tdate",
    ],
    "code": [
        "code", "ts_code", "stock_code", "symbol", "ticker", "股票代码",
        "代码", "sec_code", "wind_code", "sid",
    ],
    "target": [
        "next_ret", "forward_return", "target", "label", "y",
        "下期收益", "未来收益", "收益率", "return_fwd",
        "excess_return", "alpha",
    ],
    "pb": ["pb", "市净率", "price_to_book", "p/b", "pb_mrq"],
    "pe": ["pe", "市盈率", "price_to_earnings", "p/e", "pe_ttm"],
    "ps": ["ps", "市销率", "price_to_sales", "p/s", "ps_ttm"],
    "pcf": ["pcf", "市现率", "price_to_cashflow"],
    "ev_ebitda": ["ev", "ebitda", "企业倍数"],
    "mv": ["mv", "market_value", "总市值", "市值", "market_cap", "circulating_mv"],
    "dividend_yield": ["股息率", "dividend", "div_yield"],
    "roe": ["roe", "净资产收益率"],
    "roa": ["roa", "总资产收益率"],
    "profit_growth": ["利润总额", "净利润同比增长", "profit_growth", "net_profit_yoy"],
    "revenue_growth": ["营收", "营业总收入", "营业收入", "revenue_growth", "sales_growth"],
    "asset_growth": ["总资产同比", "asset_growth"],
    "equity_growth": ["净资产同比", "equity_growth"],
    "eps_growth": ["每股收益", "eps_growth", "基本每股收益"],
    "cashflow_growth": ["现金净流量", "经营现金流", "cashflow_growth"],
    "operating_profit_growth": ["营业利润", "operating_profit"],
}


def _normalize(s: str) -> str:
    """将列名标准化为小写、去空格。"""
    return s.lower().strip().replace(" ", "_").replace("\n", "")


def detect_columns(df: pd.DataFrame) -> dict[str, str]:
    """自动检测 DataFrame 中各语义列对应的实际列名。

    返回: {语义名: 实际列名}，未检测到的键不存在。
    """
    cols = df.columns.tolist()
    cols_norm = [_normalize(c) for c in cols]
    mapping: dict[str, str] = {}

    # 已被占用的列名
    used_cols: set[str] = set()

    for semantic, candidates in COLUMN_SEMANTICS.items():
        for candidate in candidates:
            candidate_norm = _normalize(candidate)
            for i, cn in enumerate(cols_norm):
                if cols[i] in used_cols:
                    continue
                # 精确匹配或包含匹配
                if candidate_norm == cn or candidate_norm in cn:
                    mapping[semantic] = cols[i]
                    used_cols.add(cols[i])
                    break
            if semantic in mapping:
                break

    return mapping


def get_factor_columns(df: pd.DataFrame, col_map: dict[str, str]) -> list[str]:
    """获取所有可用作因子的数值列（排除日期/代码/目标）。"""
    exclude = {"date", "code", "target"}
    exclude_cols = {col_map[k] for k in exclude if k in col_map}
    factor_cols = []
    for c in df.columns:
        if c in exclude_cols:
            continue
        if df[c].dtype in (np.float64, np.int64, float, int):
            factor_cols.append(c)
    return factor_cols


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 数据加载与预处理
# ═══════════════════════════════════════════════════════════════════════════════

class FactorDataLoader:
    """因子面板数据加载器。

    支持任意 CSV 文件，自动识别日期/代码/目标列。
    """

    def __init__(self, config: MLQuantConfig):
        self.config = config
        self.col_map: dict[str, str] = {}

    def load(self, path: str | None = None) -> pd.DataFrame:
        """加载 CSV 并执行基础清洗。"""
        path = path or self.config.data_path
        if not os.path.exists(path):
            # 尝试去掉多余的 .csv
            alt = path.replace(".csv.csv", ".csv")
            if os.path.exists(alt):
                path = alt
            else:
                raise FileNotFoundError(f"数据文件不存在: {path}")

        df = pd.read_csv(path, encoding="utf-8-sig")
        if self.config.verbose:
            print(f"[DataLoader] 加载 {len(df)} 行 × {len(df.columns)} 列 from {os.path.basename(path)}")

        # ── 自动检测列 ──────────────────────────────────────────────────
        self.col_map = detect_columns(df)
        if self.config.verbose:
            print(f"[DataLoader] 检测到的列映射: { {k: v for k, v in self.col_map.items()} }")

        # 应用用户指定的列覆盖
        if self.config.date_col:
            self.col_map["date"] = self.config.date_col
        if self.config.code_col:
            self.col_map["code"] = self.config.code_col
        if self.config.target_col:
            self.col_map["target"] = self.config.target_col

        # 验证必要列
        required = ["date", "code"]
        for r in required:
            if r not in self.col_map:
                raise KeyError(
                    f"未检测到 '{r}' 列。可用列: {list(df.columns)}。"
                    f"请通过 config.{r}_col 手动指定。"
                )

        # ── 重命名列并解析日期 ───────────────────────────────────────────
        df = df.rename(columns={v: k for k, v in self.col_map.items()})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["date", "code"]).reset_index(drop=True)

        # 添加 quarter 列
        df["quarter"] = df["date"].dt.to_period("Q")

        # ── 基本清洗 ────────────────────────────────────────────────────
        # 替换 inf
        df = df.replace([np.inf, -np.inf], np.nan)

        return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 特征工程
# ═══════════════════════════════════════════════════════════════════════════════

class FeatureEngineer:
    """因子特征工程流水线。"""

    def __init__(self, config: MLQuantConfig):
        self.config = config
        self.feature_names_: list[str] = []
        self.scaler_: StandardScaler | None = None

    def get_factor_columns(self, df: pd.DataFrame) -> list[str]:
        """从 DataFrame 中识别因子列。"""
        exclude = {"date", "code", "target", "quarter"}
        if "target" not in df.columns:
            exclude.discard("target")
        factor_cols = [
            c for c in df.columns
            if c not in exclude and df[c].dtype in (np.float64, np.int64, float, int)
        ]
        return factor_cols

    def winsorize(self, df: pd.DataFrame, factor_cols: list[str]) -> pd.DataFrame:
        """对因子列做双侧缩尾（去极值）。"""
        p = self.config.winsorize_pct
        if p <= 0:
            return df
        df = df.copy()
        for col in factor_cols:
            if col not in df.columns:
                continue
            lo = df[col].quantile(p)
            hi = df[col].quantile(1 - p)
            df[col] = df[col].clip(lo, hi)
        return df

    def fill_missing(self, df: pd.DataFrame, factor_cols: list[str]) -> pd.DataFrame:
        """缺失值填充。

        默认按横截面（同一日期）的中位数填充。
        """
        method = self.config.fill_na_method
        df = df.copy()
        if method == "drop":
            return df.dropna(subset=factor_cols)
        for col in factor_cols:
            if col not in df.columns:
                continue
            if method == "cross_sectional_median":
                df[col] = df.groupby("date")[col].transform(
                    lambda x: x.fillna(x.median())
                )
            elif method == "zero":
                df[col] = df[col].fillna(0)
            # 如果还有残余 NA（整个截面都 NaN），用全局中位数
            if df[col].isna().any():
                df[col] = df[col].fillna(df[col].median())
        return df

    def standardize_features(self, df: pd.DataFrame, factor_cols: list[str],
                             fit: bool = True) -> pd.DataFrame:
        """对因子做截面标准化（Z-score，在同一日期内）。"""
        df = df.copy()
        for col in factor_cols:
            if col not in df.columns:
                continue
            grouped = df.groupby("date")[col]
            mean_s = grouped.transform("mean")
            std_s = grouped.transform("std")
            # 避免除以 0，同时保持 NaN 传播
            std_safe = std_s.replace(0, 1.0)
            df[col] = (df[col] - mean_s) / std_safe
        # 将残余 NaN 填 0
        df[factor_cols] = df[factor_cols].fillna(0.0)
        return df

    def build_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """基于原始因子衍生新特征。

        包括：对数变换、交互项（可选）。
        目前对市值类变量做对数变换（如果存在的话）。
        """
        df = df.copy()
        # 对数市值
        if "mv" in df.columns:
            df["ln_mv"] = np.log(df["mv"].clip(lower=1))
        # 对 PE/PB 做倒数（变成 E/P, B/P，更稳健）
        for col in ["pe", "pb", "ps"]:
            if col in df.columns:
                inv_name = f"{col}_inv"
                # 避免除以 0
                df[inv_name] = 1.0 / df[col].replace(0, np.nan).clip(lower=0.01)
        return df

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """完整的 fit + transform 流水线。"""
        df = df.copy()
        factor_cols = self.get_factor_columns(df)
        self.feature_names_ = factor_cols

        if self.config.verbose:
            print(f"[FeatureEngineer] 原始因子数: {len(factor_cols)}")

        # 1. 衍生特征（在去极值前做，因为衍生特征可能也需要去极值）
        df = self.build_derived_features(df)
        factor_cols = self.get_factor_columns(df)
        self.feature_names_ = factor_cols

        # 2. 去极值
        df = self.winsorize(df, factor_cols)

        # 3. 缺失值填充
        df = self.fill_missing(df, factor_cols)

        # 4. 标准化
        if self.config.standardize:
            df = self.standardize_features(df, factor_cols, fit=True)

        if self.config.verbose:
            print(f"[FeatureEngineer] 最终特征数: {len(factor_cols)}")

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """仅 transform（用于验证/测试集，避免数据泄漏）。"""
        df = df.copy()
        factor_cols = [c for c in self.feature_names_ if c in df.columns]

        df = self.build_derived_features(df)
        factor_cols = [c for c in self.feature_names_ if c in df.columns]
        df = self.winsorize(df, factor_cols)
        df = self.fill_missing(df, factor_cols)
        if self.config.standardize:
            df = self.standardize_features(df, factor_cols, fit=False)
        return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 可插拔模型注册表
# ═══════════════════════════════════════════════════════════════════════════════

def _try_xgboost():
    """尝试导入 XGBoost，失败则返回 None。"""
    try:
        from xgboost import XGBClassifier, XGBRegressor  # noqa: PLC0415
        return XGBClassifier, XGBRegressor
    except ImportError:
        return None, None


def build_model(config: MLQuantConfig) -> Any:
    """根据配置构建模型实例。

    支持回归和分类，支持 4 种算法。
    """
    kwargs = {**config.model_kwargs}
    kwargs.setdefault("random_state", 42)
    is_clf = config.task_type == "classification"
    model_type = config.model_type

    if model_type == "linear":
        kwargs.pop("random_state", None)  # LinearRegression 不接受 random_state
        if is_clf:
            kwargs.setdefault("max_iter", 5000)
            return LogisticRegression(**kwargs)
        return LinearRegression(**kwargs)

    if model_type == "decision_tree":
        kwargs.setdefault("max_depth", 8)
        kwargs.setdefault("min_samples_leaf", 50)
        if is_clf:
            return SkDTC(**kwargs)
        return SkDTR(**kwargs)

    if model_type == "random_forest":
        kwargs.setdefault("n_estimators", 100)
        kwargs.setdefault("max_depth", 10)
        kwargs.setdefault("min_samples_leaf", 30)
        kwargs.setdefault("n_jobs", -1)
        if is_clf:
            return SkRFC(**kwargs)
        return SkRFR(**kwargs)

    if model_type == "xgboost":
        XGBC, XGBR = _try_xgboost()
        if XGBC is None:
            if config.verbose:
                print("[WARN] XGBoost 未安装，退回使用 RandomForest")
            kwargs.setdefault("n_estimators", 100)
            kwargs.setdefault("max_depth", 10)
            kwargs.setdefault("n_jobs", -1)
            if is_clf:
                return SkRFC(**kwargs)
            return SkRFR(**kwargs)
        kwargs.setdefault("n_estimators", 100)
        kwargs.setdefault("max_depth", 6)
        kwargs.setdefault("learning_rate", 0.05)
        kwargs.setdefault("verbosity", 0)
        kwargs.pop("random_state", None)  # XGBoost 用不同参数名
        if is_clf:
            kwargs.setdefault("eval_metric", "logloss")
            return XGBC(random_state=42, **kwargs)
        return XGBR(random_state=42, **kwargs)

    raise ValueError(f"不支持的模型类型: {model_type}")


MODEL_CHOICES = ["linear", "decision_tree", "random_forest", "xgboost"]
TASK_CHOICES = ["regression", "classification"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 评估指标
# ═══════════════════════════════════════════════════════════════════════════════

def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """计算回归指标。"""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    yt, yp = y_true[mask], y_pred[mask]
    if len(yt) < 2:
        return {}
    return {
        "mse": float(mean_squared_error(yt, yp)),
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "mae": float(mean_absolute_error(yt, yp)),
        "r2": float(r2_score(yt, yp)),
    }


def compute_classification_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                                   y_prob: np.ndarray | None = None) -> dict:
    """计算分类指标。"""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    yt, yp = y_true[mask].astype(int), y_pred[mask].astype(int)
    if len(yt) < 2:
        return {}
    result = {
        "accuracy": float(accuracy_score(yt, yp)),
        "precision": float(precision_score(yt, yp, zero_division=0)),
        "recall": float(recall_score(yt, yp, zero_division=0)),
        "f1": float(f1_score(yt, yp, zero_division=0)),
    }
    if y_prob is not None:
        yp_prob = y_prob[mask]
        if len(np.unique(yt)) >= 2:
            # 确保 y_prob 形状正确
            if yp_prob.ndim == 2 and yp_prob.shape[1] >= 2:
                result["auc"] = float(roc_auc_score(yt, yp_prob[:, 1]))
            else:
                result["auc"] = float(roc_auc_score(yt, yp_prob))
    return result


def compute_ic(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """计算 IC (Information Coefficient) 和 Rank IC。"""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    yt, yp = y_true[mask], y_pred[mask]
    if len(yt) < 3:
        return {"ic": None, "rank_ic": None}
    ic = float(np.corrcoef(yt, yp)[0, 1]) if np.std(yp) > 1e-12 else 0.0
    rank_ic = float(pd.Series(yt).corr(pd.Series(yp), method="spearman"))
    return {"ic": ic if np.isfinite(ic) else 0.0,
            "rank_ic": rank_ic if np.isfinite(rank_ic) else 0.0}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Walk-Forward 训练流水线
# ═══════════════════════════════════════════════════════════════════════════════

def walk_forward_train(
    df: pd.DataFrame,
    config: MLQuantConfig,
    feature_engineer: FeatureEngineer,
) -> dict:
    """按时间顺序执行 walk-forward 训练与预测。

    返回包含每期预测、真实值、模型、指标等信息的 dict。
    """
    quarters = sorted(df["quarter"].unique())
    n_quarters = len(quarters)

    if n_quarters < 3:
        raise ValueError(f"数据至少需要 3 个季度，当前只有 {n_quarters} 个")

    # 划分训练/验证/测试季度
    if config.train_quarters > 0:
        n_train_q = config.train_quarters
        n_val_q = max(1, n_quarters - n_train_q - 2)
        n_test_q = max(1, n_quarters - n_train_q - n_val_q)
    else:
        n_train_q = max(1, int(n_quarters * config.train_ratio))
        n_val_q = max(1, int(n_quarters * config.val_ratio))
        n_test_q = n_quarters - n_train_q - n_val_q
        if n_test_q < 1:
            n_test_q = 1
            n_val_q = max(1, n_quarters - n_train_q - n_test_q)

    train_quarters = quarters[:n_train_q]
    val_quarters = quarters[n_train_q:n_train_q + n_val_q]
    test_quarters = quarters[n_train_q + n_val_q:]
    # 如果 test_quarters 为空，把验证集的一部分给测试
    if len(test_quarters) == 0 and len(val_quarters) > 1:
        test_quarters = val_quarters[-1:]
        val_quarters = val_quarters[:-1]

    if config.verbose:
        print(f"[WalkForward] 季度划分: 训练 {len(train_quarters)}Q / "
              f"验证 {len(val_quarters)}Q / 测试 {len(test_quarters)}Q")
        print(f"[WalkForward] 训练: {train_quarters[0]} → {train_quarters[-1]}")
        print(f"[WalkForward] 验证: {val_quarters[0]} → {val_quarters[-1]}")
        print(f"[WalkForward] 测试: {test_quarters[0]} → {test_quarters[-1]}")

    # ── 特征工程（仅在训练集上 fit） ──────────────────────────────────────
    train_mask = df["quarter"].isin(train_quarters)
    df_train_fe = feature_engineer.fit_transform(df[train_mask].copy())
    feature_cols = feature_engineer.feature_names_

    # ── 准备训练数据 ──────────────────────────────────────────────────────
    has_target = "target" in df.columns
    if not has_target:
        raise KeyError("数据中缺少目标变量列 (target / Next_Ret 等)")

    X_train = df_train_fe[feature_cols].values
    y_train = df_train_fe["target"].values

    # 移除训练集中有 NaN 的行
    train_valid = np.isfinite(X_train).all(axis=1) & np.isfinite(y_train)
    X_train = X_train[train_valid]
    y_train = y_train[train_valid]

    if config.verbose:
        print(f"[WalkForward] 训练样本: {len(X_train)}")

    # ── 如果是分类任务，将 target 转为 0/1 ────────────────────────────
    if config.task_type == "classification":
        threshold = np.median(y_train) if len(y_train) > 0 else 0
        y_train_cls = (y_train > threshold).astype(int)
    else:
        y_train_cls = y_train

    # ── 训练模型 ──────────────────────────────────────────────────────────
    model = build_model(config)
    model.fit(X_train, y_train_cls)

    if config.verbose:
        print(f"[WalkForward] 模型训练完成: {type(model).__name__}")

    # ── 在测试集（所有 test + val 季度）上逐期预测 ────────────────────────
    all_pred_quarters = list(val_quarters) + list(test_quarters)
    predictions = []
    actuals = []

    for q in all_pred_quarters:
        q_mask = df["quarter"] == q
        df_q = df[q_mask].copy()
        if len(df_q) == 0:
            continue

        df_q_fe = feature_engineer.transform(df_q)
        X_q = df_q_fe[feature_cols].values
        valid_mask = np.isfinite(X_q).all(axis=1)

        if not valid_mask.any():
            continue

        X_q_valid = X_q[valid_mask]
        df_q_valid = df_q[valid_mask].copy()

        if config.task_type == "classification":
            pred = model.predict_proba(X_q_valid)[:, 1]  # 使用正类概率作为分数
        else:
            pred = model.predict(X_q_valid)

        df_q_valid["prediction"] = pred
        if "target" in df_q_valid.columns:
            df_q_valid["actual"] = df_q_valid["target"]

        predictions.append(df_q_valid[["date", "code", "quarter", "prediction",
                                        "actual" if "target" in df_q_valid.columns else None]])
        if "target" in df_q_valid.columns:
            actuals.append(df_q_valid["target"].values)

    df_pred = pd.concat(predictions, ignore_index=True)
    # 处理 actual 可能为 None 的情况
    if "actual" in df_pred.columns:
        df_pred["actual"] = df_pred["actual"].astype(float)

    # ── 计算评估指标 ──────────────────────────────────────────────────────
    # 区分 val 和 test
    df_pred["set"] = df_pred["quarter"].apply(
        lambda q: "val" if q in val_quarters else "test"
    )

    metrics: dict[str, Any] = {}
    for set_name, set_quarters in [("val", val_quarters), ("test", test_quarters)]:
        mask_set = df_pred["quarter"].isin(set_quarters) & df_pred["actual"].notna()
        if not mask_set.any():
            continue
        yt = df_pred.loc[mask_set, "actual"].values
        yp = df_pred.loc[mask_set, "prediction"].values

        # IC
        ic_metrics = compute_ic(yt, yp)
        prefix = f"{set_name}_"

        # 按季度计算 IC，然后取均值
        q_ics = []
        q_rank_ics = []
        for q in set_quarters:
            qm = (df_pred["quarter"] == q) & df_pred["actual"].notna()
            if qm.sum() < 3:
                continue
            q_ic = compute_ic(
                df_pred.loc[qm, "actual"].values,
                df_pred.loc[qm, "prediction"].values,
            )
            if q_ic["ic"] is not None:
                q_ics.append(q_ic["ic"])
            if q_ic["rank_ic"] is not None:
                q_rank_ics.append(q_ic["rank_ic"])

        metrics.update({
            f"{prefix}ic_mean": float(np.mean(q_ics)) if q_ics else None,
            f"{prefix}rank_ic_mean": float(np.mean(q_rank_ics)) if q_rank_ics else None,
            f"{prefix}ic_std": float(np.std(q_ics)) if q_ics else None,
            f"{prefix}icir": float(np.mean(q_ics) / np.std(q_ics)) if q_ics and np.std(q_ics) > 0 else None,
        })

        # 回归或分类指标
        if config.task_type == "regression":
            reg_metrics = compute_regression_metrics(yt, yp)
            for k, v in reg_metrics.items():
                metrics[f"{prefix}{k}"] = v
        else:
            # 分类需要离散预测
            yp_binary = (yp > 0.5).astype(int)
            yt_binary = (yt > np.median(yt)).astype(int) if len(yt) > 0 else yt.astype(int)
            clf_metrics = compute_classification_metrics(yt_binary, yp_binary, yp)
            for k, v in clf_metrics.items():
                metrics[f"{prefix}{k}"] = v

    # ── 特征重要性（树模型）───────────────────────────────────────────────
    feature_importance = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        fi_df = pd.DataFrame({
            "feature": feature_cols,
            "importance": importances,
        }).sort_values("importance", ascending=False).head(20)
        feature_importance = fi_df.to_dict(orient="records")
    elif hasattr(model, "coef_"):
        coefs = model.coef_
        if coefs.ndim == 1:
            fi_df = pd.DataFrame({
                "feature": feature_cols,
                "importance": np.abs(coefs),
            }).sort_values("importance", ascending=False).head(20)
            feature_importance = fi_df.to_dict(orient="records")

    return {
        "predictions": df_pred,
        "model": model,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "feature_cols": feature_cols,
        "train_quarters": [str(t) for t in train_quarters],
        "val_quarters": [str(v) for v in val_quarters],
        "test_quarters": [str(t) for t in test_quarters],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 回测引擎
# ═══════════════════════════════════════════════════════════════════════════════

def run_ml_backtest(
    df_pred: pd.DataFrame,
    df_original: pd.DataFrame,
    config: MLQuantConfig,
) -> dict:
    """基于 ML 预测结果进行季度选股回测。

    策略：每季度按预测值排序，选 top-N 等权持有。
    """
    quarters = sorted(df_pred["quarter"].unique())
    if config.verbose:
        print(f"[Backtest] 回测季度数: {len(quarters)}, 每期选 {config.top_n} 只")

    # 确保有日期列
    if "date" not in df_pred.columns and "date" in df_original.columns:
        # 通过 quarter 关联日期
        q_date_map = df_original.groupby("quarter")["date"].first().to_dict()
        df_pred["date"] = df_pred["quarter"].map(q_date_map)

    capital = config.initial_capital
    commission = config.commission_rate

    quarterly_results = []
    nav_series = []  # 每期末净值

    for q in quarters:
        q_pred = df_pred[df_pred["quarter"] == q].copy()
        if len(q_pred) == 0:
            continue

        # 选 top-N
        top_n = min(config.top_n, len(q_pred))
        selected = q_pred.nlargest(top_n, "prediction")

        n_stocks = len(selected)
        if n_stocks == 0:
            continue

        # 等权分配
        weight_per_stock = 1.0 / n_stocks
        capital_per_stock = capital * weight_per_stock * (1 - commission)

        # 计算本期收益（如果有 actual）
        q_return = None
        if "actual" in selected.columns:
            actual_returns = selected["actual"].values
            valid_actuals = actual_returns[np.isfinite(actual_returns)]
            if len(valid_actuals) > 0:
                q_return = float(np.mean(valid_actuals))

        # 计算等权基准收益
        benchmark_return = None
        if "actual" in q_pred.columns:
            all_actuals = q_pred["actual"].dropna().values
            all_actuals = all_actuals[np.isfinite(all_actuals)]
            if len(all_actuals) > 0:
                benchmark_return = float(np.mean(all_actuals))

        quarterly_results.append({
            "quarter": str(q),
            "n_selected": n_stocks,
            "strategy_return": q_return,
            "benchmark_return": benchmark_return,
            "excess_return": q_return - benchmark_return if q_return is not None and benchmark_return is not None else None,
            "selected_codes": selected["code"].tolist()[:10],  # 最多展示 10 只
        })

        # 更新净值
        if q_return is not None:
            capital *= (1 + q_return)
        nav_series.append(capital)

    # ── 计算累计指标 ──────────────────────────────────────────────────────
    valid_qr = [r for r in quarterly_results if r["strategy_return"] is not None]
    n_valid_q = len(valid_qr)

    if n_valid_q == 0:
        return {"quarterly_results": quarterly_results, "error": "无有效收益数据"}

    returns = np.array([r["strategy_return"] for r in valid_qr])
    benchmark_returns = np.array([
        r["benchmark_return"] for r in valid_qr if r["benchmark_return"] is not None
    ])

    # 累计收益
    cumulative_return = float(np.prod(1 + returns) - 1)

    # 年化收益（假设每期为一个季度）
    n_years = n_valid_q / 4.0
    annual_return = float((1 + cumulative_return) ** (1.0 / n_years) - 1) if n_years > 0 else 0.0

    # 基准累计收益
    if len(benchmark_returns) == len(returns):
        benchmark_cumulative = float(np.prod(1 + benchmark_returns) - 1)
        benchmark_annual = float((1 + benchmark_cumulative) ** (1.0 / n_years) - 1) if n_years > 0 else 0.0
    else:
        benchmark_cumulative = None
        benchmark_annual = None

    # 累计净值曲线
    cumulative_nav = [config.initial_capital]
    for r in valid_qr:
        cumulative_nav.append(cumulative_nav[-1] * (1 + r["strategy_return"]))

    benchmark_nav = [config.initial_capital]
    for r in valid_qr:
        br = r["benchmark_return"] if r["benchmark_return"] is not None else 0
        benchmark_nav.append(benchmark_nav[-1] * (1 + br))

    # 夏普比率
    if len(returns) > 1:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(4)) if np.std(returns) > 1e-12 else 0.0
    else:
        sharpe = 0.0

    # 最大回撤
    nav_arr = np.array(cumulative_nav[1:])  # 去除初始资金
    peak = np.maximum.accumulate(nav_arr)
    drawdowns = (nav_arr / peak - 1) * 100
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
    max_dd_idx = int(np.argmin(drawdowns)) if len(drawdowns) > 0 else 0
    max_dd_quarter = valid_qr[max_dd_idx]["quarter"] if max_dd_idx < len(valid_qr) else ""

    # 胜率
    win_rate = float(np.mean(returns > 0)) * 100

    # 超额收益胜率
    if len(benchmark_returns) == len(returns):
        excess_win_rate = float(np.mean(returns > benchmark_returns)) * 100
    else:
        excess_win_rate = None

    # IC 表现（按季度）
    ic_series = []
    rank_ic_series = []
    for q in quarters:
        q_data = df_pred[df_pred["quarter"] == q]
        if "actual" not in q_data.columns or len(q_data) < 3:
            continue
        yt_q = q_data["actual"].values
        yp_q = q_data["prediction"].values
        ic_q = compute_ic(yt_q, yp_q)
        if ic_q["ic"] is not None:
            ic_series.append({"quarter": str(q), "ic": ic_q["ic"], "rank_ic": ic_q["rank_ic"]})

    return {
        "quarterly_results": quarterly_results,
        "metrics": {
            "n_quarters": n_valid_q,
            "cumulative_return": round(cumulative_return * 100, 2),
            "annual_return": round(annual_return * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_quarter": max_dd_quarter,
            "win_rate": round(win_rate, 1),
            "excess_win_rate": round(excess_win_rate, 1) if excess_win_rate is not None else None,
            "benchmark_cumulative_return": round(benchmark_cumulative * 100, 2) if benchmark_cumulative is not None else None,
            "benchmark_annual_return": round(benchmark_annual * 100, 2) if benchmark_annual is not None else None,
            "final_value": round(cumulative_nav[-1], 2),
            "initial_capital": config.initial_capital,
        },
        "nav_curve": {
            "quarters": [r["quarter"] for r in valid_qr],
            "portfolio_value": cumulative_nav[1:],
            "benchmark_value": benchmark_nav[1:],
            "drawdown": [round(d, 4) for d in drawdowns.tolist()],
            "cumulative_return_pct": [
                round((cumulative_nav[i + 1] / config.initial_capital - 1) * 100, 4)
                for i in range(len(valid_qr))
            ],
        },
        "ic_series": ic_series,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 主流水线
# ═══════════════════════════════════════════════════════════════════════════════

def run_ml_pipeline(config: MLQuantConfig | None = None) -> dict:
    """运行完整的 ML 量化流水线，返回综合结果 dict。

    这是对外暴露的主入口。
    """
    if config is None:
        config = MLQuantConfig()

    if config.verbose:
        print("=" * 60)
        print("  🤖 ML 量化交易分析系统")
        print(f"  模型: {config.model_type} | 任务: {config.task_type} | Top-N: {config.top_n}")
        print("=" * 60)

    # ── 1. 加载数据 ──────────────────────────────────────────────────────
    loader = FactorDataLoader(config)
    df = loader.load()

    # ── 2. 特征工程 ──────────────────────────────────────────────────────
    engineer = FeatureEngineer(config)

    # ── 3. Walk-Forward 训练 ─────────────────────────────────────────────
    train_result = walk_forward_train(df, config, engineer)

    # ── 4. 回测 ──────────────────────────────────────────────────────────
    backtest_result = run_ml_backtest(
        train_result["predictions"], df, config
    )

    # ── 5. 数据摘要 ──────────────────────────────────────────────────────
    data_summary = {
        "n_rows": len(df),
        "n_stocks": int(df["code"].nunique()),
        "n_quarters": int(df["quarter"].nunique()),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "columns": df.columns.tolist(),
    }

    # ── 6. 回测结果按季度的序列（供前端图表） ─────────────────────────────
    bt = backtest_result
    quarterly_list = bt.get("quarterly_results", [])

    if config.verbose:
        m = bt.get("metrics", {})
        print(f"\n{'=' * 60}")
        print("  📊 回测结果")
        print(f"{'=' * 60}")
        print(f"  累计收益率:     {m.get('cumulative_return', 'N/A'):.2f}%" if isinstance(m.get('cumulative_return'), (int, float)) else f"  累计收益率:     {m.get('cumulative_return', 'N/A')}")
        print(f"  年化收益率:     {m.get('annual_return', 'N/A'):.2f}%" if isinstance(m.get('annual_return'), (int, float)) else f"  年化收益率:     {m.get('annual_return', 'N/A')}")
        print(f"  夏普比率:       {m.get('sharpe_ratio', 'N/A')}")
        print(f"  最大回撤:       {m.get('max_drawdown', 'N/A')}%")
        print(f"  胜率:           {m.get('win_rate', 'N/A')}%")
        print("=" * 60)

    return {
        "config": {
            "model_type": config.model_type,
            "task_type": config.task_type,
            "top_n": config.top_n,
            "train_ratio": config.train_ratio,
            "val_ratio": config.val_ratio,
            "test_ratio": config.test_ratio,
        },
        "data_summary": data_summary,
        "train_quarters": train_result["train_quarters"],
        "val_quarters": train_result["val_quarters"],
        "test_quarters": train_result["test_quarters"],
        "model_metrics": train_result["metrics"],
        "feature_importance": train_result["feature_importance"],
        "feature_cols": train_result["feature_cols"],
        # 按季度聚合预测（方便前端使用）
        "quarterly_predictions": _aggregate_quarterly_predictions(train_result["predictions"]),
        # 回测结果
        "backtest_metrics": bt.get("metrics", {}),
        "quarterly_results": quarterly_list,
        "nav_curve": bt.get("nav_curve", {}),
        "ic_series": bt.get("ic_series", []),
        # 预测详情（每期 top-N）
        "top_picks": _get_top_picks(train_result["predictions"], config.top_n),
    }


def _aggregate_quarterly_predictions(df_pred: pd.DataFrame) -> list[dict]:
    """按季度聚合预测统计信息。"""
    result = []
    for q in sorted(df_pred["quarter"].unique()):
        q_data = df_pred[df_pred["quarter"] == q]
        entry = {
            "quarter": str(q),
            "n_stocks": len(q_data),
            "pred_mean": round(float(q_data["prediction"].mean()), 6),
            "pred_std": round(float(q_data["prediction"].std()), 6),
            "pred_min": round(float(q_data["prediction"].min()), 6),
            "pred_max": round(float(q_data["prediction"].max()), 6),
        }
        if "actual" in q_data.columns and q_data["actual"].notna().any():
            entry["actual_mean"] = round(float(q_data["actual"].dropna().mean()), 6)
        result.append(entry)
    return result


def _get_top_picks(df_pred: pd.DataFrame, top_n: int) -> list[dict]:
    """获取每期 top-N 推荐股票。"""
    result = []
    for q in sorted(df_pred["quarter"].unique()):
        q_data = df_pred[df_pred["quarter"] == q].nlargest(min(top_n, len(df_pred)), "prediction")
        picks = []
        for _, row in q_data.iterrows():
            pick = {
                "code": str(row["code"]),
                "prediction": round(float(row["prediction"]), 6),
            }
            if "actual" in row and pd.notna(row["actual"]):
                pick["actual"] = round(float(row["actual"]), 6)
            picks.append(pick)
        result.append({"quarter": str(q), "picks": picks})
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 9. 模型比较 — 一次运行多个模型
# ═══════════════════════════════════════════════════════════════════════════════

def compare_models(
    config: MLQuantConfig,
    model_types: list[str] | None = None,
) -> dict:
    """在相同数据/特征下比较多个模型的回测表现。"""
    if model_types is None:
        model_types = ["linear", "decision_tree", "random_forest"]

    results = {}
    for mt in model_types:
        cfg = MLQuantConfig(
            data_path=config.data_path,
            model_type=mt,
            task_type=config.task_type,
            top_n=config.top_n,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            test_ratio=config.test_ratio,
            verbose=False,
        )
        try:
            result = run_ml_pipeline(cfg)
            results[mt] = {
                "backtest_metrics": result["backtest_metrics"],
                "model_metrics": result["model_metrics"],
                "nav_curve": result["nav_curve"],
                "quarterly_results": result["quarterly_results"],
                "ic_series": result["ic_series"],
            }
        except Exception as e:
            results[mt] = {"error": str(e)}

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 10. JSON 序列化辅助
# ═══════════════════════════════════════════════════════════════════════════════

def make_json_safe(obj: Any) -> Any:
    """递归将 numpy 类型转为 Python 原生类型。"""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(x) for x in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [make_json_safe(x) for x in obj.tolist()]
    if obj is pd.NaT or obj is pd.NA:
        return None
    return obj


# ═══════════════════════════════════════════════════════════════════════════════
# 11. 命令行入口
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """命令行测试入口。"""
    import json

    data_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA_PATH

    config = MLQuantConfig(
        data_path=data_path,
        model_type="random_forest",
        task_type="regression",
        top_n=30,
        verbose=True,
    )

    result = run_ml_pipeline(config)

    # 打印关键指标
    print("\n📋 模型指标:")
    for k, v in result["model_metrics"].items():
        if v is not None:
            print(f"   {k}: {v:.4f}" if isinstance(v, float) else f"   {k}: {v}")

    print("\n📋 回测指标:")
    for k, v in result["backtest_metrics"].items():
        if v is not None:
            print(f"   {k}: {v}")

    # 保存结果 JSON
    output_path = os.path.join(
        os.path.dirname(__file__), "..", "output", "ml_quant_result.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(make_json_safe(result), f, ensure_ascii=False, indent=2)
    print(f"\n✅ 完整结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
