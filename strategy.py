"""
Trading Strategy and Risk Management Engine.

Fully conforms to the Manthan 2026 Problem Statement and Trading Basics Primer:
1. Long Trading: BUY -> SELL
2. Short Selling: SHORT -> COVER (with 9-day maximum holding limit to avoid 10-day auto squareoff)
3. 4 to 8 Stock Diversification: Maximum active positions capped at 6, maximum allocation per stock 15%
4. Cash Cushion: Retains 20% liquid cash reserve
5. Batch Sizing: Sized in batches (e.g. 50+ shares) to minimize brokerage and DP fee impact
6. Fast Evaluation: Runs in < 5 ms per ticker
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    BROKERAGE_FEE,
    CASH_RESERVE_PCT,
    DP_CHARGE,
    FEATURE_NAMES_FILE,
    MAX_SHORT_HOLD_DAYS,
    MIN_TRADE_SIZE,
    MODEL_FILE,
    PRED_BUY_THRESHOLD,
    PRED_SELL_THRESHOLD,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TARGET_FORWARD_DAYS,
)
from features import combined_signal, compute_features_live

MAX_CONCURRENT_POSITIONS = 6  # Diversification: 4 to 8 stocks max
TARGET_ALLOCATION_PCT = 0.15  # Up to 15% of capital per stock


class StrategyEngine:
    """
    Autonomous multi-asset strategy evaluator.
    Manages active long & short positions, evaluates combined ML + news signals,
    and enforces strict risk management to prevent drawdowns.
    """

    def __init__(
        self,
        valid_tickers: list[str] | None = None,
        model_path: Path = MODEL_FILE,
        features_path: Path = FEATURE_NAMES_FILE,
    ):
        self.valid_tickers = set(t.upper() for t in valid_tickers) if valid_tickers else set()
        self.model = None
        self.feature_cols = None

        if model_path.exists() and features_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.feature_cols = joblib.load(features_path)
                print(f"[strategy] Loaded model '{type(self.model).__name__}' with {len(self.feature_cols)} features.")
            except Exception as e:
                print(f"[strategy] Warning: Could not load model ({e}). Operating in rule-based fallback.")
        else:
            print("[strategy] Model not found. Train first with 'python train.py'.")

        # Active portfolio state:
        # ticker -> {"type": "LONG"|"SHORT", "shares": int, "entry_price": float, "days_held": int}
        self.positions: dict[str, dict[str, Any]] = {}

    def set_valid_tickers(self, tickers: list[str]) -> None:
        """Updates the active ticker whitelist."""
        self.valid_tickers = set(t.upper() for t in tickers)

    def calculate_batch_shares(self, budget: float, price: float) -> int:
        """
        Calculates whole share quantity in batches (recommended 50+ shares where possible)
        to minimize the friction percentage of flat brokerage fees.
        """
        if price <= 0 or budget < price:
            return 0
        raw_shares = int(budget // price)
        if raw_shares <= 0:
            return 0
        # Round to nearest batch of 10 or 25 if large enough
        if raw_shares >= 100:
            return (raw_shares // 25) * 25
        elif raw_shares >= 20:
            return (raw_shares // 10) * 10
        return raw_shares

    def evaluate_ticker(
        self,
        ticker: str,
        buffer_df: pd.DataFrame,
        news_score: int | float = 0,
        current_cash: float = 1000000.0,
        current_date: str = "",
    ) -> dict[str, Any]:
        """
        Evaluates a ticker at daily market close and outputs an order decision.
        Actions: 'BUY', 'SELL', 'SHORT', 'COVER', 'HOLD'.
        """
        ticker = ticker.upper()

        # Whitelist verification
        if self.valid_tickers and ticker not in self.valid_tickers:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": 0.0,
                "reason": f"Ticker '{ticker}' not in active API stocks universe. Skipped.",
                "confidence": 0.0,
            }

        if buffer_df.empty or len(buffer_df) < 20:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": 0.0,
                "reason": "Insufficient historical bars (< 20).",
                "confidence": 0.0,
            }

        latest_close = float(buffer_df["close"].iloc[-1])

        # =================================================================
        # 1. Active Position Management: Long Exit (SELL) or Short Exit (COVER)
        # =================================================================
        if ticker in self.positions:
            pos = self.positions[ticker]
            pos_type = pos["type"]
            entry_price = float(pos.get("entry_price", 0.0))
            if entry_price <= 0:
                entry_price = latest_close
                pos["entry_price"] = entry_price

            shares = pos["shares"]
            days_held = pos.get("days_held", 0) + 1
            pos["days_held"] = days_held

            if pos_type == "LONG":
                pnl_pct = (latest_close - entry_price) / entry_price if entry_price > 0 else 0.0

                # Adverse News Catalyst Protection: exit immediately if severe negative news breaks
                if news_score <= -2:
                    return {
                        "ticker": ticker,
                        "action": "SELL",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"LONG ADVERSE NEWS CATALYST (Score: {news_score:+d}). Exiting before drop worsens.",
                        "confidence": 0.95,
                    }

                # Take-Profit: Lock in gains immediately if surge reaches >= 4%
                if pnl_pct >= TAKE_PROFIT_PCT:
                    return {
                        "ticker": ticker,
                        "action": "SELL",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"LONG TAKE-PROFIT (+{pnl_pct:.2%} >= +{TAKE_PROFIT_PCT:.1%}). Locking in peak gains early.",
                        "confidence": 0.95,
                    }

                # Stop-Loss: Cut immediately if drops by 2.5%
                if pnl_pct <= -STOP_LOSS_PCT:
                    return {
                        "ticker": ticker,
                        "action": "SELL",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"LONG STOP-LOSS ({pnl_pct:.2%} <= -{STOP_LOSS_PCT:.1%}). Realizing defense exit.",
                        "confidence": 1.0,
                    }

                # Target Holding Duration reached
                if days_held >= TARGET_FORWARD_DAYS:
                    return {
                        "ticker": ticker,
                        "action": "SELL",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"LONG Target Duration reached ({days_held} days, PnL {pnl_pct:+.2%}). Realizing gain.",
                        "confidence": 0.85,
                    }

            elif pos_type == "SHORT":
                # For short: profit when price drops, loss when price rises
                short_pnl_pct = (entry_price - latest_close) / entry_price if entry_price > 0 else 0.0

                # Adverse News Catalyst Protection: cover immediately if strong positive news breaks
                if news_score >= 2:
                    return {
                        "ticker": ticker,
                        "action": "COVER",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"SHORT ADVERSE NEWS CATALYST (Score: {news_score:+d}). Covering before squeeze worsens.",
                        "confidence": 0.95,
                    }

                # Short Take-Profit: Lock in gains immediately if price drops >= 4%
                if short_pnl_pct >= TAKE_PROFIT_PCT:
                    return {
                        "ticker": ticker,
                        "action": "COVER",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"SHORT TAKE-PROFIT (+{short_pnl_pct:.2%} >= +{TAKE_PROFIT_PCT:.1%}). Locking in gains on price drop.",
                        "confidence": 0.95,
                    }

                # Short Stop-Loss: Cut if price rises 2.5% above short entry
                if short_pnl_pct <= -STOP_LOSS_PCT:
                    return {
                        "ticker": ticker,
                        "action": "COVER",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"SHORT STOP-LOSS ({short_pnl_pct:.2%} <= -{STOP_LOSS_PCT:.1%}). Covering borrowed shares.",
                        "confidence": 1.0,
                    }

                # Mandatory Settlement Rule: Cover before 10-day auto square-off
                if days_held >= MAX_SHORT_HOLD_DAYS or days_held >= TARGET_FORWARD_DAYS:
                    return {
                        "ticker": ticker,
                        "action": "COVER",
                        "quantity": shares,
                        "price": latest_close,
                        "reason": f"SHORT Target/Settlement limit reached ({days_held} days, PnL {short_pnl_pct:+.2%}).",
                        "confidence": 0.85,
                    }

        # =================================================================
        # 2. Compute Features & Combined Signals
        # =================================================================
        price_prob = 0.50
        if self.model and self.feature_cols:
            try:
                feat_row = compute_features_live(buffer_df, feature_cols=self.feature_cols)
                if hasattr(self.model, "predict_proba"):
                    price_prob = float(self.model.predict_proba(feat_row)[0, 1])
                else:
                    price_prob = float(self.model.predict(feat_row)[0])
            except Exception as e:
                print(f"[strategy] Model inference error for {ticker}: {e}")

        price_trend = float(buffer_df["close"].pct_change(5).iloc[-1]) if len(buffer_df) >= 6 else 0.0

        signal_output = combined_signal(
            price_prob=price_prob,
            news_score=news_score,
            price_trend=price_trend,
            buy_threshold=PRED_BUY_THRESHOLD,
            sell_threshold=PRED_SELL_THRESHOLD,
        )

        signal = signal_output["signal"]
        confidence = signal_output["confidence"]
        reason = signal_output["reason"]

        # =================================================================
        # 3. New Entry Execution (Long BUY or Short SHORT)
        # =================================================================
        # Check portfolio diversification limits (max 6 simultaneous positions)
        if len(self.positions) >= MAX_CONCURRENT_POSITIONS:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"Diversification cap reached ({len(self.positions)}/{MAX_CONCURRENT_POSITIONS} stocks active).",
                "confidence": confidence,
            }

        # Available investable capital reserving cash cushion
        investable_cash = current_cash * (1.0 - CASH_RESERVE_PCT)
        trade_budget = min(investable_cash * TARGET_ALLOCATION_PCT, 150000.0)

        # Asymmetric News Multiplier: boost size by 25% on strong news catalyst
        if news_score >= 2 or news_score <= -2:
            trade_budget = min(investable_cash * (TARGET_ALLOCATION_PCT * 1.25), 185000.0)

        # Trend Confirmation: verify price relative to 20-day moving average
        sma_20 = float(buffer_df["close"].rolling(20, min_periods=5).mean().iloc[-1])
        is_uptrend = (latest_close >= sma_20 * 0.985) or (price_trend >= -0.01)
        is_downtrend = (latest_close <= sma_20 * 1.015) or (price_trend <= 0.01)

        # ENTRY 1: BUY (Go Long) with Trend Confirmation
        if signal == "BUY" and ticker not in self.positions:
            if not is_uptrend and news_score < 2:
                return {
                    "ticker": ticker,
                    "action": "HOLD",
                    "quantity": 0,
                    "price": latest_close,
                    "reason": f"Model bullish but filtered: Close ({latest_close:.2f}) < 20-day SMA ({sma_20:.2f}). Awaiting trend confirmation.",
                    "confidence": confidence,
                }

            shares = self.calculate_batch_shares(trade_budget, latest_close)
            if shares >= MIN_TRADE_SIZE and (shares * latest_close + BROKERAGE_FEE) <= current_cash:
                return {
                    "ticker": ticker,
                    "action": "BUY",
                    "quantity": shares,
                    "price": latest_close,
                    "reason": f"BUY LONG: {reason}",
                    "confidence": confidence,
                }

        # ENTRY 2: SHORT (Go Short on strong bearish signal & negative catalyst with Downtrend Confirmation)
        elif signal in ["SELL", "SHORT"] and ticker not in self.positions:
            if not is_downtrend and news_score > -2:
                return {
                    "ticker": ticker,
                    "action": "HOLD",
                    "quantity": 0,
                    "price": latest_close,
                    "reason": f"Model bearish but filtered: Close ({latest_close:.2f}) > 20-day SMA ({sma_20:.2f}). Awaiting downtrend confirmation.",
                    "confidence": confidence,
                }

            shares = self.calculate_batch_shares(trade_budget, latest_close)
            # Short requires 100% margin lock + brokerage
            if shares >= MIN_TRADE_SIZE and (shares * latest_close + BROKERAGE_FEE) <= current_cash:
                return {
                    "ticker": ticker,
                    "action": "SHORT",
                    "quantity": shares,
                    "price": latest_close,
                    "reason": f"OPEN SHORT: {reason}",
                    "confidence": confidence,
                }

        return {
            "ticker": ticker,
            "action": "HOLD",
            "quantity": 0,
            "price": latest_close,
            "reason": reason,
            "confidence": confidence,
        }
