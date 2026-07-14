#Requires -Version 5.1
# bootstrap.ps1 - One-command setup for Windows (PowerShell 5.1+).
# Usage: .\bootstrap.ps1
# Linux / macOS / WSL2 users: use bootstrap.sh instead.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# -- Helpers -------------------------------------------------------------------
function Write-Step  { Write-Host "  ▸ $args" -ForegroundColor Cyan }
function Write-OK    { Write-Host "  OK $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "  ⚠?  $args" -ForegroundColor Yellow }
function Write-Fail  { Write-Host "  NO $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host " Keyhole Developer Kit - bootstrap (Windows)" -ForegroundColor White
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray

# -- Execution policy guard ----------------------------------------------------
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -eq 'Restricted') {
    Write-Step "Setting execution policy to RemoteSigned for CurrentUser..."
    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
}

# -- Python version check ------------------------------------------------------
$python = $null
foreach ($cmd in @('python3.11', 'python3.12', 'python3.10', 'python3', 'python')) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        $verStr = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($verStr -match '^(\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 9) { $python = $cmd; break }
        }
    }
}
if (-not $python) { Write-Fail "Python 3.9+ not found. Install Python 3.11 from python.org and retry." }
$pyVer = & $python --version
Write-Step "Using: $pyVer"

# -- Virtual environment -------------------------------------------------------
if (-not (Test-Path '.venv')) {
    Write-Step "Creating virtual environment (.venv)..."
    & $python -m venv .venv
} else {
    Write-Step "Virtual environment already exists (.venv)"
}

$pip    = ".\.venv\Scripts\pip.exe"
$pipExe = Resolve-Path $pip -ErrorAction SilentlyContinue
if (-not $pipExe) { Write-Fail ".venv creation failed - $pip not found." }

# -- Install packages ----------------------------------------------------------
Write-Step "Upgrading pip..."
& $pip install --quiet --upgrade pip

Write-Step "Installing keyhole-sdk (editable)..."
& $pip install --quiet -e packages/python/keyhole-sdk

Write-Step "Installing keyhole-cli (editable)..."
& $pip install --quiet -e packages/python/keyhole-cli

Write-Step "Installing dev/test tools (pytest, ruff)..."
& $pip install --quiet pytest pytest-cov ruff

# -- Environment file ----------------------------------------------------------
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Step "Copied .env.example -> .env"
} else {
    Write-Step ".env already exists - skipping copy"
}

# -- Docker check --------------------------------------------------------------
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    $dockerVer = (docker --version) -replace "`n", ""
    Write-Step "Docker found: $dockerVer"
} else {
    Write-Warn "Docker not found - install Docker Desktop to run the test runtime."
}

Write-Host ""
Write-OK "Bootstrap complete."
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    .\.venv\Scripts\Activate.ps1    # activate the virtual environment"
Write-Host "    docker compose up -d             # start the local test runtime"
Write-Host "    keyhole doctor                   # verify your environment"
Write-Host "    keyhole --help                   # explore CLI commands"
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
