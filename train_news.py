"""
News Sentiment Analysis and Predictive Model Trainer.

Analyzes collected news flashes against forward stock returns (+1, +3, +5 days).
Evaluates individual keyword efficacy and sentiment score buckets, outputs an
impact table showing which words actually move prices in this competition,
and trains a lightweight Logistic Regression classifier on news features.
Saves results to logs/news_analysis.csv and models/news_model.joblib.
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    BULLISH_KEYWORDS,
    BEARISH_KEYWORDS,
    DATA_RAW_DIR,
    LOGS_DIR,
    MODELS_DIR,
    NEWS_ANALYSIS_PATH,
    NEWS_LOG_PATH,
    NEWS_MODEL_FILE,
    RANDOM_STATE,
    TARGET_PROFIT_THRESHOLD,
    TICKS_LOG_PATH,
)
from news_features import extract_numbers, keyword_score


def load_price_history_lookup() -> dict[str, pd.DataFrame]:
    """Loads historical prices for all tickers for forward return matching."""
    price_map: dict[str, pd.DataFrame] = {}
    csv_files = [f for f in DATA_RAW_DIR.glob("*.csv") if f.name not in ["news_log.csv", "ticks_log.csv"]]

    for file_path in csv_files:
        ticker = file_path.stem.upper()
        try:
            df = pd.read_csv(file_path)
            df.columns = [c.lower().strip() for c in df.columns]
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            price_map[ticker] = df
        except Exception:
            pass

    # Also incorporate ticks_log.csv if present
    if TICKS_LOG_PATH.exists() and TICKS_LOG_PATH.stat().st_size > 50:
        try:
            ticks_df = pd.read_csv(TICKS_LOG_PATH)
            ticks_df.columns = [c.lower().strip() for c in ticks_df.columns]
            ticks_df["date"] = pd.to_datetime(ticks_df.get("simulated_date", ticks_df.get("date")))
            for ticker, grp in ticks_df.groupby("ticker"):
                t_upper = str(ticker).upper()
                grp_sorted = grp.sort_values("date").reset_index(drop=True)
                if t_upper in price_map:
                    combined = pd.concat([price_map[t_upper], grp_sorted], ignore_index=True)
                    price_map[t_upper] = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                else:
                    price_map[t_upper] = grp_sorted
        except Exception as e:
            print(f"[train_news] Note: could not incorporate ticks_log.csv ({e})")

    return price_map


def compute_forward_returns_for_news(
    news_df: pd.DataFrame,
    price_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Matches each news headline with the subsequent stock prices to compute
    forward returns at +1, +3, and +5 days without lookahead.
    """
    matched_records: list[dict[str, Any]] = []

    for _, row in news_df.iterrows():
        ticker = str(row["ticker"]).strip().upper()
        if ticker not in price_map:
            continue

        news_date = pd.to_datetime(row.get("simulated_date") or row.get("date"))
        p_df = price_map[ticker]

        # Find price on or immediately after news_date
        future_bars = p_df[p_df["date"] >= news_date].reset_index(drop=True)
        if len(future_bars) < 2:
            continue

        base_close = float(future_bars.iloc[0]["close"])
        if base_close <= 0:
            continue

        ret_1d = ((float(future_bars.iloc[1]["close"]) - base_close) / base_close) if len(future_bars) > 1 else np.nan
        ret_3d = ((float(future_bars.iloc[3]["close"]) - base_close) / base_close) if len(future_bars) > 3 else np.nan
        ret_5d = ((float(future_bars.iloc[5]["close"]) - base_close) / base_close) if len(future_bars) > 5 else np.nan

        headline = str(row.get("headline", ""))
        desc = str(row.get("description", ""))
        score = keyword_score(headline, desc)
        magnitude = extract_numbers(headline)

        record = {
            "date": news_date,
            "ticker": ticker,
            "headline": headline,
            "description": desc,
            "news_score": score,
            "news_magnitude": magnitude,
            "ret_1d": ret_1d,
            "ret_3d": ret_3d,
            "ret_5d": ret_5d,
        }
        matched_records.append(record)

    if not matched_records:
        return pd.DataFrame()

    return pd.DataFrame(matched_records)


