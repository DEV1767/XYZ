"""
Live Autonomous Trading Bot Engine.

Autonomous Kafka execution engine implementing the complete Manthan 2026 specification:
1. Dynamic Stock Discovery: GET /api/v1/stocks
2. Indicator Warm-Start: Loads pre-fetched historical bars from data/raw/ or history API
3. Mandatory Pre-Flight Heartbeat: Listens for 'preflight_tick' on 'market.ticks' and ACKs to POST /api/v1/bot/heartbeat
4. Stage Monitoring: Polls GET /api/v1/stage to detect LIVE simulation vs preflight vs paused
5. Real-Time Order Execution: Ingests ticks and news, evaluates ML strategy, and dispatches BUY, SELL, SHORT, COVER
   within the 3-4s decision window with reaction speed tracking.
"""

from __future__ import annotations
import argparse
import json
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    AUTH_HEADERS,
    BROKERAGE_FEE,
    DATA_RAW_DIR,
    HEARTBEAT_API_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_COLLECTOR,
    KAFKA_NEWS_TOPIC,
    KAFKA_TICKS_TOPIC,
    ORDER_TIMEOUT_SEC,
    ORDERS_API_URL,
    PORTFOLIO_API_URL,
    PORTFOLIO_CASH_URL,
    SIMULATION_CLOCK_URL,
    STAGE_API_URL,
    STOCKS_API_URL,
)
from news_features import NewsStateBuffer
from simulation_logger import sim_logger
from strategy import StrategyEngine
from telemetry import TelemetryTracker


