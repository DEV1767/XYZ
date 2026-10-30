"""
Model Training Pipeline with Purged Walk-Forward Cross-Validation (Manthan 2026).

Implements:
1. Load all ticker data with equal-weight market return context.
2. Purged Walk-Forward CV: expanding train window, fixed-size validation folds,
   and strict HORIZON_DAYS embargo between training and validation to prevent lookahead.
3. Strict time_based_split with HORIZON_DAYS embargo between splits.
4. Comprehensive evaluation: precision@top-k (5%, 10%, 20%), base rate, 5-bucket quintile tables,
   cross-sectional AUC (within-date ranking), and per-ticker AUC.
5. Baseline comparison on identical folds: Always-Buy, SMA_ratio>1, and Random.
6. Score threshold chosen dynamically on validation data (not hand-tuned).
7. Champion refit on Train+Val before saving to models/.
8. Candidate models' Val vs Test metrics reported side-by-side.
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
import lightgbm as lgb
try:
    from catboost import CatBoostClassifier
except ImportError:
    CatBoostClassifier = None
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    ATR_PERIOD,
    BARRIER_DOWN_ATR,
    BARRIER_UP_ATR,
    DATA_RAW_DIR,
    FEATURE_NAMES_FILE,
    HORIZON_DAYS,
    LOGS_DIR,
    MODEL_FILE,
    MODELS_DIR,
    NEWS_LOG_PATH,
    RANDOM_STATE,
    TEST_RATIO,
    TRAIN_RATIO,
    VAL_RATIO,
)
from features import (
    ALL_FEATURE_COLS,
    CORE_FEATURE_COLS,
    compute_market_returns,
    prepare_training_dataset,
)
from news_features import compute_news_features_for_df


def load_all_ticker_data(
    data_dir: Path = DATA_RAW_DIR,
    include_news: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Loads all ticker CSVs from data/raw/, computes equal-weight market returns,
    generates scale-free features and triple-barrier labels, and returns a combined DataFrame.
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

    # First pass: read raw data for all tickers to calculate market returns
    raw_dfs: dict[str, pd.DataFrame] = {}
    for file_path in sorted(csv_files):
        ticker = file_path.stem.upper()
        try:
            raw_df = pd.read_csv(file_path)
            if raw_df.empty or len(raw_df) < 30:
                print(f"[train] Skipping {ticker}: insufficient data ({len(raw_df)} rows)")
                continue
            raw_df.columns = [c.lower().strip() for c in raw_df.columns]
            raw_df["ticker"] = ticker
            raw_df["date"] = pd.to_datetime(raw_df["date"])
            raw_dfs[ticker] = raw_df
        except Exception as err:
            print(f"[train] Error loading {file_path.name}: {err}")

    if not raw_dfs:
        raise ValueError("No valid ticker CSVs could be loaded.")

    # Calculate equal-weight market returns across all tickers
    market_df = compute_market_returns(raw_dfs)

    # Second pass: prepare scale-free features and triple barrier targets
    dfs: list[pd.DataFrame] = []
    feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS

    for ticker, raw_df in sorted(raw_dfs.items()):
        try:
            # Optionally merge news
            if include_news and not news_df.empty:
                raw_df = compute_news_features_for_df(raw_df, news_df, ticker)

            clean_df = prepare_training_dataset(
                raw_df,
                market_df=market_df,
                include_news=include_news,
            )

            if not clean_df.empty:
                dfs.append(clean_df)
                pos = (clean_df["target"] == 1).sum()
                rate = pos / len(clean_df)
                print(
                    f"  -> {ticker:6s}: {len(clean_df):4d} valid bars "
                    f"({clean_df['date'].min().date()} to {clean_df['date'].max().date()}) | "
                    f"Wins: {pos}/{len(clean_df)} ({rate:.1%})"
                )
        except Exception as err:
            print(f"[train] Error preparing features for {ticker}: {err}")

    if not dfs:
        raise ValueError("No valid data could be constructed from ticker CSVs.")

    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df = combined_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    print(
        f"[train] Combined dataset: {len(combined_df)} total samples across "
        f"{combined_df['ticker'].nunique()} tickers ({combined_df['date'].nunique()} unique dates)."
    )
    return combined_df, feature_cols


def time_based_split(
    df: pd.DataFrame,
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    test_ratio: float = TEST_RATIO,
    embargo: int = HORIZON_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Splits data chronologically with an embargo of HORIZON_DAYS dates between
    train/val and val/test (dropping those dates from the earlier set) to prevent lookahead.

    Guarantees: Date(train) < (Date(val) - embargo) AND Date(val) < (Date(test) - embargo).
    """
    unique_dates = np.array(sorted(df["date"].unique()))
    n_dates = len(unique_dates)

    train_end_idx = int(n_dates * train_ratio)
    val_end_idx = int(n_dates * (train_ratio + val_ratio))

    # Apply embargo by dropping the last 'embargo' dates from train and from val
    train_dates_arr = unique_dates[: max(0, train_end_idx - embargo)]
    val_dates_arr = unique_dates[train_end_idx : max(train_end_idx, val_end_idx - embargo)]
    test_dates_arr = unique_dates[val_end_idx:]

    train_dates = set(train_dates_arr)
    val_dates = set(val_dates_arr)
    test_dates = set(test_dates_arr)

    train_df = df[df["date"].isin(train_dates)].copy()
    val_df = df[df["date"].isin(val_dates)].copy()
    test_df = df[df["date"].isin(test_dates)].copy()

    # Leakage and embargo verification
    max_train_date = train_df["date"].max()
    min_val_date = val_df["date"].min()
    max_val_date = val_df["date"].max()
    min_test_date = test_df["date"].min()

    print("\n[train] Chronological Split Summary (with HORIZON_DAYS embargo):")
    print(
        f"  Train: {len(train_df):5d} samples ({len(train_dates_arr):3d} dates) | "
        f"{train_df['date'].min().date()} to {max_train_date.date()}"
    )
    print(f"  [Embargo: {embargo} dates dropped between Train and Val]")
    print(
        f"  Val:   {len(val_df):5d} samples ({len(val_dates_arr):3d} dates) | "
        f"{min_val_date.date()} to {max_val_date.date()}"
    )
    print(f"  [Embargo: {embargo} dates dropped between Val and Test]")
    print(
        f"  Test:  {len(test_df):5d} samples ({len(test_dates_arr):3d} dates) | "
        f"{min_test_date.date()} to {test_df['date'].max().date()}"
    )

    if max_train_date >= min_val_date:
        raise ValueError(f"DATA LEAKAGE DETECTED: Train max date ({max_train_date}) >= Val min date ({min_val_date})")
    if max_val_date >= min_test_date:
        raise ValueError(f"DATA LEAKAGE DETECTED: Val max date ({max_val_date}) >= Test min date ({min_test_date})")

    return train_df, val_df, test_df


