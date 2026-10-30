import joblib
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score

from train import load_all_ticker_data, time_based_split

print("================================================================================")
print(" TRAINING QUANT ADVANCED SOFT-VOTING ENSEMBLE (RandomForest + LightGBM)")
print("================================================================================")

df, feat_cols = load_all_ticker_data(include_news=False)
train_df, val_df, test_df = time_based_split(df)
train_val = pd.concat([train_df, val_df])

X_train, y_train = train_val[feat_cols], train_val["target"].values
X_test, y_test = test_df[feat_cols], test_df["target"].values

rf = RandomForestClassifier(
    n_estimators=150,
    max_depth=6,
    min_samples_leaf=15,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

hgb = HistGradientBoostingClassifier(
    max_iter=150,
    max_depth=5,
    min_samples_leaf=20,
    l2_regularization=2.0,
    class_weight="balanced",
    random_state=42,
)

ensemble = VotingClassifier(
    estimators=[("rf", rf), ("hgb", hgb)],
    voting="soft",
    weights=[0.55, 0.45],
)

print(f"Training ensemble on {len(X_train)} samples across {len(feat_cols)} features...")
ensemble.fit(X_train, y_train)

# Evaluation
test_probs = ensemble.predict_proba(X_test)[:, 1]
test_auc = roc_auc_score(y_test, test_probs)
preds = (test_probs >= 0.51).astype(int)
win_rate = y_test[preds == 1].mean() if preds.sum() > 0 else 0.0

print(f"Ensemble Test AUC: {test_auc:.4f}")
print(f"Ensemble Buy Win Rate (@ 0.51 threshold): {win_rate:.2%} across {preds.sum()} signals")

# Save as champion model
models_dir = Path("models")
models_dir.mkdir(parents=True, exist_ok=True)
joblib.dump(ensemble, models_dir / "best_model.joblib")
joblib.dump(feat_cols, models_dir / "feature_names.joblib")
print(f"Successfully saved VotingClassifier ensemble to {models_dir / 'best_model.joblib'}!")

