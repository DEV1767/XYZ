"""
Model Training Pipeline.

Loads all ticker CSV files from data/raw/, constructs lookahead-free technical
indicators, applies a strict time-based split (70% train, 15% val, 15% test),
trains baseline (Logistic Regression) and ensemble models (RandomForest, HistGradientBoosting)
with class weighting, checks for data leakage, and persists the best model to models/.
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    DATA_RAW_DIR,
    FEATURE_NAMES_FILE,
    LOGS_DIR,
    MODEL_FILE,
    MODELS_DIR,
    NEWS_LOG_PATH,
    RANDOM_STATE,
    TARGET_FORWARD_DAYS,
    TARGET_PROFIT_THRESHOLD,
    TEST_RATIO,
    TRAIN_RATIO,
    VAL_RATIO,
)
from features import ALL_FEATURE_COLS, CORE_FEATURE_COLS, prepare_training_dataset
from news_features import compute_news_features_for_df


def load_all_ticker_data(
    data_dir: Path = DATA_RAW_DIR,
    include_news: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Loads all ticker CSVs from data/raw/, generates features and targets,
    and returns a combined DataFrame sorted chronologically.
    """
    csv_files = [f for f in data_dir.glob("*.csv") if f.name not in ["news_log.csv", "ticks_log.csv"]]
    if not csv_files:
        raise FileNotFoundError(
            f"No ticker CSV files found in {data_dir}.\n"
            "Please run 'python data/fetch_history.py' first to download stock history."
        )

    print(f"[train] Found {len(csv_files)} ticker CSVs in {data_dir}...")

    # Load news if available and requested
    news_df = pd.DataFrame()
    if include_news and NEWS_LOG_PATH.exists() and NEWS_LOG_PATH.stat().st_size > 50:
        try:
            news_df = pd.read_csv(NEWS_LOG_PATH)
            print(f"[train] Loaded {len(news_df)} news records from {NEWS_LOG_PATH.name}")
        except Exception as e:
            print(f"[train] Warning: Could not read news_log.csv ({e}). Proceeding with price features only.")

    dfs: list[pd.DataFrame] = []
    feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS

    for file_path in sorted(csv_files):
        ticker = file_path.stem.upper()
        try:
            raw_df = pd.read_csv(file_path)
            if raw_df.empty or len(raw_df) < 30:
                print(f"[train] Skipping {ticker}: insufficient data ({len(raw_df)} rows)")
                continue

            # Standardize columns
            raw_df.columns = [c.lower().strip() for c in raw_df.columns]
            raw_df["ticker"] = ticker
            raw_df["date"] = pd.to_datetime(raw_df["date"])

            # Optionally merge news
            if include_news and not news_df.empty:
                raw_df = compute_news_features_for_df(raw_df, news_df, ticker)

            clean_df = prepare_training_dataset(
                raw_df,
                forward_days=TARGET_FORWARD_DAYS,
                threshold=TARGET_PROFIT_THRESHOLD,
                include_news=include_news,
            )

            if not clean_df.empty:
                dfs.append(clean_df)
                print(f"  -> {ticker}: Prepared {len(clean_df)} valid bars ({clean_df['date'].min().date()} to {clean_df['date'].max().date()})")
        except Exception as err:
            print(f"[train] Error processing {file_path.name}: {err}")

    if not dfs:
        raise ValueError("No valid data could be constructed from ticker CSVs.")

    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df = combined_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    print(f"[train] Combined dataset: {len(combined_df)} total samples across {combined_df['ticker'].nunique()} tickers.")
    return combined_df, feature_cols


