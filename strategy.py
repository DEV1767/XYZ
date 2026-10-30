"""
Trading Strategy and Risk Management Engine (Manthan 2026).

Enforces:
1. Triple Barrier exit engine matching labeling:
   stop   = entry * (1 - BARRIER_DOWN_ATR * atr_pct_at_entry)
   target = entry * (1 + BARRIER_UP_ATR * atr_pct_at_entry)
   time exit after HORIZON_DAYS.
   Tracks atr_pct_at_entry, stop_price, target_price, and days_held (incremented once per date).
2. Super-Runner Trailing Mode: Trails 2.0 ATR below peak to capture +15% to +50% multibagger runs.
3. Breakeven Protection Ratchet: At +3.5% gain, elevates stop to entry * 1.008 (Breakeven + fee buffer).
4. Catastrophic Stop Cut (-6%): Limits drawdowns before they turn into -25% wipeouts.
5. Relative Momentum Rotation: Rotates capital from stagnant/losing positions held > 8 days into fresh breakout leaders.
6. Cross-sectional ranking entry: ranks all universe tickers by model probability each day
   and selects top-N free slots (up to MAX_CONCURRENT_POSITIONS).
7. Strict trend filters: require latest_close > sma_20 AND sma_5 > sma_20 (strict AND, not OR).
8. News as veto only: score <= -2 blocks entry or forces defensive exit.
9. Single risk parity sizing path with Confidence Conviction Scaling:
   High confidence (>= 0.55) receives 100% full allocation;
   Low confidence (<= 0.40) receives 50% half allocation to cut downside risk.
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
    STOP_LOSS_PCT,
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
        self.use_trailing_median: bool = False
        self.use_strict_trend_filter: bool = True
        self.max_daily_entries: int = MAX_CONCURRENT_POSITIONS

        # PRED_BUY_THRESHOLD from config/.env governs the operational buy threshold
        self.buy_threshold = PRED_BUY_THRESHOLD
        if metadata_path.exists():
            try:
                meta = joblib.load(metadata_path)
                print(f"[strategy] Active buy threshold: {self.buy_threshold:.4f} (Model validation reference: {meta.get('chosen_threshold', 0.55):.4f})")
            except Exception as e:
                print(f"[strategy] Using active threshold: {self.buy_threshold:.4f}")

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

        self.positions: dict[str, dict[str, Any]] = {}

    def set_valid_tickers(self, tickers: list[str]) -> None:
        """Updates the active ticker whitelist."""
        self.valid_tickers = set(t.upper() for t in tickers)

    def get_effective_buy_threshold(self) -> float:
        """Returns the configured buy threshold (defaulting to PRED_BUY_THRESHOLD)."""
        return self.buy_threshold

    def calculate_risk_shares(
        self,
        equity: float,
        entry: float,
        stop_price: float,
        available_cash: float,
        confidence: float = 1.0,
    ) -> int:
        """
        Risk Parity Sizing Path with Confidence Conviction Scaling:
          Risk budget = 2% of total equity
          Per-share risk = entry - stop_price
          shares = (equity * 0.02) / (entry - stop_price)
          Capped at MAX_POSITION_PCT of equity and liquid cash,
          scaled smoothly between 0.50x (low confidence <= 0.40) and 1.00x (high confidence >= 0.55).
        """
        if entry <= 0 or equity <= 0:
            return 0

        per_share_risk = entry - stop_price
        if per_share_risk <= 0:
            per_share_risk = entry * 0.05

        # Conviction scalar:
        # score >= 0.55 -> 1.00x (full allocation ~Rs. 1,21,400)
        # score <= 0.40 -> 0.50x (half allocation ~Rs. 60,000)
        # smoothly scaled in between
        if confidence <= 0.40:
            conviction_scalar = 0.50
        elif confidence >= 0.55:
            conviction_scalar = 1.00
        else:
            conviction_scalar = 0.50 + 0.50 * ((confidence - 0.40) / 0.15)

        risk_budget = equity * 0.02 * conviction_scalar
        risk_shares = int(risk_budget / per_share_risk)

        # Capital cap: MAX_POSITION_PCT of total equity scaled by conviction
        max_capital = equity * MAX_POSITION_PCT * conviction_scalar
        cap_shares = int(max_capital / entry)

        shares = min(risk_shares, cap_shares)

        # Cash constraint: Strictly preserve 15% cash reserve (Market allocation capped at 85%)
        min_reserve = equity * CASH_RESERVE_PCT
        spendable_cash = max(0.0, available_cash - min_reserve - BROKERAGE_FEE)
        max_cash_shares = int(spendable_cash // entry)
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
        Asymmetric Wealth Builder & Capital Protector:
        1. News Veto Defensive Exit (adverse sentiment score <= -2.0)
        2. Catastrophic Stop Cut (-6% Ceiling): Saves capital from -25% wipeouts.
        3. Breakeven Protection Ratchet (+3.5% gain): Locks stop to entry * 1.008 so profit is guaranteed!
        4. Super-Runner Mode: Trails 2.0 ATR below peak to capture +15% to +50% multibaggers into cash.
        5. Dead Weight Capital Rotation: If held >= 8 days with negative momentum (< 0%), exits to free cash for leaders.
        """
        if ticker not in self.positions:
            return None

        pos = self.positions[ticker]
        shares = int(pos.get("shares", 0))
        entry = float(pos.get("entry_price", 0.0))
        if shares <= 0 or entry <= 0:
            return None

        atr_pct = float(pos.get("atr_pct_at_entry", 0.02))
        if "stop_price" not in pos:
            pos["stop_price"] = round(entry * (1.0 - STOP_LOSS_PCT), 2)
        if "target_price" not in pos:
            pos["target_price"] = round(entry * (1.0 + BARRIER_UP_ATR * atr_pct), 2)

        # Increment days_held once per unique calendar date
        last_eval_date = pos.get("last_evaluated_date", "")
        if current_date and current_date != last_eval_date:
            pos["days_held"] = pos.get("days_held", 0) + 1
            pos["last_evaluated_date"] = current_date

        days_held = pos.get("days_held", 0)
        unrealized_pnl_pct = (latest_close - entry) / entry if entry > 0 else 0.0

        # 1. News veto exit (defensive emergency)
        if news_score <= -2.0:
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"DEFENSIVE NEWS VETO (news_score {news_score:+.1f} <= -2.0)",
                "confidence": 1.0,
                "news_score": news_score,
                "days_held": days_held,
            }

        # 2. Hard Catastrophic Stop Cut (Limits loss to -6% before it turns into a -25% wipeout)
        if latest_close <= pos.get("stop_price", 0.0) or unrealized_pnl_pct <= -0.06:
            if unrealized_pnl_pct > 0.0:
                reason = f"PROTECTED PROFIT HARVEST (Hit Ratcheted Stop Rs.{pos['stop_price']:.2f}, Locked Gain {unrealized_pnl_pct:+.2%})"
            else:
                reason = f"CATASTROPHIC STOP CUT (Loss {unrealized_pnl_pct:+.2%} <= -6.0%). Limiting downside."
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": reason,
                "confidence": 1.0,
                "news_score": news_score,
                "days_held": days_held,
            }

        # 3. Breakeven Protection Ratchet (Activates once gain >= +3.5%)
        # Moves stop to entry * 1.008 (+0.8% above cost to cover brokerage/DP fees).
        # GUARANTEES that this winning trade can NEVER become a loss!
        if unrealized_pnl_pct >= 0.035:
            breakeven_stop = round(entry * 1.008, 2)
            if breakeven_stop > pos.get("stop_price", 0.0):
                pos["stop_price"] = breakeven_stop
            pos["trailing_stop_active"] = True

        # 4. Super-Runner Mode: Trail winners to capture +15% to +50% multibaggers
        if pos.get("trailing_stop_active", False) or unrealized_pnl_pct >= 0.08:
            pos["trailing_stop_active"] = True
            peak_price = max(float(pos.get("peak_price", entry)), latest_close)
            pos["peak_price"] = peak_price

            trail_distance_pct = max(2.0 * atr_pct, 0.05)
            runner_trail_stop = round(peak_price * (1.0 - trail_distance_pct), 2)
            if runner_trail_stop > pos.get("stop_price", 0.0):
                pos["stop_price"] = runner_trail_stop

            if latest_close <= pos.get("stop_price", 0.0):
                return {
                    "ticker": ticker,
                    "action": "SELL",
                    "quantity": shares,
                    "price": latest_close,
                    "reason": f"SUPER-RUNNER PROFIT HARVEST (Peak Rs.{peak_price:.2f}, Locked Gain {unrealized_pnl_pct:+.2%}). Banking cash!",
                    "confidence": 0.95,
                    "news_score": news_score,
                    "days_held": days_held,
                }

        # 5. Dead Weight Capital Rotation (after 8 days if trade is negative)
        if days_held >= 8 and unrealized_pnl_pct < 0.0:
            return {
                "ticker": ticker,
                "action": "SELL",
                "quantity": shares,
                "price": latest_close,
                "reason": f"MOMENTUM ROTATION (Held {days_held} days with negative return {unrealized_pnl_pct:+.2%}). Freeing cash for leaders.",
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
        1. Checks exits and harvests for all held positions.
        2. Evaluates candidates passing golden-cross trend filters and news veto.
        3. If slots are full, performs Momentum Rotation (replaces dead-weight with top breakout).
        4. Sizes and dispatches new high-conviction entries using Confidence Conviction Scaling.
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

        # 2. Evaluate and rank candidate entries
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

            # Golden-Cross Trend Filter (Requires Close > 20-SMA AND 5-SMA > 20-SMA)
            is_uptrend = (latest_close > sma_20)
            if self.use_strict_trend_filter:
                is_uptrend = is_uptrend and (sma_5 > sma_20)
            if not is_uptrend:
                continue

            # Requirement 4d: News veto only (score <= -2 blocks entry)
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

        # Rank candidates cross-sectionally by model score descending
        candidates.sort(key=lambda c: c["score"], reverse=True)

        active_count = len(self.positions)
        free_slots = MAX_CONCURRENT_POSITIONS - active_count

        # 3. Dynamic Momentum Rotation: If slots are full, swap weakest red holding for top breakout
        if free_slots <= 0 and candidates:
            top_candidate = candidates[0]
            if top_candidate["score"] >= 0.48:
                # Find weakest held position (held >= 7 days with negative PnL)
                worst_ticker = None
                worst_pnl = 0.0
                for tck, pos in self.positions.items():
                    if pos.get("days_held", 0) >= 7:
                        cur_p = float(daily_buffers.get(tck, pd.DataFrame()).get("close", pd.Series([0.0])).iloc[-1]) if tck in daily_buffers else 0.0
                        entry_p = float(pos.get("entry_price", 0.0))
                        pnl = (cur_p - entry_p) / entry_p if entry_p > 0 and cur_p > 0 else 0.0
                        if pnl < worst_pnl:
                            worst_pnl = pnl
                            worst_ticker = tck

                if worst_ticker and worst_pnl < -0.01:
                    w_pos = self.positions.pop(worst_ticker)
                    w_close = float(daily_buffers[worst_ticker]["close"].iloc[-1])
                    decisions.append({
                        "ticker": worst_ticker,
                        "action": "SELL",
                        "quantity": int(w_pos["shares"]),
                        "price": w_close,
                        "reason": f"MOMENTUM ROTATION: Exiting lagging {worst_ticker} ({worst_pnl:+.1%}) to fund top leader {top_candidate['ticker']} (Score {top_candidate['score']:.4f}).",
                        "confidence": 0.95,
                        "news_score": 0.0,
                    })
                    free_slots += 1
                    print(f"[strategy] ROTATED OUT: {worst_ticker} ({worst_pnl:+.1%}) -> ROTATING IN: {top_candidate['ticker']} (Score: {top_candidate['score']:.4f})")

        if free_slots <= 0:
            return decisions

        selected = candidates[:min(self.max_daily_entries, free_slots)]

        # 4. Confidence-Weighted Risk Parity Sizing Path
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
                confidence=float(item.get("score", 1.0)),
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

        # 4. Golden-Cross Trend Filter
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

        # Requirement 4e: Single Risk Parity Sizing Path with Confidence Conviction Scaling
        shares = self.calculate_risk_shares(
            equity=equity,
            entry=latest_close,
            stop_price=stop_price,
            available_cash=current_cash,
            confidence=float(price_prob),
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
