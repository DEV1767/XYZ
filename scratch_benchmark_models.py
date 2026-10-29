import joblib
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from train import load_all_ticker_data, time_based_split
from test_simulation_suite import SimulationEnvironment
from strategy import StrategyEngine

df, feat = load_all_ticker_data(include_news=False)
train_df, val_df, test_df = time_based_split(df)
train_val = pd.concat([train_df, val_df])

X_train, y_train = train_val[feat], train_val["target"].values

models = {
    "HistGradientBoosting": HistGradientBoostingClassifier(
        max_iter=150, max_depth=5, min_samples_leaf=20, l2_regularization=2.0, class_weight="balanced", random_state=42
    ),
    "RandomForest": RandomForestClassifier(
        n_estimators=150, max_depth=6, min_samples_leaf=15, class_weight="balanced", random_state=42, n_jobs=-1
    ),
}

print("\n" + "=" * 80)
print(" BENCHMARKING OPEN-SOURCE MODELS AGAINST MANTHAN 2026 TEST SUITE")
print("=" * 80)

for name, m in models.items():
    print(f"\nTraining {name} on {len(X_train)} samples...")
    m.fit(X_train, y_train)
    temp_path = Path(f"models/temp_{name}.joblib")
    joblib.dump(m, temp_path)

    strat = StrategyEngine(model_path=temp_path, features_path=Path("models/feature_names.joblib"))
    sim = SimulationEnvironment()
    res = sim.run_simulation(strategy=strat)

    p1 = res["pillar_1_total_wealth"]
    p2 = res["pillar_2_cash_utilization"]
    p4 = res["pillar_4_order_accuracy"]
    p5 = res["pillar_5_friction_and_tax_efficiency"]

    print(f"\n>>> RESULT FOR {name} <<<")
    print(f"  * Final Total Wealth:   Rs. {p1['final_total_wealth']:,.2f} ({p1['net_return_pct']:+.2f}%)")
    print(f"  * Realized PnL:         Rs. {p1['realized_pnl_inr']:,.2f}")
    print(f"  * Unrealized PnL:       Rs. {p1['unrealized_pnl_inr']:,.2f}")
    print(f"  * Cash Utilization:     {p2['average_cash_utilization_pct']:.1f}%")
    print(f"  * Total Orders:         {p4['total_orders']}")
    print(f"  * Total Frictions:      Rs. {p5['total_frictions_inr']:,.2f}")
    print("=" * 80)
