from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .applicant import Applicant
from .browser import assess_page
from .config import Config


SUCCESS = re.compile(r"application (?:was )?submitted|successfully applied|application (?:was )?sent|thank you for applying", re.I)
APPLY = re.compile(r"^(?:(?:easy\s+)?apply(?:\s+now)?|continue application|resume application)$", re.I)
NEXT = re.compile(r"^(?:next|continue|review)(?:\s+application)?$", re.I)
SUBMIT = re.compile(r"^(?:submit(?:\s+application)?|send application)$", re.I)
APPLIED = re.compile(r"^applied$", re.I)


@dataclass(frozen=True)
class ApplyResult:
    status: str
    detail: str


def _visible(locator):
    return [locator.nth(index) for index in range(locator.count()) if locator.nth(index).is_visible()]


def _has_exact_applied_status(page) -> bool:
    controls = _visible(page.get_by_role("button", name=APPLIED))
    controls += _visible(page.get_by_role("link", name=APPLIED))
    return len(controls) == 1


def _click_one(page, pattern: re.Pattern[str]) -> bool:
    buttons = _visible(page.get_by_role("button", name=pattern))
    links = _visible(page.get_by_role("link", name=pattern))
    candidates = buttons + links
    if len(candidates) != 1:
        return False
    candidates[0].click()
    page.wait_for_timeout(250)
    return True


def _open_application(page) -> bool:
    buttons = _visible(page.get_by_role("button", name=APPLY))
    links = _visible(page.get_by_role("link", name=APPLY))
    candidates = buttons + links
    if len(candidates) != 1:
        return False
    control = candidates[0]
    href = control.get_attribute("href")
    if href:
        target = urljoin(page.url, href)
        parsed = urlparse(target)
        if parsed.hostname and parsed.hostname.lower().endswith("dice.com") and "/job-applications/" in parsed.path:
            page.goto(target, wait_until="domcontentloaded")
            return True
    control.click()
    page.wait_for_timeout(250)
    return True


