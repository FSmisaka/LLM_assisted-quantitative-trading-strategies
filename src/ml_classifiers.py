"""
机器学习分类模型通用模块

提供：
  1. 数据集加载与划分（以 scikit-learn 乳腺癌数据集为示例）
  2. 抽象基类 + 4 种具体分类器（逻辑回归、决策树、随机森林、XGBoost）
  3. AUC 评估
  4. ROC 曲线绘制

所有函数与类均不绑定特定量化策略，可作为通用工具在量化或其他分类任务中复用。
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any

import numpy as np
import matplotlib.pyplot as plt
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier as SkDecisionTree
from sklearn.ensemble import RandomForestClassifier as SkRandomForest

# ── 可选依赖：XGBoost（延迟导入，仅在使用 XGBoostClassifier 时触发）──
_XGB_AVAILABLE: bool = True  # 先乐观假设可用；_build_model 中做最终检查


# ======================================================================
# 1. 数据集加载与划分
# ======================================================================

def load_breast_cancer_data(
    test_size: float = 0.2,
    val_size: Optional[float] = 0.1,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    """加载乳腺癌数据集，并划分为训练集、验证集（可选）和测试集。

    Parameters
    ----------
    test_size : float
        测试集占比（默认 0.2）。
    val_size : float or None
        验证集占「训练+验证」的比例（默认 0.1）。若为 None 则不划分验证集。
    random_state : int
        随机种子，保证可复现。

    Returns
    -------
    X_train, X_test, y_train, y_test : np.ndarray
        训练集与测试集的特征和标签。
    X_val, y_val : np.ndarray or None
        验证集的特征和标签（若未划分则为 None）。
    """
    data = load_breast_cancer()
    X, y = data.data, data.target

    # 先切出测试集
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    X_val, y_val = None, None
    if val_size is not None and val_size > 0:
        # 从「训练+验证」中再切出验证集
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_val,
            y_train_val,
            test_size=val_size,
            random_state=random_state,
            stratify=y_train_val,
        )
    else:
        X_train, y_train = X_train_val, y_train_val

    return X_train, X_test, y_train, y_test, X_val, y_val


# ======================================================================
# 2. 抽象分类器接口
# ======================================================================

class BaseClassifier(ABC):
    """所有分类器的抽象基类。

    子类只需实现 ``_build_model()`` 即可获得统一的 ``fit / predict / predict_proba`` 接口。
    """

    def __init__(self, **kwargs: Any):
        self._model_kwargs = kwargs
        self._model: Any = None

    @abstractmethod
    def _build_model(self) -> Any:
        """构建底层模型对象（由子类实现）。"""
        ...

    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseClassifier":
        """训练模型。"""
        self._model = self._build_model()
        self._model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别标签。"""
        self._check_fitted()
        return self._model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测正类概率（shape = (n_samples, 2)）。"""
        self._check_fitted()
        return self._model.predict_proba(X)

    def _check_fitted(self) -> None:
        if self._model is None:
            raise RuntimeError("模型尚未训练，请先调用 fit()。")


# ======================================================================
# 3. 具体分类器实现
# ======================================================================

class LogisticRegressionClassifier(BaseClassifier):
    """逻辑回归分类器。"""

    def _build_model(self) -> LogisticRegression:
        return LogisticRegression(
            max_iter=self._model_kwargs.pop("max_iter", 5000),
            random_state=self._model_kwargs.pop("random_state", 42),
            **self._model_kwargs,
        )


class DecisionTreeClassifier(BaseClassifier):
    """决策树分类器。"""

    def _build_model(self) -> SkDecisionTree:
        return SkDecisionTree(
            random_state=self._model_kwargs.pop("random_state", 42),
            **self._model_kwargs,
        )


class RandomForestClassifier(BaseClassifier):
    """随机森林分类器。"""

    def _build_model(self) -> SkRandomForest:
        return SkRandomForest(
            random_state=self._model_kwargs.pop("random_state", 42),
            **self._model_kwargs,
        )


class XGBoostClassifier(BaseClassifier):
    """XGBoost 分类器。

    .. note::
        采用延迟导入：只有真正调用 ``_build_model()`` 时才会 import xgboost。
        若未安装或缺少系统库（如 libomp），将在此时抛出错误并给出提示。
    """

    def _build_model(self) -> Any:
        global _XGB_AVAILABLE
        try:
            from xgboost import XGBClassifier as XGBCls  # noqa: PLC0415
        except ImportError:
            _XGB_AVAILABLE = False
            raise ImportError(
                "xgboost 未安装。请执行: pip install xgboost\n"
                "macOS 用户可能还需: brew install libomp"
            ) from None
        return XGBCls(
            eval_metric="logloss",
            random_state=self._model_kwargs.pop("random_state", 42),
            verbosity=self._model_kwargs.pop("verbosity", 0),
            **self._model_kwargs,
        )


# ======================================================================
# 4. AUC 评估
# ======================================================================

def evaluate_auc(
    model: BaseClassifier,
    X: np.ndarray,
    y: np.ndarray,
) -> float:
    """计算模型在给定数据集上的 AUC。

    Parameters
    ----------
    model : BaseClassifier
        已训练的分类器。
    X : np.ndarray
        特征矩阵。
    y : np.ndarray
        真实标签（0/1）。

    Returns
    -------
    float
        ROC-AUC 值。
    """
    y_prob = model.predict_proba(X)[:, 1]
    return float(roc_auc_score(y, y_prob))


# ======================================================================
# 5. ROC 曲线绘制
# ======================================================================

def plot_roc_curve(
    models: Dict[str, BaseClassifier],
    X: np.ndarray,
    y: np.ndarray,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 6),
) -> plt.Figure:
    """绘制一个或多个模型的 ROC 曲线。

    Parameters
    ----------
    models : dict[str, BaseClassifier]
        模型名称 → 已训练分类器的映射。
    X : np.ndarray
        测试集特征。
    y : np.ndarray
        测试集真实标签。
    save_path : str or None
        若提供，则将图片保存到该路径（自动创建父目录）。
    figsize : tuple
        图片尺寸。

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    for name, model in models.items():
        y_prob = model.predict_proba(X)[:, 1]
        auc_val = roc_auc_score(y, y_prob)
        fpr, tpr, _ = roc_curve(y, y_prob)
        ax.plot(fpr, tpr, lw=2, label=f"{name} (AUC = {auc_val:.4f})")

    # 对角线（随机分类器基线）
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Random (AUC = 0.5000)")

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("ROC Curves – Breast Cancer Classification", fontsize=14)
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path is not None:
        import os
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"[INFO] ROC 曲线已保存至: {save_path}")

    return fig


