# Dice Easy Apply Automation

A local, fail-closed automation runner for Dice-hosted Easy Apply jobs. It automatically fills and submits supported applications using only answers in your local applicant profile. It does **not** evade CAPTCHA/MFA or guess missing answers.

## What it does

- Imports job URLs from CSV into a local SQLite queue.
- Opens and processes one job at a time in a dedicated Chromium profile.
- Reuses your login without storing a password in configuration.
- Detects sign-in, CAPTCHA, and common error pages and pauses safely.
- Fills known fields, uploads your resume, advances application steps, and submits.
- Marks unsupported, ambiguous, or incomplete applications `blocked`.
- Saves screenshots and diagnostic metadata after failures.
- Verifies a Dice success message before recording an application as submitted.

## Quick start (Windows PowerShell)

```powershell
.\scripts\setup.ps1
Copy-Item config.example.json config.json
Copy-Item applicant.example.json applicant.json
Copy-Item jobs.example.csv jobs.csv
# Edit applicant.json and jobs.csv. Use an absolute resume path, then:
.\.venv\Scripts\python.exe -m dice_copilot import-csv jobs.csv
.\.venv\Scripts\python.exe -m dice_copilot discover --keyword "Python developer" --posted-date THREE --remote
.\.venv\Scripts\python.exe -m dice_copilot login
.\.venv\Scripts\python.exe -m dice_copilot run
```

The first `login` opens Dice in a dedicated browser window. Sign in yourself, complete any MFA/CAPTCHA, return to the terminal, and press Enter. Browser state stays under `.local/browser-profile/` and is excluded from Git.

## Resume selection by job title

Set `resume_folder` and `resume_rules` in `applicant.json`. Every rule is scored against the job title and the strongest keyword combination selects its file. Matching tolerates words inserted between keywords, reversed keyword order when an alternative allows it, joined or separated words, and minor spelling differences. `resume_path` is the fallback when no rule has a confident match.

```json
"resume_path": "C:/Resumes/general.pdf",
"resume_folder": "C:/Resumes",
"resume_rules": [
  {"title_pattern": "data|etl|analytics", "file": "data-engineer.pdf"},
  {"title_pattern": "java|spring", "file": "java-engineer.pdf"},
  {"title_pattern": "ai|machine learning|llm", "file": "ai-engineer.pdf"}
]
```

Rule files must be PDF, DOC, or DOCX files inside `resume_folder`. Narrow multi-keyword rules score higher than broad single-keyword rules; rule order is used only to resolve an equal score.

## CSV format

```csv
url,title,company,notes
https://www.dice.com/job-detail/example,Data Engineer,Example Inc,Referral available
```

Only `url` is required. Duplicate URLs are ignored.

## Commands

```powershell
python -m dice_copilot init
python -m dice_copilot import-csv jobs.csv
python -m dice_copilot discover --keyword "data engineer" --posted-date ONE
python -m dice_copilot discover --keyword "software engineer" --posted-date ONE --max-age-minutes 10 --limit 2
python -m dice_copilot list
python -m dice_copilot remove --job-id 42
python -m dice_copilot remove --status pending --yes
python -m dice_copilot login
python -m dice_copilot run --limit 10
python -m dice_copilot export applications.csv
python -m dice_copilot doctor
```

`--limit` controls how many unseen jobs are added. Discovery may inspect up to 100 results so previously seen URLs do not consume that limit.

`run` submits supported Dice-hosted Easy Apply applications without prompting. External ATS forms are blocked because their fields and legal questions vary by employer. `--allow-external` permits importing/opening external URLs, but it does not make them eligible for automatic submission.

## Safety model

- Dedicated browser profile; never attaches to your normal Chrome profile.
- Domain allowlist defaults to `dice.com` and `www.dice.com`.
- No credential fields in config and no password logging.
- Single tab, sequential queue, configurable cooldown, and no parallel applications.
- Required questions must have explicit values in `applicant.json`; unknown fields block submission.
- A single exact submit control and a post-submit success message are both required.
- Unexpected domains, bot challenges, or authentication walls stop the workflow.
- SQLite writes are transactional; interrupted items return to `pending` on the next run.
- `.local/`, configuration, logs, screenshots, and exports are ignored by Git.

You are responsible for following Dice's terms and each employer's instructions. Site layouts and policies change; review them before use.
