"""
Feature Engineering and Triple Barrier Signal Generation Module (Manthan 2026).

Shared by model training, live bot execution, and backtesting to guarantee zero mismatch.
All technical indicators are strictly scale-free and constructed from past OHLCV data.
Includes the Marcos Lopez de Prado Triple Barrier Labeler for target construction.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    ATR_PERIOD,
    BARRIER_DOWN_ATR,
    BARRIER_UP_ATR,
    HORIZON_DAYS,
    NEWS_STRONG_THRESHOLD,
    NEWS_WEAK_THRESHOLD,
    PRED_BUY_THRESHOLD,
    PRED_SELL_THRESHOLD,
)

# Core technical feature column names (100% scale-free, no raw price levels)
CORE_FEATURE_COLS: list[str] = [
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "sma_ratio",
    "close_to_sma20",
    "close_to_ema12",
    "rsi_14",
    "atr_pct",
    "volatility_10",
    "volatility_20",
    "volume_change",
    "volume_to_sma20",
    "hl_range",
    "dist_from_high_20",
    "dist_from_low_20",
    "market_return_5d",
    "market_return_20d",
    "relative_strength_20d",
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
    """Computes Relative Strength Index (RSI) using exponential smoothing on past prices."""
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-8)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    """Computes Average True Range (ATR) over `period` bars using past prices."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


def build_features(
    df: pd.DataFrame,
    market_df: pd.DataFrame | None = None,
    include_news: bool = False,
) -> pd.DataFrame:
    """
    Constructs all technical indicators from an OHLCV DataFrame.
    Guarantees no forward-looking bias by using past/present rolling windows.
    """
    data = df.copy()

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"])
        data = data.sort_values("date").reset_index(drop=True)

    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]

    # 1. Historical Returns (Scale-Free)
    data["return_1d"] = close.pct_change(1)
    data["return_3d"] = close.pct_change(3)
    data["return_5d"] = close.pct_change(5)
    data["return_10d"] = close.pct_change(10)
    data["return_20d"] = close.pct_change(20)

    # 2. Moving Average Ratios (Scale-Free: raw sma_5, sma_20, ema_12 removed)
    sma_5 = close.rolling(window=5, min_periods=5).mean()
    sma_20 = close.rolling(window=20, min_periods=20).mean()
    data["sma_ratio"] = sma_5 / (sma_20 + 1e-8)
    data["close_to_sma20"] = (close - sma_20) / (sma_20 + 1e-8)

    # 3. Exponential Moving Average Ratio (Scale-Free)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    data["close_to_ema12"] = (close - ema_12) / (ema_12 + 1e-8)

    # 4. Momentum - RSI(14)
    data["rsi_14"] = compute_rsi(close, period=14)

    # 5. Volatility (Scale-Free)
    ret1 = data["return_1d"]
    data["volatility_10"] = ret1.rolling(window=10, min_periods=10).std()
    data["volatility_20"] = ret1.rolling(window=20, min_periods=20).std()

    # 6. ATR Percentage (Scale-Free: ATR_PERIOD / close)
    atr = compute_atr(high, low, close, period=ATR_PERIOD)
    data["atr_pct"] = atr / (close + 1e-8)

    # 7. Volume Dynamics
    data["volume_change"] = volume.pct_change(1).replace([np.inf, -np.inf], 0.0)
    vol_sma20 = volume.rolling(window=20, min_periods=5).mean()
    data["volume_to_sma20"] = volume / (vol_sma20 + 1e-8)

    # 8. Range & Breakout Features
    data["hl_range"] = (high - low) / (close + 1e-8)
    rolling_high_20 = high.rolling(window=20, min_periods=20).max()
    rolling_low_20 = low.rolling(window=20, min_periods=20).min()
    data["dist_from_high_20"] = (close - rolling_high_20) / (rolling_high_20 + 1e-8)
    data["dist_from_low_20"] = (close - rolling_low_20) / (rolling_low_20 + 1e-8)

    # 9. Market Return & Relative Strength Features
    if market_df is not None and "market_return_5d" in market_df.columns:
        if "market_return_5d" in data.columns:
            data = data.drop(columns=["market_return_5d", "market_return_20d"], errors="ignore")
        data = data.merge(
            market_df[["date", "market_return_5d", "market_return_20d"]],
            on="date",
            how="left",
        )
        # Forward-fill latest market return if new intraday bar date is not yet in market_df
        data["market_return_5d"] = data["market_return_5d"].ffill().fillna(0.0)
        data["market_return_20d"] = data["market_return_20d"].ffill().fillna(0.0)
    elif "market_return_5d" not in data.columns:
        data["market_return_5d"] = 0.0
        data["market_return_20d"] = 0.0

    data["relative_strength_20d"] = data["return_20d"] - data["market_return_20d"]

    # 10. News Features (if requested)
    if include_news:
        for col in NEWS_FEATURE_COLS:
            if col not in data.columns:
                data[col] = 0.0

    return data