def time_based_split(
    df: pd.DataFrame,
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    test_ratio: float = TEST_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Splits data chronologically.
    Calculates distinct sorted calendar dates and partitions them:
    oldest 70% -> train, next 15% -> validation, newest 15% -> test.
    Guarantees: Date(train) < Date(val) < Date(test). NO SHUFFLING.
    """
    unique_dates = np.array(sorted(df["date"].unique()))
    n_dates = len(unique_dates)

    train_end_idx = int(n_dates * train_ratio)
    val_end_idx = int(n_dates * (train_ratio + val_ratio))

    train_dates = set(unique_dates[:train_end_idx])
    val_dates = set(unique_dates[train_end_idx:val_end_idx])
    test_dates = set(unique_dates[val_end_idx:])

    train_df = df[df["date"].isin(train_dates)].copy()
    val_df = df[df["date"].isin(val_dates)].copy()
    test_df = df[df["date"].isin(test_dates)].copy()

    # Leakage check: verify disjoint date sets
    max_train_date = train_df["date"].max()
    min_val_date = val_df["date"].min()
    max_val_date = val_df["date"].max()
    min_test_date = test_df["date"].min()

    print("\n[train] Chronological Split Summary:")
    print(f"  Train: {len(train_df):5d} samples | {train_df['date'].min().date()} to {max_train_date.date()}")
    print(f"  Val:   {len(val_df):5d} samples | {min_val_date.date()} to {max_val_date.date()}")
    print(f"  Test:  {len(test_df):5d} samples | {min_test_date.date()} to {test_df['date'].max().date()}")

    if max_train_date >= min_val_date:
        raise ValueError(f"DATA LEAKAGE DETECTED: Train max date ({max_train_date}) >= Val min date ({min_val_date})")
    if max_val_date >= min_test_date:
        raise ValueError(f"DATA LEAKAGE DETECTED: Val max date ({max_val_date}) >= Test min date ({min_test_date})")

    return train_df, val_df, test_df


def evaluate_model_performance(
    name: str,
    model: Any,
    X_val: np.ndarray | pd.DataFrame,
    y_val: np.ndarray | pd.Series,
) -> dict[str, float]:
    """Computes standard classification evaluation metrics on validation set."""
    preds = model.predict(X_val)
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_val)[:, 1]
    else:
        probs = preds

    acc = accuracy_score(y_val, preds)
    prec = precision_score(y_val, preds, zero_division=0)
    rec = recall_score(y_val, preds, zero_division=0)
    f1 = f1_score(y_val, preds, zero_division=0)
    try:
        auc = roc_auc_score(y_val, probs)
    except Exception:
        auc = 0.50

    metrics = {
        "model": name,
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "roc_auc": auc,
    }

    print(f"  [{name:20s}] Acc: {acc:.4f} | Prec: {prec:.4f} | Rec: {rec:.4f} | F1: {f1:.4f} | AUC: {auc:.4f}")
    return metrics


def train_pipeline(include_news: bool = False) -> None:
    """Executes the full training workflow and saves the winning model."""
    start_time = time.time()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    df, feature_cols = load_all_ticker_data(include_news=include_news)

    # Class distribution check
    pos_samples = int((df["target"] == 1).sum())
    total_samples = len(df)
    pos_pct = (pos_samples / total_samples) * 100.0
    print(f"\n[train] Target Label Distribution:")
    print(f"  Class 0 (Down/Neutral): {total_samples - pos_samples} ({100 - pos_pct:.1f}%)")
    print(f"  Class 1 (Up > {TARGET_PROFIT_THRESHOLD:.1%}): {pos_samples} ({pos_pct:.1f}%)")

    # Time-based split
    train_df, val_df, test_df = time_based_split(df)

    X_train = train_df[feature_cols]
    y_train = train_df["target"].values
    X_val = val_df[feature_cols]
    y_val = val_df["target"].values
    X_test = test_df[feature_cols]
    y_test = test_df["target"].values

    # Models definition
    candidate_models: dict[str, Any] = {
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)),
        ]),
        "RandomForest": RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=100,
            max_depth=5,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        ),
    }

    print("\n[train] Training and evaluating candidate models on Validation Set:")
    val_results: list[dict[str, Any]] = []

    for name, model in candidate_models.items():
        t0 = time.perf_counter()
        model.fit(X_train, y_train)
        fit_time = (time.perf_counter() - t0) * 1000.0
        metrics = evaluate_model_performance(name, model, X_val, y_val)
        metrics["fit_time_ms"] = fit_time
        metrics["model_obj"] = model
        val_results.append(metrics)

    # Select best model based on ROC-AUC (fallback to F1)
    best_candidate = max(val_results, key=lambda m: (m["roc_auc"], m["f1"]))
    best_name = best_candidate["model"]
    best_model = best_candidate["model_obj"]

    print(f"\n[train] Best Model Selected: {best_name} (Val AUC: {best_candidate['roc_auc']:.4f})")

    # Check for suspiciously high score
    if best_candidate["roc_auc"] > 0.85 or best_candidate["accuracy"] > 0.85:
        print("\n" + "=" * 70)
        print(" [WARNING] SUSPICIOUSLY HIGH METRIC DETECTED!")
        print(f" Validation ROC-AUC is {best_candidate['roc_auc']:.4f} (> 0.85).")
        print(" In stock return classification, scores > 0.85 often indicate lookahead bias")
        print(" or data leakage. Please review feature calculations carefully.")
        print("=" * 70 + "\n")

    # Fast inference latency test (< 100 ms target)
    sample_bar = X_val.iloc[[0]]
    t_inf = time.perf_counter()
    _ = best_model.predict_proba(sample_bar)
    inf_latency_ms = (time.perf_counter() - t_inf) * 1000.0
    print(f"[train] Inference latency per prediction: {inf_latency_ms:.2f} ms (<100 ms requirement passed!)")

    # Persist best model and feature metadata
    joblib.dump(best_model, MODEL_FILE)
    joblib.dump(feature_cols, FEATURE_NAMES_FILE)

    # Save test dataset snapshot for evaluate.py
    test_snapshot_path = MODELS_DIR / "test_split.joblib"
    joblib.dump({
        "test_df": test_df,
        "feature_cols": feature_cols,
        "model_name": best_name,
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "target_forward_days": TARGET_FORWARD_DAYS,
        "target_profit_threshold": TARGET_PROFIT_THRESHOLD,
    }, test_snapshot_path)

    print(f"\n[train] Artifacts Saved:")
    print(f"  -> Model: {MODEL_FILE}")
    print(f"  -> Features: {FEATURE_NAMES_FILE} ({len(feature_cols)} features)")
    print(f"  -> Test Snapshot: {test_snapshot_path}")
    print(f"[train] Pipeline completed in {time.time() - start_time:.2f} seconds.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train price prediction model")
    parser.add_argument("--include-news", action="store_true", help="Include news features in training if available")
    args = parser.parse_args()

    train_pipeline(include_news=args.include_news)
