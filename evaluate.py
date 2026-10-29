"""
Model Evaluation and Backtesting Pipeline.

Loads trained model and test split, evaluates classification metrics (Accuracy,
Precision, Recall, F1, ROC-AUC, Confusion Matrix), compares against baselines
('Always Up' and '5/20 MA Crossover'), executes a realistic backtest accounting for
Rs. 20 brokerage and Rs. 15.34 DP charges, and saves plots in logs/.
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless execution
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    BROKERAGE_FEE,
    DP_CHARGE,
    FEATURE_NAMES_FILE,
    INITIAL_CAPITAL,
    LOGS_DIR,
    MODEL_FILE,
    MODELS_DIR,
    PRED_BUY_THRESHOLD,
    STOP_LOSS_PCT,
    TARGET_FORWARD_DAYS,
)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray | None = None) -> dict[str, float]:
    """Computes standard classification metrics."""
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    if y_prob is not None:
        try:
            auc = roc_auc_score(y_true, y_prob)
        except Exception:
            auc = 0.50
    else:
        auc = 0.50

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "roc_auc": auc,
    }


def run_backtest_simulation(
    df: pd.DataFrame,
    signals: pd.Series,
    initial_capital: float = INITIAL_CAPITAL,
    hold_days: int = TARGET_FORWARD_DAYS,
) -> dict[str, Any]:
    """
    Executes a transaction-cost-aware backtest on daily close prices.
    Deducts Rs. 20 brokerage per order and Rs. 15.34 DP charge on sells.
    """
    data = df.copy()
    data["signal"] = signals.values
    data = data.sort_values("date").reset_index(drop=True)

    cash = float(initial_capital)
    portfolio_history: list[dict[str, Any]] = []

    # Active positions: ticker -> {"shares": int, "entry_price": float, "entry_day_idx": int}
    positions: dict[str, dict[str, Any]] = {}
    total_trades = 0
    winning_trades = 0
    total_fees_paid = 0.0

    # Group by date to process day by day
    dates = sorted(data["date"].unique())

    for day_idx, dt in enumerate(dates):
        day_bars = data[data["date"] == dt]

        # 1. Process exits for existing positions
        tickers_to_close = []
        for ticker, pos in positions.items():
            ticker_bar = day_bars[day_bars["ticker"] == ticker]
            if ticker_bar.empty:
                continue

            current_close = float(ticker_bar["close"].values[0])
            entry_price = pos["entry_price"]
            days_held = day_idx - pos["entry_day_idx"]
            pnl_pct = (current_close - entry_price) / entry_price

            # Exit condition: hold duration reached or stop-loss triggered
            should_exit = (days_held >= hold_days) or (pnl_pct <= -STOP_LOSS_PCT)

            if should_exit:
                revenue = pos["shares"] * current_close
                sell_fee = BROKERAGE_FEE + DP_CHARGE
                net_revenue = revenue - sell_fee
                cash += net_revenue
                total_fees_paid += sell_fee
                total_trades += 1

                trade_pnl = net_revenue - (pos["shares"] * entry_price + BROKERAGE_FEE)
                if trade_pnl > 0:
                    winning_trades += 1
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del positions[t]

        # 2. Process entry signals
        for _, row in day_bars.iterrows():
            ticker = row["ticker"]
            sig = row["signal"]
            close_price = float(row["close"])

            if sig == 1 and ticker not in positions and close_price > 0:
                # Sizing: allocate a fraction of available cash per trade (up to 20% of capital)
                trade_budget = min(cash * 0.25, 25000.0)
                if trade_budget > (close_price + BROKERAGE_FEE):
                    shares = int((trade_budget - BROKERAGE_FEE) // close_price)
                    if shares > 0:
                        cost = (shares * close_price) + BROKERAGE_FEE
                        cash -= cost
                        total_fees_paid += BROKERAGE_FEE
                        positions[ticker] = {
                            "shares": shares,
                            "entry_price": close_price,
                            "entry_day_idx": day_idx,
                        }

        # 3. Calculate total portfolio value for today
        holdings_value = 0.0
        for ticker, pos in positions.items():
            ticker_bar = day_bars[day_bars["ticker"] == ticker]
            if not ticker_bar.empty:
                c_price = float(ticker_bar["close"].values[0])
            else:
                c_price = pos["entry_price"]
            holdings_value += pos["shares"] * c_price

        total_equity = cash + holdings_value
        portfolio_history.append({"date": dt, "equity": total_equity})

    # Liquidate remaining positions at end of backtest
    final_equity = portfolio_history[-1]["equity"] if portfolio_history else initial_capital
    equity_series = pd.Series([p["equity"] for p in portfolio_history], index=[p["date"] for p in portfolio_history])

    # Compute Max Drawdown
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_dd = float(drawdown.min())

    total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd * 100.0,
        "total_trades": total_trades,
        "win_rate_pct": win_rate,
        "fees_paid": total_fees_paid,
        "equity_curve": equity_series,
    }


def plot_feature_importance(model: Any, feature_names: list[str], output_path: Path) -> None:
    """Extracts and plots feature importance or coefficients."""
    plt.figure(figsize=(10, 6))

    importances: np.ndarray | None = None
    title = "Feature Importance"

    # Check for tree-based feature_importances_
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        title = "RandomForest / Tree Feature Importance"
    # Check inside pipeline
    elif hasattr(model, "named_steps"):
        clf = model.named_steps.get("clf")
        if hasattr(clf, "coef_"):
            importances = np.abs(clf.coef_[0])
            title = "Logistic Regression Feature Coefficients (Magnitude)"

    if importances is not None and len(importances) == len(feature_names):
        indices = np.argsort(importances)[::-1]
        sorted_feats = [feature_names[i] for i in indices]
        sorted_vals = importances[indices]

        plt.barh(range(len(sorted_vals)), sorted_vals[::-1], color="#2563eb", align="center")
        plt.yticks(range(len(sorted_vals)), sorted_feats[::-1], fontsize=9)
        plt.xlabel("Importance / Absolute Weight")
        plt.title(title, fontsize=12, fontweight="bold")
    else:
        plt.text(0.5, 0.5, "Feature importances not directly extractable for this model", ha="center")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"  -> Saved feature importance plot to {output_path.name}")


def plot_confusion_matrix(cm: np.ndarray, output_path: Path) -> None:
    """Visualizes confusion matrix with counts and percentages."""
    plt.figure(figsize=(6, 5))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Test Set Confusion Matrix", fontsize=12, fontweight="bold")
    plt.colorbar()
    tick_marks = np.arange(2)
    plt.xticks(tick_marks, ["Actual 0 (Down/Flat)", "Actual 1 (Up)"])
    plt.yticks(tick_marks, ["Pred 0", "Pred 1"])

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            val = cm[i, j]
            pct = (val / cm.sum()) * 100.0
            plt.text(
                j, i, f"{val}\n({pct:.1f}%)",
                horizontalalignment="center",
                verticalalignment="center",
                color="white" if val > thresh else "black",
                fontweight="bold"
            )

    plt.ylabel("Predicted Label")
    plt.xlabel("True Label")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"  -> Saved confusion matrix plot to {output_path.name}")


def plot_equity_curves(
    model_curve: pd.Series,
    ma_curve: pd.Series,
    output_path: Path,
) -> None:
    """Plots comparative equity curves."""
    plt.figure(figsize=(10, 5))
    plt.plot(model_curve.index, model_curve.values, label="ML Model Strategy", color="#16a34a", linewidth=2.0)
    plt.plot(ma_curve.index, ma_curve.values, label="5/20 MA Crossover", color="#ea580c", linestyle="--", linewidth=1.5)
    plt.axhline(INITIAL_CAPITAL, color="#9ca3af", linestyle=":", label="Initial Capital")

    plt.title("Out-of-Sample Backtest Equity Curve (Test Period)", fontsize=12, fontweight="bold")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Equity (INR)")
    plt.legend(loc="upper left")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"  -> Saved equity curve plot to {output_path.name}")


def run_evaluation() -> None:
    """Runs the full evaluation workflow on test set."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = MODELS_DIR / "test_split.joblib"

    if not MODEL_FILE.exists() or not snapshot_path.exists():
        print(f"[evaluate] ERROR: Model or test data not found in {MODELS_DIR}.")
        print("          Please run 'python train.py' first to build and train the model.")
        return

    print(f"[evaluate] Loading trained model from {MODEL_FILE.name}...")
    model = joblib.load(MODEL_FILE)
    test_snapshot = joblib.load(snapshot_path)

    test_df: pd.DataFrame = test_snapshot["test_df"]
    feature_cols: list[str] = test_snapshot["feature_cols"]
    model_name: str = test_snapshot.get("model_name", "BestModel")

    X_test = test_df[feature_cols]
    y_test = test_df["target"].values

    # Model predictions
    y_pred = model.predict(X_test)
    if hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
    else:
        y_prob = y_pred.astype(float)

    # 1. Model Metrics
    model_metrics = compute_metrics(y_test, y_pred, y_prob)
    cm = confusion_matrix(y_test, y_pred)

    # 2. Baseline 1: Always Predict Up (All 1s)
    always_up_pred = np.ones_like(y_test)
    always_up_metrics = compute_metrics(y_test, always_up_pred)

    # 3. Baseline 2: 5/20 MA Crossover
    if "sma_ratio" in test_df.columns:
        ma_signals = (test_df["sma_ratio"] > 1.0).astype(int).values
    elif "sma_5" in test_df.columns and "sma_20" in test_df.columns:
        ma_signals = (test_df["sma_5"] > test_df["sma_20"]).astype(int).values
    else:
        ma_signals = np.zeros_like(y_test)
    ma_metrics = compute_metrics(y_test, ma_signals)

    # Print Metrics Comparison Table
    print("\n" + "=" * 78)
    print(f" TEST SET EVALUATION SUMMARY ({len(y_test)} samples across {test_df['ticker'].nunique()} tickers)")
    print("=" * 78)
    headers = f"{'Strategy / Model':<28} | {'Accuracy':<9} | {'Precision':<9} | {'Recall':<8} | {'F1':<8} | {'ROC-AUC':<8}"
    print(headers)
    print("-" * 78)
    print(f"{model_name + ' (ML Model)':<28} | {model_metrics['accuracy']:<9.4f} | {model_metrics['precision']:<9.4f} | {model_metrics['recall']:<8.4f} | {model_metrics['f1']:<8.4f} | {model_metrics['roc_auc']:<8.4f}")
    print(f"{'5/20 MA Crossover':<28} | {ma_metrics['accuracy']:<9.4f} | {ma_metrics['precision']:<9.4f} | {ma_metrics['recall']:<8.4f} | {ma_metrics['f1']:<8.4f} | {ma_metrics['roc_auc']:<8.4f}")
    print(f"{'Always Predict Up':<28} | {always_up_metrics['accuracy']:<9.4f} | {always_up_metrics['precision']:<9.4f} | {always_up_metrics['recall']:<8.4f} | {always_up_metrics['f1']:<8.4f} | {'N/A':<8}")
    print("=" * 78)

    print("\nConfusion Matrix (Model vs Actual):")
    print(f"  True Negatives  (0 -> 0): {cm[0, 0]:5d}")
    print(f"  False Positives (0 -> 1): {cm[0, 1]:5d}")
    print(f"  False Negatives (1 -> 0): {cm[1, 0]:5d}")
    print(f"  True Positives  (1 -> 1): {cm[1, 1]:5d}")

    # Check for suspiciously high scores
    if model_metrics["roc_auc"] > 0.85 or model_metrics["accuracy"] > 0.85:
        print("\n" + "!" * 78)
        print(" [WARNING] SUSPICIOUSLY HIGH METRIC DETECTED ON TEST SET!")
        print(f" Test ROC-AUC is {model_metrics['roc_auc']:.4f} (> 0.85).")
        print(" This may indicate lookahead data leakage in features or time alignment.")
        print("!" * 78 + "\n")

    # 4. Realistic Backtest with transaction costs
    print("\n[evaluate] Running backtest simulation with costs (Rs. 20 broker + Rs. 15.34 DP)...")
    model_signals = pd.Series(y_pred, index=test_df.index)
    bt_model = run_backtest_simulation(test_df, model_signals)

    ma_sig_series = pd.Series(ma_signals, index=test_df.index)
    bt_ma = run_backtest_simulation(test_df, ma_sig_series)

    print("\n" + "=" * 78)
    print(" BACKTEST PERFORMANCE COMPARISON (TEST PERIOD)")
    print("=" * 78)
    bt_header = f"{'Strategy':<22} | {'Return %':<10} | {'Max DD %':<10} | {'Trades':<8} | {'Win Rate %':<11} | {'Fees Paid':<10}"
    print(bt_header)
    print("-" * 78)
    print(f"{'ML Model Strategy':<22} | {bt_model['total_return_pct']:<+10.2f} | {bt_model['max_drawdown_pct']:<10.2f} | {bt_model['total_trades']:<8d} | {bt_model['win_rate_pct']:<11.1f} | Rs. {bt_model['fees_paid']:<6.2f}")
    print(f"{'5/20 MA Crossover':<22} | {bt_ma['total_return_pct']:<+10.2f} | {bt_ma['max_drawdown_pct']:<10.2f} | {bt_ma['total_trades']:<8d} | {bt_ma['win_rate_pct']:<11.1f} | Rs. {bt_ma['fees_paid']:<6.2f}")
    print("=" * 78)

    # 5. Generate and Save Plots
    print("\n[evaluate] Generating plots in logs/...")
    plot_feature_importance(model, feature_cols, LOGS_DIR / "feature_importance.png")
    plot_confusion_matrix(cm, LOGS_DIR / "confusion_matrix.png")
    plot_equity_curves(bt_model["equity_curve"], bt_ma["equity_curve"], LOGS_DIR / "equity_curve.png")
    print(f"[evaluate] Evaluation complete. Plots stored in {LOGS_DIR}.")


if __name__ == "__main__":
    run_evaluation()
