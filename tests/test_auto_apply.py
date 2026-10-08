from playwright.sync_api import sync_playwright

from dice_copilot.applicant import Applicant
from dice_copilot.auto_apply import submit_easy_apply
from dice_copilot.config import Config


def test_complete_easy_apply_submission(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="3125550100",
        resume_path=str(resume),
        authorized_to_work=True,
        requires_sponsorship=False,
    )
    html = """
    <aside>Already applied elsewhere? Track your applications.</aside>
    <button id="apply">Continue Application</button>
    <script>
      document.querySelector('#apply').onclick = () => {
        setTimeout(() => { document.body.innerHTML = `
          <label>First name <input required></label>
          <label>Last name <input required></label>
          <label>Email <input required></label>
          <label>Phone <input required></label>
          <label>Resume <input type="file" required></label>
          <fieldset><legend>Are you legally authorized to work?</legend>
            <label>Yes<input name="work" type="radio" value="yes" required></label>
            <label>No<input name="work" type="radio" value="no" required></label>
          </fieldset>
          <fieldset><legend>Will you require sponsorship?</legend>
            <label>Yes<input name="sponsor" type="radio" value="yes" required></label>
            <label>No<input name="sponsor" type="radio" value="no" required></label>
          </fieldset>
          <button id="next">Next</button>`;
        document.querySelector('#next').onclick = () => {
          document.body.innerHTML = '<div>Loading application…</div>';
          setTimeout(() => {
            document.body.innerHTML = '<button id="submit">Submit application</button>';
            document.querySelector('#submit').onclick = () => { document.body.innerHTML = '<h1>Application submitted</h1>'; };
          }, 900);
        };
        }, 900);
      };
    </script>
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("https://www.dice.com/fake", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto("https://www.dice.com/fake")
        result = submit_easy_apply(page, applicant, Config(), tmp_path)
        browser.close()
    assert result.status == "applied"
    assert result.detail == "Submission confirmed by Dice"


def test_exact_applied_control_is_high_confidence_status(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant("Jane", "Doe", "jane@example.com", "3125550100", resume_path=str(resume))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route(
            "https://www.dice.com/applied",
            lambda route: route.fulfill(body="<aside>Already applied elsewhere?</aside><button>Applied</button>", content_type="text/html"),
        )
        page.goto("https://www.dice.com/applied")
        result = submit_easy_apply(page, applicant, Config(), tmp_path)
        browser.close()
    assert result.status == "applied"
    assert "exact Applied" in result.detail
