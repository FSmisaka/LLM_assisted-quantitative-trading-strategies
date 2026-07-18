"""
server.py
=========
Interactive Quant Dashboard — Flask 后端。

启动：
    python app/server.py
    浏览器访问 http://localhost:5000

API 端点：
    GET  /                  — 仪表盘页面
    GET  /api/files         — 列出可用的本地数据文件
    POST /api/fetch         — 通过 TuShare 获取数据
    POST /api/indicators    — 计算技术指标并返回 JSON
"""

import json
import os
import sys

# 确保 src/ 在 import 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

from utils import load_data  # noqa: E402
from backtest import run_backtest  # noqa: E402
from turtle import run_turtle_backtest  # noqa: E402

# ── Flask 初始化 ────────────────────────────────────────────────────────────

app = Flask(__name__)

DATA_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


# ═══════════════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """主仪表盘页面。"""
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════════════════
# API — 文件列表
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/files")
def list_files():
    """返回 data/raw/ 下所有 CSV 文件的元信息。"""
    files = []
    if os.path.isdir(DATA_RAW):
        for f in sorted(os.listdir(DATA_RAW)):
            if f.endswith(".csv"):
                path = os.path.join(DATA_RAW, f)
                try:
                    df = pd.read_csv(path)
                    files.append({
                        "name": f,
                        "rows": len(df),
                        "cols": list(df.columns),
                        "ts_code": str(df["ts_code"].iloc[0]) if "ts_code" in df.columns else "N/A",
                        "date_min": str(df["trade_date"].min()),
                        "date_max": str(df["trade_date"].max()),
                    })
                except Exception:
                    files.append({"name": f, "error": "无法读取"})
    return jsonify(files)


