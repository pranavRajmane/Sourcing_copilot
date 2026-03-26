"""
McMaster-Carr Demo — raw SSE endpoint, no SDK nonsense.

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
1. Wait for the page to fully load.
2. Type "m5 0.8mm screw" in the search bar and press Enter.
3. Wait for results. You will see a grid of product categories.
   Click directly on the text "Socket Head Screws".
4. Wait for subcategories. Click directly on the text "Steel Socket Head Screws".
5. Wait for the product table to load.
6. DO NOT click any product. Just READ the table on screen.
   Look at the "M5 × 0.8 mm" section under "Black-Oxide Alloy Steel".
   Find the row with the LOWEST price.
7. Return ONLY JSON:
{"part_number":"...","price_text":"...","length_mm":"...","threading":"...","package_qty":"...","specs_met":"...","material":"Black-Oxide Alloy Steel","thread_size":"M5 x 0.8 mm"}
"""


def main():
    print("\n  McMaster-Carr — cheapest M5 0.8mm socket head cap screw")
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
            "url": "https://www.mcmaster.com",
            "goal": GOAL,
            "browser_profile": "stealth",
            "proxy_config": {"enabled": True, "country_code": "US"},
        },
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8")

            # SSE lines look like: data: {"type":"PROGRESS",...}
            if not text.startswith("data:"):
                continue
            payload = text[5:].strip()
            if not payload:
                continue

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                print(f"  [?] {payload[:100]}")
                continue

            etype = event.get("type", "")

            if etype == "STARTED":
                print(f"  [STARTED] run_id={event.get('runId', event.get('run_id', '?'))}")

            elif etype == "STREAMING_URL":
                url = event.get("streamingUrl", event.get("streaming_url", ""))
                print(f"  [LIVE]    {url}")

            elif etype == "PROGRESS":
                purpose = event.get("purpose", "")
                print(f"  [STEP]    {purpose}")

            elif etype == "HEARTBEAT":
                pass  # ignore

            elif etype == "COMPLETE":
                status = event.get("status", "?")
                print(f"  [DONE]    status={status}")

                result_data = event.get("result")
                if isinstance(result_data, str):
                    # Try parsing JSON from string
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

    # Parse price
    price = 0.0
    pt = str(result_data.get("price_text", ""))
    pm = re.search(r"[\d.]+", pt.replace(",", ""))
    if pm:
        price = float(pm.group())

    pkg = result_data.get("package_qty", "?")
    try:
        per_unit = price / int(str(pkg))
    except (ValueError, ZeroDivisionError):
        per_unit = price

    print(f"""
  ============================================================
  CHEAPEST M5 x 0.8mm SOCKET HEAD CAP SCREW
  ============================================================
  Part Number:  {result_data.get('part_number', '?')}
  Price:        {result_data.get('price_text', '?')}  (pkg of {pkg})
  Per-unit:     ${per_unit:.4f}
  Length:       {result_data.get('length_mm', '?')} mm
  Threading:    {result_data.get('threading', '?')}
  Material:     {result_data.get('material', '?')}
  Thread:       {result_data.get('thread_size', '?')}
  Specs:        {result_data.get('specs_met', '?')}
  ============================================================
  Done in {elapsed:.1f}s
""")

    with open("mcmaster_result.json", "w") as f:
        json.dump(result_data, f, indent=2)
    print("  Saved to mcmaster_result.json\n")


if __name__ == "__main__":
    main()