def compute_market_returns(all_ticker_dfs: dict[str, pd.DataFrame] | pd.DataFrame) -> pd.DataFrame:
    """
    Computes equal-weight average market return for each date across all available tickers.
    Returns DataFrame with ['date', 'market_return_5d', 'market_return_20d'].
    """
    if isinstance(all_ticker_dfs, dict):
        rows = []
        for ticker, df in all_ticker_dfs.items():
            t_df = df[["date", "close"]].copy()
            t_df["date"] = pd.to_datetime(t_df["date"])
            t_df = t_df.sort_values("date").reset_index(drop=True)
            t_df["ret_5d"] = t_df["close"].pct_change(5)
            t_df["ret_20d"] = t_df["close"].pct_change(20)
            rows.append(t_df[["date", "ret_5d", "ret_20d"]])
        combined = pd.concat(rows, ignore_index=True)
    else:
        combined = all_ticker_dfs.copy()
        combined["date"] = pd.to_datetime(combined["date"])
        if "ret_5d" not in combined.columns:
            combined["ret_5d"] = combined.groupby("ticker")["close"].pct_change(5)
            combined["ret_20d"] = combined.groupby("ticker")["close"].pct_change(20)

    market_returns = combined.groupby("date").agg(
        market_return_5d=("ret_5d", "mean"),
        market_return_20d=("ret_20d", "mean"),
    ).reset_index()
    return market_returns


def triple_barrier_labels(
    df: pd.DataFrame,
    up_atr: float = BARRIER_UP_ATR,
    down_atr: float = BARRIER_DOWN_ATR,
    horizon: int = HORIZON_DAYS,
) -> tuple[pd.Series, pd.Series]:
    """
    Computes triple barrier target labels and bars-to-exit for each bar t.

    For each bar t with ATR_t:
      Upper barrier = close_t * (1 + up_atr * atr_pct_t)
      Lower barrier = close_t * (1 - down_atr * atr_pct_t)
    Forward search up to horizon days (bars t+1 ... t+horizon):
      - Label 1 if high reaches upper barrier before low reaches lower barrier.
      - Label 0 if lower barrier is reached first, or horizon expires.
      - If both are touched in the same bar, treat as a loss (label 0).

    Uses strictly data AFTER t for the label, and only data UP TO t for features.
    """
    n = len(df)
    labels = np.full(n, np.nan)
    bars_to_exit = np.full(n, np.nan)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    atr_pct = df["atr_pct"].values

    for t in range(n):
        c_t = close[t]
        a_t = atr_pct[t]
        if np.isnan(c_t) or np.isnan(a_t) or c_t <= 0:
            continue

        up_barrier = c_t * (1.0 + up_atr * a_t)
        down_barrier = c_t * (1.0 - down_atr * a_t)

        max_k = min(t + horizon, n - 1)
        hit = False

        for k in range(t + 1, max_k + 1):
            h_k = high[k]
            l_k = low[k]

            hit_up = h_k >= up_barrier
            hit_down = l_k <= down_barrier

            if hit_up and hit_down:
                # Both barriers touched in same bar -> loss
                labels[t] = 0.0
                bars_to_exit[t] = k - t
                hit = True
                break
            elif hit_up:
                # Upper barrier reached first -> win
                labels[t] = 1.0
                bars_to_exit[t] = k - t
                hit = True
                break
            elif hit_down:
                # Lower barrier reached first -> loss
                labels[t] = 0.0
                bars_to_exit[t] = k - t
                hit = True
                break

        if not hit:
            if t + horizon < n:
                # Horizon expired without hitting upper barrier -> label 0
                labels[t] = 0.0
                bars_to_exit[t] = horizon
            else:
                # Incomplete observation at end of dataset
                labels[t] = np.nan
                bars_to_exit[t] = np.nan

    return (
        pd.Series(labels, index=df.index, name="target"),
        pd.Series(bars_to_exit, index=df.index, name="bars_to_exit"),
    )