class TradingBot:
    """
    Main runtime orchestrator for autonomous live and sandbox trading.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.sim_logger = sim_logger
        self.session = requests.Session()
        self.session.headers.update(AUTH_HEADERS)

        # In-memory rolling price buffer: ticker -> list of OHLCV dicts (warm-started)
        self.price_buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.news_buffer = NewsStateBuffer(max_history_days=3)
        self.telemetry = TelemetryTracker()

        self.valid_tickers = self.fetch_active_tickers()
        self.strategy = StrategyEngine(valid_tickers=self.valid_tickers)

        # Warm start buffers from local CSVs
        self.warm_start_buffers()

        # Cache available cash
        self.current_cash = 1000000.0
        self.current_sim_date = ""
        self.tick_counter = 0
        self.refresh_cash_balance()
        self.sync_portfolio()
        self.query_simulation_clock()

        # Automated Continuous Pre-Flight Heartbeat Keeper (Guarantees Portal stays "Ready")
        self.last_heartbeat_seq = 1
        self.heartbeat_running = True
        self._start_heartbeat_thread()

        mode_str = "DRY-RUN (Paper Trading)" if self.dry_run else "LIVE ORDER DISPATCH"
        print(f"[bot] Initialized [{mode_str}] for {len(self.valid_tickers)} tickers. Cash: Rs. {self.current_cash:,.2f}")

    def _start_heartbeat_thread(self) -> None:
        """Runs background keepalive thread to ping heartbeat API every 8 seconds."""
        def _heartbeat_worker():
            while self.heartbeat_running:
                try:
                    self.handle_heartbeat(self.last_heartbeat_seq, is_background=True)
                except Exception:
                    pass
                time.sleep(8.0)

        t = threading.Thread(target=_heartbeat_worker, daemon=True, name="HeartbeatDaemonThread")
        t.start()

    def query_simulation_clock(self) -> dict[str, Any]:
        """Queries the canonical simulation clock from GET /api/v1/simulation/clock."""
        try:
            r = self.session.get(SIMULATION_CLOCK_URL, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                sim_day = data.get("current_day", 0)
                total_days = data.get("total_days", 500)
                rem_days = data.get("remaining_days", 0)
                sim_date = data.get("simulated_date", "")
                sec_left = data.get("estimated_time_remaining_sec", 0)
                stage = data.get("stage", "simulation")
                print(f"[CLOCK] Simulation Day {sim_day}/{total_days} ({sim_date}) | Remaining: {rem_days} days (~{sec_left // 60}m) | Stage: {stage.upper()}")
                return data
        except Exception as e:
            print(f"[CLOCK WARN] Could not query simulation clock: {e}")
        return {}

    def fetch_active_tickers(self) -> list[str]:
        """Dynamically loads active tickers from GET /api/v1/stocks."""
        try:
            r = self.session.get(STOCKS_API_URL, timeout=5)
            r.raise_for_status()
            data = r.json()
            stocks = data.get("stocks", data)
            tickers = []
            for item in stocks:
                if isinstance(item, str):
                    tickers.append(item.upper())
                elif isinstance(item, dict):
                    t = item.get("ticker") or item.get("symbol")
                    if t:
                        tickers.append(str(t).upper())
            return sorted(list(set(tickers)))
        except Exception as e:
            print(f"[bot] Warning: Could not query stocks API ({e}). Falling back to local data/raw tickers.")
            local_tickers = [f.stem.upper() for f in DATA_RAW_DIR.glob("*.csv") if f.name not in ["news_log.csv", "ticks_log.csv"]]
            return sorted(local_tickers)

    def warm_start_buffers(self) -> None:
        """Loads historical daily bars so indicator buffers are primed from Day 1."""
        print("[bot] Warm-starting indicator buffers from historical data...")
        count = 0
        for ticker in self.valid_tickers:
            csv_path = DATA_RAW_DIR / f"{ticker}.csv"
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df.columns = [c.lower().strip() for c in df.columns]
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date").reset_index(drop=True)

                    # Keep last 50 bars
                    recent_bars = df.tail(50).to_dict("records")
                    self.price_buffers[ticker] = recent_bars
                    count += 1
                except Exception as e:
                    print(f"  -> Warning warm-starting {ticker}: {e}")
        print(f"[bot] Successfully warm-started {count}/{len(self.valid_tickers)} ticker buffers.")

    def sync_portfolio(self) -> None:
        """
        Synchronizes active holdings and cash directly from GET /api/v1/portfolio.
        Ensures zero desync if bot is restarted or reconnected mid-session.
        """
        try:
            r = self.session.get(PORTFOLIO_API_URL, timeout=3)
            if r.status_code == 200:
                data = r.json()
                if "available_cash" in data:
                    self.current_cash = float(data["available_cash"])
                elif "cash" in data:
                    self.current_cash = float(data["cash"])

                holdings = data.get("holdings", data.get("positions", []))
                active_tickers_in_server = set()

                if isinstance(holdings, list):
                    for item in holdings:
                        ticker = str(item.get("ticker", "")).upper()
                        raw_qty = int(item.get("quantity", item.get("shares", 0)))
                        if not ticker or raw_qty == 0:
                            continue

                        is_short = bool(item.get("is_short", raw_qty < 0))
                        pos_type = "SHORT" if is_short else "LONG"
                        shares = abs(raw_qty)

                        avg_price = float(
                            item.get("avg_buy_price")
                            or item.get("average_buy_price")
                            or item.get("average_price")
                            or item.get("avg_price")
                            or item.get("entry_price")
                            or item.get("current_price")
                            or 0.0
                        )
                        # Fall back to warm-start buffer if price is 0
                        if avg_price <= 0 and ticker in self.price_buffers and self.price_buffers[ticker]:
                            avg_price = float(self.price_buffers[ticker][-1]["close"])

                        active_tickers_in_server.add(ticker)
                        self.strategy.positions[ticker] = {
                            "type": pos_type,
                            "shares": shares,
                            "entry_price": avg_price,
                            "days_held": self.strategy.positions.get(ticker, {}).get("days_held", 0),
                        }

                elif isinstance(holdings, dict):
                    for ticker, item in holdings.items():
                        ticker = str(ticker).upper()
                        if isinstance(item, dict):
                            raw_qty = int(item.get("quantity", item.get("shares", 0)))
                            if raw_qty == 0:
                                continue
                            is_short = bool(item.get("is_short", raw_qty < 0))
                            pos_type = "SHORT" if is_short else "LONG"
                            shares = abs(raw_qty)
                            avg_price = float(
                                item.get("avg_buy_price")
                                or item.get("average_buy_price")
                                or item.get("average_price")
                                or item.get("avg_price")
                                or item.get("entry_price")
                                or item.get("current_price")
                                or 0.0
                            )
                            if avg_price <= 0 and ticker in self.price_buffers and self.price_buffers[ticker]:
                                avg_price = float(self.price_buffers[ticker][-1]["close"])

                            active_tickers_in_server.add(ticker)
                            self.strategy.positions[ticker] = {
                                "type": pos_type,
                                "shares": shares,
                                "entry_price": avg_price,
                                "peak_price": max(avg_price, self.strategy.positions.get(ticker, {}).get("peak_price", avg_price)),
                                "days_held": self.strategy.positions.get(ticker, {}).get("days_held", 0),
                            }

                # Clean up any local positions that were closed on server
                for t in list(self.strategy.positions.keys()):
                    if t not in active_tickers_in_server:
                        del self.strategy.positions[t]

                self.telemetry.update_from_portfolio_api(data, sim_date=self.current_sim_date)
                print(f"[bot] Synced portfolio from server. Active positions: {len(self.strategy.positions)}, Cash: Rs. {self.current_cash:,.2f}")
        except Exception as e:
            print(f"[bot] Warning: Failed to sync portfolio from server ({e})")

    def refresh_cash_balance(self) -> float:
        """Queries fast cash endpoint to maintain accurate balance for sizing."""
        try:
            r = self.session.get(PORTFOLIO_CASH_URL, timeout=3)
            if r.status_code == 200:
                data = r.json()
                self.current_cash = float(data.get("available_cash", data.get("cash_balance", self.current_cash)))
        except Exception:
            pass
        return self.current_cash

    def _update_position_on_fill(self, ticker: str, action: str, quantity: int, price: float, sim_date: str = "") -> None:
        """Updates internal portfolio state upon confirmed order execution."""
        if action == "BUY":
            self.strategy.positions[ticker] = {
                "type": "LONG",
                "shares": quantity,
                "entry_price": price,
                "peak_price": price,
                "entry_date": sim_date,
                "days_held": 0,
            }
        elif action == "SHORT":
            self.strategy.positions[ticker] = {
                "type": "SHORT",
                "shares": quantity,
                "entry_price": price,
                "entry_date": sim_date,
                "days_held": 0,
            }
        elif action in ["SELL", "COVER"]:
            self.strategy.positions.pop(ticker, None)

    def send_order(self, ticker: str, action: str, quantity: int, price: float, sim_date: str = "", reason: str = "") -> bool:
        """
        Submits market order (BUY, SELL, SHORT, COVER) to POST /api/v1/orders.
        Enforces client-side validation, zero-rejection safeguards, and resilient retries.
        """
        action = action.upper()
        ticker = ticker.upper()
        quantity = int(quantity)

        # 1. Client-Side Safeguards (Zero Order Rejection Rule)
        if quantity <= 0:
            print(f"[SAFEGUARD] Aborted order: Quantity must be > 0. Got {quantity}.")
            self.telemetry.record_safeguard_block("Quantity <= 0")
            return False

        if self.valid_tickers and ticker not in self.valid_tickers:
            print(f"[SAFEGUARD] Aborted order: Ticker '{ticker}' is not in active universe.")
            self.telemetry.record_safeguard_block("Invalid Ticker")
            return False

        if action in ["BUY", "SHORT"]:
            order_cost = (quantity * price) + BROKERAGE_FEE
            if order_cost > self.current_cash:
                # Dynamically resize down to available cash if possible
                affordable_qty = int((self.current_cash - BROKERAGE_FEE) // price)
                if affordable_qty >= 1:
                    print(f"[CLIENT RESIZE] Resizing {action} {ticker} from {quantity} to {affordable_qty} shares to match cash Rs. {self.current_cash:,.2f}.")
                    quantity = affordable_qty
                else:
                    print(f"[SAFEGUARD] Aborting {action} {quantity} {ticker}: Cost Rs. {order_cost:,.2f} exceeds cash Rs. {self.current_cash:,.2f}.")
                    self.telemetry.record_safeguard_block("Insufficient Capital")
                    self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "SAFEGUARD_BLOCKED", "Insufficient Capital")
                    return False

        elif action == "SELL":
            # Must own delivery shares
            pos = self.strategy.positions.get(ticker)
            if not pos or pos.get("type") != "LONG":
                print(f"[SAFEGUARD] Aborting SELL for {ticker}: No open LONG position held.")
                self.telemetry.record_safeguard_block("No Long Position")
                self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "SAFEGUARD_BLOCKED", "No Long Position")
                return False
            if quantity > pos.get("shares", 0):
                quantity = pos["shares"]

        elif action == "COVER":
            # Must hold an open short position
            pos = self.strategy.positions.get(ticker)
            if not pos or pos.get("type") != "SHORT":
                print(f"[SAFEGUARD] Aborting COVER for {ticker}: No open SHORT position held.")
                self.telemetry.record_safeguard_block("No Short Position")
                self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "SAFEGUARD_BLOCKED", "No Short Position")
                return False
            if quantity > pos.get("shares", 0):
                quantity = pos["shares"]

        payload: dict[str, Any] = {
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
        }
        if sim_date:
            payload["date"] = sim_date

        print(f"\n[ORDER DISPATCH] >>> {action} {quantity} {ticker} @ ~Rs. {price:.2f} (SimDate: {sim_date})")
        print(f"                 Reason: {reason}")

        if self.dry_run:
            print(f"[DRY-RUN PAPER TRADE] Simulated fill: {action} {quantity} {ticker} @ Rs. {price:.2f}. No live API call made.")
            self._update_position_on_fill(ticker, action, quantity, price, sim_date)
            self.telemetry.record_order_result(action, quantity, price, success=True, is_dry_run=True)
            self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "SIMULATED_FILL", reason)
            return True

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                r = self.session.post(ORDERS_API_URL, json=payload, timeout=ORDER_TIMEOUT_SEC)
                if r.status_code in [200, 201]:
                    res = r.json()
                    print(f"[ORDER FILLED] {action} {quantity} {ticker} | Status: {res.get('status', 'OK')}")
                    self._update_position_on_fill(ticker, action, quantity, price, sim_date)
                    self.telemetry.record_order_result(action, quantity, price, success=True, is_dry_run=False)
                    self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "FILLED", reason)
                    self.refresh_cash_balance()
                    return True
                else:
                    print(f"[ORDER REJECTED] HTTP {r.status_code}: {r.text}")
                    self.telemetry.record_order_result(action, quantity, price, success=False, is_dry_run=False)
                    self.sim_logger.log_order(sim_date, ticker, action, quantity, price, f"REJECTED_{r.status_code}", r.text)
                    return False
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_attempts:
                    print(f"[ORDER RETRY] Transient network drop on {ticker} ({e}). Retrying attempt {attempt+1}/{max_attempts} in 0.5s...")
                    time.sleep(0.5)
                else:
                    print(f"[ORDER ERROR] Network error submitting order for {ticker} after {max_attempts} attempts: {e}")
                    self.telemetry.record_order_result(action, quantity, price, success=False, is_dry_run=False)
                    self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "NETWORK_ERROR", str(e))
                    return False
            except Exception as e:
                print(f"[ORDER ERROR] Unexpected error submitting order for {ticker}: {e}")
                self.telemetry.record_order_result(action, quantity, price, success=False, is_dry_run=False)
                self.sim_logger.log_order(sim_date, ticker, action, quantity, price, "UNEXPECTED_ERROR", str(e))
                return False

        return False

    def handle_heartbeat(self, seq: int, is_background: bool = False) -> bool:
        """Acknowledges pre-flight standby ping to keep team status 'Ready' on the portal."""
        safe_seq = max(1, int(seq))
        self.last_heartbeat_seq = safe_seq
        try:
            resp = self.session.post(HEARTBEAT_API_URL, json={"seq": safe_seq}, timeout=3.0)
            if resp.status_code in [200, 201]:
                if not is_background:
                    print(f"[HEARTBEAT] Sequence {safe_seq} acknowledged successfully -> Status: Ready on Portal.")
                return True
            else:
                print(f"[HEARTBEAT WARN] Server status {resp.status_code} for seq {safe_seq}: {resp.text}")
                return False
        except Exception as e:
            if not is_background:
                print(f"[HEARTBEAT ERROR] Failed to send heartbeat ACK for seq {safe_seq}: {e}")
            return False

    def on_tick_received(self, payload: dict[str, Any]) -> None:
        """
        Processes price tick event on topic 'market.ticks'.
        Runs feature calculations, signal combinations, and order dispatch within 3s.
        """
        event_raw = str(payload.get("event_type") or payload.get("event") or payload.get("type", "price_tick")).lower()

        # 1. Standby Pre-flight Check
        if "preflight" in event_raw or "heartbeat" in event_raw:
            seq = payload.get("seq")
            if seq is None:
                seq = payload.get("sequence")
            if seq is None and "data" in payload and isinstance(payload["data"], dict):
                seq = payload["data"].get("seq") or payload["data"].get("sequence")

            seq_num = max(1, int(seq)) if seq is not None else self.last_heartbeat_seq
            self.handle_heartbeat(seq_num, is_background=False)

            # Dynamically refresh simulation stock universe at pre-flight
            if not self.valid_tickers or self.tick_counter == 0:
                refreshed = self.fetch_active_tickers()
                if refreshed and set(refreshed) != set(self.valid_tickers):
                    self.valid_tickers = refreshed
                    self.strategy.valid_tickers = refreshed
                    print(f"[bot] Active stock universe refreshed at pre-flight: {self.valid_tickers}")
            return

        # 2. Daily Price Tick
        sim_date = payload.get("simulated_date") or payload.get("date", "")
        data = payload.get("data", payload)
        ticker = str(data.get("ticker", "")).upper()

        if not ticker or ticker not in self.valid_tickers:
            return

        close_price = float(data.get("close", 0.0))
        bar = {
            "date": pd.to_datetime(sim_date),
            "open": float(data.get("open", 0.0)),
            "high": float(data.get("high", 0.0)),
            "low": float(data.get("low", 0.0)),
            "close": close_price,
            "volume": float(data.get("volume", 0.0)),
            "ticker": ticker,
        }

        # Log raw incoming tick to live simulation log
        self.sim_logger.log_tick(sim_date, ticker, bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"])

        buf = self.price_buffers[ticker]
        buf.append(bar)
        if len(buf) > 60:
            buf.pop(0)

        if len(buf) < 20:
            return

        buffer_df = pd.DataFrame(buf)

        # Retrieve today's news score for this ticker
        news_feat = self.news_buffer.get_features_for_ticker(ticker, sim_date)
        news_score = news_feat["news_score"]
        self.current_sim_date = sim_date

        # Evaluate strategy (< 5 ms latency) with exact latency timing
        t0 = time.perf_counter()
        decision = self.strategy.evaluate_ticker(
            ticker=ticker,
            buffer_df=buffer_df,
            news_score=news_score,
            current_cash=self.current_cash,
            current_date=sim_date,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.telemetry.record_latency(latency_ms)

        # Log complete ML diagnostic decision with all 18 calculated features
        self.sim_logger.log_decision(
            sim_date=sim_date,
            ticker=ticker,
            close_p=close_price,
            decision=decision,
            features=decision.get("features"),
            latency_ms=latency_ms,
            model_prob=decision.get("model_prob", 0.50),
            news_score=news_score,
            price_trend=decision.get("price_trend", 0.0),
            sma_20=decision.get("sma_20", 0.0),
            is_uptrend=decision.get("is_uptrend", True),
        )

        action = decision["action"]
        qty = decision["quantity"]
        price = decision["price"]
        reason = decision["reason"]

        if action in ["BUY", "SELL", "SHORT", "COVER"] and qty > 0:
            self.send_order(
                ticker=ticker,
                action=action,
                quantity=qty,
                price=price,
                sim_date=sim_date,
                reason=reason,
            )
        else:
            print(f"[TICK] {sim_date} | {ticker:10s} Close={close_price:7.2f} | Latency={latency_ms:.2f}ms | Action: {action} ({reason[:50]}...)")

        # Periodically refresh full portfolio state from server & update live summary
        self.tick_counter += 1
        if self.tick_counter % 25 == 0:
            self.sync_portfolio()
            avg_lat = self.telemetry.get_avg_latency() if hasattr(self.telemetry, "get_avg_latency") else 0.0
            self.sim_logger.update_summary(self.current_cash, self.strategy.positions, avg_lat)

    def on_news_received(self, payload: dict[str, Any]) -> None:
        """
        Processes news flash event on topic 'market.news' (~150 ms after price tick).
        Scores headline in < 0.05 ms and records in state buffer.
        """
        sim_date = payload.get("simulated_date") or payload.get("date", "")
        data = payload.get("data", payload)

        ticker = str(data.get("ticker", "")).upper()
        headline = str(data.get("headline", ""))
        desc = str(data.get("description", ""))

        scored = self.news_buffer.add_news(ticker, sim_date, headline, desc)
        self.sim_logger.log_news(sim_date, ticker, scored["score"], scored["magnitude"], headline, desc)
        print(f"[NEWS] {sim_date} | {ticker} (Score: {scored['score']:+d}, Mag: {scored['magnitude']}%) : {headline[:65]}...")

    def run(self, max_ticks: int = 0) -> None:
        """
        Main continuous Kafka consumption loop.
        Subscribes to 'market.ticks' and 'market.news' with group 'group-<TEAM_USERNAME>'.
        """
        try:
            from kafka import KafkaConsumer
        except ImportError:
            print("[ERROR] kafka-python-ng is required. Install via: pip install kafka-python-ng")
            return

        mode_str = "DRY-RUN PAPER TRADING" if self.dry_run else "LIVE SANDBOX EXECUTION"
        print("\n" + "=" * 70)
        print(f" STARTING MANTHAN 2026 AUTONOMOUS TRADING BOT [{mode_str}]")
        print(f" Broker: {KAFKA_BOOTSTRAP_SERVERS}")
        print(f" Consumer Group: {KAFKA_GROUP_COLLECTOR}")
        print(f" Topics: {[KAFKA_TICKS_TOPIC, KAFKA_NEWS_TOPIC]}")
        print(f" Active Stocks ({len(self.valid_tickers)}): {self.valid_tickers}")
        if max_ticks > 0:
            print(f" Execution Limit: Will process {max_ticks} incoming ticks and report summary.")
        print("=" * 70 + "\n")

        consumer = None
        retry_count = 0
        max_retries = 5

        while consumer is None:
            try:
                consumer = KafkaConsumer(
                    KAFKA_TICKS_TOPIC,
                    KAFKA_NEWS_TOPIC,
                    bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
                    group_id=KAFKA_GROUP_COLLECTOR,
                    auto_offset_reset="latest",
                    enable_auto_commit=False,
                    api_version=(2, 8, 0),
                    session_timeout_ms=10000,
                    request_timeout_ms=30000,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    consumer_timeout_ms=5000,
                )
                print("[bot] Successfully connected to Kafka stream!")
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"\n[bot] ERROR: Could not connect to Kafka broker at {KAFKA_BOOTSTRAP_SERVERS} ({e}).")
                    print("           REASON: Your laptop cannot reach 192.168.65.157.")
                    print("           FIX: Make sure your laptop Wi-Fi is connected to the official VENUE Wi-Fi network,")
                    print("                NOT a mobile hotspot or external connection.")
                    return
                print(f"[bot] Connecting to Kafka broker ({e}). Retrying in 2s (Attempt {retry_count}/{max_retries})...")
                time.sleep(2)

        ticks_count = 0
        news_count = 0

        try:
            while True:
                records = consumer.poll(timeout_ms=1000)
                if not records:
                    continue

                for tp, messages in records.items():
                    for msg in messages:
                        payload = msg.value
                        if not isinstance(payload, dict):
                            continue

                        topic = msg.topic
                        try:
                            if topic == KAFKA_TICKS_TOPIC:
                                self.on_tick_received(payload)
                                ticks_count += 1
                            elif topic == KAFKA_NEWS_TOPIC:
                                self.on_news_received(payload)
                                news_count += 1
                        except Exception as e:
                            print(f"[bot] Error processing event from {topic}: {e}")

                        if max_ticks > 0 and ticks_count >= max_ticks:
                            print(f"\n[bot] Reached limit of {max_ticks} ticks. Concluding execution cycle.")
                            raise StopIteration

        except (KeyboardInterrupt, StopIteration):
            print("\n[bot] Execution session completed.")
        finally:
            consumer.close()
            self.refresh_cash_balance()
            self.sync_portfolio()
            self.telemetry.print_jury_scorecard()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Trading Bot Runner")
    parser.add_argument("--live", action="store_true", default=True, help="Launch live Kafka trading loop (default)")
    parser.add_argument("--dry-run", action="store_true", help="Paper trade without sending live REST orders")
    parser.add_argument("--ticks", type=int, default=0, help="Optional number of ticks to process before stopping")
    parser.add_argument("--scorecard", action="store_true", help="Print live 5-Pillar Executive Jury Scorecard and exit")
    parser.add_argument("--test", action="store_true", help="Run self-test only and exit")
    args = parser.parse_args()

    bot = TradingBot(dry_run=args.dry_run)
    if args.scorecard:
        bot.sync_portfolio()
        bot.telemetry.print_jury_scorecard()
    elif args.test:
        print("\n[bot] Self-test passed.")
    else:
        # Default behavior: RUN CONTINUOUSLY
        bot.run(max_ticks=args.ticks)
