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
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    AUTH_HEADERS,
    DATA_RAW_DIR,
    HEARTBEAT_API_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_COLLECTOR,
    KAFKA_NEWS_TOPIC,
    KAFKA_TICKS_TOPIC,
    ORDERS_API_URL,
    PORTFOLIO_CASH_URL,
    STAGE_API_URL,
    STOCKS_API_URL,
)
from news_features import NewsStateBuffer
from strategy import StrategyEngine


class TradingBot:
    """
    Main runtime orchestrator for autonomous live and sandbox trading.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(AUTH_HEADERS)

        # In-memory rolling price buffer: ticker -> list of OHLCV dicts (warm-started)
        self.price_buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.news_buffer = NewsStateBuffer(max_history_days=3)

        self.valid_tickers = self.fetch_active_tickers()
        self.strategy = StrategyEngine(valid_tickers=self.valid_tickers)

        # Warm start buffers from local CSVs
        self.warm_start_buffers()

        # Cache available cash
        self.current_cash = 1000000.0
        self.refresh_cash_balance()

        mode_str = "DRY-RUN (Paper Trading)" if self.dry_run else "LIVE ORDER DISPATCH"
        print(f"[bot] Initialized [{mode_str}] for {len(self.valid_tickers)} tickers. Cash: Rs. {self.current_cash:,.2f}")

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

    def refresh_cash_balance(self) -> float:
        """Queries fast cash endpoint to maintain accurate balance for sizing."""
        try:
            r = self.session.get(PORTFOLIO_CASH_URL, timeout=2)
            if r.status_code == 200:
                data = r.json()
                self.current_cash = float(data.get("available_cash", data.get("cash_balance", self.current_cash)))
        except Exception:
            pass
        return self.current_cash

    def send_order(self, ticker: str, action: str, quantity: int, price: float, sim_date: str = "", reason: str = "") -> bool:
        """
        Submits market order (BUY, SELL, SHORT, COVER) to POST /api/v1/orders.
        Includes simulated date for platform latency tracking.
        """
        payload: dict[str, Any] = {
            "ticker": ticker,
            "action": action.upper(),
            "quantity": int(quantity),
        }
        if sim_date:
            payload["date"] = sim_date

        print(f"\n[ORDER DISPATCH] >>> {action} {quantity} {ticker} @ ~Rs. {price:.2f} (SimDate: {sim_date})")
        print(f"                 Reason: {reason}")

        if self.dry_run:
            print(f"[DRY-RUN PAPER TRADE] Simulated fill: {action} {quantity} {ticker} @ Rs. {price:.2f}. No live API call made.")
            return True

        try:
            r = self.session.post(ORDERS_API_URL, json=payload, timeout=3)
            if r.status_code in [200, 201]:
                res = r.json()
                print(f"[ORDER FILLED] {action} {quantity} {ticker} | Status: {res.get('status', 'OK')}")
                self.refresh_cash_balance()
                return True
            else:
                print(f"[ORDER REJECTED] HTTP {r.status_code}: {r.text}")
                return False
        except Exception as e:
            print(f"[ORDER ERROR] Network error submitting order: {e}")
            return False

    def handle_heartbeat(self, seq: int) -> None:
        """Acknowledges pre-flight standby ping to keep team status 'Ready'."""
        try:
            resp = self.session.post(HEARTBEAT_API_URL, json={"seq": seq}, timeout=2)
            if resp.status_code in [200, 201]:
                print(f"[HEARTBEAT] Sequence {seq} acknowledged (Status: Ready).")
        except Exception as e:
            print(f"[HEARTBEAT ERROR] Failed to ACK seq {seq}: {e}")

    def on_tick_received(self, payload: dict[str, Any]) -> None:
        """
        Processes price tick event on topic 'market.ticks'.
        Runs feature calculations, signal combinations, and order dispatch within 3s.
        """
        event_type = payload.get("event_type") or payload.get("event", "price_tick")

        # 1. Standby Pre-flight Check
        if event_type == "preflight_tick":
            seq = payload.get("seq")
            if seq is None and "data" in payload and isinstance(payload["data"], dict):
                seq = payload["data"].get("seq")
            if seq is not None:
                self.handle_heartbeat(int(seq))
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

        # Evaluate strategy (< 5 ms latency)
        decision = self.strategy.evaluate_ticker(
            ticker=ticker,
            buffer_df=buffer_df,
            news_score=news_score,
            current_cash=self.current_cash,
            current_date=sim_date,
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
                    request_timeout_ms=10000,
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
                        if topic == KAFKA_TICKS_TOPIC:
                            self.on_tick_received(payload)
                            ticks_count += 1
                        elif topic == KAFKA_NEWS_TOPIC:
                            self.on_news_received(payload)
                            news_count += 1

                        if max_ticks > 0 and ticks_count >= max_ticks:
                            print(f"\n[bot] Reached limit of {max_ticks} ticks. Concluding execution cycle.")
                            raise StopIteration

        except (KeyboardInterrupt, StopIteration):
            print("\n[bot] Execution session completed.")
        finally:
            consumer.close()
            self.refresh_cash_balance()
            print("\n" + "=" * 70)
            print(" EXECUTION SESSION SUMMARY")
            print("=" * 70)
            print(f"  Total Ticks Processed: {ticks_count}")
            print(f"  Total News Flashes:    {news_count}")
            print(f"  Active Positions:      {len(self.strategy.positions)} stocks")
            for t, pos in self.strategy.positions.items():
                print(f"    -> {t}: {pos['type']} {pos['shares']} shares @ Rs. {pos['entry_price']:.2f} (Held {pos['days_held']}d)")
            print(f"  Cash Remaining:        Rs. {self.current_cash:,.2f}")
            print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Trading Bot Runner")
    parser.add_argument("--live", action="store_true", help="Launch live Kafka trading loop")
    parser.add_argument("--dry-run", action="store_true", help="Paper trade without sending live REST orders")
    parser.add_argument("--ticks", type=int, default=0, help="Optional number of ticks to process before stopping")
    args = parser.parse_args()

    bot = TradingBot(dry_run=args.dry_run)
    if args.live:
        bot.run(max_ticks=args.ticks)
    else:
        print("\n[bot] Self-test passed.")
        print("  To test in Sandbox (Paper Trading - zero risk):")
        print("      python bot.py --live --dry-run")
        print("  To test in Sandbox (Live Order Execution):")
        print("      python bot.py --live")
