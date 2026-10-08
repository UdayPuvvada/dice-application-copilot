from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config


CHALLENGE_TEXT = re.compile(r"captcha|verify you are human|unusual traffic|security check", re.I)
AUTH_TEXT = re.compile(r"sign in|log in|enter your password", re.I)


@dataclass(frozen=True)
class PageAssessment:
    kind: str
    detail: str = ""


def assess_page(url: str, title: str, body_text: str, config: Config) -> PageAssessment:
    sample = f"{title}\n{body_text[:8000]}"
    if not config.allows(url):
        return PageAssessment("external", url)
    if CHALLENGE_TEXT.search(sample):
        return PageAssessment("challenge", "CAPTCHA or anti-bot check detected")
    if AUTH_TEXT.search(sample) and ("login" in url.lower() or "signin" in url.lower()):
        return PageAssessment("auth", "Sign-in is required")
    if re.search(r"access denied|temporarily unavailable|something went wrong", sample, re.I):
        return PageAssessment("error", "The page reports an error")
    return PageAssessment("ready")


class BrowserSession:
    def __init__(self, config: Config, profile_dir: Path, artifacts_dir: Path):
        self.config = config
        self.profile_dir = profile_dir
        self.artifacts_dir = artifacts_dir
        self.playwright = None
        self.context = None
        self.page = None

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = sync_playwright().start()
        browser_type = self.playwright.chromium
        options = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.config.headless,
            "viewport": {"width": 1440, "height": 900},
            "locale": "en-US",
        }
        if self.config.browser_channel != "chromium":
            options["channel"] = self.config.browser_channel
        self.context = browser_type.launch_persistent_context(**options)
        self.context.set_default_timeout(self.config.navigation_timeout_seconds * 1000)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def __exit__(self, *_: object) -> None:
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def navigate(self, url: str) -> PageAssessment:
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)
        return assess_page(self.page.url, self.page.title(), self.page.locator("body").inner_text(), self.config)

    def screenshot(self, job_id: int) -> Path:
        assert self.page is not None
        path = self.artifacts_dir / f"job-{job_id}.png"
        self.page.screenshot(path=str(path), full_page=False)
        return path

