from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .applicant import Applicant
from .auto_apply import submit_easy_apply
from .browser import BrowserSession
from .config import Config
from .db import Database
from .dice_mcp import DiceMCPClient, MCPError, normalize_job, posted_age_minutes


ROOT = Path.cwd()
LOCAL = ROOT / ".local"
DB_PATH = LOCAL / "applications.sqlite3"
PROFILE = LOCAL / "browser-profile"
ARTIFACTS = LOCAL / "artifacts"


def load_config() -> Config:
    return Config.load(ROOT / "config.json")


def valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def command_init(_: argparse.Namespace) -> int:
    LOCAL.mkdir(exist_ok=True)
    with Database(DB_PATH):
        pass
    target = ROOT / "config.json"
    if not target.exists():
        shutil.copyfile(ROOT / "config.example.json", target)
    print(f"Initialized {DB_PATH}")
    return 0


def command_import(args: argparse.Namespace) -> int:
    config = load_config()
    added = ignored = invalid = 0
    with Path(args.csv).open(newline="", encoding="utf-8-sig") as source, Database(DB_PATH) as db:
        for row in csv.DictReader(source):
            url = (row.get("url") or "").strip()
            if not valid_http_url(url) or (not args.allow_external and not config.allows(url)):
                invalid += 1
                continue
            if db.add(url, (row.get("title") or "").strip(), (row.get("company") or "").strip(), (row.get("notes") or "").strip()):
                added += 1
            else:
                ignored += 1
    print(f"Imported {added}; duplicates {ignored}; invalid/disallowed {invalid}")
    return 0 if invalid == 0 else 2


