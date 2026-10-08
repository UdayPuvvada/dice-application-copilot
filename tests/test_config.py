from dice_copilot.config import Config


def test_domain_allowlist_accepts_subdomains_but_not_suffix_attacks():
    config = Config()
    assert config.allows("https://www.dice.com/job-detail/123")
    assert config.allows("https://jobs.dice.com/example")
    assert not config.allows("http://www.dice.com/job-detail/123")
    assert not config.allows("https://dice.com.evil.example/job")
    assert not config.allows("javascript:alert(1)")
