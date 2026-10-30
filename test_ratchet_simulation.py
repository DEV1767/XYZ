from pathlib import Path
from test_simulation_suite import SimulationEnvironment
from strategy import StrategyEngine
import strategy

# Inject the user's Tiered Ratchet (10% / 14% / 18%) directly into StrategyEngine.evaluate_ticker
orig_eval = StrategyEngine.evaluate_ticker

def evaluate_ticker_with_ratchet(self, ticker, buffer_df, news_score=0, current_cash=1000000.0, current_date=""):
    # First check position exits
    ticker = ticker.upper()
    if ticker in self.positions:
        pos = self.positions[ticker]
        if pos.get("type") == "LONG":
            entry_p = float(pos.get("entry_price", 0.0))
            if entry_p > 0 and not buffer_df.empty:
                latest_c = float(buffer_df["close"].iloc[-1])
                peak_p = max(float(pos.get("peak_price", entry_p)), latest_c)
                pos["peak_price"] = peak_p
                pnl = (latest_c - entry_p) / entry_p
                peak_pnl = (peak_p - entry_p) / entry_p
                trail_drop = (peak_p - latest_c) / peak_p if peak_p > 0 else 0.0
                shares = pos["shares"]

                # User's Tier 3 (+18% reached, lock if pulls back 4%)
                if peak_pnl >= 0.18 and trail_drop >= 0.04:
                    return {
                        "ticker": ticker, "action": "SELL", "quantity": shares, "price": latest_c,
                        "reason": f"TIER 3 TARGET LOCK: Booked +{pnl:.2%} profit (peak was +{peak_pnl:.2%})",
                        "confidence": 0.95
                    }

                # User's Tier 2 (+14% reached, lock if pulls back to <= +11%)
                if peak_pnl >= 0.14 and pnl <= 0.11:
                    return {
                        "ticker": ticker, "action": "SELL", "quantity": shares, "price": latest_c,
                        "reason": f"TIER 2 PROFIT LOCK: Protected +{pnl:.2%} profit (peak was +{peak_pnl:.2%})",
                        "confidence": 0.95
                    }

                # User's Tier 1 (+10% reached, lock if pulls back to <= +7%, never let +10% turn red!)
                if peak_pnl >= 0.10 and pnl <= 0.07:
                    return {
                        "ticker": ticker, "action": "SELL", "quantity": shares, "price": latest_c,
                        "reason": f"TIER 1 PROFIT LOCK: Protected +{pnl:.2%} profit (peak was +{peak_pnl:.2%})",
                        "confidence": 0.95
                    }

    return orig_eval(self, ticker, buffer_df, news_score, current_cash, current_date)

StrategyEngine.evaluate_ticker = evaluate_ticker_with_ratchet

print("=== TESTING USER'S TIERED PROFIT RATCHET (10% / 14% / 18%) ===")
strat = StrategyEngine(model_path=Path("models/best_model.joblib"), features_path=Path("models/feature_names.joblib"))
sim = SimulationEnvironment()
res = sim.run_simulation(strategy=strat)

p1 = res["pillar_1_total_wealth"]
p2 = res["pillar_2_cash_utilization"]
p4 = res["pillar_4_order_accuracy"]
p5 = res["pillar_5_friction_and_tax_efficiency"]

print(f"\n=======================================================")
print(f" RESULTS WITH TIERED RATCHET LOCKS (10% / 14% / 18%):")
print(f" Final Total Wealth:   Rs. {p1['final_total_wealth']:,.2f} ({p1['net_return_pct']:+.2f}%)")
print(f" Realized PnL:         Rs. {p1['realized_pnl_inr']:,.2f}")
print(f" Unrealized PnL:       Rs. {p1['unrealized_pnl_inr']:,.2f}")
print(f" Cash Utilization:     {p2['average_cash_utilization_pct']:.1f}%")
print(f" Total Orders:         {p4['total_orders']}")
print(f" Total Frictions:      Rs. {p5['total_frictions_inr']:,.2f}")
print(f"=======================================================")

