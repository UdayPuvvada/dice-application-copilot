from dice_copilot.browser import assess_page
from dice_copilot.config import Config


def test_page_assessment_stops_on_challenge_auth_and_external():
    config = Config()
    assert assess_page("https://www.dice.com/jobs", "Jobs", "Ready", config).kind == "ready"
    assert assess_page("https://www.dice.com/jobs", "Security", "Verify you are human", config).kind == "challenge"
    assert assess_page("https://www.dice.com/dashboard/login", "Sign in", "Enter your password", config).kind == "auth"
    assert assess_page("https://example.com/apply", "Apply", "Ready", config).kind == "external"
