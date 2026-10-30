"""
Configuration module for the autonomous trading bot (Manthan 2026).
Loads environment variables and defines constants, paths, trading costs,
risk controls, news keywords, and ML hyperparameters with strict range validation.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)


# =====================================================================
# Strict Type Parsing & Range Checking Utilities (Fail Loudly)
# =====================================================================
def parse_float(
    name: str,
    val: Any,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
) -> float:
    """Parses a float with support for negatives and exponents, raising on failure or bound violation."""
    if val is None or str(val).strip() == "":
        parsed = default
    else:
        try:
            parsed = float(val)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid float for config setting '{name}': {val!r}") from exc

    if min_val is not None:
        if min_inclusive and parsed < min_val:
            raise ValueError(f"Config '{name}'={parsed} violates lower bound >= {min_val}")
        if not min_inclusive and parsed <= min_val:
            raise ValueError(f"Config '{name}'={parsed} violates lower bound > {min_val}")

    if max_val is not None:
        if max_inclusive and parsed > max_val:
            raise ValueError(f"Config '{name}'={parsed} violates upper bound <= {max_val}")
        if not max_inclusive and parsed >= max_val:
            raise ValueError(f"Config '{name}'={parsed} violates upper bound < {max_val}")

    return parsed


def parse_int(
    name: str,
    val: Any,
    default: int,
    min_val: int | None = None,
    max_val: int | None = None,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
) -> int:
    """Parses an integer with support for negatives and exponents, raising on failure or bound violation."""
    if val is None or str(val).strip() == "":
        parsed = default
    else:
        try:
            parsed = int(val)
        except (ValueError, TypeError):
            try:
                f_val = float(val)
                if f_val.is_integer():
                    parsed = int(f_val)
                else:
                    raise ValueError(f"Config '{name}' must be an integer, got {val!r}")
            except Exception as exc:
                raise ValueError(f"Invalid integer for config setting '{name}': {val!r}") from exc

    if min_val is not None:
        if min_inclusive and parsed < min_val:
            raise ValueError(f"Config '{name}'={parsed} violates lower bound >= {min_val}")
        if not min_inclusive and parsed <= min_val:
            raise ValueError(f"Config '{name}'={parsed} violates lower bound > {min_val}")

    if max_val is not None:
        if max_inclusive and parsed > max_val:
            raise ValueError(f"Config '{name}'={parsed} violates upper bound <= {max_val}")
        if not max_inclusive and parsed >= max_val:
            raise ValueError(f"Config '{name}'={parsed} violates upper bound < {max_val}")

    return parsed


# =====================================================================
# Server & API Configuration
# =====================================================================
SERVER_IP: str = os.getenv("SERVER_IP", "192.168.65.157").strip()
API_PORT: int = parse_int("API_PORT", os.getenv("API_PORT"), 3002, min_val=1, max_val=65535)
BASE_URL: str = f"http://{SERVER_IP}:{API_PORT}"

# Raise loudly at startup if BOT_ACCESS_TOKEN is missing or empty
BOT_ACCESS_TOKEN: str = os.getenv("BOT_ACCESS_TOKEN", "").strip()
if not BOT_ACCESS_TOKEN:
    raise ValueError("BOT_ACCESS_TOKEN is empty! Set a valid JWT access token in .env or environment.")

AUTH_HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {BOT_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

STOCKS_API_URL: str = f"{BASE_URL}/api/v1/stocks"
HISTORY_API_URL_TEMPLATE: str = f"{BASE_URL}/api/v1/stocks/{{ticker}}/history"
STAGE_API_URL: str = f"{BASE_URL}/api/v1/stage"
SIMULATION_CLOCK_URL: str = f"{BASE_URL}/api/v1/simulation/clock"
HEARTBEAT_API_URL: str = f"{BASE_URL}/api/v1/bot/heartbeat"
PORTFOLIO_API_URL: str = f"{BASE_URL}/api/v1/portfolio"
PORTFOLIO_CASH_URL: str = f"{BASE_URL}/api/v1/portfolio/cash"
ORDERS_API_URL: str = f"{BASE_URL}/api/v1/orders"

# =====================================================================
# Kafka Stream Configuration
# =====================================================================
TEAM_USERNAME: str = os.getenv("TEAM_USERNAME", "mn2612").strip()
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", f"{SERVER_IP}:9094").strip()
KAFKA_NEWS_TOPIC: str = os.getenv("KAFKA_NEWS_TOPIC", "market.news").strip()
KAFKA_TICKS_TOPIC: str = os.getenv("KAFKA_TICKS_TOPIC", "market.ticks").strip()
KAFKA_GROUP_COLLECTOR: str = f"group-{TEAM_USERNAME}"

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
BROKERAGE_FEE: float = parse_float("BROKERAGE_FEE", os.getenv("BROKERAGE_FEE"), 20.0, min_val=0.0, max_val=1000.0)
DP_CHARGE: float = parse_float("DP_CHARGE", os.getenv("DP_CHARGE"), 15.34, min_val=0.0, max_val=1000.0)
STCG_RATE: float = 0.15          # 15% Short Term Capital Gains (<=365d)
LTCG_RATE: float = 0.10          # 10% Long Term Capital Gains (>365d)
LTCG_EXEMPTION: float = 100000.0 # First Rs. 1,00,000 exempt under Sec 112A
INITIAL_CAPITAL: float = 1000000.0

# =====================================================================
# Barrier & Exit Parameters (Single Source of Truth)
# =====================================================================
BARRIER_UP_ATR: float = parse_float("BARRIER_UP_ATR", os.getenv("BARRIER_UP_ATR"), 2.0, min_val=0.1, max_val=20.0)
BARRIER_DOWN_ATR: float = parse_float("BARRIER_DOWN_ATR", os.getenv("BARRIER_DOWN_ATR"), 1.5, min_val=0.1, max_val=20.0)
HORIZON_DAYS: int = parse_int("HORIZON_DAYS", os.getenv("HORIZON_DAYS", os.getenv("TARGET_FORWARD_DAYS")), 15, min_val=1, max_val=100)
ATR_PERIOD: int = parse_int("ATR_PERIOD", os.getenv("ATR_PERIOD"), 14, min_val=2, max_val=100)
TARGET_FORWARD_DAYS: int = HORIZON_DAYS  # Alias for backward compatibility

# Risk & Portfolio Controls
STOP_LOSS_PCT: float = parse_float("STOP_LOSS_PCT", os.getenv("STOP_LOSS_PCT"), 0.06, min_val=0.0, max_val=0.5, min_inclusive=False, max_inclusive=False)
TRAILING_STOP_PCT: float = parse_float("TRAILING_STOP_PCT", os.getenv("TRAILING_STOP_PCT"), 0.08, min_val=0.0, max_val=0.5, min_inclusive=False, max_inclusive=False)
MIN_TRADE_SIZE: int = parse_int("MIN_TRADE_SIZE", os.getenv("MIN_TRADE_SIZE"), 1, min_val=1, max_val=100000)
CASH_RESERVE_PCT: float = parse_float("CASH_RESERVE_PCT", os.getenv("CASH_RESERVE_PCT"), 0.15, min_val=0.0, max_val=0.5, min_inclusive=True, max_inclusive=False)
MAX_SHORT_HOLD_DAYS: int = parse_int("MAX_SHORT_HOLD_DAYS", os.getenv("MAX_SHORT_HOLD_DAYS"), 9, min_val=1, max_val=30)
ORDER_TIMEOUT_SEC: float = parse_float("ORDER_TIMEOUT_SEC", os.getenv("ORDER_TIMEOUT_SEC"), 5.0, min_val=0.1, max_val=60.0)
MAX_CONCURRENT_POSITIONS: int = parse_int("MAX_CONCURRENT_POSITIONS", os.getenv("MAX_CONCURRENT_POSITIONS"), 5, min_val=1, max_val=20)
MAX_POSITION_PCT: float = 0.17  # 4 x 21.25% = 85.0%   # Maximum 22.0% equity per position (4 x 22.0% = 88.0% max market allocation, 12% cash reserve)

# =====================================================================
# Machine Learning Splits & Decision Thresholds
# =====================================================================
TRAIN_RATIO: float = 0.70
VAL_RATIO: float = 0.15
TEST_RATIO: float = 0.15
RANDOM_STATE: int = 42

PRED_BUY_THRESHOLD: float = parse_float("PRED_BUY_THRESHOLD", os.getenv("PRED_BUY_THRESHOLD"), 0.40, min_val=0.1, max_val=1.0, min_inclusive=True, max_inclusive=False)
PRED_SELL_THRESHOLD: float = parse_float("PRED_SELL_THRESHOLD", os.getenv("PRED_SELL_THRESHOLD"), 0.35, min_val=0.0, max_val=0.5, min_inclusive=True, max_inclusive=False)
ENABLE_SHORT_SELLING: bool = os.getenv("ENABLE_SHORT_SELLING", "False").lower() in ("true", "1", "yes")

# =====================================================================
# News Sentiment Keywords & Thresholds
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

NEWS_STRONG_THRESHOLD: int = 2
NEWS_WEAK_THRESHOLD: int = -2


# =====================================================================
# Effective Configuration Inspector
# =====================================================================
def get_effective_config() -> dict[str, Any]:
    """Returns effective runtime configuration dictionary."""
    return {
        "SERVER_IP": SERVER_IP,
        "API_PORT": API_PORT,
        "BASE_URL": BASE_URL,
        "BOT_ACCESS_TOKEN_SET": bool(BOT_ACCESS_TOKEN),
        "TEAM_USERNAME": TEAM_USERNAME,
        "KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP_SERVERS,
        "BROKERAGE_FEE": BROKERAGE_FEE,
        "DP_CHARGE": DP_CHARGE,
        "STCG_RATE": STCG_RATE,
        "LTCG_RATE": LTCG_RATE,
        "LTCG_EXEMPTION": LTCG_EXEMPTION,
        "INITIAL_CAPITAL": INITIAL_CAPITAL,
        "BARRIER_UP_ATR": BARRIER_UP_ATR,
        "BARRIER_DOWN_ATR": BARRIER_DOWN_ATR,
        "HORIZON_DAYS": HORIZON_DAYS,
        "ATR_PERIOD": ATR_PERIOD,
        "STOP_LOSS_PCT": STOP_LOSS_PCT,
        "TRAILING_STOP_PCT": TRAILING_STOP_PCT,
        "MIN_TRADE_SIZE": MIN_TRADE_SIZE,
        "CASH_RESERVE_PCT": CASH_RESERVE_PCT,
        "MAX_CONCURRENT_POSITIONS": MAX_CONCURRENT_POSITIONS,
        "MAX_POSITION_PCT": MAX_POSITION_PCT,
        "PRED_BUY_THRESHOLD": PRED_BUY_THRESHOLD,
        "PRED_SELL_THRESHOLD": PRED_SELL_THRESHOLD,
        "ENABLE_SHORT_SELLING": ENABLE_SHORT_SELLING,
    }


def print_effective_config() -> None:
    """Prints effective configuration parameters."""
    print("=" * 70)
    print(" MANTHAN 2026: EFFECTIVE CONFIGURATION (after .env overrides)")
    print("=" * 70)
    for k, v in get_effective_config().items():
        print(f"  {k:<26} = {v}")
    print("=" * 70)


# Print effective config at startup/import
print_effective_config()
