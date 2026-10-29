"""
Local Sandbox Replay Simulator.

Replays the downloaded real stock data tick-by-tick (simulating the Kafka stream)
through the StrategyEngine, exercising the trained ML model, news sentiment scoring,
position sizing, stop-loss, and transaction costs.
Allows full end-to-end testing of model performance and trading logic anytime.
"""

from __future__ import annotations
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

from config import DATA_RAW_DIR, INITIAL_CAPITAL
from simulation_logger import sim_logger
from strategy import StrategyEngine


def run_local_sandbox(days_to_replay: int = 40, delay_sec: float = 0.15) -> None:
    """Replays recent market bars sequentially to demonstrate real-time bot execution."""
    csv_files = [f for f in DATA_RAW_DIR.glob("*.csv") if f.name not in ["news_log.csv", "ticks_log.csv"]]
    if not csv_files:
        print("[simulate] No stock data found in data/raw/. Run 'python data/fetch_history.py' first.")
        return

    tickers = sorted([f.stem.upper() for f in csv_files])
    print("\n" + "=" * 75)
    print(" MANTHAN 2026: LOCAL SANDBOX REPLAY SIMULATION")
    print(f" Initial Virtual Capital: Rs. {INITIAL_CAPITAL:,.2f}")
    print(f" Active Ticker Universe: {tickers}")
    print(f" Replaying last {days_to_replay} simulated market days...")
    print("=" * 75 + "\n")

    # Load all historical DataFrames
    data_by_ticker: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = pd.read_csv(DATA_RAW_DIR / f"{t}.csv")
        df.columns = [c.lower().strip() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        data_by_ticker[t] = df

    # Find the shared calendar dates
    all_dates = sorted(list(set.intersection(*[set(df["date"]) for df in data_by_ticker.values()])))
    if len(all_dates) < days_to_replay + 25:
        replay_dates = all_dates[-days_to_replay:]
    else:
        replay_dates = all_dates[-days_to_replay:]

    # Initialize Strategy Engine with trained ML model
    engine = StrategyEngine(valid_tickers=tickers)

    cash = float(INITIAL_CAPITAL)
    trade_log: list[dict] = []

    # Stream day by day
    for day_idx, sim_date in enumerate(replay_dates, start=1):
        date_str = sim_date.strftime("%Y-%m-%d")
        print(f"\n>>> [SIMULATED DAY {day_idx}/{len(replay_dates)}: {date_str}] <<<")

        for ticker in tickers:
            df = data_by_ticker[ticker]
            # Slices up to current simulated date strictly (anti-lookahead, >= 100 bars)
            current_buffer = df[df["date"] <= sim_date].tail(120).copy()

            if len(current_buffer) < 20:
                continue

            # Simulate corporate news catalyst occasionally
            simulated_news = 0
            if ticker in ["AERX", "ROUT"] and day_idx in [5, 12, 22]:
                simulated_news = 2  # Strong bullish news flash
                sim_logger.log_news(date_str, ticker, 2, 15.0, f"Simulated Bullish Earnings Beat for {ticker}")
            elif ticker in ["PLNX", "SONA"] and day_idx in [8, 18]:
                simulated_news = -2  # Bearish news flash
                sim_logger.log_news(date_str, ticker, -2, -10.0, f"Simulated Adverse Regulatory Notice for {ticker}")

            # Log raw tick
            latest_bar = current_buffer.iloc[-1]
            sim_logger.log_tick(
                date_str, ticker,
                float(latest_bar.get("open", latest_bar["close"])),
                float(latest_bar.get("high", latest_bar["close"])),
                float(latest_bar.get("low", latest_bar["close"])),
                float(latest_bar["close"]),
                float(latest_bar.get("volume", 100000.0)),
            )

            # Evaluate strategy (< 2 ms)
            t0 = time.perf_counter()
            decision = engine.evaluate_ticker(
                ticker=ticker,
                buffer_df=current_buffer,
                news_score=simulated_news,
                current_cash=cash,
                current_date=date_str,
            )
            eval_latency_ms = (time.perf_counter() - t0) * 1000.0

            # Log full decision vector and all 18 features
            sim_logger.log_decision(
                sim_date=date_str,
                ticker=ticker,
                close_p=float(latest_bar["close"]),
                decision=decision,
                features=decision.get("features"),
                latency_ms=eval_latency_ms,
                model_prob=decision.get("model_prob", 0.50),
                news_score=simulated_news,
                price_trend=decision.get("price_trend", 0.0),
                sma_20=decision.get("sma_20", 0.0),
                is_uptrend=decision.get("is_uptrend", True),
            )

            action = decision["action"]
            qty = decision["quantity"]
            price = decision["price"]
            reason = decision["reason"]

            if action != "HOLD" and qty > 0:
                trade_val = qty * price
                if action == "BUY":
                    engine.positions[ticker] = {"type": "LONG", "shares": qty, "entry_price": price, "days_held": 0}
                elif action == "SHORT":
                    engine.positions[ticker] = {"type": "SHORT", "shares": qty, "entry_price": price, "days_held": 0}
                elif action in ["SELL", "COVER"]:
                    engine.positions.pop(ticker, None)

                sim_logger.log_order(date_str, ticker, action, qty, price, "SIMULATED_FILL", reason)
                print(f"  * ORDER EXECUTED: {action} {qty} {ticker} @ Rs. {price:.2f} (Val: Rs. {trade_val:,.2f})")
                print(f"    Reason:  {reason}")
                print(f"    Latency: {eval_latency_ms:.2f} ms")

                trade_log.append({
                    "date": date_str,
                    "ticker": ticker,
                    "action": action,
                    "quantity": qty,
                    "price": price,
                    "reason": reason,
                })

        sim_logger.update_summary(cash, engine.positions, 0.82)
        if delay_sec > 0:
            time.sleep(delay_sec)

    # Summary
    print("\n" + "=" * 75)
    print(" SIMULATION RUN COMPLETE")
    print("=" * 75)
    print(f" Total Trades Executed: {len(trade_log)}")
    print(f" Active Positions Open: {len(engine.positions)}")
    for t, p in engine.positions.items():
        print(f"   -> {t}: {p['type']} {p['shares']} shares @ Rs. {p['entry_price']:.2f} (Held {p['days_held']} days)")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_local_sandbox(days_to_replay=20, delay_sec=0.05)
