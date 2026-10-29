"""
Real-Time Simulation Diagnostic Logger.

Captures all live ticks, news flashes, computed ML feature vectors, model
probabilities, strategy decisions, and order execution fills during live simulation.
Enables instant post-simulation extraction, diagnostic auditing, and model fine-tuning
before the final hackathon competition run.
"""

from __future__ import annotations
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))

from config import DATA_RAW_DIR, LOGS_DIR


class SimulationLogger:
    """
    High-performance diagnostic logger for live simulation.
    Appends records immediately to dedicated CSV and JSON files in logs/.
    """
    def __init__(self, logs_dir: Path = LOGS_DIR, raw_dir: Path = DATA_RAW_DIR):
        self.logs_dir = Path(logs_dir)
        self.raw_dir = Path(raw_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.ticks_csv_path = self.logs_dir / "live_simulation_ticks.csv"
        self.news_csv_path = self.logs_dir / "live_simulation_news.csv"
        self.decisions_csv_path = self.logs_dir / "live_simulation_decisions.csv"
        self.orders_csv_path = self.logs_dir / "live_simulation_orders.csv"
        self.summary_json_path = self.logs_dir / "live_simulation_summary.json"

        # Also maintain copy in raw_dir for pipeline compatibility
        self.raw_ticks_path = self.raw_dir / "ticks_log.csv"
        self.raw_news_path = self.raw_dir / "news_log.csv"

        self._init_files()

        # Session tracking metrics
        self.session_start_time = time.time()
        self.total_ticks = 0
        self.total_news = 0
        self.total_decisions = 0
        self.action_counts = {"BUY": 0, "SELL": 0, "SHORT": 0, "COVER": 0, "HOLD": 0}
        self.orders_filled = 0
        self.orders_rejected = 0
        self.orders_blocked = 0

    def _init_files(self) -> None:
        """Initializes CSV files with headers if they do not exist."""
        # 1. Ticks CSV
        if not self.ticks_csv_path.exists() or self.ticks_csv_path.stat().st_size == 0:
            with open(self.ticks_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "simulated_date", "ticker", "open", "high", "low", "close", "volume"
                ])

        if not self.raw_ticks_path.exists() or self.raw_ticks_path.stat().st_size == 0:
            with open(self.raw_ticks_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "simulated_date", "ticker", "open", "high", "low", "close", "volume"
                ])

        # 2. News CSV
        if not self.news_csv_path.exists() or self.news_csv_path.stat().st_size == 0:
            with open(self.news_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "simulated_date", "ticker", "score", "magnitude", "headline", "description"
                ])

        if not self.raw_news_path.exists() or self.raw_news_path.stat().st_size == 0:
            with open(self.raw_news_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "simulated_date", "ticker", "score", "magnitude", "headline", "description"
                ])

        # 3. Decisions & Features CSV (The ML Goldmine)
        if not self.decisions_csv_path.exists() or self.decisions_csv_path.stat().st_size == 0:
            with open(self.decisions_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "simulated_date",
                    "ticker",
                    "close",
                    "model_prob",
                    "news_score",
                    "price_trend",
                    "sma_20",
                    "is_uptrend",
                    "action",
                    "quantity",
                    "price",
                    "confidence",
                    "latency_ms",
                    "reason",
                    # Computed 18 quantitative features at this exact moment
                    "return_1d",
                    "return_3d",
                    "return_5d",
                    "return_10d",
                    "sma_5",
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
                ])

        # 4. Orders CSV
        if not self.orders_csv_path.exists() or self.orders_csv_path.stat().st_size == 0:
            with open(self.orders_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "simulated_date", "ticker", "action", "quantity", "price", "order_cost", "status", "reason"
                ])

    def log_tick(
        self,
        sim_date: str,
        ticker: str,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        volume: float,
    ) -> None:
        """Logs an incoming price bar to both logs/ and data/raw/ticks_log.csv."""
        ts = datetime.now().isoformat()
        row = [ts, sim_date, ticker.upper(), f"{open_p:.2f}", f"{high_p:.2f}", f"{low_p:.2f}", f"{close_p:.2f}", f"{volume:.0f}"]
        
        try:
            with open(self.ticks_csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            with open(self.raw_ticks_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            self.total_ticks += 1
        except Exception as e:
            print(f"[logger] Error writing tick: {e}")

    def log_news(
        self,
        sim_date: str,
        ticker: str,
        score: int | float,
        magnitude: float,
        headline: str,
        description: str = "",
    ) -> None:
        """Logs an incoming news flash to both logs/ and data/raw/news_log.csv."""
        ts = datetime.now().isoformat()
        clean_headline = headline.replace("\n", " ").replace("\r", " ").strip()
        clean_desc = description.replace("\n", " ").replace("\r", " ").strip()
        row = [ts, sim_date, ticker.upper(), score, magnitude, clean_headline, clean_desc]

        try:
            with open(self.news_csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            with open(self.raw_news_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            self.total_news += 1
        except Exception as e:
            print(f"[logger] Error writing news: {e}")

    def log_decision(
        self,
        sim_date: str,
        ticker: str,
        close_p: float,
        decision: dict[str, Any],
        features: dict[str, float] | None = None,
        latency_ms: float = 0.0,
        model_prob: float = 0.50,
        news_score: int | float = 0,
        price_trend: float = 0.0,
        sma_20: float = 0.0,
        is_uptrend: bool = True,
    ) -> None:
        """
        Logs complete decision vector and all 18 calculated features.
        This provides the exact empirical ground truth for model fine-tuning.
        """
        ts = datetime.now().isoformat()
        action = decision.get("action", "HOLD")
        qty = decision.get("quantity", 0)
        price = decision.get("price", close_p)
        conf = decision.get("confidence", 0.50)
        reason = str(decision.get("reason", "")).replace("\n", " ").strip()

        feat = features or {}

        row = [
            ts,
            sim_date,
            ticker.upper(),
            f"{close_p:.2f}",
            f"{model_prob:.4f}",
            f"{news_score}",
            f"{price_trend:.4f}",
            f"{sma_20:.2f}",
            int(is_uptrend),
            action,
            qty,
            f"{price:.2f}",
            f"{conf:.4f}",
            f"{latency_ms:.2f}",
            reason,
            # 18 Features
            f"{feat.get('return_1d', 0.0):.6f}",
            f"{feat.get('return_3d', 0.0):.6f}",
            f"{feat.get('return_5d', 0.0):.6f}",
            f"{feat.get('return_10d', 0.0):.6f}",
            f"{feat.get('sma_5', 0.0):.2f}",
            f"{feat.get('sma_ratio', 1.0):.6f}",
            f"{feat.get('close_to_sma20', 0.0):.6f}",
            f"{feat.get('ema_12', 0.0):.2f}",
            f"{feat.get('close_to_ema12', 0.0):.6f}",
            f"{feat.get('rsi_14', 50.0):.2f}",
            f"{feat.get('volatility_10', 0.0):.6f}",
            f"{feat.get('volatility_20', 0.0):.6f}",
            f"{feat.get('volume_change', 0.0):.4f}",
            f"{feat.get('volume_to_sma20', 1.0):.4f}",
            f"{feat.get('hl_range', 0.0):.6f}",
            f"{feat.get('dist_from_high_20', 0.0):.6f}",
            f"{feat.get('dist_from_low_20', 0.0):.6f}",
        ]

        try:
            with open(self.decisions_csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            self.total_decisions += 1
            if action in self.action_counts:
                self.action_counts[action] += 1
        except Exception as e:
            print(f"[logger] Error writing decision: {e}")

    def log_order(
        self,
        sim_date: str,
        ticker: str,
        action: str,
        quantity: int,
        price: float,
        status: str,
        reason: str = "",
    ) -> None:
        """Logs an order dispatch and execution outcome."""
        ts = datetime.now().isoformat()
        cost = quantity * price
        clean_reason = reason.replace("\n", " ").strip()
        row = [ts, sim_date, ticker.upper(), action, quantity, f"{price:.2f}", f"{cost:.2f}", status, clean_reason]

        try:
            with open(self.orders_csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)

            if status in ["FILLED", "SUCCESS", "OK", "SIMULATED_FILL"]:
                self.orders_filled += 1
            elif "REJECT" in status:
                self.orders_rejected += 1
            elif "BLOCK" in status or "SAFEGUARD" in status:
                self.orders_blocked += 1
        except Exception as e:
            print(f"[logger] Error writing order: {e}")

    def update_summary(
        self,
        current_cash: float,
        portfolio_positions: dict[str, Any],
        avg_latency_ms: float = 0.0,
    ) -> None:
        """Writes live executive summary JSON for real-time monitoring."""
        elapsed_sec = max(1.0, time.time() - self.session_start_time)
        summary = {
            "session_active": True,
            "updated_at": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed_sec, 1),
            "total_ticks_recorded": self.total_ticks,
            "total_news_recorded": self.total_news,
            "total_decisions": self.total_decisions,
            "actions_breakdown": self.action_counts,
            "orders": {
                "filled": self.orders_filled,
                "rejected": self.orders_rejected,
                "safeguard_blocked": self.orders_blocked,
            },
            "portfolio": {
                "cash": current_cash,
                "active_positions_count": len(portfolio_positions),
                "holdings": portfolio_positions,
            },
            "performance": {
                "average_decision_latency_ms": round(avg_latency_ms, 2),
            },
            "files": {
                "ticks_csv": str(self.ticks_csv_path),
                "news_csv": str(self.news_csv_path),
                "decisions_csv": str(self.decisions_csv_path),
                "orders_csv": str(self.orders_csv_path),
            }
        }

        try:
            with open(self.summary_json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        except Exception as e:
            pass


# Global singleton instance
sim_logger = SimulationLogger()

