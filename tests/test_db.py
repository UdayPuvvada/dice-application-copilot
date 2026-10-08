from dice_copilot.db import Database


def test_queue_is_deduplicated_and_resumable(tmp_path):
    path = tmp_path / "queue.sqlite3"
    with Database(path) as db:
        assert db.add("https://www.dice.com/job-detail/1", "Role")
        assert not db.add("https://www.dice.com/job-detail/1", "Duplicate")
        job = db.claim_next()
        assert job is not None
        assert job["title"] == "Role"

    with Database(path) as db:
        rows = db.list("pending")
        assert len(rows) == 1
        assert rows[0]["attempts"] == 1
        db.finish(rows[0]["id"], "applied")
        assert db.list()[0]["status"] == "applied"


def test_repair_false_applied_is_exact_and_preserves_real_results(tmp_path):
    with Database(tmp_path / "queue.sqlite3") as db:
        db.add("https://www.dice.com/job-detail/false")
        false_job = db.claim_next()
        db.finish(false_job["id"], "applied", "Dice reports this application was already submitted")
        db.add("https://www.dice.com/job-detail/real")
        real_job = db.claim_next()
        db.finish(real_job["id"], "applied", "Submission confirmed by Dice")
        assert db.repair_false_applied("Dice reports this application was already submitted") == 1
        rows = db.list()
        assert rows[0]["status"] == "pending"
        assert rows[1]["status"] == "applied"


def test_retry_network_blocked_only_matches_prefix(tmp_path):
    with Database(tmp_path / "queue.sqlite3") as db:
        db.add("https://www.dice.com/job-detail/network")
        network_job = db.claim_next()
        db.finish(network_job["id"], "blocked", "Error: Page.goto: net::ERR_NETWORK_ACCESS_DENIED at https://www.dice.com")
        db.add("https://www.dice.com/job-detail/form")
        form_job = db.claim_next()
        db.finish(form_job["id"], "blocked", "Unanswered required fields")
        assert db.retry_blocked_prefix("Error: Page.goto: net::ERR_NETWORK_ACCESS_DENIED") == 1
        rows = db.list()
        assert rows[0]["status"] == "pending"
        assert rows[1]["status"] == "blocked"


def test_claim_specific_pending_job(tmp_path):
    with Database(tmp_path / "queue.sqlite3") as db:
        db.add("https://www.dice.com/job-detail/one")
        db.add("https://www.dice.com/job-detail/two")
        job = db.claim_next(2)
        assert job is not None
        assert job["id"] == 2
        assert db.list()[0]["status"] == "pending"


def test_delete_by_id_and_status(tmp_path):
    with Database(tmp_path / "queue.sqlite3") as db:
        db.add("https://www.dice.com/job-detail/one")
        db.add("https://www.dice.com/job-detail/two")
        second = db.claim_next(2)
        db.finish(second["id"], "blocked", "test")
        assert db.count(status="pending") == 1
        assert db.delete(status="blocked") == 1
        assert db.delete(job_id=1) == 1
        assert db.count() == 0