# ═══════════════════════════════════════════════════════════════════════════
# API — 数据获取
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/fetch", methods=["POST"])
def fetch_data():
    """通过 TuShare 获取日线数据并保存。"""
    data = request.get_json()
    ts_code = data.get("ts_code", "688256.SH")
    start_date = data.get("start_date", "20250701")
    end_date = data.get("end_date", "20260701")

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "TUSHARE_TOKEN 环境变量未设置"}), 400

    try:
        import tushare as ts
        pro = ts.pro_api(token)
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

        if df.empty:
            return jsonify({"ok": False, "error": "未获取到数据，请检查代码和日期范围"}), 404

        df = df.sort_values("trade_date").reset_index(drop=True)

        # 保存
        filename = f"{ts_code.replace('.', '_')}_{start_date}_{end_date}.csv"
        filepath = os.path.join(DATA_RAW, filename)
        os.makedirs(DATA_RAW, exist_ok=True)
        df.to_csv(filepath, index=False, encoding="utf-8-sig")

        return jsonify({
            "ok": True,
            "filename": filename,
            "rows": len(df),
            "date_min": str(df["trade_date"].min()),
            "date_max": str(df["trade_date"].max()),
            "preview": df.head(5).to_dict(orient="records"),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# API — 指标计算
# ═══════════════════════════════════════════════════════════════════════════

def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_macd(close: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = 2.0 * (dif - dea)
    return dif, dea, hist


def _compute_bb(close: pd.Series, period: int, std: float):
    mid = close.rolling(window=period).mean()
    s = close.rolling(window=period).std()
    upper = mid + std * s
    lower = mid - std * s
    width = (upper - lower) / mid * 100
    return mid, upper, lower, width


def _compute_ma(close: pd.Series, periods: list):
    result = {}
    for p in periods:
        result[f"MA{p}"] = close.rolling(window=p).mean()
    return result


@app.route("/api/indicators", methods=["POST"])
def compute_indicators():
    """
    根据请求参数计算技术指标，返回 JSON 供前端 Plotly 渲染。

    请求体：
    {
        "file": "688256_SH_20210701_20260701.csv",      // data/raw/ 下的文件名
        "rsi_period": 14,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "bb_period": 20, "bb_std": 2.0,
        "ma_periods": [5, 10, 20, 60, 120]
    }
    """
    data = request.get_json()
    filename = data.get("file", "688256_SH_20210701_20260701.csv")
    filepath = os.path.join(DATA_RAW, filename)

    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    try:
        df = load_data(filepath)
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取文件失败: {e}"}), 500

    close = df.set_index("trade_date")["close"]
    n = len(close)

    # ── 参数 ────────────────────────────────────────────────────────────
    rsi_period = data.get("rsi_period", 14)
    macd_fast = data.get("macd_fast", 12)
    macd_slow = data.get("macd_slow", 26)
    macd_signal = data.get("macd_signal", 9)
    bb_period = data.get("bb_period", 20)
    bb_std = data.get("bb_std", 2.0)
    ma_periods = data.get("ma_periods", [5, 10, 20, 60, 120])

    # ── 计算 ────────────────────────────────────────────────────────────
    rsi = _compute_rsi(close, period=rsi_period)
    dif, dea, hist = _compute_macd(close, fast=macd_fast, slow=macd_slow, signal=macd_signal)
    bb_mid, bb_upper, bb_lower, bb_width = _compute_bb(close, period=bb_period, std=bb_std)
    ma_dict = _compute_ma(close, periods=ma_periods)

    dates_str = close.index.strftime("%Y-%m-%d").tolist()

    # ── 构建响应 ────────────────────────────────────────────────────────
    def safe(v):
        """将 NaN / inf 替换为 null (JSON-safe)。"""
        if hasattr(v, "fillna"):
            return v.fillna(0).replace([np.inf, -np.inf], 0).round(4).tolist()
        return [round(x, 4) if pd.notna(x) and np.isfinite(x) else 0 for x in v]

    # 信号摘要
    last_close = float(close.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50
    last_dif = float(dif.iloc[-1]) if pd.notna(dif.iloc[-1]) else 0
    last_dea = float(dea.iloc[-1]) if pd.notna(dea.iloc[-1]) else 0
    last_bb_upper = float(bb_upper.iloc[-1]) if pd.notna(bb_upper.iloc[-1]) else 0
    last_bb_lower = float(bb_lower.iloc[-1]) if pd.notna(bb_lower.iloc[-1]) else 0
    bb_pos = ((last_close - last_bb_lower) / (last_bb_upper - last_bb_lower) * 100) if last_bb_upper != last_bb_lower else 50

    return jsonify({
        "ok": True,
        "data": {
            "dates": dates_str,
            "close": safe(close),
            "rsi": safe(rsi),
            "rsi_period": rsi_period,
            "dif": safe(dif),
            "dea": safe(dea),
            "macd_hist": safe(hist),
            "bb_upper": safe(bb_upper),
            "bb_mid": safe(bb_mid),
            "bb_lower": safe(bb_lower),
            "bb_width": safe(bb_width),
            "ma": {k: safe(v) for k, v in ma_dict.items()},
        },
        "signal": {
            "date": dates_str[-1],
            "close": round(last_close, 2),
            "rsi": round(last_rsi, 1),
            "rsi_label": "超买" if last_rsi > 70 else ("超卖" if last_rsi < 30 else "中性"),
            "macd_dif": round(last_dif, 2),
            "macd_dea": round(last_dea, 2),
            "macd_hist": round(float(hist.iloc[-1]), 2) if pd.notna(hist.iloc[-1]) else 0,
            "macd_label": "金叉多头" if last_dif > last_dea else "死叉空头",
            "bb_upper": round(last_bb_upper, 2),
            "bb_lower": round(last_bb_lower, 2),
            "bb_pos": round(bb_pos, 0),
            "bb_label": "突破上轨" if bb_pos > 100 else ("跌破下轨" if bb_pos < 0 else "通道内"),
        },
        "n_records": n,
    })


# ═══════════════════════════════════════════════════════════════════════════
# API — 双均线回测
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/backtest", methods=["POST"])
def backtest():
    """
    运行双均线策略回测，返回信号、净值曲线、回撤及绩效指标。

    请求体：
    {
        "file": "688256_SH_20210701_20260701.csv",
        "start_date": "2025-01-01",          // 可选，YYYYMMDD 或 YYYY-MM-DD
        "end_date": "2026-07-01",            // 可选
        "short_sma": 5,
        "long_sma": 20,
        "commission_enabled": false,
        "initial_capital": 100000
    }
    """
    data = request.get_json()
    filename = data.get("file", "")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    short_sma = int(data.get("short_sma", 5))
    long_sma = int(data.get("long_sma", 20))
    commission_enabled = data.get("commission_enabled", False)
    initial_capital = float(data.get("initial_capital", 100000))

    # ── 参数校验 ──────────────────────────────────────────────────────────
    if not filename:
        return jsonify({"ok": False, "error": "请选择数据文件"}), 400

    filepath = os.path.join(DATA_RAW, filename)
    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    if short_sma >= long_sma:
        return jsonify({"ok": False, "error": "短周期 SMA 必须小于长周期 SMA"}), 400

    if short_sma < 2:
        return jsonify({"ok": False, "error": "短周期 SMA 最小为 2"}), 400

    if initial_capital <= 0:
        return jsonify({"ok": False, "error": "初始资金必须大于 0"}), 400

    # ── 加载数据 ──────────────────────────────────────────────────────────
    try:
        df = load_data(filepath)
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取文件失败: {e}"}), 500

    # 获取文件原始日期范围（用于前端校验提示）
    raw_dates = df["trade_date"]
    if not pd.api.types.is_datetime64_any_dtype(raw_dates):
        raw_dates = pd.to_datetime(raw_dates.astype(str), format="%Y%m%d")
    file_date_min = raw_dates.min().strftime("%Y-%m-%d")
    file_date_max = raw_dates.max().strftime("%Y-%m-%d")

    # ── 验证日期范围 ──────────────────────────────────────────────────────
    if start_date:
        start_dt = pd.to_datetime(start_date)
        if start_dt < raw_dates.min():
            return jsonify({
                "ok": False,
                "error": f"起始日期 {start_date} 早于文件最早日期 {file_date_min}"
            }), 400
        if start_dt > raw_dates.max():
            return jsonify({
                "ok": False,
                "error": f"起始日期 {start_date} 晚于文件最晚日期 {file_date_max}"
            }), 400
    if end_date:
        end_dt = pd.to_datetime(end_date)
        if end_dt < raw_dates.min():
            return jsonify({
                "ok": False,
                "error": f"结束日期 {end_date} 早于文件最早日期 {file_date_min}"
            }), 400
        if end_dt > raw_dates.max():
            return jsonify({
                "ok": False,
                "error": f"结束日期 {end_date} 晚于文件最晚日期 {file_date_max}"
            }), 400

    if start_date and end_date:
        if pd.to_datetime(start_date) >= pd.to_datetime(end_date):
            return jsonify({"ok": False, "error": "起始日期必须早于结束日期"}), 400

    # ── 运行回测 ──────────────────────────────────────────────────────────
    commission_rate = 0.0003 if commission_enabled else 0.0

    try:
        result = run_backtest(
            df=df,
            short_period=short_sma,
            long_period=long_sma,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"回测失败: {e}"}), 500

    # ── 组装响应 ──────────────────────────────────────────────────────────
    return jsonify({
        "ok": True,
        "data": result["data"],
        "metrics": result["metrics"],
        "file_date_min": file_date_min,
        "file_date_max": file_date_max,
        "params": {
            "short_sma": short_sma,
            "long_sma": long_sma,
            "commission_enabled": commission_enabled,
            "initial_capital": initial_capital,
        },
    })


# ═══════════════════════════════════════════════════════════════════════════
# API — 海龟交易法则回测
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/turtle", methods=["POST"])
def turtle_backtest():
    """
    运行海龟交易法则回测，返回信号、净值曲线、回撤及绩效指标。

    请求体：
    {
        "file": "688256_SH_20210701_20260701.csv",
        "start_date": "2025-01-01",          // 可选
        "end_date": "2026-07-01",            // 可选
        "entry_period": 20,                  // 入场通道周期（唐奇安上轨）
        "exit_period": 10,                   // 出场通道周期（唐奇安下轨）
        "atr_period": 14,                    // ATR 周期
        "add_step": 0.5,                     // 加仓步长（几倍 ATR）
        "commission_enabled": false,
        "initial_capital": 100000
    }
    """
    data = request.get_json()
    filename = data.get("file", "")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    entry_period = int(data.get("entry_period", 20))
    exit_period = int(data.get("exit_period", 10))
    atr_period = int(data.get("atr_period", 14))
    add_step = float(data.get("add_step", 0.5))
    commission_enabled = data.get("commission_enabled", False)
    initial_capital = float(data.get("initial_capital", 100000))

    # ── 参数校验 ──────────────────────────────────────────────────────────
    if not filename:
        return jsonify({"ok": False, "error": "请选择数据文件"}), 400

    filepath = os.path.join(DATA_RAW, filename)
    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    if entry_period < 2:
        return jsonify({"ok": False, "error": "入场通道周期最小为 2"}), 400
    if exit_period < 2:
        return jsonify({"ok": False, "error": "出场通道周期最小为 2"}), 400
    if atr_period < 2:
        return jsonify({"ok": False, "error": "ATR 周期最小为 2"}), 400
    if add_step <= 0:
        return jsonify({"ok": False, "error": "加仓步长必须大于 0"}), 400
    if initial_capital <= 0:
        return jsonify({"ok": False, "error": "初始资金必须大于 0"}), 400

    # ── 加载数据 ──────────────────────────────────────────────────────────
    try:
        df = load_data(filepath)
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取文件失败: {e}"}), 500

    raw_dates = df["trade_date"]
    if not pd.api.types.is_datetime64_any_dtype(raw_dates):
        raw_dates = pd.to_datetime(raw_dates.astype(str), format="%Y%m%d")
    file_date_min = raw_dates.min().strftime("%Y-%m-%d")
    file_date_max = raw_dates.max().strftime("%Y-%m-%d")

    # ── 验证日期范围 ──────────────────────────────────────────────────────
    if start_date:
        start_dt = pd.to_datetime(start_date)
        if start_dt < raw_dates.min():
            return jsonify({
                "ok": False,
                "error": f"起始日期 {start_date} 早于文件最早日期 {file_date_min}"
            }), 400
        if start_dt > raw_dates.max():
            return jsonify({
                "ok": False,
                "error": f"起始日期 {start_date} 晚于文件最晚日期 {file_date_max}"
            }), 400
    if end_date:
        end_dt = pd.to_datetime(end_date)
        if end_dt < raw_dates.min():
            return jsonify({
                "ok": False,
                "error": f"结束日期 {end_date} 早于文件最早日期 {file_date_min}"
            }), 400
        if end_dt > raw_dates.max():
            return jsonify({
                "ok": False,
                "error": f"结束日期 {end_date} 晚于文件最晚日期 {file_date_max}"
            }), 400

    if start_date and end_date:
        if pd.to_datetime(start_date) >= pd.to_datetime(end_date):
            return jsonify({"ok": False, "error": "起始日期必须早于结束日期"}), 400

    # ── 运行回测 ──────────────────────────────────────────────────────────
    commission_rate = 0.0003 if commission_enabled else 0.0

    try:
        result = run_turtle_backtest(
            df=df,
            entry_period=entry_period,
            exit_period=exit_period,
            atr_period=atr_period,
            add_step=add_step,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"回测失败: {e}"}), 500

    return jsonify({
        "ok": True,
        "data": result["data"],
        "metrics": result["metrics"],
        "file_date_min": file_date_min,
        "file_date_max": file_date_max,
        "params": {
            "entry_period": entry_period,
            "exit_period": exit_period,
            "atr_period": atr_period,
            "add_step": add_step,
            "commission_enabled": commission_enabled,
            "initial_capital": initial_capital,
        },
    })


# ═══════════════════════════════════════════════════════════════════════════
# API — ML 量化分析
# ═══════════════════════════════════════════════════════════════════════════

from ml_quant import (  # noqa: E402
    MLQuantConfig,
    MODEL_CHOICES,
    TASK_CHOICES,
    compare_models,
    make_json_safe,
    run_ml_pipeline,
)

ML_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def _list_ml_files() -> list[dict]:
    """列出 data/raw 和 data/processed 下所有 CSV 文件。"""
    files = []
    for dirpath in [ML_DATA_DIR, os.path.join(os.path.dirname(__file__), "..", "data", "processed")]:
        if not os.path.isdir(dirpath):
            continue
        for f in sorted(os.listdir(dirpath)):
            if f.endswith(".csv"):
                path = os.path.join(dirpath, f)
                try:
                    df = pd.read_csv(path, nrows=5)
                    files.append({
                        "name": f,
                        "path": path,
                        "dir": os.path.basename(dirpath),
                        "cols": list(df.columns),
                        "n_cols": len(df.columns),
                    })
                except Exception:
                    files.append({"name": f, "path": path, "dir": os.path.basename(dirpath), "error": "无法读取"})
    return files


@app.route("/api/ml/files")
def ml_list_files():
    """返回可用于 ML 分析的 CSV 文件列表。"""
    return jsonify({"ok": True, "files": _list_ml_files()})


@app.route("/api/ml/data-preview", methods=["POST"])
def ml_data_preview():
    """预览数据文件的前 N 行和列信息。

    请求体：{"file": "stock_factor_panel_data.csv.csv"}
    """
    data = request.get_json()
    filename = data.get("file", "")

    if not filename:
        return jsonify({"ok": False, "error": "请指定数据文件"}), 400

    # 查找文件
    filepath = None
    for f_info in _list_ml_files():
        if f_info["name"] == filename:
            filepath = f_info["path"]
            break

    if filepath is None:
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig")
        n_rows = len(df)
        n_cols = len(df.columns)

        # 自动检测列
        from ml_quant import detect_columns, get_factor_columns
        col_map = detect_columns(df)
        factor_cols = get_factor_columns(df, col_map)

        return jsonify({
            "ok": True,
            "n_rows": n_rows,
            "n_cols": n_cols,
            "columns": df.columns.tolist(),
            "dtypes": {c: str(df[c].dtype) for c in df.columns},
            "col_map": {k: v for k, v in col_map.items()},
            "factor_cols": factor_cols,
            "preview": make_json_safe(df.head(10).to_dict(orient="records")),
            "date_range": {
                "min": str(df[col_map["date"]].min()) if "date" in col_map else "N/A",
                "max": str(df[col_map["date"]].max()) if "date" in col_map else "N/A",
            } if "date" in col_map else None,
            "n_stocks": int(df[col_map["code"]].nunique()) if "code" in col_map else 0,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ml/analyze", methods=["POST"])
def ml_analyze():
    """运行完整的 ML 量化分析流水线。

    请求体：
    {
        "file": "stock_factor_panel_data.csv.csv",
        "model_type": "random_forest",     // linear | decision_tree | random_forest | xgboost
        "task_type": "regression",         // regression | classification
        "top_n": 30,
        "train_ratio": 0.6,
        "val_ratio": 0.2,
        "winsorize_pct": 0.01,
        "standardize": true,
        "model_kwargs": {}                 // 可选的模型参数覆盖
    }
    """
    data = request.get_json()
    filename = data.get("file", "")

    if not filename:
        return jsonify({"ok": False, "error": "请选择数据文件"}), 400

    # 查找文件路径
    filepath = None
    for f_info in _list_ml_files():
        if f_info["name"] == filename:
            filepath = f_info["path"]
            break

    if filepath is None:
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    # 验证模型类型
    model_type = data.get("model_type", "random_forest")
    if model_type not in MODEL_CHOICES:
        return jsonify({"ok": False, "error": f"不支持的模型类型: {model_type}。可选: {MODEL_CHOICES}"}), 400

    task_type = data.get("task_type", "regression")
    if task_type not in TASK_CHOICES:
        return jsonify({"ok": False, "error": f"不支持的任务类型: {task_type}。可选: {TASK_CHOICES}"}), 400

    try:
        config = MLQuantConfig(
            data_path=filepath,
            model_type=model_type,
            task_type=task_type,
            top_n=int(data.get("top_n", 30)),
            train_ratio=float(data.get("train_ratio", 0.6)),
            val_ratio=float(data.get("val_ratio", 0.2)),
            test_ratio=float(data.get("test_ratio", 0.2)),
            winsorize_pct=float(data.get("winsorize_pct", 0.01)),
            standardize=data.get("standardize", True),
            model_kwargs=data.get("model_kwargs", {}),
            verbose=False,
        )

        result = run_ml_pipeline(config)
        safe_result = make_json_safe(result)

        return jsonify({
            "ok": True,
            **safe_result,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ml/compare", methods=["POST"])
def ml_compare():
    """运行多模型对比分析。

    请求体：
    {
        "file": "stock_factor_panel_data.csv.csv",
        "model_types": ["linear", "decision_tree", "random_forest"],
        "task_type": "regression",
        "top_n": 30
    }
    """
    data = request.get_json()
    filename = data.get("file", "")

    if not filename:
        return jsonify({"ok": False, "error": "请选择数据文件"}), 400

    filepath = None
    for f_info in _list_ml_files():
        if f_info["name"] == filename:
            filepath = f_info["path"]
            break

    if filepath is None:
        return jsonify({"ok": False, "error": f"文件不存在: {filename}"}), 404

    model_types = data.get("model_types", ["linear", "decision_tree", "random_forest"])
    task_type = data.get("task_type", "regression")
    top_n = int(data.get("top_n", 30))

    try:
        config = MLQuantConfig(
            data_path=filepath,
            task_type=task_type,
            top_n=top_n,
            verbose=False,
        )
        results = compare_models(config, model_types)
        safe_results = make_json_safe(results)

        return jsonify({
            "ok": True,
            "comparison": safe_results,
            "model_types": model_types,
            "task_type": task_type,
            "top_n": top_n,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  📊 Quant Dashboard")
    print("  http://localhost:8080")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=8080)