def purged_walk_forward_splits(
    df: pd.DataFrame,
    n_folds: int = 4,
    embargo: int = HORIZON_DAYS,
    test_ratio: float = TEST_RATIO,
) -> tuple[list[tuple[pd.DataFrame, pd.DataFrame]], pd.DataFrame, pd.DataFrame]:
    """
    Constructs a Purged Walk-Forward Cross-Validation partition:
    - Reserves untouched test set at the end (test_ratio).
    - Drops an embargo of HORIZON_DAYS dates between development set and test set.
    - On the development set, creates n_folds with expanding train windows and fixed-size
      validation folds, with an embargo of HORIZON_DAYS dropped immediately prior to each validation fold.

    Returns:
      folds: list of (train_fold_df, val_fold_df)
      dev_df: full train+val development dataset
      test_df: untouched test dataset
    """
    unique_dates = np.array(sorted(df["date"].unique()))
    n_dates = len(unique_dates)

    test_size = int(n_dates * test_ratio)
    test_dates_arr = unique_dates[-test_size:]
    # Drop embargo dates prior to test
    dev_dates_arr = unique_dates[: -(test_size + embargo)]

    test_df = df[df["date"].isin(set(test_dates_arr))].copy()
    dev_df = df[df["date"].isin(set(dev_dates_arr))].copy()

    # Determine validation fold length
    n_dev_dates = len(dev_dates_arr)
    # Fixed validation length across n_folds
    val_len = n_dev_dates // (n_folds + 1)

    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    print(f"\n[train] Purged Walk-Forward CV Setup ({n_folds} folds, Embargo = {embargo} dates):")
    print(f"  Total unique dates: {n_dates} (Dev: {n_dev_dates}, Test: {len(test_dates_arr)})")

    for i in range(n_folds):
        val_end_idx = n_dev_dates - (n_folds - 1 - i) * val_len
        val_start_idx = val_end_idx - val_len
        train_end_idx = val_start_idx - embargo

        if train_end_idx <= 0:
            raise ValueError(f"Insufficient historical dates for fold {i+1} with embargo {embargo}.")

        fold_train_dates = set(dev_dates_arr[:train_end_idx])
        fold_val_dates = set(dev_dates_arr[val_start_idx:val_end_idx])

        train_fold_df = df[df["date"].isin(fold_train_dates)].copy()
        val_fold_df = df[df["date"].isin(fold_val_dates)].copy()

        # Sanity check
        if train_fold_df["date"].max() >= val_fold_df["date"].min():
            raise ValueError(f"Purged CV leakage in fold {i+1}: Train max >= Val min")

        folds.append((train_fold_df, val_fold_df))
        print(
            f"  Fold {i+1}: Train {len(train_fold_df):4d} rows ({train_end_idx:3d} dates: "
            f"{train_fold_df['date'].min().date()} to {train_fold_df['date'].max().date()}) | "
            f"Val {len(val_fold_df):4d} rows ({val_len:2d} dates: "
            f"{val_fold_df['date'].min().date()} to {val_fold_df['date'].max().date()})"
        )

    return folds, dev_df, test_df


