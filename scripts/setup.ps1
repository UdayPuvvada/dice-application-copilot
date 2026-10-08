$ErrorActionPreference = "Stop"

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    $candidate = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($candidate) {
        $pythonExecutable = $candidate.FullName
    }
}
if (-not $pythonCommand -and -not $pythonExecutable) {
    throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/ and rerun this script."
}

if ($pythonCommand -and $pythonCommand.Name -eq "py.exe") {
    & $pythonCommand.Source -3 -m venv .venv
} else {
    if (-not $pythonExecutable) {
        $pythonExecutable = $pythonCommand.Source
    }
    & $pythonExecutable -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\python.exe -m playwright install chromium
& .\.venv\Scripts\python.exe -m playwright install winldd
& .\.venv\Scripts\python.exe -m pytest
Write-Host "Setup complete. Copy config.example.json to config.json, then run the commands in README.md."