def prepare_training_dataset(
    df: pd.DataFrame,
    market_df: pd.DataFrame | None = None,
    include_news: bool = False,
) -> pd.DataFrame:
    """
    Full feature and triple barrier target preparation pipeline for a single ticker DataFrame.
    Drops initial burn-in rows (warm-up for rolling indicators) and unlabelled rows.
    """
    df_feat = build_features(df, market_df=market_df, include_news=include_news)
    labels, bars_to_exit = triple_barrier_labels(df_feat)
    df_feat["target"] = labels
    df_feat["bars_to_exit"] = bars_to_exit

    feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS
    clean_df = df_feat.dropna(subset=feature_cols + ["target"]).reset_index(drop=True)
    clean_df["target"] = clean_df["target"].astype(int)
    clean_df["bars_to_exit"] = clean_df["bars_to_exit"].astype(int)
    return clean_df


def compute_features_live(
    buffer_df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    include_news: bool = False,
    market_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Fast feature calculation for live execution.
    Requires >= 100 bars of historical OHLCV data.
    Fails loudly without fillna(0.0) if any missing values occur.
    """
    if len(buffer_df) < 100:
        raise ValueError(
            f"compute_features_live requires >= 100 bars of history for stable rolling features, "
            f"got only {len(buffer_df)} bars."
        )

    if feature_cols is None:
        feature_cols = ALL_FEATURE_COLS if include_news else CORE_FEATURE_COLS

    df_feat = build_features(buffer_df, market_df=market_df, include_news=include_news)
    latest_row = df_feat.iloc[[-1]][feature_cols]

    # Fail loudly on missing values - NO silent fillna(0.0)
    nan_cols = latest_row.columns[latest_row.isna().any()].tolist()
    if nan_cols:
        raise ValueError(f"Missing feature values in compute_features_live: {nan_cols}")

    return latest_row


def combined_signal(
    price_prob: float,
    news_score: int | float = 0,
    price_trend: float = 0.0,
    buy_threshold: float = PRED_BUY_THRESHOLD,
    sell_threshold: float = PRED_SELL_THRESHOLD,
) -> dict[str, Any]:
    """Combines model probability and news sentiment into a final signal dict."""
    signal = "HOLD"
    confidence = 0.50
    reasons: list[str] = []

    price_bullish = price_prob >= buy_threshold
    price_bearish = price_prob <= sell_threshold
    news_strongly_bullish = news_score >= NEWS_STRONG_THRESHOLD
    news_strongly_bearish = news_score <= NEWS_WEAK_THRESHOLD

    reasons.append(f"Price prob: {price_prob:.3f} (Buy>={buy_threshold}, Sell<={sell_threshold})")
    reasons.append(f"News score: {news_score:+d}" if isinstance(news_score, int) else f"News score: {news_score:+.2f}")
    reasons.append(f"Trend: {price_trend:+.2%}")

    if price_bullish and news_score >= 0:
        signal = "BUY"
        boost = 0.15 if news_strongly_bullish else 0.05
        confidence = min(0.95, price_prob + boost)
        reasons.append("Price model bullish and news sentiment supportive.")
    elif price_bullish and news_strongly_bearish:
        signal = "HOLD"
        confidence = 0.50
        reasons.append("Conflicting signals: Model bullish but strong negative news flash. Exercising caution.")
    elif price_bullish:
        signal = "BUY"
        confidence = price_prob - 0.05
        reasons.append("Price model bullish with mild negative news noise.")
    elif price_bearish and news_score <= 0:
        signal = "SELL"
        confidence = min(0.95, (1.0 - price_prob) + (0.10 if news_strongly_bearish else 0.05))
        reasons.append("Price model bearish and news sentiment negative.")
    elif price_bearish and news_strongly_bullish:
        signal = "HOLD"
        confidence = 0.50
        reasons.append("Conflicting signals: Model bearish but strong positive news flash. Exercising caution.")
    elif price_bearish:
        signal = "SELL"
        confidence = (1.0 - price_prob) - 0.05
        reasons.append("Price model bearish with mild positive news noise.")
    else:
        signal = "HOLD"
        confidence = 0.50
        reasons.append("Neutral price probability and insufficient conviction to trade.")

    return {
        "signal": signal,
        "confidence": round(float(confidence), 3),
        "reason": " | ".join(reasons),
        "price_prob": round(float(price_prob), 4),
        "news_score": news_score,
    }
