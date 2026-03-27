"""
CAD File Sourcing — Google → free CAD site → download STEP file.

Usage:
    python cad_download.py
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
1. You are on google.com. Type "M5x25F  socket head cap screw STEP file free download site:grabcad.com OR site:3dcontentcentral.com OR site:traceparts.com" in the search bar and press Enter.
2. Wait for search results to load.
3. Look at the results. Click the FIRST result that is from GrabCAD, 3DContentCentral, or TraceParts.

   DO NOT click any McMaster-Carr link. DO NOT go to mcmaster.com.
   SKIP any result from mcmaster.com, amazon.com, or indiamart.com.

4. Wait for the page to load. Close any cookie banners or popups.
5. On the page, find a download button for a STEP (.step or .stp) file.
   - If the site shows a format dropdown, select "STEP" or "STP".
   - If there are multiple parts, pick the one closest to M5x25F  socket head cap screw.
   - If the site requires login to download, DO NOT sign up.
     Return {"downloaded": false, "reason": "login_required", "source_site": "...", "source_url": "..."}.
6. Click the download button.
7. Return ONLY JSON:
{"downloaded": true, "filename": "...", "format": "STEP", "part_description": "M5 x 0.8mm socket head cap screw", "source_site": "name of website", "source_url": "page URL", "download_url": "direct download URL if visible"}
"""


def main():
    print("\n  CAD Download — M5x25F  socket head cap screw STEP file")
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
            "url": "hhttps://duckduckgo.com",
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

    downloaded = result_data.get("downloaded", False)

    if downloaded:
        print(f"""
  ============================================================
  CAD FILE DOWNLOADED
  ============================================================
  File:         {result_data.get('filename', '?')}
  Format:       {result_data.get('format', '?')}
  Part:         {result_data.get('part_description', '?')}
  Source:       {result_data.get('source_site', '?')}
  Page URL:     {result_data.get('source_url', '?')}
  Download URL: {result_data.get('download_url', '?')}
  ============================================================
  Done in {elapsed:.1f}s
""")
    else:
        print(f"""
  ============================================================
  CAD FILE NOT DOWNLOADED
  ============================================================
  Reason:       {result_data.get('reason', '?')}
  Source:       {result_data.get('source_site', '?')}
  Page URL:     {result_data.get('source_url', '?')}
  ============================================================
  Done in {elapsed:.1f}s
""")

    with open("cad_result.json", "w") as f:
        json.dump(result_data, f, indent=2)
    print("  Saved to cad_result.json\n")


if __name__ == "__main__":
    main()