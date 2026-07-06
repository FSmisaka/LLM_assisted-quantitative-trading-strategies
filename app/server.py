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
        "file": "688256_daily.csv",      // data/raw/ 下的文件名
        "rsi_period": 14,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "bb_period": 20, "bb_std": 2.0,
        "ma_periods": [5, 10, 20, 60, 120]
    }
    """
    data = request.get_json()
    filename = data.get("file", "688256_daily.csv")
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
# 启动
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  📊 Quant Dashboard")
    print("  http://localhost:8080")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=8080)