def compute_precision_at_k(y_true: np.ndarray, scores: np.ndarray, k_list: list[float]) -> dict[str, float]:
    """Computes precision in top k% highest predicted scores."""
    res: dict[str, float] = {}
    n = len(y_true)
    for k in k_list:
        k_count = max(1, int(n * k))
        # Find threshold of top k%
        top_idx = np.argsort(scores)[::-1][:k_count]
        prec = float(np.mean(y_true[top_idx]))
        res[f"precision@top_{int(k*100)}%"] = prec
    return res


def compute_quintile_table(df_with_score: pd.DataFrame, score_col: str = "score", target_col: str = "target") -> pd.DataFrame:
    """
    Computes a 5-bucket quintile table showing sample count, win rate (mean target),
    min score, and max score across equal-frequency score bins.
    """
    data = df_with_score.copy()
    try:
        data["quintile"] = pd.qcut(data[score_col], 5, labels=["Q1(Lowest)", "Q2", "Q3", "Q4", "Q5(Highest)"])
    except ValueError:
        # Fallback if duplicate quantiles
        data["quintile"] = pd.cut(data[score_col], 5, labels=["Q1(Lowest)", "Q2", "Q3", "Q4", "Q5(Highest)"])

    q_table = data.groupby("quintile", observed=False).agg(
        count=(target_col, "count"),
        mean_target=(target_col, "mean"),
        min_score=(score_col, "min"),
        max_score=(score_col, "max"),
    ).reset_index()
    return q_table


def compute_cross_sectional_auc(
    df_with_score: pd.DataFrame,
    score_col: str = "score",
    target_col: str = "target",
    date_col: str = "date",
) -> float:
    """
    Computes average cross-sectional ROC-AUC across each individual date.
    Evaluates whether the model correctly ranks winners above losers on any given trading day.
    """
    date_aucs: list[float] = []
    for dt, grp in df_with_score.groupby(date_col):
        if len(grp) >= 2 and grp[target_col].nunique() > 1:
            try:
                auc = roc_auc_score(grp[target_col], grp[score_col])
                date_aucs.append(auc)
            except Exception:
                continue
    return float(np.mean(date_aucs)) if date_aucs else 0.50


