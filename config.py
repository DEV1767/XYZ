"""
Configuration module for the autonomous trading bot.
Loads environment variables and defines constants, paths, trading costs,
risk controls, news keywords, and ML hyperparameters.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# =====================================================================
# Server & API Configuration
# =====================================================================
SERVER_IP: str = os.getenv("SERVER_IP", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "3002"))
BASE_URL: str = f"http://{SERVER_IP}:{API_PORT}"
BOT_ACCESS_TOKEN: str = os.getenv("BOT_ACCESS_TOKEN", "")

AUTH_HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {BOT_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

STOCKS_API_URL: str = f"{BASE_URL}/api/v1/stocks"
HISTORY_API_URL_TEMPLATE: str = f"{BASE_URL}/api/v1/stocks/{{ticker}}/history"

# =====================================================================
# Kafka Stream Configuration
# =====================================================================
TEAM_USERNAME: str = os.getenv("TEAM_USERNAME", "mn2612")
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", f"{SERVER_IP}:9094")
KAFKA_NEWS_TOPIC: str = os.getenv("KAFKA_NEWS_TOPIC", "market.news")
KAFKA_TICKS_TOPIC: str = os.getenv("KAFKA_TICKS_TOPIC", "market.ticks")
KAFKA_GROUP_COLLECTOR: str = f"group-{TEAM_USERNAME}"

# Endpoints as per Problem Statement
STAGE_API_URL: str = f"{BASE_URL}/api/v1/stage"
HEARTBEAT_API_URL: str = f"{BASE_URL}/api/v1/bot/heartbeat"
PORTFOLIO_API_URL: str = f"{BASE_URL}/api/v1/portfolio"
PORTFOLIO_CASH_URL: str = f"{BASE_URL}/api/v1/portfolio/cash"
ORDERS_API_URL: str = f"{BASE_URL}/api/v1/orders"

# =====================================================================
# Directory & File Paths
# =====================================================================
DATA_DIR: Path = BASE_DIR / "data"
DATA_RAW_DIR: Path = DATA_DIR / "raw"
MODELS_DIR: Path = BASE_DIR / "models"
LOGS_DIR: Path = BASE_DIR / "logs"

DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

NEWS_LOG_PATH: Path = DATA_RAW_DIR / "news_log.csv"
TICKS_LOG_PATH: Path = DATA_RAW_DIR / "ticks_log.csv"
NEWS_ANALYSIS_PATH: Path = LOGS_DIR / "news_analysis.csv"

MODEL_FILE: Path = MODELS_DIR / "best_model.joblib"
FEATURE_NAMES_FILE: Path = MODELS_DIR / "feature_names.joblib"
NEWS_MODEL_FILE: Path = MODELS_DIR / "news_model.joblib"

# =====================================================================
# Trading & Transaction Costs (Manthan 2026 Problem Statement)
# =====================================================================
# Platform transaction costs & taxes
BROKERAGE_FEE: float = float(os.getenv("BROKERAGE_FEE", "20.0"))     # Flat Rs. 20 per order
DP_CHARGE: float = float(os.getenv("DP_CHARGE", "15.34"))            # Flat Rs. 15.34 on sells
STCG_RATE: float = 0.15                                              # 15% Short Term Capital Gains (<=365d)
LTCG_RATE: float = 0.10                                              # 10% Long Term Capital Gains (>365d)
LTCG_EXEMPTION: float = 100000.0                                     # First Rs. 1,00,000 exempt under Sec 112A

def safe_float(val: Any, default: float) -> float:
    try:
        import re
        cleaned = re.sub(r"[^\d.]", "", str(val))
        return float(cleaned) if cleaned else default
    except Exception:
        return default

def safe_int(val: Any, default: int) -> int:
    try:
        import re
        cleaned = re.sub(r"[^\d]", "", str(val))
        return int(cleaned) if cleaned else default
    except Exception:
        return default

# Risk Controls & Portfolio Sizing
STOP_LOSS_PCT: float = safe_float(os.getenv("STOP_LOSS_PCT"), 0.03)     # 3% stop loss
MIN_TRADE_SIZE: int = safe_int(os.getenv("MIN_TRADE_SIZE"), 1)          # Minimum shares
CASH_RESERVE_PCT: float = safe_float(os.getenv("CASH_RESERVE_PCT"), 0.10)  # Retain 10% cash reserve
INITIAL_CAPITAL: float = 1000000.0                                   # Rs. 10,00,000 (Ten Lakhs INR)
MAX_SHORT_HOLD_DAYS: int = 9                                         # Bi-weekly squareoff is on Day 10

# =====================================================================
# Machine Learning Target & Splits
# =====================================================================
TARGET_FORWARD_DAYS: int = int(os.getenv("TARGET_FORWARD_DAYS", "3"))
TARGET_PROFIT_THRESHOLD: float = float(os.getenv("TARGET_PROFIT_THRESHOLD", "0.015")) # 1.5% profit target

# Time-based splitting (No shuffling allowed!)
TRAIN_RATIO: float = 0.70
VAL_RATIO: float = 0.15
TEST_RATIO: float = 0.15
RANDOM_STATE: int = 42

# Decision thresholds for classification
PRED_BUY_THRESHOLD: float = 0.55
PRED_SELL_THRESHOLD: float = 0.45

# =====================================================================
# News Sentiment Keywords & Negations
# =====================================================================
BULLISH_KEYWORDS: list[str] = [
    "PROFIT", "SURGE", "GROWTH", "RECORD", "BEAT",
    "EXPANSION", "DIVIDEND", "PARTNERSHIP", "UPGRADE"
]

BEARISH_KEYWORDS: list[str] = [
    "LOSS", "PLUNGE", "DROP", "FRAUD", "SCRUTINY",
    "RESIGNATION", "PROBE", "DOWNGRADE", "DEFAULT", "LAWSUIT"
]

NEGATION_WORDS: list[str] = [
    "NO", "NOT", "FAILS", "FAILED", "NEVER",
    "WITHOUT", "HARDLY", "LACK", "DON'T", "CANNOT", "WON'T"
]

# Combined Signal Thresholds
NEWS_STRONG_THRESHOLD: int = 2     # Strong positive keyword score >= 2
NEWS_WEAK_THRESHOLD: int = -2      # Strong negative keyword score <= -2
