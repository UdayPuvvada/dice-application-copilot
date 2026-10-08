from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    start_url: str = "https://www.dice.com/dashboard/login"
    allowed_domains: list[str] = field(default_factory=lambda: ["dice.com", "www.dice.com"])
    cooldown_seconds: float = 3.0
    navigation_timeout_seconds: float = 30.0
    headless: bool = False
    browser_channel: str = "chromium"
    artifact_retention_days: int = 14
    applicant_file: str = "applicant.json"
    max_application_steps: int = 8

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {name for name in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        config = cls(**data)
        config.validate()
        return config

    def validate(self) -> None:
        if urlparse(self.start_url).scheme != "https":
            raise ValueError("start_url must use https")
        if not self.allowed_domains:
            raise ValueError("allowed_domains must not be empty")
        if self.cooldown_seconds < 0 or self.navigation_timeout_seconds <= 0:
            raise ValueError("timeouts must be positive")
        if self.max_application_steps < 1 or self.max_application_steps > 20:
            raise ValueError("max_application_steps must be between 1 and 20")

    def allows(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in self.allowed_domains)
