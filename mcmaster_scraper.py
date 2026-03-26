"""
McMaster-Carr one-shot scraper.

TinyFish opens mcmaster.com, searches for the query, reads the search results
page, and extracts the top products.  No retries, no page 2.  One shot.
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
class McmasterPartQuote:
    name: str
    price_usd: float
    part_number: str
    availability: str
    url: str


# ---------------------------------------------------------------------------
# TinyFish goal
# ---------------------------------------------------------------------------


def _build_goal(query: str) -> str:
    return (
        f'You are on mcmaster.com.  Follow these steps EXACTLY:\n'
        f'\n'
        f'1. Type "{query}" into the search bar and press Enter.\n'
        f'2. Wait for the search results page to load completely.\n'
        f'3. If the page shows PRODUCT CATEGORIES or subcategories instead of\n'
        f'   specific parts with prices, click the single most relevant\n'
        f'   category to reach a page with actual product listings and prices.\n'
        f'   Only click ONE category — do not drill deeper.\n'
        f'4. Once you see a page with specific parts that have prices and part\n'
        f'   numbers, extract up to 5 products.  For each product extract:\n'
        f'   - product name / description\n'
        f'   - price (the per-unit or "each" price, e.g. "$4.72")\n'
        f'   - McMaster part number (e.g. "91251A197")\n'
        f'   - availability text (e.g. "In Stock", ships date, etc.)\n'
        f'   - product URL (the link href, or construct it as\n'
        f'     https://www.mcmaster.com/<part_number>)\n'
        f'\n'
        f'RULES:\n'
        f'- Do NOT click on any individual product detail page.\n'
        f'- Do NOT go to page 2.\n'
        f'- Do NOT navigate away from the results after the one allowed\n'
        f'  category click.\n'
        f'- Extract ONLY what is visible on screen.\n'
        f'- Maximum 5 products.\n'
        f'- If prices show quantity breaks, use the single-unit / "Each" price.\n'
        f'\n'
        f'Return ONLY this JSON (no markdown, no explanation):\n'
        f'{{"results": [\n'
        f'  {{"name": "...", "price_text": "...", "part_number": "...", '
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
    text = text.replace("$", "").replace(",", "")
    # Strip per-unit suffixes
    text = re.sub(r"(?i)\s*/?\s*(each|ea|per\s+unit|per\s+piece)\.?", "", text)
    text = text.strip()
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_mcmaster(query: str) -> list[McmasterPartQuote]:
    """
    Search mcmaster.com for the query.  Returns list of McmasterPartQuote.
    Blocking call (no async needed — single TinyFish session).
    """
    logger.info("Searching McMaster-Carr for: %s", query)

    goal = _build_goal(query)
    data = _run_tinyfish("https://www.mcmaster.com", goal)

    if data is None:
        logger.error("TinyFish returned nothing.")
        return []

    raw_results = data.get("results", [])
    if not raw_results:
        logger.error("No results in TinyFish response: %s", data)
        return []

    quotes: list[McmasterPartQuote] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue

        price = _parse_price(item.get("price_text") or item.get("price"))
        if price is None:
            logger.warning("Skipping (no price): %s", item.get("name", "?"))
            continue

        name = str(item.get("name") or "Unknown")
        part_number = str(item.get("part_number") or "N/A")
        availability = str(item.get("availability") or "Unknown")
        url = str(item.get("url") or f"https://www.mcmaster.com/{part_number}")

        quotes.append(McmasterPartQuote(
            name=name,
            price_usd=price,
            part_number=part_number,
            availability=availability,
            url=url,
        ))

    return quotes