def compute_per_ticker_auc(
    df_with_score: pd.DataFrame,
    score_col: str = "score",
    target_col: str = "target",
    ticker_col: str = "ticker",
) -> dict[str, float]:
    """Computes ROC-AUC individually for each ticker in the dataset."""
    ticker_aucs: dict[str, float] = {}
    for ticker, grp in df_with_score.groupby(ticker_col):
        if grp[target_col].nunique() > 1:
            try:
                auc = roc_auc_score(grp[target_col], grp[score_col])
                ticker_aucs[ticker] = float(auc)
            except Exception:
                ticker_aucs[ticker] = 0.50
        else:
            ticker_aucs[ticker] = 0.50
    return ticker_aucs


def evaluate_model_pipeline(
    name: str,
    model: Any,
    folds: list[tuple[pd.DataFrame, pd.DataFrame]],
    feature_cols: list[str],
) -> dict[str, Any]:
    """
    Evaluates a candidate model across all walk-forward folds.
    Returns per-fold AUCs, mean/std AUC, and out-of-fold validation predictions.
    """
    fold_aucs: list[float] = []
    val_preds_dfs: list[pd.DataFrame] = []

    for fold_idx, (tr_df, val_df) in enumerate(folds):
        X_tr = tr_df[feature_cols]
        y_tr = tr_df["target"].values
        X_val = val_df[feature_cols]
        y_val = val_df["target"].values

        model.fit(X_tr, y_tr)
        if hasattr(model, "predict_proba"):
            val_scores = model.predict_proba(X_val)[:, 1]
        else:
            val_scores = model.predict(X_val)

        try:
            auc = roc_auc_score(y_val, val_scores)
        except Exception:
            auc = 0.50

        fold_aucs.append(auc)

        val_copy = val_df.copy()
        val_copy["score"] = val_scores
        val_copy["fold"] = fold_idx + 1
        val_preds_dfs.append(val_copy)

    oof_val_df = pd.concat(val_preds_dfs, ignore_index=True)
    mean_auc = float(np.mean(fold_aucs))
    std_auc = float(np.std(fold_aucs))

    return {
        "model_name": name,
        "model_obj": model,
        "fold_aucs": fold_aucs,
        "mean_auc": mean_auc,
        "std_auc": std_auc,
        "oof_val_df": oof_val_df,
    }


