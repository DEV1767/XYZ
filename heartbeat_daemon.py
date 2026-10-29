"""
Continuous Pre-Flight Heartbeat Daemon.

Sends mandatory heartbeat sequence acknowledgments to:
POST http://<SERVER_IP>:3002/api/v1/bot/heartbeat
Maintains active 'Ready' status on the Participant Dashboard.
"""

from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent))

from config import (
    AUTH_HEADERS,
    HEARTBEAT_API_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_COLLECTOR,
    KAFKA_TICKS_TOPIC,
)


def send_heartbeat_ack(session: requests.Session, seq: int) -> bool:
    """Dispatches sequence ACK to keep status 'Ready'."""
    try:
        r = session.post(HEARTBEAT_API_URL, json={"seq": seq}, timeout=3.0)
        if r.status_code in [200, 201]:
            print(f"[HEARTBEAT] Seq {seq} ACK confirmed! (Status: Ready on Portal)")
            return True
        else:
            print(f"[HEARTBEAT] Server response {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"[HEARTBEAT] Could not reach server: {e}")
        return False


def run_heartbeat_daemon() -> None:
    """Listens to Kafka for preflight ticks and sends periodic keepalive ACKs."""
    session = requests.Session()
    session.headers.update(AUTH_HEADERS)

    print("\n" + "=" * 65)
    print(" STARTING MANTHAN 2026 PRE-FLIGHT HEARTBEAT DAEMON")
    print(f" Target Endpoint: {HEARTBEAT_API_URL}")
    print(f" Kafka Broker:    {KAFKA_BOOTSTRAP_SERVERS}")
    print(f" Consumer Group:  {KAFKA_GROUP_COLLECTOR}")
    print("=" * 65 + "\n")

    # Initial ping
    send_heartbeat_ack(session, seq=1)

    try:
        from kafka import KafkaConsumer
        consumer = KafkaConsumer(
            KAFKA_TICKS_TOPIC,
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
        print("[daemon] Connected to Kafka ticks stream. Listening for pre-flight sequence pings...")

        last_ack_time = time.time()
        last_seq = 1

        while True:
            records = consumer.poll(timeout_ms=1000)
            now = time.time()

            if records:
                for tp, messages in records.items():
                    for msg in messages:
                        payload = msg.value
                        if not isinstance(payload, dict):
                            continue
                        event = payload.get("event") or payload.get("event_type")
                        if event == "preflight_tick":
                            seq = payload.get("seq")
                            if seq is None and "data" in payload and isinstance(payload["data"], dict):
                                seq = payload["data"].get("seq")
                            if seq is not None:
                                last_seq = max(1, int(seq))
                                send_heartbeat_ack(session, last_seq)
                                last_ack_time = now

            # Ensure we send an ACK at least once every 8 seconds even during standby idle
            if now - last_ack_time >= 8.0:
                send_heartbeat_ack(session, last_seq)
                last_ack_time = now

    except Exception as exc:
        print(f"[daemon] Kafka listener note ({exc}). Falling back to 8s HTTP keepalive timer...")
        seq = 1
        while True:
            send_heartbeat_ack(session, seq)
            seq += 1
            time.sleep(8)


if __name__ == "__main__":
    run_heartbeat_daemon()
