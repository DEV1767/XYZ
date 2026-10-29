"""
Kafka News and Price Tick Collector.

Listens continuously to Kafka topics ('market.news' and 'market.ticks') with
group ID 'group-<TEAM_USERNAME>-collector', appending incoming events to
data/raw/news_log.csv and data/raw/ticks_log.csv.
Designed to run resiliently in the background with auto-reconnect and regular flushing.
Includes a --mock generator for offline development and testing.
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_COLLECTOR,
    KAFKA_NEWS_TOPIC,
    KAFKA_TICKS_TOPIC,
    NEWS_LOG_PATH,
    TICKS_LOG_PATH,
)

# Headers for logging CSVs
NEWS_HEADERS = ["received_at", "simulated_date", "ticker", "headline", "description", "event_type"]
TICKS_HEADERS = ["received_at", "simulated_date", "ticker", "open", "high", "low", "close", "volume"]


def initialize_csv(path: Path, headers: list[str]) -> None:
    """Ensures CSV file exists with proper column headers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def process_news_message(payload: dict[str, Any], file_obj: Any, writer: Any) -> None:
    """Parses and appends a news_flash event to news_log.csv."""
    event_type = payload.get("event_type", "news_flash")
    simulated_date = payload.get("simulated_date") or payload.get("date", "")
    data = payload.get("data", payload)

    ticker = data.get("ticker", "")
    headline = data.get("headline", "")
    description = data.get("description", "")
    received_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    writer.writerow([received_at, simulated_date, ticker, headline, description, event_type])
    file_obj.flush()
    print(f"[NEWS] {simulated_date} | {ticker}: {headline[:60]}...")


def process_tick_message(payload: dict[str, Any], file_obj: Any, writer: Any, session: Any = None) -> None:
    """Parses and appends a price_tick event to ticks_log.csv. Handles preflight heartbeat ACKs."""
    event_type = payload.get("event_type") or payload.get("event", "price_tick")

    # Handle Pre-Flight Heartbeat
    if event_type == "preflight_tick":
        seq = payload.get("seq")
        if seq is None and "data" in payload and isinstance(payload["data"], dict):
            seq = payload["data"].get("seq")
        if seq is not None and session is not None:
            from config import HEARTBEAT_API_URL
            try:
                resp = session.post(HEARTBEAT_API_URL, json={"seq": seq}, timeout=2.0)
                print(f"[HEARTBEAT ACK] Standby seq={seq} acknowledged. Status: {resp.status_code}")
            except Exception as exc:
                print(f"[HEARTBEAT ERROR] Could not ACK seq={seq}: {exc}")
        return

    simulated_date = payload.get("simulated_date") or payload.get("date", "")
    data = payload.get("data", payload)

    ticker = data.get("ticker", "")
    o = data.get("open", 0.0)
    h = data.get("high", 0.0)
    l = data.get("low", 0.0)
    c = data.get("close", 0.0)
    v = data.get("volume", 0)
    received_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    writer.writerow([received_at, simulated_date, ticker, o, h, l, c, v])
    file_obj.flush()
    print(f"[TICK] {simulated_date} | {ticker}: Close={c}, Vol={v}")


