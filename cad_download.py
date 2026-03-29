"""
CAD Download — LOCAL browser via Playwright.

Setup:
    pip install --upgrade playwright python-dotenv
    playwright install chromium

Add to .env:
    THREEDFIND_EMAIL=your@email.com
    THREEDFIND_PASSWORD=yourpassword

Usage:
    python cad_download.py "ISO 4017 M8"
    python cad_download.py "ISO 4762 M5"
    python cad_download.py "DIN 933 M10x30"
    python cad_download.py                  # prompts interactively

Session persistence:
    After first login, cookies saved to auth_state.json.
    Subsequent runs skip login. Delete auth_state.json to force fresh login.
"""

import os
import sys
import time
import glob
import json
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.environ.get("THREEDFIND_EMAIL", "")
PASS = os.environ.get("THREEDFIND_PASSWORD", "")

if not EMAIL or not PASS:
    print("Add THREEDFIND_EMAIL and THREEDFIND_PASSWORD to .env")
    sys.exit(1)

DOWNLOAD_DIR = os.path.join(os.getcwd(), "cad_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

AUTH_STATE_FILE = os.path.join(os.getcwd(), "auth_state.json")

DEBUG = True
DEBUG_DIR = os.path.join(os.getcwd(), "debug_screenshots")
if DEBUG:
    os.makedirs(DEBUG_DIR, exist_ok=True)


def get_search_query():
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    env_query = os.environ.get("CAD_SEARCH_QUERY", "")
    if env_query:
        return env_query
    print("\n  No search query provided.")
    print("  Examples: ISO 4017 M8, ISO 4762 M5, DIN 933 M10x30\n")
    query = input("  Enter search query: ").strip()
    if not query:
        print("  No query entered. Exiting.")
        sys.exit(1)
    return query


def debug_screenshot(page, name):
    if not DEBUG:
        return
    path = os.path.join(DEBUG_DIR, f"{name}.png")
    try:
        page.screenshot(path=path)
        print(f"    [DEBUG] Screenshot: {path}")
    except Exception as e:
        print(f"    [DEBUG] Screenshot failed: {e}")


def safe_click(page, selectors, timeout=3000):
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout)
            el.click()
            print(f"    Clicked: {sel}")
            return sel
        except Exception:
            continue
    return None


