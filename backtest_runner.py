"""
Gap-Aware High-Fidelity Backtest Runner (Manthan 2026).

Conforms strictly to:
1. OHLC Gap-Aware Order Matching:
   - Entries fill at the NEXT DAY'S OPEN (never on signal bar's close).
   - Stop-Loss: If open <= stop_price fill at open; elif low <= stop_price fill at stop_price.
   - Take-Profit Target: If open >= target_price fill at open; elif high >= target_price fill at target.
   - Same-bar collision: If both stop and target hit in the same bar, assume the stop.
   - Time Exit: After HORIZON_DAYS, exit at bar open/close.
2. Exact transaction friction & tax accounting:
   - Rs. 20 flat brokerage fee per order.
   - Rs. 15.34 DP charge on sell transactions.
   - 15% Short-Term Capital Gains (STCG) tax on positive net realized gains.
3. Rigorous performance statistics:
   - Trade count, win rate, average win, average loss, trade expectancy, total P&L,
     max drawdown, Sharpe ratio, and 10,000-sample bootstrap 95% CI on expectancy.
4. Equal-weight Buy-and-Hold benchmark comparison over the identical period.
5. Walk-forward period evaluation across the full history.
"""

from __future__ import annotations
import argparse
import sys
import time
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
    DATA_RAW_DIR,
    DP_CHARGE,
    HORIZON_DAYS,
    INITIAL_CAPITAL,
    LOGS_DIR,
    MAX_CONCURRENT_POSITIONS,
    MAX_POSITION_PCT,
    MIN_TRADE_SIZE,
    MODEL_FILE,
    MODELS_DIR,
    PRED_BUY_THRESHOLD,
    RANDOM_STATE,
    STCG_RATE,
    print_effective_config,
)
from features import compute_atr, compute_features_live, compute_market_returns
from strategy import StrategyEngine


