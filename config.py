"""
Configuration for the sourcing agent.
Loads settings from .env file.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Add it to your .env file or export it in your shell."
        )
    return value


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

TINYFISH_API_KEY: str = _require("TINYFISH_API_KEY")

# ---------------------------------------------------------------------------
# Sourcing settings
# ---------------------------------------------------------------------------

MAX_SUPPLIERS: int = int(os.getenv("MAX_SUPPLIERS", "4"))

# Fallback supplier list (used if Google search returns nothing)
_DEFAULT_SUPPLIER_URLS = (
    "IndiaMART|https://www.indiamart.com,"
    "Amazon India|https://www.amazon.in,"
    "Moglix|https://www.moglix.com,"
    "TradeIndia|https://www.tradeindia.com,"
    "Flipkart|https://www.flipkart.com"
)


def _parse_suppliers(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for entry in raw.split(","):
        entry = entry.strip()
        if "|" in entry:
            name, url = entry.split("|", 1)
            pairs.append((name.strip(), url.strip()))
    return pairs


SUPPLIERS: list[tuple[str, str]] = _parse_suppliers(
    os.getenv("SUPPLIER_URLS", _DEFAULT_SUPPLIER_URLS)
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