def generate_mock_stream(num_days: int = 30, interval_sec: float = 0.1) -> None:
    """
    Simulates Kafka stream delivery for local testing when Kafka is offline.
    Generates realistic sequential price ticks and corresponding news flashes.
    """
    initialize_csv(NEWS_LOG_PATH, NEWS_HEADERS)
    initialize_csv(TICKS_LOG_PATH, TICKS_HEADERS)

    sample_tickers = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK"]
    sample_news_templates = [
        ("{ticker} POSTS RECORD PROFIT SURGE OF {pct}%, BEATING STREET ESTIMATES", "Quarterly profit grew significantly.", 1),
        ("{ticker} FACES REGULATORY SCRUTINY AND COMPLAINT PROBE, DOWNGRADE LIKELY", "Authorities request accounting records.", -1),
        ("{ticker} ANNOUNCES STRATEGIC EXPANSION AND DIVIDEND PAYOUT", "Board approves new joint venture.", 1),
        ("{ticker} REPORTS QUARTERLY LOSS OF {pct}%, FAILS TO BEAT TARGETS", "Operational margin pressures lead to drop.", -1),
        ("{ticker} SIGNS MULTI-YEAR PARTNERSHIP WITH GLOBAL TECH LEADER", "Expected to boost long-term growth.", 1),
        ("{ticker} WITNESSES EXECUTIVE RESIGNATION AMID FRAUD ALLEGATIONS", "Leadership changes rattle investors.", -1),
    ]

    import random

    start_date = pd.Timestamp.now() - pd.Timedelta(days=num_days * 2)
    calendar_dates = pd.bdate_range(start=start_date, periods=num_days)

    print(f"[collector-mock] Simulating {num_days} days of ticks and news across {len(sample_tickers)} tickers...")
    with open(NEWS_LOG_PATH, "a", newline="", encoding="utf-8") as news_f, \
         open(TICKS_LOG_PATH, "a", newline="", encoding="utf-8") as ticks_f:

        news_writer = csv.writer(news_f)
        ticks_writer = csv.writer(ticks_f)

        base_prices = {t: random.uniform(500, 3000) for t in sample_tickers}

        for sim_date in calendar_dates:
            date_str = sim_date.strftime("%Y-%m-%d")

            for t in sample_tickers:
                # 1. Price Tick
                p = base_prices[t] * (1.0 + random.gauss(0.0005, 0.02))
                base_prices[t] = p
                h = p * (1.0 + random.uniform(0.005, 0.02))
                l = p * (1.0 - random.uniform(0.005, 0.02))
                o = l + (h - l) * random.random()
                v = random.randint(50000, 2000000)

                tick_payload = {
                    "event_type": "price_tick",
                    "simulated_date": date_str,
                    "data": {
                        "ticker": t,
                        "open": round(o, 2),
                        "high": round(h, 2),
                        "low": round(l, 2),
                        "close": round(p, 2),
                        "volume": v,
                    }
                }
                process_tick_message(tick_payload, ticks_f, ticks_writer)

                # 2. News Flash (~40% chance of news for this ticker on this day)
                if random.random() < 0.40:
                    template, desc, _ = random.choice(sample_news_templates)
                    pct = random.randint(5, 30)
                    headline = template.format(ticker=t, pct=pct)
                    news_payload = {
                        "event_type": "news_flash",
                        "simulated_date": date_str,
                        "data": {
                            "ticker": t,
                            "headline": headline,
                            "description": desc,
                            "date": date_str,
                        }
                    }
                    process_news_message(news_payload, news_f, news_writer)

            if interval_sec > 0:
                time.sleep(interval_sec)

    print(f"[collector-mock] Completed mock simulation. Data stored in:\n  -> {NEWS_LOG_PATH}\n  -> {TICKS_LOG_PATH}")


def run_kafka_collector() -> None:
    """Connects to Kafka and consumes from market.news and market.ticks."""
    try:
        from kafka import KafkaConsumer
    except ImportError:
        print("[ERROR] kafka-python-ng is not installed. Run: pip install kafka-python-ng")
        return

    initialize_csv(NEWS_LOG_PATH, NEWS_HEADERS)
    initialize_csv(TICKS_LOG_PATH, TICKS_HEADERS)

    topics = [KAFKA_NEWS_TOPIC, KAFKA_TICKS_TOPIC]
    print(f"[collector] Starting Kafka consumer...")
    print(f"            Broker: {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"            Group ID: {KAFKA_GROUP_COLLECTOR}")
    print(f"            Topics: {topics}")
    print(f"            News Log: {NEWS_LOG_PATH}")
    print(f"            Ticks Log: {TICKS_LOG_PATH}")

    retry_delay = 2
    consumer = None

    while consumer is None:
        try:
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
                group_id=KAFKA_GROUP_COLLECTOR,
                auto_offset_reset="latest",
                enable_auto_commit=False,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                consumer_timeout_ms=5000,
            )
            print("[collector] Successfully connected to Kafka cluster.")
        except Exception as exc:
            print(f"[collector] Connection failed ({exc}). Retrying in {retry_delay}s...")
            print("            (Tip: Use 'python data/collect_news.py --mock' if Kafka is not yet live)")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)

    import requests
    from config import AUTH_HEADERS
    session = requests.Session()
    session.headers.update(AUTH_HEADERS)

    with open(NEWS_LOG_PATH, "a", newline="", encoding="utf-8") as news_f, \
         open(TICKS_LOG_PATH, "a", newline="", encoding="utf-8") as ticks_f:

        news_writer = csv.writer(news_f)
        ticks_writer = csv.writer(ticks_f)

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
                        event_type = payload.get("event_type") or payload.get("event", "")

                        if topic == KAFKA_NEWS_TOPIC or event_type == "news_flash":
                            process_news_message(payload, news_f, news_writer)
                        elif topic == KAFKA_TICKS_TOPIC or event_type in ["price_tick", "preflight_tick"]:
                            process_tick_message(payload, ticks_f, ticks_writer, session=session)

        except KeyboardInterrupt:
            print("\n[collector] Stopped by user.")
        finally:
            if consumer:
                consumer.close()
            print("[collector] Shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect live news and price ticks from Kafka")
    parser.add_argument("--mock", action="store_true", help="Simulate Kafka streaming to generate initial logs")
    parser.add_argument("--mock-days", type=int, default=40, help="Days of mock history to generate")
    args = parser.parse_args()

    if args.mock:
        generate_mock_stream(num_days=args.mock_days, interval_sec=0.0)
    else:
        run_kafka_collector()