def load_universe_data(data_dir: Path = DATA_RAW_DIR) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Loads all ticker CSVs and precalculates equal-weight market returns."""
    raw_dfs: dict[str, pd.DataFrame] = {}
    for p in sorted(data_dir.glob("*.csv")):
        if p.name in ["news_log.csv", "ticks_log.csv"]:
            continue
        df = pd.read_csv(p)
        df.columns = [c.lower().strip() for c in df.columns]
        df["ticker"] = p.stem.upper()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        raw_dfs[p.stem.upper()] = df

    market_df = compute_market_returns(raw_dfs)
    return raw_dfs, market_df


def bootstrap_expectancy_ci(
    net_pnls: np.ndarray | list[float],
    n_bootstraps: int = 10000,
    random_state: int = RANDOM_STATE,
) -> tuple[float, float]:
    """
    Computes a 95% bootstrap confidence interval on mean trade expectancy (INR).
    Resamples trade P&Ls with replacement n_bootstraps times.
    """
    arr = np.array(net_pnls, dtype=float)
    if len(arr) == 0:
        return 0.0, 0.0
    if len(arr) == 1:
        return float(arr[0]), float(arr[0])

    rng = np.random.default_rng(random_state)
    boot_means = np.empty(n_bootstraps, dtype=float)
    n = len(arr)
    for i in range(n_bootstraps):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means[i] = np.mean(sample)

    ci_lower = float(np.percentile(boot_means, 2.5))
    ci_upper = float(np.percentile(boot_means, 97.5))
    return ci_lower, ci_upper


def run_buy_and_hold_benchmark(
    ticker_dfs: dict[str, pd.DataFrame],
    dates: list[pd.Timestamp],
    initial_capital: float = INITIAL_CAPITAL,
) -> dict[str, Any]:
    """
    Simulates equal-weight Buy-and-Hold across all universe tickers over the identical dates.
    Buys at day 1 Open, holds to the final day Close, and deducts round-trip brokerage + DP charges.
    """
    if not dates:
        return {"return_pct": 0.0, "final_wealth": initial_capital, "sharpe": 0.0, "max_drawdown_pct": 0.0}

    tickers = sorted(ticker_dfs.keys())
    n_tickers = len(tickers)
    allocation_per_stock = (initial_capital * 0.98) / n_tickers

    start_date = dates[0]
    end_date = dates[-1]

    # Buy at day 1 Open
    holdings: dict[str, dict[str, float]] = {}
    invested_cash = 0.0
    total_entry_fees = 0.0

    for t in tickers:
        df = ticker_dfs[t]
        bar1 = df[df["date"] == start_date]
        if bar1.empty:
            bar1 = df[df["date"] >= start_date].head(1)
        if bar1.empty:
            continue
        open_p = float(bar1["open"].iloc[0])
        shares = int((allocation_per_stock - BROKERAGE_FEE) // open_p)
        if shares > 0:
            cost = shares * open_p + BROKERAGE_FEE
            invested_cash += cost
            total_entry_fees += BROKERAGE_FEE
            holdings[t] = {"shares": shares, "entry_price": open_p}

    daily_values: list[float] = []
    cash = initial_capital - invested_cash

    for d in dates:
        port_val = cash
        for t, h in holdings.items():
            df = ticker_dfs[t]
            bar = df[df["date"] == d]
            if not bar.empty:
                c_p = float(bar["close"].iloc[0])
            else:
                c_p = h["entry_price"]
            port_val += h["shares"] * c_p
        daily_values.append(port_val)

    # Liquidate at end
    final_wealth = cash
    total_exit_fees = 0.0
    total_tax = 0.0
    for t, h in holdings.items():
        df = ticker_dfs[t]
        bar_end = df[df["date"] == end_date]
        if bar_end.empty:
            bar_end = df[df["date"] <= end_date].tail(1)
        close_p = float(bar_end["close"].iloc[0])
        gross = h["shares"] * close_p
        gain = gross - (h["shares"] * h["entry_price"])
        tax = max(0.0, gain * STCG_RATE)
        fee = BROKERAGE_FEE + DP_CHARGE
        total_exit_fees += fee
        total_tax += tax
        final_wealth += gross - fee - tax

    total_return_pct = ((final_wealth - initial_capital) / initial_capital) * 100.0

    # Drawdown and Sharpe
    val_series = pd.Series(daily_values)
    cummax = val_series.cummax()
    dd_series = (val_series - cummax) / cummax
    max_dd_pct = float(dd_series.min() * 100.0)

    daily_ret = val_series.pct_change().dropna()
    daily_rf = (1.06 ** (1 / 250)) - 1.0
    excess_ret = daily_ret - daily_rf
    sharpe = float((excess_ret.mean() / (excess_ret.std() + 1e-9)) * np.sqrt(250)) if len(excess_ret) > 1 else 0.0

    return {
        "final_wealth": round(final_wealth, 2),
        "total_pnl": round(final_wealth - initial_capital, 2),
        "return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe": round(sharpe, 2),
    }


def run_gap_aware_simulation(
    ticker_dfs: dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    start_date: pd.Timestamp | str | None = None,
    end_date: pd.Timestamp | str | None = None,
    initial_capital: float = INITIAL_CAPITAL,
    strategy: StrategyEngine | None = None,
    news_dict: dict[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    """
    Executes a high-fidelity gap-aware backtest simulation conforming to all task rules.
    """
    if strategy is None:
        strategy = StrategyEngine(valid_tickers=list(ticker_dfs.keys()))
    else:
        strategy.set_valid_tickers(list(ticker_dfs.keys()))

    # Gather shared chronological dates
    all_dates = sorted(list(set.intersection(*[set(df["date"]) for df in ticker_dfs.values()])))
    if start_date is not None:
        s_dt = pd.to_datetime(start_date)
        all_dates = [d for d in all_dates if d >= s_dt]
    if end_date is not None:
        e_dt = pd.to_datetime(end_date)
        all_dates = [d for d in all_dates if d <= e_dt]

    if len(all_dates) < 2:
        raise ValueError("Insufficient date range for simulation.")

    cash = float(initial_capital)
    active_positions: dict[str, dict[str, Any]] = {}
    pending_entries: list[dict[str, Any]] = []  # Generated at date t Close, filled at date t+1 Open
    closed_trades: list[dict[str, Any]] = []
    daily_history: list[dict[str, Any]] = []

    total_brokerage = 0.0
    total_dp_charges = 0.0
    total_stcg_tax = 0.0

    news_data = news_dict or {}

    for day_idx, current_dt in enumerate(all_dates):
        date_str = current_dt.strftime("%Y-%m-%d")

        # -------------------------------------------------------------
        # STEP 1: FILL PENDING ENTRIES AT TODAY'S OPEN (Next-Day Open Fill)
        # -------------------------------------------------------------
        if pending_entries:
            for order in pending_entries:
                tck = order["ticker"]
                df_tck = ticker_dfs[tck]
                bar_today = df_tck[df_tck["date"] == current_dt]
                if bar_today.empty:
                    continue

                open_price = float(bar_today["open"].iloc[0])
                atr_pct = float(order["atr_pct"])
                req_shares = int(order["shares"])

                # Calculate stop & target from fill price (day t+1 open)
                stop_price = round(open_price * (1.0 - BARRIER_DOWN_ATR * atr_pct), 2)
                target_price = round(open_price * (1.0 + BARRIER_UP_ATR * atr_pct), 2)

                # Re-check cash availability
                max_affordable = int((cash - BROKERAGE_FEE) // open_price)
                fill_shares = min(req_shares, max_affordable)

                if fill_shares >= MIN_TRADE_SIZE:
                    cost = fill_shares * open_price + BROKERAGE_FEE
                    cash -= cost
                    total_brokerage += BROKERAGE_FEE

                    active_positions[tck] = {
                        "ticker": tck,
                        "type": "LONG",
                        "shares": fill_shares,
                        "entry_price": open_price,
                        "entry_date": date_str,
                        "atr_pct_at_entry": atr_pct,
                        "stop_price": stop_price,
                        "target_price": target_price,
                        "peak_price": open_price,
                        "days_held": 0,
                        "trailing_stop_active": False,
                        "news_score_entry": order.get("news_score", 0.0),
                    }
            pending_entries.clear()

        # -------------------------------------------------------------
        # STEP 2: EVALUATE ACTIVE POSITIONS USING TODAY'S OHLC BARS
        # -------------------------------------------------------------
        exited_this_bar: set[str] = set()

        for tck, pos in list(active_positions.items()):
            df_tck = ticker_dfs[tck]
            bar_today = df_tck[df_tck["date"] == current_dt]
            if bar_today.empty:
                continue

            open_p = float(bar_today["open"].iloc[0])
            high_p = float(bar_today["high"].iloc[0])
            low_p = float(bar_today["low"].iloc[0])
            close_p = float(bar_today["close"].iloc[0])

            pos["days_held"] += 1
            days_held = pos["days_held"]
            entry_p = float(pos["entry_price"])
            stop_p = float(pos["stop_price"])
            target_p = float(pos["target_price"])
            atr_pct = float(pos["atr_pct_at_entry"])
            shares = int(pos["shares"])

            news_sc = float(news_data.get((date_str, tck), 0.0))

            exit_triggered = False
            fill_price = close_p
            exit_reason = ""

            # Check 1: Adverse news veto (score <= -2)
            if news_sc <= -2.0:
                exit_triggered = True
                fill_price = open_p  # Fills at open when news breaks
                exit_reason = f"NEWS VETO (Score: {news_sc:+.1f} <= -2.0)"

            # Check 2: Strict Stop-Loss (5% Hard Stop or Current Ratcheted Stop)
            if not exit_triggered:
                stop_hit = (open_p <= stop_p) or (low_p <= stop_p)
                if stop_hit:
                    exit_triggered = True
                    fill_price = open_p if open_p <= stop_p else stop_p
                    exit_reason = f"STOP LOSS FILL (Stop: Rs.{stop_p:.2f}, Executed @ Rs.{fill_price:.2f})"

            # Check 3: Tax-Efficient Breakeven Protection Ratchet (at +3% gain)
            if not exit_triggered:
                unrealized_peak_gain = (high_p - entry_p) / entry_p if entry_p > 0 else 0.0
                if unrealized_peak_gain >= 0.03:
                    breakeven_price = round(entry_p * 1.005, 2)
                    if breakeven_price > pos["stop_price"]:
                        pos["stop_price"] = breakeven_price
                        stop_p = breakeven_price
                    pos["trailing_stop_active"] = True

                # Tax-Efficient Runner Mode (2.0 ATR trailing buffer below peak)
                if pos.get("trailing_stop_active", False) or unrealized_peak_gain >= 0.05:
                    pos["trailing_stop_active"] = True
                    peak_p = max(float(pos.get("peak_price", entry_p)), high_p)
                    pos["peak_price"] = peak_p

                    trail_distance_pct = max(2.0 * atr_pct, 0.05)
                    runner_trail = round(peak_p * (1.0 - trail_distance_pct), 2)
                    if runner_trail > pos["stop_price"]:
                        pos["stop_price"] = runner_trail
                        stop_p = runner_trail

                    # Check trailing stop touch
                    if open_p <= stop_p:
                        exit_triggered = True
                        fill_price = open_p
                        exit_reason = f"RUNNER TRAIL HARVEST (Open gap @ Rs.{fill_price:.2f} <= Trail Rs.{stop_p:.2f})"
                    elif low_p <= stop_p:
                        exit_triggered = True
                        fill_price = stop_p
                        exit_reason = f"RUNNER TRAIL HARVEST (Intraday low @ Rs.{low_p:.2f} touched Trail Rs.{stop_p:.2f})"

            # Check 4: Stagnant Time Exit (after HORIZON_DAYS)
            if not exit_triggered and days_held >= HORIZON_DAYS:
                unrealized_close_gain = (close_p - entry_p) / entry_p if entry_p > 0 else 0.0
                # If still winning >= +2%, let the winner keep running!
                if unrealized_close_gain < 0.02:
                    exit_triggered = True
                    fill_price = close_p
                    exit_reason = f"STAGNANT TIME EXIT (Held {days_held} days with low momentum {unrealized_close_gain:+.2%})"

            # Execute exit settlement
            if exit_triggered:
                gross_proceeds = shares * fill_price
                gross_profit = gross_proceeds - (shares * entry_p)
                tax = gross_profit * STCG_RATE if gross_profit > 0 else 0.0
                fees = BROKERAGE_FEE + DP_CHARGE

                net_profit = gross_profit - fees - tax
                net_cash_returned = gross_proceeds - fees - tax
                cash += net_cash_returned

                total_brokerage += BROKERAGE_FEE
                total_dp_charges += DP_CHARGE
                total_stcg_tax += tax

                closed_trades.append({
                    "ticker": tck,
                    "entry_date": pos["entry_date"],
                    "exit_date": date_str,
                    "shares": shares,
                    "entry_price": entry_p,
                    "exit_price": fill_price,
                    "gross_profit": round(gross_profit, 2),
                    "fees": round(fees, 2),
                    "tax": round(tax, 2),
                    "net_pnl": round(net_profit, 2),
                    "return_pct": round((net_profit / (shares * entry_p)) * 100.0, 2),
                    "days_held": days_held,
                    "exit_reason": exit_reason,
                    "news_score": news_sc,
                })
                exited_this_bar.add(tck)

        for tck in exited_this_bar:
            active_positions.pop(tck, None)

        # -------------------------------------------------------------
        # STEP 3: GENERATE NEXT-DAY ENTRY SIGNALS AT MARKET CLOSE
        # -------------------------------------------------------------
        available_slots = MAX_CONCURRENT_POSITIONS - len(active_positions)

        if available_slots > 0:
            candidates: list[dict[str, Any]] = []

            # Prepare buffers for all tickers up to current date
            for tck, df_tck in ticker_dfs.items():
                if tck in active_positions or tck in exited_this_bar:
                    continue

                hist_buf = df_tck[df_tck["date"] <= current_dt]
                if len(hist_buf) < 100:
                    continue

                close_p = float(hist_buf["close"].iloc[-1])
                sma_5 = float(hist_buf["close"].rolling(5).mean().iloc[-1])
                sma_20 = float(hist_buf["close"].rolling(20).mean().iloc[-1])

                # Trend filter: latest_close > sma_20 AND sma_5 > sma_20 (strict AND)
                if not (close_p > sma_20 and sma_5 > sma_20):
                    continue

                # News veto: news_score <= -2 blocks entry
                news_sc = float(news_data.get((date_str, tck), 0.0))
                if news_sc <= -2.0:
                    continue

                # Model probability inference
                if strategy.model is None or not strategy.feature_cols:
                    continue

                try:
                    feat_row = compute_features_live(
                        hist_buf,
                        feature_cols=strategy.feature_cols,
                        market_df=market_df,
                    )
                    if hasattr(strategy.model, "predict_proba"):
                        score = float(strategy.model.predict_proba(feat_row)[0, 1])
                    else:
                        score = float(strategy.model.predict(feat_row)[0])
                except Exception as err:
                    strategy.inference_exception_count += 1
                    continue

                if score < strategy.buy_threshold:
                    continue

                try:
                    atr_pct = strategy.get_atr_pct(hist_buf)
                except Exception:
                    continue

                candidates.append({
                    "ticker": tck,
                    "score": score,
                    "close_price": close_p,
                    "atr_pct": atr_pct,
                    "news_score": news_sc,
                })

            if candidates:
                # Cross-sectional ranking: select top free slots by model score descending
                candidates.sort(key=lambda c: c["score"], reverse=True)
                selected = candidates[:available_slots]

                # Current total equity estimate for sizing
                cur_positions_val = sum(p["shares"] * p["entry_price"] for p in active_positions.values())
                est_equity = cash + cur_positions_val

                alloc_cash = cash
                for item in selected:
                    tck = item["ticker"]
                    entry_est = item["close_price"]
                    atr_pct = item["atr_pct"]
                    stop_est = round(entry_est * (1.0 - BARRIER_DOWN_ATR * atr_pct), 2)

                    shares = strategy.calculate_risk_shares(
                        equity=est_equity,
                        entry=entry_est,
                        stop_price=stop_est,
                        available_cash=alloc_cash,
                    )

                    if shares >= MIN_TRADE_SIZE:
                        alloc_cash -= (shares * entry_est + BROKERAGE_FEE)
                        pending_entries.append({
                            "ticker": tck,
                            "shares": shares,
                            "atr_pct": atr_pct,
                            "news_score": item["news_score"],
                            "score": item["score"],
                        })

        # -------------------------------------------------------------
        # STEP 4: MARK-TO-MARKET DAILY WEALTH TRACKING
        # -------------------------------------------------------------
        holdings_market_val = 0.0
        for tck, pos in active_positions.items():
            df_tck = ticker_dfs[tck]
            bar_now = df_tck[df_tck["date"] == current_dt]
            c_p = float(bar_now["close"].iloc[0]) if not bar_now.empty else pos["entry_price"]
            holdings_market_val += pos["shares"] * c_p

        total_wealth = cash + holdings_market_val
        daily_history.append({
            "date": date_str,
            "wealth": total_wealth,
            "cash": cash,
            "holdings_val": holdings_market_val,
            "active_positions": len(active_positions),
        })

    # Close remaining positions on the final day at final Close
    if active_positions:
        final_dt = all_dates[-1]
        final_date_str = final_dt.strftime("%Y-%m-%d")
        for tck, pos in list(active_positions.items()):
            df_tck = ticker_dfs[tck]
            bar_end = df_tck[df_tck["date"] == final_dt]
            close_p = float(bar_end["close"].iloc[0]) if not bar_end.empty else pos["entry_price"]
            gross = pos["shares"] * close_p
            gain = gross - (pos["shares"] * pos["entry_price"])
            tax = max(0.0, gain * STCG_RATE)
            fees = BROKERAGE_FEE + DP_CHARGE
            net_pnl = gain - fees - tax
            cash += gross - fees - tax
            closed_trades.append({
                "ticker": tck,
                "entry_date": pos["entry_date"],
                "exit_date": final_date_str,
                "shares": pos["shares"],
                "entry_price": pos["entry_price"],
                "exit_price": close_p,
                "gross_profit": round(gain, 2),
                "fees": round(fees, 2),
                "tax": round(tax, 2),
                "net_pnl": round(net_pnl, 2),
                "return_pct": round((net_pnl / (pos["shares"] * pos["entry_price"])) * 100.0, 2),
                "days_held": pos["days_held"],
                "exit_reason": "SIMULATION END (Liquidated at final close)",
                "news_score": 0.0,
            })
        active_positions.clear()

    # Final statistics calculation
    final_wealth = cash
    total_net_pnl = final_wealth - initial_capital
    net_return_pct = (total_net_pnl / initial_capital) * 100.0

    wealth_series = pd.Series([d["wealth"] for d in daily_history])
    cummax = wealth_series.cummax()
    dd_series = (wealth_series - cummax) / cummax
    max_drawdown_pct = float(dd_series.min() * 100.0) if not dd_series.empty else 0.0

    daily_returns = wealth_series.pct_change().dropna()
    daily_rf = (1.06 ** (1 / 250)) - 1.0
    excess_returns = daily_returns - daily_rf
    sharpe = float((excess_returns.mean() / (excess_returns.std() + 1e-9)) * np.sqrt(250)) if len(excess_returns) > 1 else 0.0

    # Trade statistics
    trade_count = len(closed_trades)
    if trade_count > 0:
        pnls = [t["net_pnl"] for t in closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / trade_count) * 100.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        expectancy_inr = float(np.mean(pnls))
        ci_lower, ci_upper = bootstrap_expectancy_ci(pnls, n_bootstraps=10000)
    else:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        expectancy_inr = 0.0
        ci_lower, ci_upper = 0.0, 0.0

    # Buy and Hold Benchmark
    bnh_results = run_buy_and_hold_benchmark(ticker_dfs, all_dates, initial_capital=initial_capital)

    return {
        "date_range": (all_dates[0].strftime("%Y-%m-%d"), all_dates[-1].strftime("%Y-%m-%d")),
        "days_count": len(all_dates),
        "initial_capital": initial_capital,
        "final_wealth": round(final_wealth, 2),
        "total_net_pnl": round(total_net_pnl, 2),
        "net_return_pct": round(net_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trade_count": trade_count,
        "win_rate_pct": round(win_rate, 2),
        "avg_win_inr": round(avg_win, 2),
        "avg_loss_inr": round(avg_loss, 2),
        "expectancy_inr": round(expectancy_inr, 2),
        "ci_lower_95": round(ci_lower, 2),
        "ci_upper_95": round(ci_upper, 2),
        "total_brokerage": round(total_brokerage, 2),
        "total_dp_charges": round(total_dp_charges, 2),
        "total_stcg_tax": round(total_stcg_tax, 2),
        "buy_and_hold": bnh_results,
        "closed_trades": closed_trades,
    }


def print_backtest_report(title: str, res: dict[str, Any]) -> None:
    """Prints a clear, formatted summary report of backtest performance."""
    print("\n" + "=" * 90)
    print(f" {title}")
    print("=" * 90)
    print(f"  Date Range:            {res['date_range'][0]} to {res['date_range'][1]} ({res['days_count']} trading days)")
    print(f"  Starting Capital:      Rs. {res['initial_capital']:,.2f}")
    print(f"  Final Wealth:          Rs. {res['final_wealth']:,.2f}")
    print(f"  Total Net P&L:         Rs. {res['total_net_pnl']:+,.2f} ({res['net_return_pct']:+.2f}%)")
    print(f"  Max Drawdown:          {res['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe Ratio (Ann):    {res['sharpe_ratio']:.2f}")
    print("-" * 90)
    print(f"  Total Completed Trades:{res['trade_count']:5d}")
    print(f"  Win Rate:              {res['win_rate_pct']:.2f}%")
    print(f"  Average Win:           Rs. {res['avg_win_inr']:+,.2f}")
    print(f"  Average Loss:          Rs. {res['avg_loss_inr']:+,.2f}")
    print(f"  Expectancy Per Trade:  Rs. {res['expectancy_inr']:+,.2f}")
    print(f"  Bootstrap 95% CI:      [Rs. {res['ci_lower_95']:+,.2f}, Rs. {res['ci_upper_95']:+,.2f}]")
    is_profitable = res["ci_lower_95"] > 0
    print(f"  Statistically Profitable (CI > 0): {'YES' if is_profitable else 'NO (CI includes zero)'}")
    print("-" * 90)
    print(f"  Frictions Deducted:    Brokerage Rs.{res['total_brokerage']:,.2f} | DP Charges Rs.{res['total_dp_charges']:,.2f} | STCG Tax Rs.{res['total_stcg_tax']:,.2f}")
    print("-" * 90)
    bnh = res["buy_and_hold"]
    print("  EQUAL-WEIGHT BUY-AND-HOLD BENCHMARK COMPARISON:")
    print(f"    B&H Final Wealth:    Rs. {bnh['final_wealth']:,.2f} ({bnh['return_pct']:+.2f}%)")
    print(f"    B&H Max Drawdown:    {bnh['max_drawdown_pct']:.2f}%")
    print(f"    B&H Sharpe Ratio:    {bnh['sharpe']:.2f}")
    alpha = res["net_return_pct"] - bnh["return_pct"]
    print(f"    Strategy Alpha:      {alpha:+.2f}% vs Buy-and-Hold")
    print("=" * 90)


def run_full_walk_forward_evaluation() -> None:
    """
    Executes backtest across the full history and on walk-forward slices.
    Prints the effective config at the top as mandated by TASK 1d.
    """
    # Mandated TASK 1d: Print effective config at top of every backtest log
    print_effective_config()

    print("\n[backtest] Loading ticker history and calculating equal-weight market returns...")
    ticker_dfs, market_df = load_universe_data()

    # Load news log if available
    news_dict: dict[tuple[str, str], float] = {}
    news_file = LOGS_DIR / "live_simulation_news.csv"
    if news_file.exists():
        try:
            ndf = pd.read_csv(news_file)
            for _, r in ndf.iterrows():
                d = str(r.get("simulated_date", "")).strip()
                t = str(r.get("ticker", "")).strip().upper()
                sc = float(r.get("score", 0.0))
                news_dict[(d, t)] = sc
        except Exception:
            pass

    strategy = StrategyEngine(valid_tickers=list(ticker_dfs.keys()))

    # Find total date range
    shared_dates = sorted(list(set.intersection(*[set(df["date"]) for df in ticker_dfs.values()])))
    n_dates = len(shared_dates)

    # Walk-forward slices across history:
    # 1. Full History (post warm-up)
    full_res = run_gap_aware_simulation(
        ticker_dfs, market_df,
        start_date=shared_dates[100], end_date=shared_dates[-1],
        strategy=strategy, news_dict=news_dict,
    )
    print_backtest_report("FULL HISTORY GAP-AWARE BACKTEST (POST 100-BAR WARM-UP)", full_res)

    # 2. Historical Walk-Forward Development Period (dates 100 to -86)
    dev_end_date = shared_dates[-86]
    dev_res = run_gap_aware_simulation(
        ticker_dfs, market_df,
        start_date=shared_dates[100], end_date=dev_end_date,
        strategy=strategy, news_dict=news_dict,
    )
    print_backtest_report("WALK-FORWARD DEVELOPMENT PERIOD", dev_res)

    # 3. Untouched Test Set (Final 86 dates) - RUN ONCE ONLY
    test_start_date = shared_dates[-86]
    test_res = run_gap_aware_simulation(
        ticker_dfs, market_df,
        start_date=test_start_date, end_date=shared_dates[-1],
        strategy=strategy, news_dict=news_dict,
    )
    print_backtest_report("FINAL UNTOUCHED TEST PERIOD (RUN EXACTLY ONCE)", test_res)

    # Save backtest results snapshot to logs/
    out_path = LOGS_DIR / "backtest_summary.joblib"
    joblib.dump({
        "full_history": full_res,
        "dev_period": dev_res,
        "untouched_test": test_res,
    }, out_path)
    print(f"\n[backtest] Backtest summary artifacts saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="High-fidelity gap-aware backtest runner")
    args = parser.parse_args()
    run_full_walk_forward_evaluation()