# ======================================================================
# 6. 主函数 —— 端到端测试
# ======================================================================

def main() -> None:
    """端到端测试：加载乳腺癌数据 → 训练 4 种分类器 → 评估 AUC → 绘制 ROC。"""
    print("=" * 60)
    print("  机器学习分类模型 —— 乳腺癌数据集测试")
    print("=" * 60)

    # ── 加载与划分数据 ──────────────────────────────────────────
    print("\n[1/4] 加载 & 划分乳腺癌数据集 ...")
    X_train, X_test, y_train, y_test, X_val, y_val = load_breast_cancer_data(
        test_size=0.2, val_size=0.1, random_state=42
    )
    print(f"      训练集: {X_train.shape[0]} 样本")
    print(f"      测试集: {X_test.shape[0]} 样本")
    if X_val is not None:
        print(f"      验证集: {X_val.shape[0]} 样本")

    # ── 定义待评测模型 ──────────────────────────────────────────
    classifier_registry: Dict[str, BaseClassifier] = {
        "Logistic Regression": LogisticRegressionClassifier(),
        "Decision Tree":       DecisionTreeClassifier(max_depth=5),
        "Random Forest":       RandomForestClassifier(n_estimators=100),
        "XGBoost":             XGBoostClassifier(n_estimators=100, verbosity=0),
    }

    # ── 训练 & 评估 ─────────────────────────────────────────────
    print("\n[2/4] 训练模型 ...")
    for name, clf in classifier_registry.items():
        clf.fit(X_train, y_train)
        print(f"      ✓ {name} 训练完成")

    print("\n[3/4] 测试集 AUC 评估 ...\n")
    results: Dict[str, float] = {}
    for name, clf in classifier_registry.items():
        auc = evaluate_auc(clf, X_test, y_test)
        results[name] = auc
        print(f"      {name:<25s}  AUC = {auc:.4f}")

    # 最优模型
    best_name = max(results, key=results.get)  # type: ignore[arg-type]
    print(f"\n      ★ 最优模型: {best_name} (AUC = {results[best_name]:.4f})")

    # ── 绘制 ROC 曲线 ───────────────────────────────────────────
    print("\n[4/4] 绘制 ROC 曲线 ...")
    save_path = "output/figures/roc_curves.png"
    plot_roc_curve(classifier_registry, X_test, y_test, save_path=save_path)
    plt.show()

    print("\n" + "=" * 60)
    print("  测试完成 ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
