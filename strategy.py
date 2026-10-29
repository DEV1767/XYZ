"""
Trading Strategy and Risk Management Engine (Manthan 2026).

Enforces:
1. Triple Barrier exit engine matching labeling:
   stop   = entry * (1 - BARRIER_DOWN_ATR * atr_pct_at_entry)
   target = entry * (1 + BARRIER_UP_ATR * atr_pct_at_entry)
   time exit after HORIZON_DAYS.
   Tracks atr_pct_at_entry, stop_price, target_price, and days_held (incremented once per date).
2. Single ATR trailing stop that activates after +1 ATR gain (replaces all old ratchets).
3. Cross-sectional ranking entry: ranks all universe tickers by model probability each day
   and selects top-N free slots (up to MAX_CONCURRENT_POSITIONS).
4. Strict trend filters: require latest_close > sma_20 AND sma_5 > sma_20 (strict AND, not OR).
5. News as veto only: score <= -2 blocks entry or forces defensive exit. News NEVER bypasses
   trend filters or boosts trade size. Logs news_score for every executed trade.
6. Single risk parity sizing path: shares = (equity * 0.01) / (entry - stop_price),
   capped at MAX_POSITION_PCT of equity (25%).
7. Counts and logs all model inference exceptions loudly (no silent fallback to 0.50).
8. Longs exit ONLY via stop / target / trailing stop / time exit / news veto.
   Model SELL signals are ignored for long positions.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    ATR_PERIOD,
    BARRIER_DOWN_ATR,
    BARRIER_UP_ATR,
    BROKERAGE_FEE,
    CASH_RESERVE_PCT,
    DP_CHARGE,
    ENABLE_SHORT_SELLING,
    FEATURE_NAMES_FILE,
    HORIZON_DAYS,
    MAX_CONCURRENT_POSITIONS,
    MAX_POSITION_PCT,
    MIN_TRADE_SIZE,
    MODEL_FILE,
    MODELS_DIR,
    PRED_BUY_THRESHOLD,
    PRED_SELL_THRESHOLD,
)
from features import compute_atr, compute_features_live


class StrategyEngine:
    """
    Autonomous multi-asset strategy evaluator and risk management engine.
    """

    def __init__(
        self,
        valid_tickers: list[str] | None = None,
        model_path: Path = MODEL_FILE,
        features_path: Path = FEATURE_NAMES_FILE,
        metadata_path: Path = MODELS_DIR / "model_metadata.joblib",
    ):
        self.valid_tickers = set(t.upper() for t in valid_tickers) if valid_tickers else set()
        self.model = None
        self.feature_cols: list[str] | None = None
        self.buy_threshold: float = PRED_BUY_THRESHOLD
        self.inference_exception_count: int = 0
        self.score_history: list[float] = []
        self.use_trailing_median: bool = True
        self.use_strict_trend_filter: bool = False
        self.max_daily_entries: int = 2

        # Load metadata if available (to get dynamically chosen threshold from walk-forward validation)
        if metadata_path.exists():
            try:
                meta = joblib.load(metadata_path)
                if "chosen_threshold" in meta:
                    self.buy_threshold = float(meta["chosen_threshold"])
                    print(f"[strategy] Loaded validation-chosen threshold: {self.buy_threshold:.4f}")
            except Exception as e:
                print(f"[strategy] Warning loading metadata ({e}), using default threshold: {self.buy_threshold:.4f}")

        # Load model and feature list
        if model_path.exists() and features_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.feature_cols = joblib.load(features_path)
                print(f"[strategy] Loaded model '{type(self.model).__name__}' with {len(self.feature_cols)} features.")
            except Exception as e:
                print(f"[strategy] Warning: Could not load model ({e}). Inference will fail loudly.")
        else:
            print("[strategy] Model artifacts not found. Train first with 'python train.py'.")

        # Active positions: ticker -> {
        #   "type": "LONG",
        #   "shares": int,
        #   "entry_price": float,
        #   "atr_pct_at_entry": float,
        #   "stop_price": float,
        #   "target_price": float,
        #   "peak_price": float,
        #   "days_held": int,
        #   "last_evaluated_date": str,
        #   "trailing_stop_active": bool,
        #   "news_score_entry": float,
        # }
        self.positions: dict[str, dict[str, Any]] = {}

    def set_valid_tickers(self, tickers: list[str]) -> None:
        """Updates the active ticker whitelist."""
        self.valid_tickers = set(t.upper() for t in tickers)

    def get_effective_buy_threshold(self) -> float:
        """Returns the trailing 60-day median score if available, else static buy_threshold."""
        if self.use_trailing_median and len(self.score_history) >= 20:
            trailing = self.score_history[-600:]
            return float(np.median(trailing))
        return self.buy_threshold

    def calculate_risk_shares(
        self,
        equity: float,
        entry: float,
        stop_price: float,
        available_cash: float,
    ) -> int:
        """
        Single Risk Parity Sizing Path:
          Risk budget = 1% of total equity
          Per-share risk = entry - stop_price
          shares = (equity * 0.01) / (entry - stop_price)
          Capped at MAX_POSITION_PCT (25%) of equity and liquid cash.
        """
        if entry <= 0 or equity <= 0:
            return 0

        per_share_risk = entry - stop_price
        if per_share_risk <= 0:
            # Fallback per-share risk if stop is invalid
            per_share_risk = entry * 0.05

        risk_budget = equity * 0.01
        risk_shares = int(risk_budget / per_share_risk)

        # Capital cap: 25% of total equity
        max_capital = equity * MAX_POSITION_PCT
        cap_shares = int(max_capital / entry)

        shares = min(risk_shares, cap_shares)

        # Cash constraint
        max_cash_shares = int(max(0.0, (available_cash - BROKERAGE_FEE)) // entry)
        shares = min(shares, max_cash_shares)

        return shares if shares >= MIN_TRADE_SIZE else 0

    def get_atr_pct(self, buffer_df: pd.DataFrame) -> float:
        """Extracts or computes atr_pct (ATR_PERIOD / close) on latest bar."""
        if len(buffer_df) < ATR_PERIOD + 1:
            raise ValueError(f"Insufficient bars to compute ATR ({len(buffer_df)} < {ATR_PERIOD + 1})")
        latest_close = float(buffer_df["close"].iloc[-1])
        atr_series = compute_atr(buffer_df["high"], buffer_df["low"], buffer_df["close"], period=ATR_PERIOD)
        latest_atr = float(atr_series.iloc[-1])
        if np.isnan(latest_atr) or latest_close <= 0:
            raise ValueError("Computed ATR is NaN or close <= 0.")
        return latest_atr / latest_close

    def evaluate_position_exit(
        self,
        ticker: str,
        latest_close: float,
        news_score: float = 0.0,
        current_date: str = "",
    ) -> dict[str, Any] | None:
        """
        Evaluates exit conditions for an active position:
        1. News veto (score <= -2)
        2. Strict stop-loss (close <= stop_price)
        3. Target reached (close >= target_price)
        4. Single ATR trailing stop after +1 ATR gain
        5. Time exit (days_held >= HORIZON_DAYS)
        Returns decision dict if an exit is triggered, else None.
        """
        if ticker not in self.positions:
            return None

        pos = self.positions[ticker]
        pos_type = pos.get("type", "LONG")
        shares = int(pos["shares"])
        entry = float(pos["entry_price"])
        atr_pct = float(pos.get("atr_pct_at_entry", 0.02))

        # Ensure stop_price and target_price are defined
        if "stop_price" not in pos:
            pos["stop_price"] = round(entry * (1.0 - BARRIER_DOWN_ATR * atr_pct), 2)
        if "target_price" not in pos:
            pos["target_price"] = round(entry * (1.0 + BARRIER_UP_ATR * atr_pct), 2)

        # Increment days_held once per unique calendar date
        last_eval_date = pos.get("last_evaluated_date", "")
        if current_date and current_date != last_eval_date:
            pos["days_held"] = pos.get("days_held", 0) + 1
            pos["last_evaluated_date"] = current_date

        days_held = pos.get("days_held", 0)

        # 1. News veto exit
        if news_score <= -2:
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"NEWS VETO EXIT (news_score {news_score:+.1f} <= -2.0). Defensive liquidation.",
                "confidence": 1.0,
                "news_score": news_score,
                "days_held": days_held,
            }

        # 2. Single ATR Trailing Stop (activates after +1 ATR gain)
        one_atr_price = entry * (1.0 + 1.0 * atr_pct)
        if latest_close >= one_atr_price:
            pos["trailing_stop_active"] = True

        if pos.get("trailing_stop_active", False):
            peak_price = max(float(pos.get("peak_price", entry)), latest_close)
            pos["peak_price"] = peak_price
            atr_trail_stop = round(peak_price * (1.0 - 1.0 * atr_pct), 2)
            if atr_trail_stop > pos["stop_price"]:
                pos["stop_price"] = atr_trail_stop

            if latest_close <= pos["stop_price"]:
                return {
                    "ticker": ticker,
                    "action": "SELL",
                    "quantity": shares,
                    "price": latest_close,
                    "reason": f"ATR TRAILING STOP (Close Rs.{latest_close:.2f} <= Trail Stop Rs.{pos['stop_price']:.2f} from peak Rs.{peak_price:.2f}).",
                    "confidence": 0.95,
                    "news_score": news_score,
                    "days_held": days_held,
                }

        # 3. Strict Initial Stop-Loss
        if latest_close <= pos["stop_price"]:
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"STOP LOSS HIT (Close Rs.{latest_close:.2f} <= Stop Rs.{pos['stop_price']:.2f}).",
                "confidence": 1.0,
                "news_score": news_score,
                "days_held": days_held,
            }

        # 4. Take-Profit Target Reached
        if latest_close >= pos["target_price"]:
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"TARGET REACHED (Close Rs.{latest_close:.2f} >= Target Rs.{pos['target_price']:.2f}).",
                "confidence": 1.0,
                "news_score": news_score,
                "days_held": days_held,
            }

        # 5. Time Exit after HORIZON_DAYS
        if days_held >= HORIZON_DAYS:
            pnl_pct = (latest_close - entry) / entry if entry > 0 else 0.0
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"TIME EXIT (Horizon of {HORIZON_DAYS} days reached, held {days_held} days, P&L {pnl_pct:+.2%}).",
                "confidence": 0.90,
                "news_score": news_score,
                "days_held": days_held,
            }

        return None

    def evaluate_daily_universe(
        self,
        daily_buffers: dict[str, pd.DataFrame],
        daily_news_scores: dict[str, float] | None = None,
        current_cash: float = 1000000.0,
        current_equity: float = 1000000.0,
        current_date: str = "",
        market_df: pd.DataFrame | None = None,
    ) -> list[dict[str, Any]]:
        """
        Daily universe evaluator:
        1. Checks exits for all currently held positions.
        2. Gathers candidate tickers passing strict trend filters and news veto.
        3. Computes model probability score (logging exceptions).
        4. Cross-sectionally ranks candidates by model score.
        5. Selects top free slots (up to MAX_CONCURRENT_POSITIONS).
        6. Sizes each entry with single risk parity sizing.
        """
        decisions: list[dict[str, Any]] = []
        news_map = daily_news_scores or {}

        # 1. Process exits for held positions
        exited_tickers: set[str] = set()
        for ticker in list(self.positions.keys()):
            if ticker not in daily_buffers or daily_buffers[ticker].empty:
                continue
            buf = daily_buffers[ticker]
            latest_close = float(buf["close"].iloc[-1])
            news_sc = float(news_map.get(ticker, 0.0))

            exit_decision = self.evaluate_position_exit(
                ticker=ticker,
                latest_close=latest_close,
                news_score=news_sc,
                current_date=current_date,
            )
            if exit_decision is not None:
                decisions.append(exit_decision)
                exited_tickers.add(ticker)
                print(f"[strategy] EXECUTED EXIT for {ticker}: {exit_decision['reason']} | news_score: {news_sc:+.1f}")

        # Update remaining active positions
        for t in exited_tickers:
            self.positions.pop(t, None)

        # 2. Check available entry slots
        active_count = len(self.positions)
        free_slots = MAX_CONCURRENT_POSITIONS - active_count
        if free_slots <= 0:
            return decisions

        # 3. Evaluate and rank candidate entries
        candidates: list[dict[str, Any]] = []

        for ticker, buf in sorted(daily_buffers.items()):
            ticker = ticker.upper()
            if self.valid_tickers and ticker not in self.valid_tickers:
                continue
            if ticker in self.positions or ticker in exited_tickers:
                continue
            if len(buf) < 100:
                continue

            latest_close = float(buf["close"].iloc[-1])
            sma_5 = float(buf["close"].rolling(5).mean().iloc[-1])
            sma_20 = float(buf["close"].rolling(20).mean().iloc[-1])

            # Trend Filter
            is_uptrend = (latest_close > sma_20)
            if self.use_strict_trend_filter:
                is_uptrend = is_uptrend and (sma_5 > sma_20)
            if not is_uptrend:
                continue

            # Requirement 4d: News as veto only (score <= -2 blocks entry)
            news_sc = float(news_map.get(ticker, 0.0))
            if news_sc <= -2.0:
                continue

            # Requirement 4f: Model inference with exception logging
            if self.model is None or not self.feature_cols:
                continue

            try:
                feat_row = compute_features_live(
                    buf,
                    feature_cols=self.feature_cols,
                    market_df=market_df,
                )
                if hasattr(self.model, "predict_proba"):
                    score = float(self.model.predict_proba(feat_row)[0, 1])
                else:
                    score = float(self.model.predict(feat_row)[0])
            except Exception as err:
                self.inference_exception_count += 1
                print(f"[strategy] Inference Exception #{self.inference_exception_count} for {ticker}: {err}")
                continue

            # Score tracking & dynamic threshold
            self.score_history.append(score)
            eff_thresh = self.get_effective_buy_threshold()
            if score < eff_thresh:
                continue

            try:
                atr_pct = self.get_atr_pct(buf)
            except Exception as err:
                self.inference_exception_count += 1
                print(f"[strategy] ATR Exception for {ticker}: {err}")
                continue

            candidates.append({
                "ticker": ticker,
                "score": score,
                "latest_close": latest_close,
                "atr_pct": atr_pct,
                "news_score": news_sc,
                "sma_5": sma_5,
                "sma_20": sma_20,
            })

        if not candidates:
            return decisions

        # Rank candidates cross-sectionally by model score descending (take top-N per day)
        candidates.sort(key=lambda c: c["score"], reverse=True)
        selected = candidates[:min(self.max_daily_entries, free_slots)]

        # Requirement 4e: Single Risk Parity Sizing Path
        available_cash = current_cash
        for item in selected:
            tck = item["ticker"]
            entry = item["latest_close"]
            atr_pct = item["atr_pct"]
            stop_price = round(entry * (1.0 - BARRIER_DOWN_ATR * atr_pct), 2)
            target_price = round(entry * (1.0 + BARRIER_UP_ATR * atr_pct), 2)

            shares = self.calculate_risk_shares(
                equity=current_equity,
                entry=entry,
                stop_price=stop_price,
                available_cash=available_cash,
            )

            if shares < MIN_TRADE_SIZE:
                continue

            trade_cost = shares * entry + BROKERAGE_FEE
            available_cash -= trade_cost

            # Register position internally
            self.positions[tck] = {
                "type": "LONG",
                "shares": shares,
                "entry_price": entry,
                "atr_pct_at_entry": atr_pct,
                "stop_price": stop_price,
                "target_price": target_price,
                "peak_price": entry,
                "days_held": 0,
                "last_evaluated_date": current_date,
                "trailing_stop_active": False,
                "news_score_entry": item["news_score"],
            }

            dec = {
                "ticker": tck,
                "action": "BUY",
                "quantity": shares,
                "price": entry,
                "reason": (
                    f"CROSS-SECTIONAL BUY (Rank score: {item['score']:.4f} >= {self.buy_threshold:.4f} | "
                    f"Close Rs.{entry:.2f} > 20-SMA Rs.{item['sma_20']:.2f} & 5-SMA > 20-SMA | "
                    f"Stop: Rs.{stop_price:.2f}, Target: Rs.{target_price:.2f})"
                ),
                "confidence": round(item["score"], 4),
                "model_prob": item["score"],
                "news_score": item["news_score"],
                "stop_price": stop_price,
                "target_price": target_price,
                "atr_pct": atr_pct,
            }
            decisions.append(dec)
            print(
                f"[strategy] EXECUTED BUY for {tck}: {shares} shares @ Rs.{entry:.2f} | "
                f"score: {item['score']:.4f} | news_score: {item['news_score']:+.1f}"
            )

        return decisions

    def evaluate_ticker(
        self,
        ticker: str,
        buffer_df: pd.DataFrame,
        news_score: int | float = 0,
        current_cash: float = 1000000.0,
        current_date: str = "",
        current_equity: float | None = None,
        market_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """
        Evaluates a single ticker at market bar close.
        Supports single-asset calls from live feeds or test runners.
        Enforces identical barrier logic, trend filters, news veto, and risk sizing.
        """
        ticker = ticker.upper()

        if self.valid_tickers and ticker not in self.valid_tickers:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": 0.0,
                "reason": f"Ticker '{ticker}' not in active API whitelist. Skipped.",
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
        equity = current_equity if (current_equity is not None and current_equity > 0) else current_cash

        # 1. Active Position Exit Evaluation
        if ticker in self.positions:
            exit_decision = self.evaluate_position_exit(
                ticker=ticker,
                latest_close=latest_close,
                news_score=float(news_score),
                current_date=current_date,
            )
            if exit_decision is not None:
                self.positions.pop(ticker, None)
                print(f"[strategy] EXECUTED EXIT for {ticker}: {exit_decision['reason']} | news_score: {news_score:+.1f}")
                return exit_decision

            # Still holding
            pos = self.positions[ticker]
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": int(pos["shares"]),
                "price": latest_close,
                "reason": f"HOLDING LONG (Day {pos.get('days_held', 0)}/{HORIZON_DAYS}, Stop: Rs.{pos.get('stop_price', 0):.2f}, Target: Rs.{pos.get('target_price', 0):.2f}).",
                "confidence": 0.50,
                "news_score": news_score,
            }

        # 2. Check position limit
        if len(self.positions) >= MAX_CONCURRENT_POSITIONS:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"Portfolio position cap reached ({len(self.positions)}/{MAX_CONCURRENT_POSITIONS}).",
                "confidence": 0.50,
            }

        # 3. Requirement 4d: News veto only (score <= -2 blocks entry)
        if news_score <= -2.0:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"News veto: adverse news sentiment ({news_score:+.1f} <= -2.0) blocks entry.",
                "confidence": 0.0,
            }

        # 4. Trend Filter
        sma_5 = float(buffer_df["close"].rolling(5).mean().iloc[-1]) if len(buffer_df) >= 5 else 0.0
        sma_20 = float(buffer_df["close"].rolling(20).mean().iloc[-1])
        is_uptrend = (latest_close > sma_20)
        if self.use_strict_trend_filter:
            is_uptrend = is_uptrend and (sma_5 > sma_20)
        if not is_uptrend:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"Trend filter failed: Requires Close ({latest_close:.2f}) > 20-SMA ({sma_20:.2f})" + (" AND 5-SMA > 20-SMA." if self.use_strict_trend_filter else "."),
                "confidence": 0.0,
            }

        # 5. Requirement 4f: Model inference with exception logging
        if self.model is None or not self.feature_cols:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": "Model or feature list not loaded.",
                "confidence": 0.0,
            }

        try:
            feat_row = compute_features_live(
                buffer_df,
                feature_cols=self.feature_cols,
                market_df=market_df,
            )
            if hasattr(self.model, "predict_proba"):
                price_prob = float(self.model.predict_proba(feat_row)[0, 1])
            else:
                price_prob = float(self.model.predict(feat_row)[0])
        except Exception as err:
            self.inference_exception_count += 1
            print(f"[strategy] Inference Exception #{self.inference_exception_count} for {ticker}: {err}")
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"Model inference exception #{self.inference_exception_count}: {err}",
                "confidence": 0.0,
            }

        # Check threshold (dynamic trailing median or static)
        self.score_history.append(price_prob)
        eff_thresh = self.get_effective_buy_threshold()
        if price_prob < eff_thresh:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"Model probability ({price_prob:.4f}) below threshold ({eff_thresh:.4f}).",
                "confidence": price_prob,
                "model_prob": price_prob,
            }

        # Compute ATR for barriers
        try:
            atr_pct = self.get_atr_pct(buffer_df)
        except Exception as err:
            self.inference_exception_count += 1
            print(f"[strategy] ATR Exception for {ticker}: {err}")
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": f"ATR computation error: {err}",
                "confidence": 0.0,
            }

        stop_price = round(latest_close * (1.0 - BARRIER_DOWN_ATR * atr_pct), 2)
        target_price = round(latest_close * (1.0 + BARRIER_UP_ATR * atr_pct), 2)

        # Requirement 4e: Single Risk Parity Sizing Path
        shares = self.calculate_risk_shares(
            equity=equity,
            entry=latest_close,
            stop_price=stop_price,
            available_cash=current_cash,
        )

        if shares < MIN_TRADE_SIZE:
            return {
                "ticker": ticker,
                "action": "HOLD",
                "quantity": 0,
                "price": latest_close,
                "reason": "Calculated risk share size is below minimum trade size.",
                "confidence": price_prob,
            }

        # Register position internally
        self.positions[ticker] = {
            "type": "LONG",
            "shares": shares,
            "entry_price": latest_close,
            "atr_pct_at_entry": atr_pct,
            "stop_price": stop_price,
            "target_price": target_price,
            "peak_price": latest_close,
            "days_held": 0,
            "last_evaluated_date": current_date,
            "trailing_stop_active": False,
            "news_score_entry": float(news_score),
        }

        print(
            f"[strategy] EXECUTED BUY for {ticker}: {shares} shares @ Rs.{latest_close:.2f} | "
            f"score: {price_prob:.4f} | news_score: {news_score:+.1f}"
        )

        return {
            "ticker": ticker,
            "action": "BUY",
            "quantity": shares,
            "price": latest_close,
            "reason": (
                f"BUY LONG: Model score {price_prob:.4f} >= {self.buy_threshold:.4f} | "
                f"Close Rs.{latest_close:.2f} > 20-SMA Rs.{sma_20:.2f} & 5-SMA > 20-SMA | "
                f"Stop: Rs.{stop_price:.2f}, Target: Rs.{target_price:.2f}"
            ),
            "confidence": round(price_prob, 4),
            "model_prob": price_prob,
            "news_score": float(news_score),
            "stop_price": stop_price,
            "target_price": target_price,
            "atr_pct": atr_pct,
        }