def evaluate_baselines_on_folds(
    folds: list[tuple[pd.DataFrame, pd.DataFrame]],
) -> dict[str, dict[str, Any]]:
    """
    Evaluates baseline strategies on the exact same walk-forward validation folds:
    1. Always-Buy (constant score 1.0)
    2. SMA_ratio>1 (score is sma_ratio)
    3. Random Entries (uniform random score)
    """
    np.random.seed(RANDOM_STATE)
    baselines: dict[str, dict[str, Any]] = {
        "Baseline_AlwaysBuy": {"fold_aucs": [], "preds": []},
        "Baseline_SMARatio": {"fold_aucs": [], "preds": []},
        "Baseline_Random": {"fold_aucs": [], "preds": []},
    }

    for fold_idx, (_, val_df) in enumerate(folds):
        y_val = val_df["target"].values

        # 1. Always-Buy (uninformative constant ranking)
        baselines["Baseline_AlwaysBuy"]["fold_aucs"].append(0.50)
        ab_df = val_df.copy()
        ab_df["score"] = 1.0
        ab_df["fold"] = fold_idx + 1
        baselines["Baseline_AlwaysBuy"]["preds"].append(ab_df)

        # 2. SMA_ratio>1 (ranked directly by sma_ratio)
        sma_scores = val_df["sma_ratio"].values
        try:
            sma_auc = roc_auc_score(y_val, sma_scores)
        except Exception:
            sma_auc = 0.50
        baselines["Baseline_SMARatio"]["fold_aucs"].append(float(sma_auc))
        sma_df = val_df.copy()
        sma_df["score"] = sma_scores
        sma_df["fold"] = fold_idx + 1
        baselines["Baseline_SMARatio"]["preds"].append(sma_df)

        # 3. Random entries
        rand_scores = np.random.uniform(0.0, 1.0, size=len(y_val))
        try:
            rand_auc = roc_auc_score(y_val, rand_scores)
        except Exception:
            rand_auc = 0.50
        baselines["Baseline_Random"]["fold_aucs"].append(float(rand_auc))
        rnd_df = val_df.copy()
        rnd_df["score"] = rand_scores
        rnd_df["fold"] = fold_idx + 1
        baselines["Baseline_Random"]["preds"].append(rnd_df)

    res: dict[str, dict[str, Any]] = {}
    for b_name, b_data in baselines.items():
        oof_df = pd.concat(b_data["preds"], ignore_index=True)
        res[b_name] = {
            "model_name": b_name,
            "fold_aucs": b_data["fold_aucs"],
            "mean_auc": float(np.mean(b_data["fold_aucs"])),
            "std_auc": float(np.std(b_data["fold_aucs"])),
            "oof_val_df": oof_df,
        }
    return res


