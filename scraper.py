"""
Robu.in one-shot scraper.

TinyFish opens robu.in, searches for the query, reads the search results
page, and extracts the top products.  No clicking into products, no page 2,
no retries.  One shot.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from tinyfish import TinyFish

import config  # noqa: F401 — loads .env

logger = logging.getLogger(__name__)

_client = TinyFish()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class PartQuote:
    name: str
    price: float
    currency: str
    lead_time_days: int | None
    url: str
    sku: str


# ---------------------------------------------------------------------------
# TinyFish goal
# ---------------------------------------------------------------------------


def _build_goal(query: str) -> str:
    return (
        f'You are on robu.in.  Follow these steps EXACTLY:\n'
        f'\n'
        f'1. Type "{query}" into the search bar and press Enter.\n'
        f'2. Wait for the search results page to load.\n'
        f'3. Read the FIRST PAGE of results.  For each product visible '
        f'(up to 5), extract:\n'
        f'   - product name\n'
        f'   - price (exact text, e.g. "₹299.00")\n'
        f'   - SKU or product code (if visible)\n'
        f'   - availability text (e.g. "In Stock", "Out of Stock")\n'
        f'   - product URL (the link href)\n'
        f'\n'
        f'RULES:\n'
        f'- Do NOT click on any product.\n'
        f'- Do NOT go to page 2.\n'
        f'- Do NOT navigate away from the search results page.\n'
        f'- Extract ONLY what is visible on screen.\n'
        f'- Maximum 5 products.\n'
        f'\n'
        f'Return ONLY this JSON (no markdown):\n'
        f'{{"results": [\n'
        f'  {{"name": "...", "price_text": "...", "sku": "...", '
        f'"availability": "...", "url": "..."}},\n'
        f'  ...\n'
        f']}}\n'
        f'\n'
        f'Respond NOW after reading the results page.'
    )


# ---------------------------------------------------------------------------
# TinyFish SDK runner
# ---------------------------------------------------------------------------


def _get_event_type(event) -> str:
    return type(event).__name__.replace("Event", "").upper()


def _extract_json(text: str) -> Optional[dict]:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _run_tinyfish(url: str, goal: str) -> Optional[dict]:
    """Blocking call — run TinyFish, return parsed JSON or None."""
    try:
        with _client.agent.stream(url=url, goal=goal) as stream:
            for event in stream:
                etype = _get_event_type(event)

                if etype == "PROGRESS":
                    msg = getattr(event, "message", getattr(event, "description", ""))
                    if msg:
                        logger.info("[TinyFish] %s", msg)

                elif "STREAM" in etype:
                    live = getattr(event, "streaming_url", None) or getattr(event, "url", None)
                    if live:
                        logger.info("[TinyFish] Live: %s", live)

                elif etype in ("ERROR", "FAILED"):
                    err = getattr(event, "error", getattr(event, "message", "unknown"))
                    logger.error("[TinyFish] ERROR: %s", err)
                    return None

                elif etype == "COMPLETE":
                    raw = (
                        getattr(event, "result_json", None)
                        or getattr(event, "resultJson", None)
                        or getattr(event, "result", None)
                        or getattr(event, "data", None)
                        or getattr(event, "output", None)
                        or getattr(event, "text", None)
                    )
                    if not raw:
                        logger.error("[TinyFish] COMPLETE but empty payload")
                        return None
                    if isinstance(raw, dict):
                        return raw
                    parsed = _extract_json(str(raw))
                    if parsed:
                        return parsed
                    logger.error("[TinyFish] Could not parse: %.300s", str(raw))
                    return None

    except Exception as exc:
        logger.error("[TinyFish] %s", exc, exc_info=True)
        return None

    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_price(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw)
    text = re.sub(r"[₹$€£]", "", text)
    text = text.replace("Rs.", "").replace("Rs", "").replace("INR", "")
    text = text.replace(",", "").strip()
    # Range → take low end
    if "-" in text or "\u2013" in text:
        text = re.split(r"[-\u2013]", text)[0].strip()
    # Strip trailing words
    text = re.sub(r"[a-zA-Z/]+.*$", "", text).strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        pass
    match = re.search(r"[\d]+\.?\d*", str(raw))
    return float(match.group()) if match else None


def _parse_lead_time(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).lower()
    if any(kw in text for kw in ("in stock", "same day", "ships today", "ready", "available")):
        return 1
    if any(kw in text for kw in ("out of stock", "backorder", "unavailable")):
        return 999
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_robu(query: str) -> list[PartQuote]:
    """
    Search robu.in for the query.  Returns list of PartQuote.
    Blocking call (no async needed — single TinyFish session).
    """
    logger.info("Searching robu.in for: %s", query)

    goal = _build_goal(query)
    data = _run_tinyfish("https://robu.in", goal)

    if data is None:
        logger.error("TinyFish returned nothing.")
        return []

    raw_results = data.get("results", [])
    if not raw_results:
        logger.error("No results in TinyFish response: %s", data)
        return []

    quotes: list[PartQuote] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue

        price = _parse_price(item.get("price_text") or item.get("price"))
        if price is None:
            logger.warning("Skipping (no price): %s", item.get("name", "?"))
            continue

        lead = _parse_lead_time(item.get("availability"))
        name = str(item.get("name") or "Unknown")
        sku = str(item.get("sku") or "N/A")
        url = str(item.get("url") or "")

        quotes.append(PartQuote(
            name=name,
            price=price,
            currency="INR",
            lead_time_days=lead,
            url=url,
            sku=sku,
        ))

    return quotes
