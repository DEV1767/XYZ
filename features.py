"""
Feature Engineering and Signal Generation Module.

Shared by both model training and live bot execution to guarantee zero mismatch.
All technical indicators are constructed strictly from past OHLCV data to eliminate
lookahead bias. Includes fast single-bar inference for rolling buffers and the
conservative price + news signal combination engine.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Allow running directly or via imports
sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    NEWS_STRONG_THRESHOLD,
    NEWS_WEAK_THRESHOLD,
    PRED_BUY_THRESHOLD,
    PRED_SELL_THRESHOLD,
    TARGET_FORWARD_DAYS,
    TARGET_PROFIT_THRESHOLD,
)

# Core technical feature column names
CORE_FEATURE_COLS: list[str] = [
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "sma_5",
    "sma_20",
    "sma_ratio",
    "close_to_sma20",
    "ema_12",
    "close_to_ema12",
    "rsi_14",
    "volatility_10",
    "volatility_20",
    "volume_change",
    "volume_to_sma20",
    "hl_range",
    "dist_from_high_20",
    "dist_from_low_20",
]

# Optional news-enhanced feature columns
NEWS_FEATURE_COLS: list[str] = [
    "news_score",
    "news_magnitude",
    "has_news_today",
    "news_count_3d",
    "avg_news_score_3d",
]

ALL_FEATURE_COLS: list[str] = CORE_FEATURE_COLS + NEWS_FEATURE_COLS


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Computes standard Relative Strength Index (RSI) using exponential smoothing.
    Uses strictly past prices (no lookahead).
    """
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing / EMA with alpha = 1 / period
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-8)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def build_features(df: pd.DataFrame, include_news: bool = False) -> pd.DataFrame:
    """
    Constructs all technical indicators from an OHLCV DataFrame.
    Guarantees no forward-looking bias by using past/present rolling windows.

    Parameters:
        df: DataFrame containing ['date', 'open', 'high', 'low', 'close', 'volume']
        include_news: Whether news features are present in df or should be defaulted to 0

    Returns:
        DataFrame with feature columns appended.
    """
    data = df.copy()

    # Ensure date sorted
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"])
        data = data.sort_values("date").reset_index(drop=True)

    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]

    # 1. Historical Returns
    data["return_1d"] = close.pct_change(1)
    data["return_3d"] = close.pct_change(3)
    data["return_5d"] = close.pct_change(5)
    data["return_10d"] = close.pct_change(10)

    # 2. Moving Averages & Ratios
    data["sma_5"] = close.rolling(window=5, min_periods=5).mean()
    data["sma_20"] = close.rolling(window=20, min_periods=20).mean()
    data["sma_ratio"] = data["sma_5"] / (data["sma_20"] + 1e-8)
    data["close_to_sma20"] = (close - data["sma_20"]) / (data["sma_20"] + 1e-8)

    # 3. Exponential Moving Average (12-day)
    data["ema_12"] = close.ewm(span=12, adjust=False).mean()
    data["close_to_ema12"] = (close - data["ema_12"]) / (data["ema_12"] + 1e-8)

    # 4. Momentum - RSI(14)
    data["rsi_14"] = compute_rsi(close, period=14)

    # 5. Rolling Volatility (annualized or daily standard deviation of returns)
    ret1 = data["return_1d"]
    data["volatility_10"] = ret1.rolling(window=10, min_periods=10).std()
    data["volatility_20"] = ret1.rolling(window=20, min_periods=20).std()

    # 6. Volume Dynamics
    data["volume_change"] = volume.pct_change(1).replace([np.inf, -np.inf], 0.0)
    vol_sma20 = volume.rolling(window=20, min_periods=5).mean()
    data["volume_to_sma20"] = volume / (vol_sma20 + 1e-8)

    # 7. Range & Breakout Features
    data["hl_range"] = (high - low) / (close + 1e-8)
    rolling_high_20 = high.rolling(window=20, min_periods=20).max()
    rolling_low_20 = low.rolling(window=20, min_periods=20).min()
    data["dist_from_high_20"] = (close - rolling_high_20) / (rolling_high_20 + 1e-8)
    data["dist_from_low_20"] = (close - rolling_low_20) / (rolling_low_20 + 1e-8)

    # 8. News Features (if present or requested)
    if include_news:
        for col in NEWS_FEATURE_COLS:
            if col not in data.columns:
                data[col] = 0.0

    return data


