from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


MCP_ENDPOINT = "https://mcp.dice.com/mcp"
PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    pass


def _decode_response(content_type: str, payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8")
    if "text/event-stream" in content_type:
        messages = []
        for line in text.splitlines():
            if line.startswith("data:"):
                value = line[5:].strip()
                if value and value != "[DONE]":
                    messages.append(json.loads(value))
        if not messages:
            raise MCPError("Dice MCP returned an empty event stream")
        return messages[-1]
    return json.loads(text)


class DiceMCPClient:
    def __init__(self, endpoint: str = MCP_ENDPOINT, timeout: float = 30):
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id: str | None = None
        self.request_id = 0

    def _send(self, method: str, params: dict[str, Any] | None = None, notification: bool = False) -> dict[str, Any]:
        self.request_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            message["id"] = self.request_id
        if params is not None:
            message["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": "dice-application-copilot/0.1.0",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(message).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.headers.get("MCP-Session-Id"):
                    self.session_id = response.headers["MCP-Session-Id"]
                if notification or response.status == 202:
                    return {}
                decoded = _decode_response(response.headers.get("Content-Type", "application/json"), response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MCPError(f"Dice MCP HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"Could not reach Dice MCP: {exc.reason}") from exc
        if "error" in decoded:
            error = decoded["error"]
            raise MCPError(f'Dice MCP error {error.get("code")}: {error.get("message")}')
        return decoded.get("result", {})

    def initialize(self) -> dict[str, Any]:
        result = self._send(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "dice-application-copilot", "version": "0.1.0"},
            },
        )
        self._send("notifications/initialized", notification=True)
        return result

    def tools(self) -> list[dict[str, Any]]:
        return self._send("tools/list").get("tools", [])

    def search_jobs(self, **arguments: Any) -> list[dict[str, Any]]:
        result = self._send("tools/call", {"name": "search_jobs", "arguments": arguments})
        if result.get("isError"):
            texts = [item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"]
            raise MCPError("Dice search failed: " + " ".join(texts))
        structured = result.get("structuredContent")
        if structured:
            return _find_jobs(structured)
        for item in result.get("content", []):
            if item.get("type") != "text":
                continue
            try:
                return _find_jobs(json.loads(item.get("text", "")))
            except json.JSONDecodeError:
                continue
        raise MCPError("Dice MCP response did not contain structured job results")


def _find_jobs(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    if isinstance(value, dict):
        for key in ("jobs", "results", "data", "items"):
            if key in value:
                found = _find_jobs(value[key])
                if found:
                    return found
        for child in value.values():
            found = _find_jobs(child)
            if found:
                return found
    return []


@dataclass(frozen=True)
class NormalizedJob:
    url: str
    title: str
    company: str
    notes: str


def normalize_job(job: dict[str, Any]) -> NormalizedJob | None:
    url = str(job.get("detailsPageUrl") or job.get("url") or job.get("jobUrl") or "").strip()
    if not url:
        return None
    title = str(job.get("title") or job.get("jobTitle") or "").strip()
    company = str(job.get("companyName") or job.get("company") or "").strip()
    details = []
    for key in ("jobLocation", "postedDate", "employmentType", "salary"):
        value = job.get(key)
        if value:
            details.append(f"{key}={value}")
    return NormalizedJob(url=url, title=title, company=company, notes="; ".join(details))


def posted_age_minutes(job: dict[str, Any], current_time: datetime | None = None) -> float | None:
    value = job.get("postedDate") or job.get("posted_date")
    if value is None:
        return None
    now = current_time or datetime.now(timezone.utc)
    text = str(value).strip()
    relative = re.fullmatch(r"(?:posted\s+)?(\d+)\s+(minute|hour)s?\s+ago", text, re.I)
    if relative:
        amount = int(relative.group(1))
        return float(amount if relative.group(2).lower() == "minute" else amount * 60)
    if re.fullmatch(r"(?:just now|moments ago)", text, re.I):
        return 0.0
    try:
        posted = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return max(0.0, (now - posted.astimezone(timezone.utc)).total_seconds() / 60)
    except ValueError:
        return None
