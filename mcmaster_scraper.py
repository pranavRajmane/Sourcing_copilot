"""
Sourcing Demo — Google search → first link → extract pricing.

Usage:
    python mcmaster_demo.py
"""

import json
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("TINYFISH_API_KEY")
if not API_KEY:
    print("Set TINYFISH_API_KEY in .env")
    sys.exit(1)

GOAL = """\
1. You are on google.com. Type "M5x25F  socket head cap screw (India) " in the search bar and press Enter.
2. Wait for search results to load.
3. Click on the FIRST organic search result link (skip any ads).
4. Wait for that page to fully load.
5. Extract product information from the page. Look for:
   - Product name / description
   - Price (with currency)
   - Seller / supplier name
   - Availability / stock status
   - Material
   - Specifications (thread size, length, etc.)
   - Product URL
   - Any minimum order quantity

   If the page shows multiple products or variants, pick the cheapest one.

   If a cookie banner or popup appears, close it first.

6. Return ONLY this JSON:
{"product_name":"...","price":"...","currency":"...","supplier":"...","availability":"...","material":"...","thread_size":"...","length":"...","url":"...","min_order_qty":"...","source_website":"..."}
"""


def main():
    print("\n  Sourcing — M5x25F  socket head cap screw (India)")
    print("  " + "=" * 55)

    t0 = time.perf_counter()
    result_data = None

    with requests.post(
        "https://agent.tinyfish.ai/v1/automation/run-sse",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "url": "https://duckduckgo.com",
            "goal": GOAL,
        },
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8")
            if not text.startswith("data:"):
                continue
            payload = text[5:].strip()
            if not payload:
                continue

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "STARTED":
                print(f"  [STARTED] run_id={event.get('runId', event.get('run_id', '?'))}")
            elif etype == "STREAMING_URL":
                print(f"  [LIVE]    {event.get('streamingUrl', event.get('streaming_url', ''))}")
            elif etype == "PROGRESS":
                print(f"  [STEP]    {event.get('purpose', '')}")
            elif etype == "HEARTBEAT":
                pass
            elif etype == "COMPLETE":
                print(f"  [DONE]    status={event.get('status', '?')}")
                result_data = event.get("result")
                if isinstance(result_data, str):
                    try:
                        result_data = json.loads(result_data)
                    except json.JSONDecodeError:
                        m = re.search(r"\{.*\}", result_data, re.DOTALL)
                        if m:
                            try:
                                result_data = json.loads(m.group())
                            except json.JSONDecodeError:
                                pass
                if event.get("error"):
                    print(f"  [ERROR]   {event['error']}")
            else:
                print(f"  [{etype}]  {json.dumps(event)[:120]}")

    elapsed = time.perf_counter() - t0

    if not result_data or not isinstance(result_data, dict):
        print(f"\n  FAILED after {elapsed:.1f}s — no result")
        print(f"  Raw: {result_data}")
        sys.exit(1)

    print(f"""
  ============================================================
  SOURCING RESULT
  ============================================================
  Product:      {result_data.get('product_name', '?')}
  Price:        {result_data.get('price', '?')} {result_data.get('currency', '')}
  Supplier:     {result_data.get('supplier', '?')}
  Availability: {result_data.get('availability', '?')}
  Material:     {result_data.get('material', '?')}
  Thread:       {result_data.get('thread_size', '?')}
  Length:       {result_data.get('length', '?')}
  Min Order:    {result_data.get('min_order_qty', '?')}
  Source:       {result_data.get('source_website', '?')}
  URL:          {result_data.get('url', '?')}
  ============================================================
  Done in {elapsed:.1f}s
""")

    with open("sourcing_result.json", "w") as f:
        json.dump(result_data, f, indent=2)
    print("  Saved to sourcing_result.json\n")


if __name__ == "__main__":
    main()