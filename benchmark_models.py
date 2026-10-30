"""
Purged Walk-Forward Benchmark of Advanced Models.
Compares:
1. HistGradientBoosting (Current scikit-learn Champion)
2. Official LightGBM (LGBMClassifier)
3. Soft-Voting Ensemble (RandomForest + HistGradientBoosting)
4. Soft-Voting Ensemble (RandomForest + LightGBM)
Evaluates on 4 Purged Walk-Forward Folds with 15-day embargo.
"""

import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import roc_auc_score, precision_score

import lightgbm as lgb
from catboost import CatBoostClassifier

from train import (
    load_all_ticker_data,
    purged_walk_forward_splits,
    compute_precision_at_k,
    HORIZON_DAYS,
)

print("=" * 80)
print(" BENCHMARKING ADVANCED MODELS ON 4-FOLD PURGED WALK-FORWARD CV")
print("=" * 80)

df, feat_cols = load_all_ticker_data(include_news=False)
folds, dev_df, test_df = purged_walk_forward_splits(df, n_folds=4, embargo=HORIZON_DAYS)

# Define Model Configurations
models = {
    "HistGradientBoosting (Current)": lambda: HistGradientBoostingClassifier(
        max_iter=150,
        max_depth=5,
        min_samples_leaf=20,
        l2_regularization=2.0,
        class_weight="balanced",
        random_state=42,
    ),
    "Official LightGBM (LGBMClassifier)": lambda: lgb.LGBMClassifier(
        n_estimators=150,
        max_depth=5,
        num_leaves=31,
        learning_rate=0.05,
        min_child_samples=20,
        reg_lambda=2.0,
        class_weight="balanced",
        random_state=42,
        verbosity=-1,
        n_jobs=-1,
    ),
    "Ensemble (RF + HistGB)": lambda: VotingClassifier(
        estimators=[
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=6, min_samples_leaf=15, class_weight="balanced", random_state=42, n_jobs=-1)),
            ("hgb", HistGradientBoostingClassifier(max_iter=150, max_depth=5, min_samples_leaf=20, l2_regularization=2.0, class_weight="balanced", random_state=42)),
        ],
        voting="soft",
        weights=[0.4, 0.6],
    ),
    "Ensemble (RF + LightGBM)": lambda: VotingClassifier(
        estimators=[
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=6, min_samples_leaf=15, class_weight="balanced", random_state=42, n_jobs=-1)),
            ("lgbm", lgb.LGBMClassifier(n_estimators=150, max_depth=5, num_leaves=31, learning_rate=0.05, min_child_samples=20, reg_lambda=2.0, class_weight="balanced", random_state=42, verbosity=-1, n_jobs=-1)),
        ],
        voting="soft",
        weights=[0.4, 0.6],
    ),
    "CatBoostClassifier": lambda: CatBoostClassifier(
        iterations=150,
        depth=5,
        learning_rate=0.05,
        l2_leaf_reg=3.0,
        auto_class_weights="Balanced",
        random_seed=42,
        verbose=0,
    ),
}

results = {name: {"fold_aucs": [], "prec10s": [], "times": []} for name in models}

for fold_idx, (train_fold, val_fold) in enumerate(folds):
    print(f"\n--- FOLD {fold_idx + 1}/4 (Train: {len(train_fold)} samples, Val: {len(val_fold)} samples) ---")
    X_tr, y_tr = train_fold[feat_cols], train_fold["target"].values
    X_va, y_va = val_fold[feat_cols], val_fold["target"].values

    for name, model_fn in models.items():
        t0 = time.perf_counter()
        m = model_fn()
        m.fit(X_tr, y_tr)
        t_fit = (time.perf_counter() - t0) * 1000.0

        val_probs = m.predict_proba(X_va)[:, 1]
        auc = roc_auc_score(y_va, val_probs)
        p10 = compute_precision_at_k(y_va, val_probs, [0.10])["precision@top_10%"]

        results[name]["fold_aucs"].append(auc)
        results[name]["prec10s"].append(p10)
        results[name]["times"].append(t_fit)
        print(f"  {name:36s} | AUC: {auc:.4f} | Prec@10%: {p10:.4f} | Fit: {t_fit:6.1f}ms")

# Summary Comparison Table
print("\n" + "=" * 85)
print(f"{'MODEL':36s} | {'WALK-FORWARD AUC':20s} | {'PRECISION@10%':16s} | {'FIT TIME':8s}")
print("=" * 85)

for name in models:
    aucs = np.array(results[name]["fold_aucs"])
    p10s = np.array(results[name]["prec10s"])
    times = np.array(results[name]["times"])
    mean_auc, std_auc = aucs.mean(), aucs.std()
    mean_p10 = p10s.mean()
    mean_time = times.mean()
    print(f"{name:36s} | {mean_auc:.4f} +/- {std_auc:.4f}      | {mean_p10:6.4f}          | {mean_time:6.1f}ms")

print("=" * 85)
