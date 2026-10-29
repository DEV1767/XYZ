"""
Automated Stock Discovery, History Fetcher, and Quick Retrainer.

Designed specifically for when the hackathon judges add new stocks to the exchange:
1. Dynamically queries GET /api/v1/stocks
2. Identifies any newly added tickers not yet in data/raw/
3. Fetches the maximum available history for the new tickers
4. Automatically retrains the machine learning model on the expanded universe (< 5 seconds)
5. Updates models/best_model.joblib and models/feature_names.joblib seamlessly
"""

from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from config import DATA_RAW_DIR
from data.fetch_history import create_resilient_session, fetch_ticker_history, fetch_tickers
from train import train_pipeline


def update_and_retrain(days: int = 500) -> None:
    """Discovers new stocks, downloads their history, and retrains the model."""
    print("\n" + "=" * 70)
    print(" DYNAMIC STOCK DISCOVERY & RAPID RETRAINING PIPELINE")
    print("=" * 70)

    session = create_resilient_session(retries=3, backoff_factor=0.5)

    try:
        remote_tickers = fetch_tickers(session=session)
    except Exception as exc:
        print(f"[update] Could not reach GET /api/v1/stocks ({exc}).")
        print("         Ensure you are connected to the venue Wi-Fi network.")
        return

    # Check existing tickers in data/raw/
    existing_files = list(DATA_RAW_DIR.glob("*.csv"))
    existing_tickers = {f.stem.upper() for f in existing_files if f.name not in ["news_log.csv", "ticks_log.csv"]}

    new_tickers = [t for t in remote_tickers if t not in existing_tickers]
    print(f"\n[update] Total Active Stocks on Exchange: {len(remote_tickers)}")
    print(f"[update] Previously Downloaded Stocks:    {len(existing_tickers)}")
    print(f"[update] Newly Added Stocks Detected:     {len(new_tickers)} -> {new_tickers if new_tickers else 'None'}")

    if new_tickers:
        print(f"\n[update] Fetching historical data for {len(new_tickers)} new stocks...")
        for idx, ticker in enumerate(new_tickers, start=1):
            print(f"  [{idx}/{len(new_tickers)}] Fetching {ticker} history ({days} days)...")
            try:
                df = fetch_ticker_history(session=session, ticker=ticker, days=days)
                if not df.empty:
                    save_path = DATA_RAW_DIR / f"{ticker}.csv"
                    df.to_csv(save_path, index=False)
                    print(f"    -> Saved {len(df)} bars to {save_path.name}")
            except Exception as e:
                print(f"    -> Error fetching {ticker}: {e}")
            time.sleep(0.05)
    else:
        print("[update] No new tickers found. Historical data for all stocks is already up to date.")

    # Retrain model on expanded universe
    print("\n[update] Retraining ML model across the complete updated stock universe...")
    t0 = time.time()
    train_pipeline(include_news=False)
    print(f"[update] Complete pipeline updated and retrained in {time.time() - t0:.2f} seconds!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    update_and_retrain()