def _wait_for_application_step(page, previous_url: str, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if page.url != previous_url:
            page.wait_for_load_state("domcontentloaded")
            return
        controls = page.get_by_role("button", name=NEXT)
        controls = controls.or_(page.get_by_role("button", name=SUBMIT))
        controls = controls.or_(page.get_by_role("link", name=NEXT))
        if any(controls.nth(index).is_visible() for index in range(controls.count())):
            return
        page.wait_for_timeout(250)
    raise TimeoutError("Application step controls did not become visible")


def _fill_text_fields(page, applicant: Applicant) -> None:
    for pattern, value in applicant.field_values():
        matches = page.get_by_label(re.compile(pattern, re.I))
        for control in _visible(matches):
            tag = control.evaluate("element => element.tagName.toLowerCase()")
            if tag not in {"input", "textarea"}:
                continue
            input_type = (control.get_attribute("type") or "text").lower()
            if input_type in {"checkbox", "radio", "file", "hidden", "submit", "button"}:
                continue
            if not control.input_value().strip():
                control.fill(value)


def _upload_resume(page, resume: Path) -> None:
    inputs_locator = page.locator('input[type="file"]')
    inputs = [inputs_locator.nth(index) for index in range(inputs_locator.count())]
    if len(inputs) > 1:
        raise ValueError("Multiple visible file upload controls are ambiguous")
    if inputs:
        inputs[0].set_input_files(str(resume))


def _choose_boolean(page, question: str, value: bool | None) -> None:
    if value is None:
        return
    answer = "Yes" if value else "No"
    containers = page.locator("fieldset, [role='group']").filter(has_text=re.compile(question, re.I))
    for container in _visible(containers):
        choices = container.get_by_label(re.compile(rf"^{answer}$", re.I))
        visible = _visible(choices)
        if len(visible) == 1:
            visible[0].check()


def _fill_custom_answers(page, answers: dict[str, str]) -> None:
    for question, answer in answers.items():
        controls = page.get_by_label(re.compile(re.escape(question), re.I))
        visible = _visible(controls)
        if len(visible) != 1:
            continue
        control = visible[0]
        tag = control.evaluate("element => element.tagName.toLowerCase()")
        if tag == "select":
            control.select_option(label=answer)
        elif (control.get_attribute("type") or "").lower() in {"checkbox", "radio"}:
            if answer.lower() in {"yes", "true", "1"}:
                control.check()
        else:
            control.fill(answer)


def _unanswered_required(page) -> list[str]:
    script = """
    elements => elements.filter(e => {
      if (!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)) return false;
      if (e.disabled) return false;
      if (e.type === 'checkbox' || e.type === 'radio') {
        if (e.name) return !document.querySelector(`input[name="${CSS.escape(e.name)}"]:checked`);
        return !e.checked;
      }
      return !(e.value || '').trim();
    }).map(e => {
      const label = e.labels && e.labels[0];
      return (label ? label.innerText : e.getAttribute('aria-label') || e.name || e.id || e.type).trim();
    })
    """
    values = page.locator("input[required], textarea[required], select[required], [aria-required='true']").evaluate_all(script)
    return sorted(set(value for value in values if value))


def submit_easy_apply(
    page,
    applicant: Applicant,
    config: Config,
    applicant_base: Path,
    job_title: str = "",
    selected_resume: Path | None = None,
) -> ApplyResult:
    if _has_exact_applied_status(page):
        return ApplyResult("applied", "Dice job page shows the exact Applied status control")
    job_url = page.url
    if not _open_application(page):
        return ApplyResult("blocked", "Exactly one Dice Easy Apply control was not found; the job may already be applied or unsupported")
    try:
        _wait_for_application_step(page, job_url, int(config.navigation_timeout_seconds * 1000))
    except Exception as exc:
        return ApplyResult("blocked", f"Application wizard did not become ready: {type(exc).__name__}")

    for step in range(1, config.max_application_steps + 1):
        page.wait_for_timeout(500)
        assessment = assess_page(page.url, page.title(), page.locator("body").inner_text(), config)
        if assessment.kind != "ready":
            return ApplyResult("blocked", assessment.detail)

        body = page.locator("body").inner_text()
        if SUCCESS.search(body):
            return ApplyResult("applied", "Submission confirmed by Dice")

        _fill_text_fields(page, applicant)
        _upload_resume(page, selected_resume or applicant.resume_for(job_title, applicant_base))
        _choose_boolean(page, r"authorized|legally.*work", applicant.authorized_to_work)
        _choose_boolean(page, r"sponsor|sponsorship", applicant.requires_sponsorship)
        _fill_custom_answers(page, applicant.answers)

        unanswered = _unanswered_required(page)
        if unanswered:
            return ApplyResult("blocked", "Unanswered required fields: " + ", ".join(unanswered[:10]))

        submit_buttons = _visible(page.get_by_role("button", name=SUBMIT))
        if len(submit_buttons) == 1:
            submit_buttons[0].click()
            try:
                page.wait_for_function(
                    """
                    () => /application (?:was )?submitted|successfully applied|application (?:was )?sent|thank you for applying/i
                      .test(document.body.innerText)
                    """,
                    timeout=int(config.navigation_timeout_seconds * 1000),
                )
            except Exception:
                pass
            final_assessment = assess_page(page.url, page.title(), page.locator("body").inner_text(), config)
            if final_assessment.kind != "ready":
                return ApplyResult("blocked", final_assessment.detail)
            if SUCCESS.search(page.locator("body").inner_text()):
                return ApplyResult("applied", "Submission confirmed by Dice")
            try:
                page.goto(job_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1000)
                if _has_exact_applied_status(page):
                    return ApplyResult("applied", "Submission confirmed by the exact Dice Applied status control")
            except Exception:
                pass
            return ApplyResult("blocked", "Submit was clicked but no success confirmation appeared")
        if len(submit_buttons) > 1:
            return ApplyResult("blocked", "Multiple submit controls are ambiguous")
        step_url = page.url
        if not _click_one(page, NEXT):
            return ApplyResult("blocked", f"No unambiguous next or submit control at step {step}")
        page.wait_for_timeout(500)
        try:
            _wait_for_application_step(page, step_url, int(config.navigation_timeout_seconds * 1000))
        except Exception as exc:
            return ApplyResult("blocked", f"Application step {step + 1} did not become ready: {type(exc).__name__}")

    return ApplyResult("blocked", f"Application exceeded {config.max_application_steps} steps")
