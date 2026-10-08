# Dice Automation Command Reference

Run commands from PowerShell in the project directory:

```powershell
cd "C:\path\to\Dice automation"
```

The recommended command launcher is:

```powershell
.\scripts\run.ps1 <command> [options]
```

It automatically uses the project's Python virtual environment.

## Setup and diagnostics

### Install the project

```powershell
.\scripts\setup.ps1
```

Creates `.venv`, installs the project dependencies and Chromium, and runs the automated tests. Normally this is required only once.

### Initialize local storage

```powershell
.\scripts\run.ps1 init
```

Creates the `.local` directory and SQLite job queue. It also creates `config.json` from the example when no configuration exists.

### Check the installation

```powershell
.\scripts\run.ps1 doctor
```

Checks the configuration, applicant profile, configured resume files, Playwright installation, Chromium launch, Python version, and database location.

## Discover jobs

### Basic discovery

```powershell
.\scripts\run.ps1 discover --keyword "Data Engineer"
```

Uses the Dice MCP server to find Dice Easy Apply jobs and adds unseen URLs to the local queue.

### Common discovery options

```powershell
.\scripts\run.ps1 discover `
  --keyword "Data Engineer" `
  --posted-date ONE `
  --remote `
  --limit 5
```

| Option | Description |
|---|---|
| `--keyword "..."` | Required job title or skills query. |
| `--posted-date ONE` | Uses Dice's one-day posting window. Valid values are `ONE`, `THREE`, and `SEVEN`. |
| `--remote` | Returns remote jobs only. |
| `--location "Dallas, TX"` | Filters results by location. |
| `--limit 5` | Adds at most five previously unseen jobs. Valid range is 1–100. |
| `--max-age-minutes 10` | Locally keeps only postings whose reported age is no more than 10 minutes. |

Example for five very recent remote jobs:

```powershell
.\scripts\run.ps1 discover `
  --keyword "Software Engineer" `
  --posted-date ONE `
  --max-age-minutes 10 `
  --remote `
  --limit 5
```

Previously seen URLs are treated as duplicates and are not added again.

## View the queue

### List every job

```powershell
.\scripts\run.ps1 list
```

### Filter by status

```powershell
.\scripts\run.ps1 list --status pending
.\scripts\run.ps1 list --status in_progress
.\scripts\run.ps1 list --status applied
.\scripts\run.ps1 list --status blocked
.\scripts\run.ps1 list --status skipped
```

The list displays the database ID, status, title or URL, and company.

## Log in to Dice

```powershell
.\scripts\run.ps1 login
```

Opens the dedicated automation browser. Log in to Dice, complete MFA or CAPTCHA when required, return to PowerShell, and press Enter. The browser session is saved under `.local/browser-profile`.

The automation does not store your Dice password and does not attempt to bypass MFA or CAPTCHA.

## Run applications

### Process every pending job

```powershell
.\scripts\run.ps1 run
```

Processes pending jobs sequentially and automatically submits supported Dice Easy Apply applications. The resume is selected from the configured profile folder using a best-match keyword score across all resume rules. Specific multi-keyword matches beat broad matches, and minor spelling or word-spacing differences are tolerated.

Before each application, the terminal prints both the selected resume folder and filename:

```text
Resume folder: C:\path\to\Dice profiles\Data Engineer
Selected resume: Uday_Sujith_Resume.pdf
```

### Process a limited number

```powershell
.\scripts\run.ps1 run --limit 5
```

Processes at most five pending jobs.

### Process one job

```powershell
.\scripts\run.ps1 run --job-id 42
```

Processes only pending job ID `42`.

If the process is interrupted, the active job is returned to `pending`. The next run continues with pending work.

## Import job URLs from CSV

```powershell
.\scripts\run.ps1 import-csv jobs.csv
```

Expected CSV structure:

```csv
url,title,company,notes
https://www.dice.com/job-detail/example,Data Engineer,Example Inc,Optional note
```

Only `url` is required. Duplicate URLs are ignored.

To permit importing external ATS URLs:

```powershell
.\scripts\run.ps1 import-csv jobs.csv --allow-external
```

Allowing an external URL to be imported or opened does not make it eligible for automatic submission.

## Remove jobs

### Remove one job

```powershell
.\scripts\run.ps1 remove --job-id 42
```

### Remove jobs by status

```powershell
.\scripts\run.ps1 remove --status pending --yes
.\scripts\run.ps1 remove --status blocked --yes
.\scripts\run.ps1 remove --status applied --yes
```

### Clear the entire queue

```powershell
.\scripts\run.ps1 remove --all --yes
```

Bulk removal requires `--yes`. Before removing records, the program creates a timestamped SQLite backup under `.local`.

## Retry and repair commands

### Retry authentication failures

```powershell
.\scripts\run.ps1 retry-auth-blocked
```

Returns jobs blocked by an expired Dice session to `pending`. Run `login` before processing them again.

### Retry network failures

```powershell
.\scripts\run.ps1 retry-network-blocked
```

Returns jobs blocked by a local browser `ERR_NETWORK_ACCESS_DENIED` error to `pending`.

### Retry selector and wizard failures

```powershell
.\scripts\run.ps1 retry-selector-blocked
```

Returns jobs blocked by obsolete application-wizard selector and timing failures to `pending`.

### Recheck unconfirmed submissions

```powershell
.\scripts\run.ps1 retry-unconfirmed-submit
```

Returns jobs where Submit was clicked but no success confirmation appeared to `pending` for Dice status reconciliation.

### Repair historical false positives

```powershell
.\scripts\run.ps1 repair-false-applied
```

Resets records affected by the obsolete page-wide “already submitted” detector to `pending`.

## Export results

```powershell
.\scripts\run.ps1 export applications.csv
```

Exports job URLs, titles, companies, statuses, attempt counts, error information, and timestamps to a CSV file.

## Command help

```powershell
.\scripts\run.ps1 --help
.\scripts\run.ps1 discover --help
.\scripts\run.ps1 run --help
.\scripts\run.ps1 remove --help
```

## Direct Python form

Every command can also be invoked directly through the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m dice_copilot doctor
.\.venv\Scripts\python.exe -m dice_copilot list --status pending
```

Using `scripts\run.ps1` is shorter and is recommended for normal operation.

## Typical workflow

```powershell
# 1. Verify the installation and profile
.\scripts\run.ps1 doctor

# 2. Fetch five recent, unseen Easy Apply jobs
.\scripts\run.ps1 discover --keyword "Data Engineer" --posted-date ONE --remote --limit 5

# 3. Review the pending queue
.\scripts\run.ps1 list --status pending

# 4. Refresh the saved Dice login when necessary
.\scripts\run.ps1 login

# 5. Process the five jobs
.\scripts\run.ps1 run --limit 5

# 6. Review outcomes
.\scripts\run.ps1 list

# 7. Export a report
.\scripts\run.ps1 export applications.csv
```

## Safety behavior

- Only Dice-hosted Easy Apply applications are automatically submitted.
- Unknown required questions stop the application instead of guessing.
- Authentication walls, CAPTCHA, and MFA stop the run for manual resolution.
- Failed applications save screenshots under `.local/artifacts`.
- A Dice success confirmation is required before a job is recorded as applied.
- Jobs are processed sequentially with the cooldown configured in `config.json`.