def create_target(
    df: pd.DataFrame,
    forward_days: int = TARGET_FORWARD_DAYS,
    threshold: float = TARGET_PROFIT_THRESHOLD,
) -> pd.DataFrame:
    """
    Computes the forward-looking target label for training.
    label = 1 if close price N days ahead is higher than today's close by > threshold.
    Otherwise label = 0.
    Adds 'forward_return' and 'target'.
    """
    data = df.copy()
    data["future_close"] = data["close"].shift(-forward_days)
    data["forward_return"] = (data["future_close"] - data["close"]) / (data["close"] + 1e-8)
    data["target"] = (data["forward_return"] > threshold).astype(float)

    # The last `forward_days` rows will not have future prices yet; mark target as NaN
    data.loc[data["future_close"].isna(), "target"] = np.nan
    data = data.drop(columns=["future_close"])
    return data


def prepare_training_dataset(
    df: pd.DataFrame,
    forward_days: int = TARGET_FORWARD_DAYS,
    threshold: float = TARGET_PROFIT_THRESHOLD,
    include_news: bool = False,
) -> pd.DataFrame:
    """
    Full feature and target preparation pipeline for a single ticker DataFrame.
    Drops initial burn-in rows (warm-up for rolling indicators) and final unlabelled rows.
    """
    df_feat = build_features(df, include_news=include_news)
    df_with_target = create_target(df_feat, forward_days=forward_days, threshold=threshold)

    # Drop burn-in rows where technical features are NaN, and rows where target is NaN
    feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS
    clean_df = df_with_target.dropna(subset=feature_cols + ["target"]).reset_index(drop=True)
    clean_df["target"] = clean_df["target"].astype(int)
    return clean_df


def compute_features_live(
    buffer_df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    include_news: bool = False,
) -> pd.DataFrame:
    """
    Fast feature calculation for live execution (< 10 ms).
    Expects buffer_df to contain at least the last 25-30 bars of OHLCV data.
    Returns a single-row DataFrame containing the calculated features for the latest bar.
    """
    if feature_cols is None:
        feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS

    if len(buffer_df) < 20:
        raise ValueError(f"Insufficient history in buffer ({len(buffer_df)} bars). Need at least 20 bars.")

    df_feat = build_features(buffer_df, include_news=include_news)
    latest_row = df_feat.iloc[[-1]][feature_cols]

    # Fill any remaining NaNs with 0 to prevent model failure during live streaming
    latest_row = latest_row.fillna(0.0)
    return latest_row