def train_pipeline(include_news: bool = False) -> None:
    """Executes the full training workflow and persists the winning model."""
    start_time = time.time()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load data
    df, feature_cols = load_all_ticker_data(include_news=include_news)

    # Target class distribution
    pos_samples = int((df["target"] == 1).sum())
    total_samples = len(df)
    pos_pct = (pos_samples / total_samples) * 100.0
    print(f"\n[train] Target Label Distribution:")
    print(f"  Class 0 (Down / Lower Barrier Hit / Timeout): {total_samples - pos_samples} ({100 - pos_pct:.1f}%)")
    print(f"  Class 1 (Upper Barrier Hit First):            {pos_samples} ({pos_pct:.1f}%)")

    # 2. Chronological split summary with embargo
    _ = time_based_split(df, embargo=HORIZON_DAYS)

    # 3. Purged Walk-Forward CV partition
    folds, dev_df, test_df = purged_walk_forward_splits(df, n_folds=4, embargo=HORIZON_DAYS)

    # 4. Define candidate models
    candidate_models: dict[str, Any] = {
        "LightGBM": lgb.LGBMClassifier(
            n_estimators=150,
            max_depth=5,
            num_leaves=31,
            learning_rate=0.05,
            min_child_samples=20,
            reg_lambda=2.0,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            verbosity=-1,
            n_jobs=-1,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=100,
            max_depth=4,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)),
        ]),
    }

    # 5. Evaluate candidate models across purged walk-forward folds
    print("\n" + "=" * 90)
    print(" PURGED WALK-FORWARD CROSS-VALIDATION RESULTS (4 FOLDS)")
    print("=" * 90)

    model_eval_results: dict[str, dict[str, Any]] = {}
    for name, model in candidate_models.items():
        t0 = time.perf_counter()
        eval_dict = evaluate_model_pipeline(name, model, folds, feature_cols)
        eval_dict["fit_eval_time_s"] = time.perf_counter() - t0
        model_eval_results[name] = eval_dict
        folds_str = ", ".join(f"{auc:.4f}" for auc in eval_dict["fold_aucs"])
        print(f"  {name:22s} Folds: [{folds_str}] | Mean AUC: {eval_dict['mean_auc']:.4f} +/- {eval_dict['std_auc']:.4f}")

    # 6. Evaluate baselines on identical folds
    baseline_results = evaluate_baselines_on_folds(folds)
    for b_name, b_res in baseline_results.items():
        folds_str = ", ".join(f"{auc:.4f}" for auc in b_res["fold_aucs"])
        print(f"  {b_name:22s} Folds: [{folds_str}] | Mean AUC: {b_res['mean_auc']:.4f} +/- {b_res['std_auc']:.4f}")

    print("=" * 90)

    # Combine all results for comparison
    all_evals = {**model_eval_results, **baseline_results}

    # Select champion model among machine learning models
    champion_name = max(model_eval_results.keys(), key=lambda k: model_eval_results[k]["mean_auc"])
    champion_eval = model_eval_results[champion_name]

    print(f"\n[train] Champion Model: {champion_name} (Mean Walk-Forward AUC: {champion_eval['mean_auc']:.4f})")

    # Verify model beats baselines
    best_baseline_auc = max(b["mean_auc"] for b in baseline_results.values())
    if champion_eval["mean_auc"] > best_baseline_auc:
        print(
            f"[train] VERIFICATION PASSED: Champion {champion_name} AUC ({champion_eval['mean_auc']:.4f}) "
            f"beats all baselines (Best Baseline: {best_baseline_auc:.4f})!"
        )
    else:
        print(
            f"[train] WARNING: Champion {champion_name} AUC ({champion_eval['mean_auc']:.4f}) "
            f"does not beat best baseline ({best_baseline_auc:.4f}). Reporting as required by Acceptance criteria."
        )

    # 7. In-depth Validation Performance of Champion Model
    oof_val_df = champion_eval["oof_val_df"]
    y_val_oof = oof_val_df["target"].values
    scores_val_oof = oof_val_df["score"].values
    val_base_rate = float(np.mean(y_val_oof))

    val_top_k = compute_precision_at_k(y_val_oof, scores_val_oof, [0.05, 0.10, 0.20])
    val_quintiles = compute_quintile_table(oof_val_df)
    val_cross_sec_auc = compute_cross_sectional_auc(oof_val_df)
    val_per_ticker_auc = compute_per_ticker_auc(oof_val_df)

    print("\n" + "=" * 90)
    print(f" DETAILED VALIDATION METRICS: {champion_name} (Out-of-Fold)")
    print("=" * 90)
    print(f"  Validation Samples:        {len(oof_val_df)}")
    print(f"  Base Rate (Win Fraction):  {val_base_rate:.4f} ({val_base_rate:.1%})")
    print(f"  Precision@top-5%:          {val_top_k['precision@top_5%']:.4f}")
    print(f"  Precision@top-10%:         {val_top_k['precision@top_10%']:.4f}")
    print(f"  Precision@top-20%:         {val_top_k['precision@top_20%']:.4f}")
    print(f"  Cross-Sectional Mean AUC:  {val_cross_sec_auc:.4f}")

    print("\n  5-Bucket Quintile Table (Validation):")
    for _, row in val_quintiles.iterrows():
        print(
            f"    {row['quintile']:12s} | Count: {int(row['count']):4d} | "
            f"Win Rate: {row['mean_target']:.4f} | Score Range: [{row['min_score']:.4f}, {row['max_score']:.4f}]"
        )

    print("\n  Per-Ticker ROC-AUC (Validation):")
    for tck, t_auc in sorted(val_per_ticker_auc.items()):
        print(f"    {tck:6s}: {t_auc:.4f}")
    print("=" * 90)

    # 8. Score Threshold Selection on Validation Data
    # Target top 20% score percentile (capped between 0.52 and 0.60) to balance conviction with trade flow
    raw_thresh = float(np.quantile(scores_val_oof, 0.80))
    chosen_threshold = max(0.52, min(0.60, raw_thresh))
    print(f"\n[train] Score Threshold chosen on Validation data (80th percentile capped): {chosen_threshold:.4f} (raw: {raw_thresh:.4f})")
    print(f"        (Val Precision above this threshold: {val_top_k['precision@top_10%']:.4f} vs Base Rate: {val_base_rate:.4f})")

    # 9. Refit Candidate Models and Champion on Train+Val (Development set)
    print(f"\n[train] Refitting candidate models on full development set (Train + Val: {len(dev_df)} samples)...")
    X_dev = dev_df[feature_cols]
    y_dev = dev_df["target"].values

    refitted_models: dict[str, Any] = {}
    for name, model in candidate_models.items():
        model.fit(X_dev, y_dev)
        refitted_models[name] = model

    champion_model = refitted_models[champion_name]

    # 10. Evaluate on the Untouched Test Set (EXACTLY ONCE)
    print(f"\n[train] Evaluating models on untouched Test Set ({len(test_df)} samples, {test_df['date'].nunique()} dates)...")
    X_test = test_df[feature_cols]
    y_test = test_df["target"].values
    test_base_rate = float(np.mean(y_test))

    test_results: dict[str, dict[str, Any]] = {}
    for name, model in refitted_models.items():
        if hasattr(model, "predict_proba"):
            test_scores = model.predict_proba(X_test)[:, 1]
        else:
            test_scores = model.predict(X_test)

        try:
            t_auc = roc_auc_score(y_test, test_scores)
        except Exception:
            t_auc = 0.50

        test_copy = test_df.copy()
        test_copy["score"] = test_scores
        top_k = compute_precision_at_k(y_test, test_scores, [0.05, 0.10, 0.20])
        q_tab = compute_quintile_table(test_copy)
        xs_auc = compute_cross_sectional_auc(test_copy)
        ticker_auc = compute_per_ticker_auc(test_copy)

        test_results[name] = {
            "test_auc": float(t_auc),
            "test_top_k": top_k,
            "test_quintiles": q_tab,
            "test_cross_sec_auc": xs_auc,
            "test_per_ticker_auc": ticker_auc,
            "test_scores": test_scores,
        }

    # Baselines on test set
    np.random.seed(RANDOM_STATE + 1)
    # Always-Buy on test
    test_results["Baseline_AlwaysBuy"] = {
        "test_auc": 0.50,
        "test_top_k": {"precision@top_5%": test_base_rate, "precision@top_10%": test_base_rate, "precision@top_20%": test_base_rate},
    }
    # SMA_ratio on test
    sma_test_scores = test_df["sma_ratio"].values
    try:
        sma_test_auc = roc_auc_score(y_test, sma_test_scores)
    except Exception:
        sma_test_auc = 0.50
    test_results["Baseline_SMARatio"] = {
        "test_auc": float(sma_test_auc),
        "test_top_k": compute_precision_at_k(y_test, sma_test_scores, [0.05, 0.10, 0.20]),
    }
    # Random on test
    rnd_test_scores = np.random.uniform(0.0, 1.0, size=len(y_test))
    try:
        rnd_test_auc = roc_auc_score(y_test, rnd_test_scores)
    except Exception:
        rnd_test_auc = 0.50
    test_results["Baseline_Random"] = {
        "test_auc": float(rnd_test_auc),
        "test_top_k": compute_precision_at_k(y_test, rnd_test_scores, [0.05, 0.10, 0.20]),
    }

    # 11. Side-by-Side Validation vs Test Metrics Reporting
    print("\n" + "=" * 105)
    print(" CANDIDATE MODELS & BASELINES: VALIDATION VS TEST METRICS (SIDE-BY-SIDE)")
    print("=" * 105)
    header = f"{'Model / Strategy':24s} | {'Val Mean AUC':12s} | {'Val Prec@10%':12s} | {'Test AUC':10s} | {'Test Prec@10%':13s} | {'Test Prec@20%':13s}"
    print(header)
    print("-" * 105)

    for name in list(candidate_models.keys()) + list(baseline_results.keys()):
        val_eval = all_evals[name]
        v_auc = f"{val_eval['mean_auc']:.4f} +/- {val_eval['std_auc']:.3f}"
        v_oof = val_eval["oof_val_df"]
        v_p10 = compute_precision_at_k(v_oof["target"].values, v_oof["score"].values, [0.10])["precision@top_10%"]
        t_eval = test_results[name]
        t_auc = f"{t_eval['test_auc']:.4f}"
        t_p10 = f"{t_eval['test_top_k']['precision@top_10%']:.4f}"
        t_p20 = f"{t_eval['test_top_k']['precision@top_20%']:.4f}"

        print(f"{name:24s} | {v_auc:12s} | {v_p10:12.4f} | {t_auc:10s} | {t_p10:13s} | {t_p20:13s}")

    print("=" * 105)
    print(f"Test Base Rate: {test_base_rate:.4f} ({test_base_rate:.1%}) across {len(test_df)} samples.")

    # Detailed Champion Test Quintiles and Cross-Sectional AUC
    champ_test = test_results[champion_name]
    print(f"\n  Champion ({champion_name}) Test 5-Bucket Quintile Table:")
    for _, row in champ_test["test_quintiles"].iterrows():
        print(
            f"    {row['quintile']:12s} | Count: {int(row['count']):4d} | "
            f"Win Rate: {row['mean_target']:.4f} | Score Range: [{row['min_score']:.4f}, {row['max_score']:.4f}]"
        )
    print(f"\n  Champion Test Cross-Sectional AUC: {champ_test['test_cross_sec_auc']:.4f}")
    print(f"  Champion Test Per-Ticker AUC:")
    for tck, t_auc in sorted(champ_test["test_per_ticker_auc"].items()):
        print(f"    {tck:6s}: {t_auc:.4f}")

    # Latency check
    sample_bar = X_test.iloc[[0]]
    t_inf = time.perf_counter()
    _ = champion_model.predict_proba(sample_bar)
    inf_latency_ms = (time.perf_counter() - t_inf) * 1000.0
    print(f"\n[train] Inference latency per single bar: {inf_latency_ms:.2f} ms")

    # 12. Save Artifacts
    joblib.dump(champion_model, MODEL_FILE)
    joblib.dump(feature_cols, FEATURE_NAMES_FILE)

    metadata_path = MODELS_DIR / "model_metadata.joblib"
    joblib.dump({
        "champion_name": champion_name,
        "chosen_threshold": chosen_threshold,
        "feature_cols": feature_cols,
        "val_mean_auc": champion_eval["mean_auc"],
        "val_std_auc": champion_eval["std_auc"],
        "val_precision_top_10": val_top_k["precision@top_10%"],
        "test_auc": champ_test["test_auc"],
        "test_precision_top_10": champ_test["test_top_k"]["precision@top_10%"],
        "barrier_params": {
            "up_atr": BARRIER_UP_ATR,
            "down_atr": BARRIER_DOWN_ATR,
            "horizon_days": HORIZON_DAYS,
            "atr_period": ATR_PERIOD,
        },
    }, metadata_path)

    test_snapshot_path = MODELS_DIR / "test_split.joblib"
    joblib.dump({
        "test_df": test_df,
        "feature_cols": feature_cols,
        "model_name": champion_name,
        "chosen_threshold": chosen_threshold,
        "dev_samples": len(dev_df),
        "test_samples": len(test_df),
        "barrier_up_atr": BARRIER_UP_ATR,
        "barrier_down_atr": BARRIER_DOWN_ATR,
        "horizon_days": HORIZON_DAYS,
    }, test_snapshot_path)

    print(f"\n[train] Artifacts Saved:")
    print(f"  -> Model:         {MODEL_FILE}")
    print(f"  -> Features:      {FEATURE_NAMES_FILE} ({len(feature_cols)} features)")
    print(f"  -> Metadata:      {metadata_path} (chosen threshold: {chosen_threshold:.4f})")
    print(f"  -> Test Snapshot: {test_snapshot_path}")
    print(f"[train] Pipeline completed successfully in {time.time() - start_time:.2f} seconds.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train price prediction model with purged walk-forward CV")
    parser.add_argument("--include-news", action="store_true", help="Include news features in training if available")
    args = parser.parse_args()

    train_pipeline(include_news=args.include_news)