def command_list(args: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        rows = db.list(args.status)
    if not rows:
        print("No jobs found.")
        return 0
    for row in rows:
        label = row["title"] or row["url"]
        print(f'{row["id"]:>4}  {row["status"]:<11}  {label}  {row["company"]}')
    return 0


def command_remove(args: argparse.Namespace) -> int:
    status = args.status
    remove_all = args.all
    if (status is not None or remove_all) and not args.yes:
        raise ValueError("Bulk removal requires --yes")
    with Database(DB_PATH) as db:
        count = db.count(job_id=args.job_id, status=status)
    if count == 0:
        print("No matching jobs found; nothing removed.")
        return 0
    LOCAL.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = LOCAL / f"applications-before-remove-{stamp}.sqlite3"
    shutil.copy2(DB_PATH, backup)
    with Database(DB_PATH) as db:
        removed = db.delete(job_id=args.job_id, status=status)
    print(f"Removed {removed} job(s). Backup: {backup}")
    return 0


def command_discover(args: argparse.Namespace) -> int:
    config = load_config()
    if args.max_age_minutes is not None and args.max_age_minutes < 1:
        raise ValueError("--max-age-minutes must be positive")
    arguments: dict[str, object] = {
        "keyword": args.keyword,
        "posted_date": args.posted_date,
        # Inspect a full page so already-seen URLs do not consume --limit.
        "jobs_per_page": 100,
        "easy_apply": True,
    }
    if args.location:
        arguments["location"] = args.location
    if args.remote:
        arguments["workplace_types"] = ["Remote"]
    client = DiceMCPClient(timeout=config.navigation_timeout_seconds)
    client.initialize()
    jobs = client.search_jobs(**arguments)
    if args.max_age_minutes:
        jobs = [job for job in jobs if (age := posted_age_minutes(job)) is not None and age <= args.max_age_minutes]
        jobs.sort(key=lambda job: posted_age_minutes(job) or 0)
    added = duplicate = invalid = 0
    with Database(DB_PATH) as db:
        for raw_job in jobs:
            if added >= args.limit:
                break
            job = normalize_job(raw_job)
            if not job or not valid_http_url(job.url) or not config.allows(job.url):
                invalid += 1
                continue
            if db.add(job.url, job.title, job.company, job.notes):
                added += 1
            else:
                duplicate += 1
    print(f"Dice MCP returned {len(jobs)} jobs; queued {added}; duplicates {duplicate}; invalid/disallowed {invalid}")
    return 0


def command_login(_: argparse.Namespace) -> int:
    config = load_config()
    print("A dedicated browser will open. Sign in and complete any challenge yourself.")
    with BrowserSession(config, PROFILE, ARTIFACTS) as browser:
        browser.navigate(config.start_url)
        input("When login is complete, return here and press Enter to save the session...")
    print("Browser session saved locally.")
    return 0


def command_run(args: argparse.Namespace) -> int:
    config = load_config()
    applicant_path = (ROOT / config.applicant_file).resolve()
    applicant = Applicant.load(applicant_path)
    completed = 0
    run_limit = 1 if args.job_id is not None else args.limit
    with Database(DB_PATH) as db, BrowserSession(config, PROFILE, ARTIFACTS) as browser:
        while run_limit is None or completed < run_limit:
            job = db.claim_next(args.job_id)
            if not job:
                print(f"Pending job #{args.job_id} was not found." if args.job_id else "Queue complete.")
                break
            completed += 1
            if not args.allow_external and not config.allows(job["url"]):
                db.finish(job["id"], "blocked", "Domain is not allowlisted")
                continue
            print(f'\nOpening #{job["id"]}: {job["title"] or job["url"]}')
            try:
                assessment = browser.navigate(job["url"])
                if assessment.kind != "ready":
                    artifact = browser.screenshot(job["id"])
                    db.finish(job["id"], "blocked", f"{assessment.detail}; screenshot={artifact}")
                    print(f"Paused safely: {assessment.detail}. Screenshot: {artifact}")
                    if assessment.kind in {"challenge", "auth"}:
                        print("Resolve it manually, then rerun; no bypass will be attempted.")
                        break
                    continue
                try:
                    job_description = browser.page.locator("body").inner_text(timeout=5000)
                except Exception:
                    job_description = job["notes"] or ""
                selected_resume = applicant.resume_for(job["title"], applicant_path.parent, job_description)
                print(f"Resume folder: {selected_resume.parent}")
                print(f"Selected resume: {selected_resume.name}")
                result = submit_easy_apply(
                    browser.page,
                    applicant,
                    config,
                    applicant_path.parent,
                    job["title"],
                    selected_resume,
                )
                if result.status == "blocked":
                    artifact = browser.screenshot(job["id"])
                    detail = f"{result.detail}; screenshot={artifact}"
                    db.finish(job["id"], "blocked", detail)
                    print(f"Blocked safely: {detail}")
                else:
                    db.finish(job["id"], "applied", result.detail)
                    print(f"Applied automatically: {result.detail}")
                if config.cooldown_seconds:
                    time.sleep(config.cooldown_seconds)
            except KeyboardInterrupt:
                db.finish(job["id"], "pending", "Interrupted by user")
                raise
            except Exception as exc:
                try:
                    artifact = browser.screenshot(job["id"])
                    detail = f"{type(exc).__name__}: {exc}; screenshot={artifact}"
                except Exception:
                    detail = f"{type(exc).__name__}: {exc}"
                db.finish(job["id"], "blocked", detail)
                print(f"Job blocked safely: {detail}", file=sys.stderr)
    return 0


def command_export(args: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        rows = db.list()
    fields = ["id", "url", "title", "company", "notes", "status", "attempts", "last_error", "created_at", "updated_at"]
    with Path(args.csv).open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)
    print(f"Exported {len(rows)} rows to {args.csv}")
    return 0


def command_repair_false_applied(_: argparse.Namespace) -> int:
    reason = "Dice reports this application was already submitted"
    with Database(DB_PATH) as db:
        repaired = db.repair_false_applied(reason)
    print(f"Reset {repaired} known false-positive applied rows to pending")
    return 0


def command_retry_network_blocked(_: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        repaired = db.retry_blocked_prefix("Error: Page.goto: net::ERR_NETWORK_ACCESS_DENIED")
    print(f"Reset {repaired} network-denied rows to pending")
    return 0


def command_retry_auth_blocked(_: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        repaired = db.retry_blocked_prefix("Sign-in is required")
    print(f"Reset {repaired} authentication-blocked rows to pending")
    return 0


def command_retry_selector_blocked(_: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        repaired = db.retry_blocked_prefix("No unambiguous next or submit control")
        repaired += db.retry_blocked_prefix("Exactly one Dice Easy Apply control was not found")
        repaired += db.retry_blocked_prefix("Application wizard did not become ready")
        repaired += db.retry_blocked_prefix("Application step ")
    print(f"Reset {repaired} obsolete selector-blocked rows to pending")
    return 0


def command_retry_unconfirmed_submit(_: argparse.Namespace) -> int:
    with Database(DB_PATH) as db:
        repaired = db.retry_blocked_prefix("Submit was clicked but no success confirmation appeared")
    print(f"Reset {repaired} unconfirmed-submit rows for Dice status reconciliation")
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    issues: list[str] = []
    try:
        config = load_config()
        config.validate()
        print("OK config")
        applicant_path = (ROOT / config.applicant_file).resolve()
        Applicant.load(applicant_path)
        print("OK applicant profile and resume")
    except Exception as exc:
        issues.append(f"configuration/profile: {exc}")
    try:
        from playwright.sync_api import sync_playwright
        print("OK Playwright package")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        print("OK Chromium launch")
    except ImportError:
        issues.append("Playwright is not installed")
    except Exception as exc:
        issues.append(f"Chromium launch: {exc}")
    print(f"Python {sys.version.split()[0]}")
    print(f"Database {DB_PATH}")
    for issue in issues:
        print(f"ERROR {issue}", file=sys.stderr)
    return 1 if issues else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="dice-copilot", description="Fail-closed Dice Easy Apply automation")
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init", help="Initialize local state")
    p.set_defaults(handler=command_init)
    p = commands.add_parser("import-csv", help="Import supplied job URLs")
    p.add_argument("csv")
    p.add_argument("--allow-external", action="store_true")
    p.set_defaults(handler=command_import)
    p = commands.add_parser("list", help="List queued jobs")
    p.add_argument("--status", choices=["pending", "in_progress", "applied", "skipped", "blocked"])
    p.set_defaults(handler=command_list)
    p = commands.add_parser("remove", help="Remove jobs after creating a database backup")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--job-id", type=int, help="Remove one job by ID")
    target.add_argument("--status", choices=["pending", "in_progress", "applied", "skipped", "blocked"])
    target.add_argument("--all", action="store_true", help="Remove every job record")
    p.add_argument("--yes", action="store_true", help="Confirm status-group or full-queue removal")
    p.set_defaults(handler=command_remove)
    p = commands.add_parser("discover", help="Populate the queue with Dice Easy Apply jobs using the official MCP server")
    p.add_argument("--keyword", required=True, help="Job title or skills query")
    p.add_argument("--posted-date", choices=["ONE", "THREE", "SEVEN"], default="THREE")
    p.add_argument("--location")
    p.add_argument("--remote", action="store_true")
    p.add_argument("--limit", type=int, choices=range(1, 101), default=25, metavar="1-100")
    p.add_argument("--max-age-minutes", type=int, help="Locally keep only postings no older than this many minutes")
    p.set_defaults(handler=command_discover)
    p = commands.add_parser("login", help="Open a browser for manual login")
    p.set_defaults(handler=command_login)
    p = commands.add_parser("run", help="Automatically submit supported Dice Easy Apply jobs")
    p.add_argument("--limit", type=int)
    p.add_argument("--job-id", type=int, help="Process one specific pending job")
    p.add_argument("--allow-external", action="store_true")
    p.set_defaults(handler=command_run)
    p = commands.add_parser("export", help="Export queue and outcomes")
    p.add_argument("csv")
    p.set_defaults(handler=command_export)
    p = commands.add_parser("repair-false-applied", help="Reset rows affected by the obsolete page-wide detector")
    p.set_defaults(handler=command_repair_false_applied)
    p = commands.add_parser("retry-network-blocked", help="Retry rows blocked only by local browser network denial")
    p.set_defaults(handler=command_retry_network_blocked)
    p = commands.add_parser("retry-auth-blocked", help="Retry rows blocked because the Dice session expired")
    p.set_defaults(handler=command_retry_auth_blocked)
    p = commands.add_parser("retry-selector-blocked", help="Retry rows blocked by the obsolete wizard timing logic")
    p.set_defaults(handler=command_retry_selector_blocked)
    p = commands.add_parser("retry-unconfirmed-submit", help="Recheck Dice after a submit confirmation timeout")
    p.set_defaults(handler=command_retry_unconfirmed_submit)
    p = commands.add_parser("doctor", help="Check local installation")
    p.set_defaults(handler=command_doctor)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError, MCPError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