def analyze_keywords_and_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes statistical efficacy of each individual keyword and score bucket:
    Average forward return, hit rate (accuracy of direction), and sample count.
    """
    print("\n" + "=" * 80)
    print(" KEYWORD IMPACT ANALYSIS (Which words actually move prices in this market?)")
    print("=" * 80)

    all_words = [(w, "BULLISH") for w in BULLISH_KEYWORDS] + [(w, "BEARISH") for w in BEARISH_KEYWORDS]
    keyword_stats: list[dict[str, Any]] = []

    for word, sentiment_type in all_words:
        # Check occurrence in headline or description
        mask = df["headline"].str.upper().str.contains(r"\b" + word + r"\b", regex=True, na=False) | \
               df["description"].str.upper().str.contains(r"\b" + word + r"\b", regex=True, na=False)

        subset = df[mask]
        count = len(subset)
        if count == 0:
            continue

        avg_ret_1d = subset["ret_1d"].mean()
        avg_ret_3d = subset["ret_3d"].mean()

        # Hit rate: % of times bullish keyword yielded positive return or bearish yielded negative
        if sentiment_type == "BULLISH":
            hit_rate_3d = (subset["ret_3d"] > 0).mean() * 100.0
        else:
            hit_rate_3d = (subset["ret_3d"] < 0).mean() * 100.0

        keyword_stats.append({
            "keyword": word,
            "type": sentiment_type,
            "count": count,
            "avg_ret_1d_pct": avg_ret_1d * 100.0,
            "avg_ret_3d_pct": avg_ret_3d * 100.0,
            "hit_rate_3d_pct": hit_rate_3d,
        })

    kw_summary_df = pd.DataFrame(keyword_stats)
    if not kw_summary_df.empty:
        kw_summary_df = kw_summary_df.sort_values("count", reverse=True if hasattr(kw_summary_df, "count") else False, by="count", ascending=False)
        header = f"{'Keyword':<14} | {'Type':<8} | {'Count':<6} | {'Avg 1D Ret':<11} | {'Avg 3D Ret':<11} | {'Hit Rate (3D)':<13}"
        print(header)
        print("-" * 80)
        for _, r in kw_summary_df.iterrows():
            print(f"{r['keyword']:<14} | {r['type']:<8} | {int(r['count']):<6d} | {r['avg_ret_1d_pct']:<+10.2f}% | {r['avg_ret_3d_pct']:<+10.2f}% | {r['hit_rate_3d_pct']:<12.1f}%")
        print("=" * 80)

    # Score Buckets Analysis
    print("\n" + "=" * 60)
    print(" NEWS SCORE BUCKET ANALYSIS")
    print("=" * 60)
    df["bucket"] = pd.cut(
        df["news_score"],
        bins=[-np.inf, -2, -0.5, 0.5, 2, np.inf],
        labels=["Strong Bearish (<= -2)", "Mild Bearish (-1)", "Neutral (0)", "Mild Bullish (+1)", "Strong Bullish (>= +2)"]
    )
    bucket_summary = df.groupby("bucket", observed=False).agg(
        sample_count=("ret_3d", "count"),
        avg_ret_1d=("ret_1d", lambda x: x.mean() * 100.0),
        avg_ret_3d=("ret_3d", lambda x: x.mean() * 100.0),
        win_rate_3d=("ret_3d", lambda x: (x > 0).mean() * 100.0),
    ).reset_index()

    b_header = f"{'Sentiment Bucket':<24} | {'Count':<6} | {'Avg 1D':<8} | {'Avg 3D':<8} | {'% Up 3D':<8}"
    print(b_header)
    print("-" * 60)
    for _, b in bucket_summary.iterrows():
        print(f"{str(b['bucket']):<24} | {int(b['sample_count']):<6d} | {b['avg_ret_1d']:<+7.2f}% | {b['avg_ret_3d']:<+7.2f}% | {b['win_rate_3d']:<7.1f}%")
    print("=" * 60)

    return kw_summary_df


def train_news_model(df: pd.DataFrame) -> None:
    """
    Trains a small Logistic Regression model on news features (score, magnitude)
    to predict 3-day return direction, using a time-based split.
    """
    valid_df = df.dropna(subset=["ret_3d"]).sort_values("date").reset_index(drop=True)
    if len(valid_df) < 15:
        print(f"[train_news] Insufficient samples ({len(valid_df)}) for ML model training. Need at least 15.")
        return

    # Target: 1 if ret_3d > 0.01 (or threshold), else 0
    valid_df["target"] = (valid_df["ret_3d"] > TARGET_PROFIT_THRESHOLD).astype(int)

    feature_cols = ["news_score", "news_magnitude"]
    split_idx = int(len(valid_df) * 0.75)

    train_data = valid_df.iloc[:split_idx]
    test_data = valid_df.iloc[split_idx:]

    X_train = train_data[feature_cols]
    y_train = train_data["target"].values
    X_test = test_data[feature_cols]
    y_test = test_data["target"].values

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(class_weight="balanced", random_state=RANDOM_STATE)),
    ])
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, preds)
    f1 = f1_score(y_test, preds, zero_division=0)
    try:
        auc = roc_auc_score(y_test, probs)
    except Exception:
        auc = 0.50

    # Baselines
    kw_baseline_pred = (test_data["news_score"] > 0).astype(int)
    kw_acc = accuracy_score(y_test, kw_baseline_pred)

    print("\n[train_news] News Model Out-of-Sample Results:")
    print(f"  News Logistic Regression -> Acc: {acc:.4f} | F1: {f1:.4f} | ROC-AUC: {auc:.4f}")
    print(f"  Keyword Score Baseline   -> Acc: {kw_acc:.4f}")

    joblib.dump(model, NEWS_MODEL_FILE)
    print(f"[train_news] Saved trained news model to {NEWS_MODEL_FILE.name}")


def run_news_pipeline() -> None:
    """Main execution orchestrator for news analysis and model training."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if not NEWS_LOG_PATH.exists() or NEWS_LOG_PATH.stat().st_size < 50:
        print(f"[train_news] No live news collected yet at {NEWS_LOG_PATH}.")
        print("             Keep 'python data/collect_news.py' running in the background")
        print("             as the Kafka sandbox streams so headlines accumulate.")
        return

    print(f"[train_news] Loading news records from {NEWS_LOG_PATH.name}...")
    news_df = pd.read_csv(NEWS_LOG_PATH)
    if news_df.empty:
        print("[train_news] News log is empty.")
        return

    price_map = load_price_history_lookup()
    if not price_map:
        print("[train_news] No stock price history found. Run 'python data/fetch_history.py' first.")
        return

    matched_df = compute_forward_returns_for_news(news_df, price_map)
    if matched_df.empty:
        print("[train_news] Could not match any news headlines with subsequent stock price bars.")
        return

    print(f"[train_news] Successfully matched {len(matched_df)} news events with subsequent prices.")

    # 1. Statistical Keyword & Bucket Breakdown
    kw_df = analyze_keywords_and_buckets(matched_df)
    if not kw_df.empty:
        kw_df.to_csv(NEWS_ANALYSIS_PATH, index=False)
        print(f"\n[train_news] Saved detailed keyword analysis to {NEWS_ANALYSIS_PATH}")

    # 2. Train and evaluate news classifier
    train_news_model(matched_df)


if __name__ == "__main__":
    run_news_pipeline()
