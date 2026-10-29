"""
Historical Stock Data Fetcher.

Fetches the complete historical OHLCV data for all tickers provided by the
hackathon server via REST API and saves them into data/raw/<TICKER>.csv.
Supports retries with exponential backoff, response parsing, data cleaning,
sorting by date, and a mock generator for offline testing.
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Allow running directly from project root or data/ directory
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import (
    AUTH_HEADERS,
    DATA_RAW_DIR,
    HISTORY_API_URL_TEMPLATE,
    STOCKS_API_URL,
)


def create_resilient_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Creates a requests.Session configured with automatic retries for transient errors."""
    session = requests.Session()
    session.headers.update(AUTH_HEADERS)
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_tickers(session: requests.Session, timeout: float = 10.0) -> list[str]:
    """
    Fetches the list of active stock tickers from GET /api/v1/stocks.
    Handles multiple response schemas: list of strings, list of dicts, or nested dict.
    """
    print(f"[fetch_history] Querying tickers from: {STOCKS_API_URL}")
    response = session.get(STOCKS_API_URL, timeout=timeout)
    response.raise_for_status()
    data: Any = response.json()

    tickers: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                tickers.append(item.strip().upper())
            elif isinstance(item, dict):
                ticker = item.get("ticker") or item.get("symbol") or item.get("name")
                if ticker:
                    tickers.append(str(ticker).strip().upper())
    elif isinstance(data, dict):
        stocks_list = data.get("stocks") or data.get("tickers") or data.get("data") or []
        if isinstance(stocks_list, list):
            for item in stocks_list:
                if isinstance(item, str):
                    tickers.append(item.strip().upper())
                elif isinstance(item, dict):
                    ticker = item.get("ticker") or item.get("symbol")
                    if ticker:
                        tickers.append(str(ticker).strip().upper())

    tickers = sorted(list(set(tickers)))
    if not tickers:
        raise ValueError(f"No tickers found in API response: {data}")

    print(f"[fetch_history] Discovered {len(tickers)} tickers: {tickers}")
    return tickers


def fetch_ticker_history(
    session: requests.Session,
    ticker: str,
    days: int = 500,
    timeout: float = 10.0,
) -> pd.DataFrame:
    """
    Fetches historical OHLCV data for a specific ticker.
    API endpoint: GET /api/v1/stocks/:ticker/history?days=N
    Expected response: {"prices":[{"date","open","high","low","close","volume"}]}
    """
    url = HISTORY_API_URL_TEMPLATE.format(ticker=ticker)
    params = {"days": days}
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    prices = payload.get("prices", [])
    if not prices and isinstance(payload, list):
        prices = payload

    if not prices:
        print(f"[WARN] No price records returned for ticker: {ticker}")
        return pd.DataFrame()

    df = pd.DataFrame(prices)

    # Standardize column names
    df.columns = [col.lower().strip() for col in df.columns]
    required_cols = ["date", "open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Missing required column '{col}' for ticker {ticker}. Found: {df.columns.tolist()}")

    # Parse and sort by date ascending
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Handle missing or invalid values
    # Forward fill then backward fill for OHLC, fill volume with 0
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill().bfill()
    df["volume"] = df["volume"].fillna(0)

    # Drop any remaining unfillable rows
    df = df.dropna(subset=["close", "date"]).reset_index(drop=True)

    # Add ticker identifier column
    df["ticker"] = ticker
    return df


def generate_mock_history(
    tickers: list[str] | None = None,
    days: int = 400,
    output_dir: Path = DATA_RAW_DIR,
) -> list[str]:
    """
    Generates realistic synthetic OHLCV data for local testing when the hackathon
    API server is unreachable or during offline development.
    """
    if not tickers:
        tickers = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK", "TATAMOTORS", "SBIN", "BHARTIARTL"]

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    end_date = pd.Timestamp.now().normalize()
    dates = pd.bdate_range(end=end_date, periods=days)

    print(f"[fetch_history] Generating synthetic data for {len(tickers)} tickers ({days} days)...")
    for ticker in tickers:
        base_price = rng.uniform(200.0, 3500.0)
        # Geometric Brownian Motion with slight drift
        daily_returns = rng.normal(0.0004, 0.018, size=days)
        price_series = base_price * np.exp(np.cumsum(daily_returns))

        highs = price_series * (1.0 + rng.uniform(0.002, 0.025, size=days))
        lows = price_series * (1.0 - rng.uniform(0.002, 0.025, size=days))
        opens = lows + (highs - lows) * rng.uniform(0.2, 0.8, size=days)
        volumes = rng.integers(100000, 5000000, size=days)

        df = pd.DataFrame({
            "date": dates,
            "open": np.round(opens, 2),
            "high": np.round(highs, 2),
            "low": np.round(lows, 2),
            "close": np.round(price_series, 2),
            "volume": volumes,
            "ticker": ticker,
        })
        save_path = output_dir / f"{ticker}.csv"
        df.to_csv(save_path, index=False)
        print(f"  -> Saved mock data for {ticker} ({len(df)} rows) to {save_path.name}")

    return tickers


def run_fetch_history(days: int = 500, use_mock: bool = False) -> None:
    """Main execution orchestrator for fetching history of all tickers."""
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if use_mock:
        print("[fetch_history] Mock flag supplied. Generating synthetic datasets.")
        generate_mock_history(days=days)
        return

    session = create_resilient_session(retries=3, backoff_factor=1.0)
    try:
        tickers = fetch_tickers(session=session)
    except Exception as exc:
        print(f"[fetch_history] ERROR: Failed to fetch tickers from API: {exc}")
        print("                 Please ensure SERVER_IP and BOT_ACCESS_TOKEN in .env are correct")
        print("                 and the hackathon API server is online.")
        return

    successful_count = 0
    for idx, ticker in enumerate(tickers, start=1):
        print(f"[{idx}/{len(tickers)}] Fetching history for {ticker} (max {days} days)...")
        try:
            df = fetch_ticker_history(session=session, ticker=ticker, days=days)
            if not df.empty:
                save_path = DATA_RAW_DIR / f"{ticker}.csv"
                df.to_csv(save_path, index=False)
                print(f"  -> Saved {len(df)} bars to {save_path.name}")
                successful_count += 1
            else:
                print(f"  -> [WARN] Empty data for {ticker}")
        except Exception as err:
            print(f"  -> [ERROR] Failed to fetch {ticker}: {err}")
        time.sleep(0.05)  # Rate limiting courtesy

    print(f"\n[fetch_history] Successfully downloaded {successful_count}/{len(tickers)} tickers into {DATA_RAW_DIR}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch historical stock data from hackathon API")
    parser.add_argument("--days", type=int, default=500, help="Number of historical days to fetch")
    parser.add_argument("--mock", action="store_true", help="Generate synthetic stock data for offline testing")
    args = parser.parse_args()

    run_fetch_history(days=args.days, use_mock=args.mock)
