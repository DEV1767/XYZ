"""
Deploy the High-Performance LightGBM Champion Model for Live Trading.
Trains on full historical dev data (Train + Val), calibrates threshold,
and saves production artifacts to models/.
"""

import time
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from config import MODELS_DIR, MODEL_FILE, FEATURE_NAMES_FILE
from train import load_all_ticker_data, purged_walk_forward_splits, compute_precision_at_k, HORIZON_DAYS

print("================================================================================")
print(" TRAINING & DEPLOYING OFFICIAL LIGHTGBM CHAMPION MODEL")
print("================================================================================")

# 1. Load data
df, feature_cols = load_all_ticker_data(include_news=False)
folds, dev_df, test_df = purged_walk_forward_splits(df, n_folds=4, embargo=HORIZON_DAYS)

X_dev = dev_df[feature_cols]
y_dev = dev_df["target"].values
X_test = test_df[feature_cols]
y_test = test_df["target"].values

# 2. Configure Official LightGBM for maximum precision & profit
model = lgb.LGBMClassifier(
    n_estimators=150,
    max_depth=5,
    num_leaves=31,
    learning_rate=0.04,
    min_child_samples=20,
    subsample=0.85,
    colsample_bytree=0.85,
    reg_alpha=0.5,
    reg_lambda=2.0,
    class_weight="balanced",
    random_state=42,
    verbosity=-1,
    n_jobs=-1,
)

t0 = time.perf_counter()
model.fit(X_dev, y_dev)
fit_time_ms = (time.perf_counter() - t0) * 1000.0

# 3. Evaluate on untouched Test set
test_probs = model.predict_proba(X_test)[:, 1]
test_auc = roc_auc_score(y_test, test_probs)
test_prec10 = compute_precision_at_k(y_test, test_probs, [0.10])["precision@top_10%"]
test_prec20 = compute_precision_at_k(y_test, test_probs, [0.20])["precision@top_20%"]
base_rate = float(np.mean(y_test))

# 4. Calibrate buy threshold for active trade generation (top 25% percentile or 0.52)
dev_probs = model.predict_proba(X_dev)[:, 1]
calibrated_threshold = max(0.51, min(0.55, float(np.quantile(dev_probs, 0.75))))

print(f"\n[deploy] Model Fit Time:           {fit_time_ms:.1f} ms")
print(f"[deploy] Test Set ROC-AUC:         {test_auc:.4f}")
print(f"[deploy] Test Precision@Top-10%:   {test_prec10:.4f} (vs Base Rate: {base_rate:.4f})")
print(f"[deploy] Test Precision@Top-20%:   {test_prec20:.4f}")
print(f"[deploy] Calibrated Buy Threshold: {calibrated_threshold:.4f}")

# 5. Save model artifacts
MODELS_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(model, MODEL_FILE)
joblib.dump(feature_cols, FEATURE_NAMES_FILE)

meta = {
    "model_type": "LGBMClassifier",
    "features_count": len(feature_cols),
    "chosen_threshold": calibrated_threshold,
    "test_auc": float(test_auc),
    "test_prec10": float(test_prec10),
    "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
}
metadata_path = MODELS_DIR / "model_metadata.joblib"
joblib.dump(meta, metadata_path)

print(f"\n[deploy] SUCCESS: Production model saved to {MODEL_FILE}")
print(f"[deploy] Metadata saved to {metadata_path}")
print("================================================================================")
