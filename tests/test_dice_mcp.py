import json
from datetime import datetime, timezone

from dice_copilot.dice_mcp import _decode_response, normalize_job, posted_age_minutes


def test_decode_sse_response():
    payload = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    assert _decode_response("text/event-stream", payload)["result"]["ok"] is True


def test_normalize_official_job_shape():
    job = normalize_job({
        "title": "Data Engineer",
        "companyName": "Example",
        "detailsPageUrl": "https://www.dice.com/job-detail/123",
        "postedDate": "2026-10-04",
    })
    assert job is not None
    assert job.title == "Data Engineer"
    assert job.company == "Example"
    assert "postedDate=2026-10-04" in job.notes


def test_posted_age_minutes_handles_iso_and_relative_values():
    now = datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc)
    assert posted_age_minutes({"postedDate": "5 minutes ago"}, now) == 5
    assert posted_age_minutes({"postedDate": "2026-10-04T18:52:00Z"}, now) == 8
    assert posted_age_minutes({"postedDate": "Today"}, now) is None