def click_part_card(page, search_query):
    """
    Click the first PART card on the search results page.
    Skips: manufacturer cards, header/search bar, nav elements.
    
    Key fix: checks bounding box y > 80 to avoid clicking the search bar.
    """
    page.wait_for_timeout(2000)

    # Extract keywords from query, skipping standard prefixes
    keywords = []
    for word in search_query.split():
        w = word.strip().upper()
        if w in ("ISO", "DIN", "EN", "BS", "ANSI", "ASME"):
            continue
        keywords.append(w)

    skip_texts = [
        "ISO-Chemie", "Register", "Login", "Filter", "Browse",
        "Search in", "Not found?", "Request manufacturer",
        "Search tips", "No suggestions",
    ]

    if not keywords:
        print("    [!] No keywords extracted from query.")
        return False

    primary_keyword = keywords[0]
    print(f"    Looking for parts matching '{primary_keyword}'...")

    try:
        matches = page.locator(f"text={primary_keyword}").all()
        print(f"    Found {len(matches)} elements with '{primary_keyword}'")

        for m in matches:
            try:
                text = (m.text_content() or "").strip()

                # Skip too long (container div) or too short
                if len(text) > 300 or len(text) < 5:
                    continue

                # Skip known non-part elements
                if any(skip in text for skip in skip_texts):
                    continue

                # CRITICAL: Skip elements in the header/search bar area
                box = m.bounding_box()
                if not box or box["y"] < 80:
                    continue

                m.click()
                print(f"    Clicked: {text[:80]}")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"    Strategy 1 failed: {e}")

    # Strategy 2: Find part-like links with y > 80
    try:
        all_links = page.locator("a[href]").all()
        for link in all_links:
            try:
                text = (link.text_content() or "").strip()
                if len(text) < 5 or len(text) > 300:
                    continue
                if any(skip in text for skip in skip_texts):
                    continue

                box = link.bounding_box()
                if not box or box["y"] < 80:
                    continue

                text_upper = text.upper()
                if any(kw in text_upper for kw in keywords):
                    link.click()
                    print(f"    Clicked link: {text[:80]}")
                    return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def do_login(page):
    """Handle the full-page SSO login."""
    print("    Performing login on SSO page...")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2000)

    email_input = None
    try:
        email_input = page.locator("input").first
        if not email_input.is_visible(timeout=3000):
            email_input = None
    except Exception:
        pass

    if not email_input:
        for sel in [
            "input[name*='email']", "input[id*='email']",
            "input[type='email']", "input[type='text']",
            "input:not([type='hidden']):not([type='password'])",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    email_input = loc
                    break
            except Exception:
                continue

    if not email_input:
        debug_screenshot(page, "login_no_email")
        print("    [!] Could not find email input.")
        return False

    email_input.click()
    page.wait_for_timeout(300)
    email_input.fill(EMAIL)
    print(f"    Entered email: {EMAIL}")

    safe_click(page, [
        "text=Continue to Login", "button:has-text('Continue')",
        "text=Continue", "button[type='submit']",
    ], timeout=5000)

    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle", timeout=10000)
    page.wait_for_timeout(1000)

    pass_input = None
    for sel in ["input[type='password']", "input[name='password']"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                pass_input = loc
                break
        except Exception:
            continue

    if not pass_input:
        debug_screenshot(page, "login_no_password")
        print("    [!] Could not find password input.")
        return False

    pass_input.click()
    page.wait_for_timeout(300)
    pass_input.fill(PASS)
    print("    Entered password.")

    safe_click(page, [
        "text=Login", "text=Log in",
        "text=Sign in", "button[type='submit']",
    ], timeout=5000)

    print("    Waiting for login to complete...")
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)
    debug_screenshot(page, "login_complete")
    print(f"    Post-login URL: {page.url}")
    return True


def select_step_format(page):
    """Handle the CAD format selection modal."""
    print("    Handling format selection modal...")
    page.wait_for_timeout(1000)

    try:
        if not page.locator("text=CAD format selection").first.is_visible(timeout=5000):
            print("    [!] Format modal not visible.")
            return False
        print("    Format modal is open.")
    except Exception:
        print("    [!] Format modal not found.")
        return False

    # Check if STEP already selected
    step_selected = False
    try:
        your_sel = page.locator("text=Your selection").first
        if your_sel.is_visible(timeout=2000):
            parent = your_sel.locator("xpath=ancestor::div[1] | xpath=..")
            if "STEP" in (parent.text_content() or "").upper():
                step_selected = True
                print("    STEP already selected.")
    except Exception:
        pass

    if not step_selected:
        for fmt in ["STEP AP203", "STEP AP214", "STEP AP242"]:
            try:
                opt = page.locator(f"text={fmt}").first
                if opt.is_visible(timeout=2000):
                    opt.click()
                    print(f"    Selected {fmt}.")
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue

    # Ensure "Download" radio is selected (not "E-mail")
    try:
        # Be careful not to click a "Download" button — only the radio
        radios = page.locator("text=Download").all()
        for r in radios:
            try:
                parent_text = r.evaluate("el => el.parentElement?.textContent || ''")
                if "E-mail" in parent_text:
                    r.click()
                    print("    Ensured 'Download' radio selected.")
                    break
            except Exception:
                continue
    except Exception:
        pass

    debug_screenshot(page, "format_ready")
    return True


def has_saved_session():
    if not os.path.exists(AUTH_STATE_FILE):
        return False
    try:
        with open(AUTH_STATE_FILE, "r") as f:
            data = json.load(f)
        return len(data.get("cookies", [])) > 0
    except Exception:
        return False


def save_session(context):
    try:
        context.storage_state(path=AUTH_STATE_FILE)
        print(f"    Session saved to {AUTH_STATE_FILE}")
    except Exception as e:
        print(f"    [!] Could not save session: {e}")


def main():
    search_query = get_search_query()
    search_url_query = urllib.parse.quote_plus(search_query)
    search_url = f"https://www.3dfindit.com/en/search/?q={search_url_query}"

    print(f"\n  CAD Download — 3DFindIt")
    print(f"  Search:    {search_query}")
    print(f"  Login:     {EMAIL}")
    print(f"  Downloads: {DOWNLOAD_DIR}")
    if has_saved_session():
        print(f"  Session:   Reusing saved session")
    else:
        print(f"  Session:   Fresh login required")
    print("  " + "=" * 55)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n  Run: pip install --upgrade playwright && playwright install chromium")
        sys.exit(1)

    t0 = time.time()

    with sync_playwright() as p:
        print("  [0] Launching Chrome...")
        try:
            browser = p.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as e:
            print(f"    System Chrome failed ({e}). Falling back to Chromium...")
            try:
                browser = p.chromium.launch(headless=False, args=["--start-maximized"])
            except Exception as e2:
                print(f"\n  Chromium launch failed: {e2}")
                sys.exit(1)

        try:
            ctx_opts = {"accept_downloads": True, "no_viewport": True}
            if has_saved_session():
                ctx_opts["storage_state"] = AUTH_STATE_FILE
            context = browser.new_context(**ctx_opts)
            page = context.new_page()
            _run_automation(page, context, t0, search_query, search_url)
        except KeyboardInterrupt:
            print("\n  Interrupted by user.")
        except Exception as e:
            print(f"\n  Error: {e}")
            print(f"  Current page: {page.url}")
            debug_screenshot(page, "crash")
            input("  Press Enter to close browser...")
        finally:
            browser.close()


def _run_automation(page, context, t0, search_query, search_url):
    # =========================================================
    # Step 1: Search
    # =========================================================
    print(f"  [1] Searching for '{search_query}'...")
    page.goto(search_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=15000)
    debug_screenshot(page, "01_search_loaded")

    # =========================================================
    # Step 2: Cookie banner
    # =========================================================
    print("  [2] Handling cookies...")
    safe_click(page, [
        "text=Accept All", "text=Accept all",
        "button:has-text('Accept')", "text=Allow all",
    ], timeout=5000)
    page.wait_for_timeout(1000)

    # =========================================================
    # Step 3: Click a PART card
    # =========================================================
    print("  [3] Clicking a part result...")
    if not click_part_card(page, search_query):
        debug_screenshot(page, "03_no_part_found")
        raise Exception(f"Could not find any part for '{search_query}'.")

    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    debug_screenshot(page, "03_part_page")

    part_page_url = page.url
    print(f"    Part page: {part_page_url}")

    # Verify we landed on a part detail page (not still on search results)
    if "/search/" in page.url:
        print("    [!] Still on search page. Clicked wrong element. Retrying...")
        page.wait_for_timeout(1000)
        # Dismiss any popups that appeared
        page.mouse.click(10, 400)
        page.wait_for_timeout(1000)
        if not click_part_card(page, search_query):
            debug_screenshot(page, "03_retry_failed")
            raise Exception("Could not click a part card (retry failed).")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        part_page_url = page.url
        debug_screenshot(page, "03_part_page_retry")

    print("    Waiting for 3D viewer...")
    page.wait_for_timeout(5000)

    # =========================================================
    # Step 4: Click CAD button
    # =========================================================
    print("  [4] Clicking CAD button...")
    cad_clicked = safe_click(page, [
        "button:has-text('CAD')", "a:has-text('CAD')",
        "text=CAD (1)", "text=CAD (",
    ], timeout=8000)

    if not cad_clicked:
        page.evaluate("window.scrollBy(0, 300)")
        page.wait_for_timeout(2000)
        cad_clicked = safe_click(page, ["button:has-text('CAD')", "text=CAD"], timeout=5000)

    if not cad_clicked:
        debug_screenshot(page, "04_no_cad_button")
        raise Exception("Could not find CAD button.")

    page.wait_for_timeout(3000)
    debug_screenshot(page, "04_after_cad_click")

    # =========================================================
    # Step 5: Handle login gate if it appears
    # =========================================================
    print("  [5] Checking if login is required...")

    login_gate_visible = False
    try:
        for indicator in ["Sign up to access", "New to 3Dfindit"]:
            if page.locator(f"text={indicator}").first.is_visible(timeout=2000):
                login_gate_visible = True
                print(f"    Login gate detected ('{indicator}')")
                break
    except Exception:
        pass

    if login_gate_visible:
        if os.path.exists(AUTH_STATE_FILE):
            os.remove(AUTH_STATE_FILE)
            print("    Removed stale auth_state.json")

        print("    Clicking 'Log in' in gate modal...")
        clicked = False
        try:
            elements = page.locator("text=Log in").all()
            for el in elements:
                try:
                    box = el.bounding_box()
                    if box and box["y"] > 100:
                        el.click()
                        clicked = True
                        break
                except Exception:
                    continue
        except Exception:
            pass
        if not clicked:
            safe_click(page, ["button:has-text('Log in')"], timeout=3000)

        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(1000)

        login_success = do_login(page)

        if login_success:
            save_session(context)
            print("  [6] Post-login navigation...")

            if "digitaltwin" not in page.url and "detail" not in page.url:
                print("    Navigating back to part page...")
                page.goto(part_page_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=15000)
                page.wait_for_timeout(5000)
            else:
                page.wait_for_timeout(3000)

            debug_screenshot(page, "06_back_on_part")

            print("    Clicking CAD button again...")
            page.wait_for_timeout(2000)
            safe_click(page, [
                "button:has-text('CAD')", "a:has-text('CAD')",
                "text=CAD (1)", "text=CAD (",
            ], timeout=8000)
            page.wait_for_timeout(3000)
        else:
            print("    [!] Login failed.")
    else:
        print("    No login gate — already logged in.")
        save_session(context)

    # =========================================================
    # Step 6.5: Dismiss popups if format modal didn't appear
    # =========================================================
    print("  [6.5] Checking for format modal or popups...")

    format_modal_visible = False
    try:
        format_modal_visible = page.locator("text=CAD format selection").first.is_visible(timeout=2000)
    except Exception:
        pass

    if not format_modal_visible:
        print("    Format modal not showing. Dismissing popups...")

        # Close Recommendations popup
        try:
            rec = page.locator("text=Recommendations").first
            if rec.is_visible(timeout=1000):
                # Find nearby close button
                close_btns = page.locator("button").all()
                for btn in close_btns:
                    try:
                        btn_text = btn.text_content() or ""
                        box = btn.bounding_box()
                        rec_box = rec.bounding_box()
                        if box and rec_box:
                            # Close button should be near the Recommendations title
                            if abs(box["y"] - rec_box["y"]) < 40 and box["x"] > rec_box["x"]:
                                btn.click()
                                print("    Closed Recommendations popup")
                                page.wait_for_timeout(500)
                                break
                    except Exception:
                        continue
        except Exception:
            pass

        # Click neutral area to dismiss overlays
        page.mouse.click(10, 400)
        page.wait_for_timeout(1000)

        # Re-click CAD
        print("    Re-clicking CAD button...")
        safe_click(page, [
            "button:has-text('CAD')", "a:has-text('CAD')",
            "text=CAD (1)", "text=CAD (",
        ], timeout=8000)
        page.wait_for_timeout(3000)
        debug_screenshot(page, "065_after_reclick")

    # =========================================================
    # Step 7: Format selection modal
    # =========================================================
    print("  [7] Handling format selection...")
    page.wait_for_timeout(2000)

    select_step_format(page)
    debug_screenshot(page, "07_format_ready")

    # =========================================================
    # Step 8: Click "Create CAD-files"
    # =========================================================
    print("  [8] Clicking 'Create CAD-files'...")

    safe_click(page, [
        "text=Create CAD-files",
        "text=Create CAD",
        "button:has-text('Create')",
    ], timeout=8000)

    print("    Waiting for CAD file generation (30-60s)...")

    # =========================================================
    # Step 9: Wait for pink "Download" button and click it
    # =========================================================
    print("  [9] Waiting for Download button...")

    downloaded_file = None

    # Poll for the pink Download button to appear
    download_btn = None
    for attempt in range(30):  # up to 60 seconds
        try:
            btns = page.locator("text=Download").all()
            for btn in btns:
                try:
                    if not btn.is_visible(timeout=500):
                        continue

                    # Skip the radio button in format selection
                    parent_text = btn.evaluate("el => el.parentElement?.textContent || ''")
                    if "E-mail" in parent_text and "How would you like" in parent_text:
                        continue

                    # Check if it looks like a button (not a label)
                    tag = btn.evaluate("el => el.tagName").lower()
                    classes = (btn.evaluate("el => el.className") or "").lower()
                    parent_tag = btn.evaluate("el => el.parentElement?.tagName || ''").lower()

                    is_button = (
                        tag in ("button", "a")
                        or parent_tag in ("button", "a")
                        or "btn" in classes
                        or "button" in classes
                        or "download" in classes
                    )

                    if is_button:
                        download_btn = btn
                        break
                except Exception:
                    continue

            if download_btn:
                break
        except Exception:
            pass

        if attempt % 5 == 0 and attempt > 0:
            print(f"    Still waiting... ({attempt * 2}s)")

        page.wait_for_timeout(2000)

    if download_btn:
        print("    Download button found! Clicking...")
        debug_screenshot(page, "09_download_btn")

        try:
            with page.expect_download(timeout=30000) as dl_info:
                download_btn.click()

            download = dl_info.value
            filename = download.suggested_filename or f"{search_query.replace(' ', '_')}.step"
            save_path = os.path.join(DOWNLOAD_DIR, filename)
            download.save_as(save_path)
            downloaded_file = save_path
        except Exception as e:
            print(f"    expect_download failed: {e}")
            page.wait_for_timeout(5000)
    else:
        print("    [!] Download button did not appear after 60s.")
        debug_screenshot(page, "09_no_download_btn")

    # Fallback: check downloads dir
    if not downloaded_file:
        page.wait_for_timeout(3000)
        all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
        if all_files:
            latest = max(all_files, key=os.path.getctime)
            if time.time() - os.path.getctime(latest) < 120:
                downloaded_file = latest

    # =========================================================
    # Result
    # =========================================================
    elapsed = time.time() - t0

    if downloaded_file and os.path.exists(downloaded_file):
        size = os.path.getsize(downloaded_file)
        print(f"""
  ============================================================
  CAD FILE SAVED!
  ============================================================
  Query:    {search_query}
  File:     {downloaded_file}
  Size:     {size:,} bytes
  Source:   {page.url}
  ============================================================
  Done in {elapsed:.1f}s
""")
    else:
        all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
        if all_files:
            latest = max(all_files, key=os.path.getctime)
            print(f"\n  Found file: {latest} ({os.path.getsize(latest):,} bytes)")
        else:
            print(f"\n  No file downloaded after {elapsed:.1f}s")
            print(f"  Page: {page.url}")
            debug_screenshot(page, "final_state")
            input("  Browser still open — download manually. Press Enter to close...")


if __name__ == "__main__":
    main()