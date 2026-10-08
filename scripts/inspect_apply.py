import argparse
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


arguments = argparse.ArgumentParser()
arguments.add_argument("--click", action="store_true")
arguments.add_argument("--job-id", type=int, default=1)
arguments.add_argument("--advance", action="store_true")
args = arguments.parse_args()
root = Path(__file__).resolve().parents[1]
with sqlite3.connect(root / ".local" / "applications.sqlite3") as connection:
    row = connection.execute("SELECT url FROM jobs WHERE id=?", (args.job_id,)).fetchone()
    if not row:
        raise SystemExit(f"Unknown job id: {args.job_id}")
    url = row[0]

with sync_playwright() as playwright:
    context = playwright.chromium.launch_persistent_context(
        str(root / ".local" / "browser-profile"),
        headless=False,
        viewport={"width": 1440, "height": 900},
    )
    page = context.pages[0] if context.pages else context.new_page()
    failures = []
    errors = []
    page.on("requestfailed", lambda request: failures.append((request.method, request.url, request.failure)))
    page.on("response", lambda response: errors.append((response.status, response.url)) if response.status >= 400 else None)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if args.advance:
        match = re.search(r"/job-detail/([0-9a-f-]+)", url, re.I)
        if match:
            page.goto(f"https://www.dice.com/job-applications/{match.group(1)}/wizard", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
    pattern = re.compile(r"^(?:easy\s+)?apply(?:\s+now)?$", re.I)
    button_candidates = page.get_by_role("button", name=pattern)
    link_candidates = page.get_by_role("link", name=pattern)
    print(f"before_url={page.url}")
    print(f"button_apply_count={button_candidates.count()}")
    print(f"link_apply_count={link_candidates.count()}")
    candidates = [button_candidates.nth(i) for i in range(button_candidates.count())]
    candidates += [link_candidates.nth(i) for i in range(link_candidates.count())]
    for index, item in enumerate(candidates):
        print(f"apply[{index}] visible={item.is_visible()} html={item.evaluate('e => e.outerHTML')}")
    visible = [item for item in candidates if item.is_visible()]
    if args.click and len(visible) == 1:
        href = visible[0].get_attribute("href")
        if href and "/job-applications/" in href:
            page.goto(urljoin(page.url, href), wait_until="domcontentloaded")
        else:
            visible[0].click()
        page.wait_for_timeout(2500)
    if args.advance:
        next_controls = page.get_by_role("button", name=re.compile(r"^next$", re.I))
        if next_controls.count() == 1:
            next_controls.click()
            page.wait_for_timeout(10000)
    print(f"page_count={len(context.pages)}")
    for index, open_page in enumerate(context.pages):
        print(f"page[{index}] url={open_page.url} title={open_page.title()!r}")
        controls = open_page.get_by_role("button")
        print(f"page[{index}] buttons={controls.all_inner_texts()}")
    print(f"failed_requests={failures}")
    print(f"error_responses={errors}")
    context.close()