def combined_signal(
    price_prob: float,
    news_score: int | float = 0,
    price_trend: float = 0.0,
    buy_threshold: float = PRED_BUY_THRESHOLD,
    sell_threshold: float = PRED_SELL_THRESHOLD,
) -> dict[str, Any]:
    """
    Combines the machine learning model price probability with news sentiment score.

    Rules & Conservative Defaults:
    1. News alone NEVER triggers a trade unless the score is strong AND price trend does not contradict it.
    2. If price model probability is high (>= buy_threshold) and news is non-negative: Strong BUY.
    3. If price model probability is high but news is strongly bearish: Conflicting signal -> HOLD.
    4. If price model probability is low (<= sell_threshold) and news is non-positive: SELL / SHORT.
    5. If price model probability is low but news is strongly bullish: Conflicting signal -> HOLD.
    6. If price model is neutral (sell_threshold < price_prob < buy_threshold):
       - If news is strongly positive (>= NEWS_STRONG_THRESHOLD) AND price_trend >= -0.01: Conservative BUY.
       - If news is strongly negative (<= NEWS_WEAK_THRESHOLD) AND price_trend <= 0.01: Conservative SELL.
       - Otherwise: HOLD.

    Returns:
        dict with keys: 'signal' (BUY/SELL/SHORT/HOLD), 'confidence' (0.0 to 1.0), 'reason' (explanation)
    """
    signal = "HOLD"
    confidence = 0.50
    reasons: list[str] = []

    # Assess individual component directions
    price_bullish = price_prob >= buy_threshold
    price_bearish = price_prob <= sell_threshold
    news_strongly_bullish = news_score >= NEWS_STRONG_THRESHOLD
    news_strongly_bearish = news_score <= NEWS_WEAK_THRESHOLD

    reasons.append(f"Price prob: {price_prob:.3f} (Buy>={buy_threshold}, Sell<={sell_threshold})")
    reasons.append(f"News score: {news_score:+d}" if isinstance(news_score, int) else f"News score: {news_score:+.2f}")
    reasons.append(f"Trend: {price_trend:+.2%}")

    # Case 1: Both price model and news are bullish
    if price_bullish and news_score >= 0:
        signal = "BUY"
        boost = 0.15 if news_strongly_bullish else 0.05
        confidence = min(0.95, price_prob + boost)
        reasons.append("Price model bullish and news sentiment supportive.")

    # Case 2: Price model is bullish but news is strongly bearish (Conflict)
    elif price_bullish and news_strongly_bearish:
        signal = "HOLD"
        confidence = 0.50
        reasons.append("Conflicting signals: Model bullish but strong negative news flash. Exercising caution.")

    # Case 3: Price model is bullish and news is mildly negative
    elif price_bullish:
        signal = "BUY"
        confidence = price_prob - 0.05
        reasons.append("Price model bullish with mild negative news noise.")

    # Case 4: Both price model and news are bearish
    elif price_bearish and news_score <= 0:
        signal = "SELL"
        confidence = min(0.95, (1.0 - price_prob) + (0.10 if news_strongly_bearish else 0.05))
        reasons.append("Price model bearish and news sentiment negative.")

    # Case 5: Price model is bearish but news is strongly bullish (Conflict)
    elif price_bearish and news_strongly_bullish:
        signal = "HOLD"
        confidence = 0.50
        reasons.append("Conflicting signals: Model bearish but strong positive news flash. Exercising caution.")

    # Case 6: Price model is bearish and news is mildly positive
    elif price_bearish:
        signal = "SELL"
        confidence = (1.0 - price_prob) - 0.05
        reasons.append("Price model bearish with mild positive news noise.")

    # Case 7: Price model is neutral - evaluate if strong news can break the tie safely
    else:
        if news_strongly_bullish and price_trend >= -0.01:
            signal = "BUY"
            confidence = 0.65
            reasons.append("Strong positive news catalyst confirmed by non-negative price trend.")
        elif news_strongly_bearish and price_trend <= 0.01:
            signal = "SELL"
            confidence = 0.65
            reasons.append("Strong negative news catalyst confirmed by non-positive price trend.")
        else:
            signal = "HOLD"
            confidence = 0.50
            reasons.append("Neutral price probability and insufficient news conviction to trade.")

    return {
        "signal": signal,
        "confidence": round(float(confidence), 3),
        "reason": " | ".join(reasons),
        "price_prob": round(float(price_prob), 4),
        "news_score": news_score,
    }


if __name__ == "__main__":
    print("[features] Self-testing feature calculation...")
    # Generate small sample test dataframe
    dates = pd.date_range("2026-01-01", periods=50, freq="B")
    test_df = pd.DataFrame({
        "date": dates,
        "open": np.linspace(100, 150, 50) + np.random.randn(50),
        "high": np.linspace(102, 155, 50) + np.random.randn(50),
        "low": np.linspace(98, 148, 50) + np.random.randn(50),
        "close": np.linspace(100, 150, 50) + np.random.randn(50),
        "volume": np.random.randint(10000, 50000, 50),
        "ticker": "TEST",
    })
    prep_df = prepare_training_dataset(test_df)
    print(f"[features] Successfully created training dataset with {len(prep_df)} samples.")
    print(f"[features] Feature columns ({len(CORE_FEATURE_COLS)}): {CORE_FEATURE_COLS}")

    # Test live buffer inference
    import time
    t0 = time.perf_counter()
    feat_live = compute_features_live(test_df)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"[features] Single-bar live feature inference latency: {elapsed_ms:.2f} ms (<10 ms target)")

    # Test combined signal
    sig1 = combined_signal(price_prob=0.72, news_score=3, price_trend=0.02)
    sig2 = combined_signal(price_prob=0.68, news_score=-4, price_trend=-0.01)
    sig3 = combined_signal(price_prob=0.51, news_score=3, price_trend=0.005)
    print("[features] Test Combined Signals:")
    print(f"  Signal 1 (Aligned Buy): {sig1}")
    print(f"  Signal 2 (Conflict Hold): {sig2}")
    print(f"  Signal 3 (News Catalyst): {sig3}")
