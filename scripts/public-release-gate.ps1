param(
    [switch]$SkipInstall,
    [switch]$IncludeLiveProof,
    [switch]$RunGoverned,
    [switch]$AllowLocalGeneratedState
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$IsWindowsPlatform = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)

if ($IsWindowsPlatform) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
else {
    $VenvPython = Join-Path $RepoRoot ".venv/bin/python"
}

$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host ""
    Write-Host ":: $Name"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Keyhole {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $CliArguments = @("-m", "keyhole_cli.cli") + $Arguments
    Invoke-External $Name $Python $CliArguments
}

function Assert-NoForbiddenPublicText {
    $Rg = Get-Command rg -ErrorAction SilentlyContinue
    if (-not $Rg) {
        throw "ripgrep (rg) is required for the public sanitation scan."
    }

    $Forbidden = @(
        ("anaconda" + "3"),
        ("C:" + "\\Users\\natha"),
        ("\\." + "local" + "\\" + "bin"),
        ("keyhole login " + "--device"),
        ("governed run --repo-dir " + "\\.\\my-first-app"),
        ("repo register --path " + "my-first-app"),
        ("context compile --repo-dir " + "my-first-app"),
        ("pyyaml is a soft " + "dependency"),
        ("not in pyproject" + "\\.toml")
    )
    $Pattern = $Forbidden -join "|"
    $Targets = @("README.md", "docs", "packages", "my-first-app", "examples", "tests", "scripts")

    Write-Host ""
    Write-Host ":: Public text sanitation scan"
    & $Rg.Source "-n" $Pattern @Targets "-g" "!*__pycache__*"
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0) {
        throw "Public sanitation scan found local-path or stale-command text."
    }
    if ($ExitCode -gt 1) {
        throw "Public sanitation scan failed with exit code $ExitCode."
    }
}

function Assert-GeneratedStatePolicy {
    $GeneratedPaths = @(
        ".keyhole",
        "proof_bundle",
        "examples/second-governed-app/.keyhole",
        "examples/second-governed-app/proof_bundle",
        "my-first-app/.keyhole",
        "my-first-app/proof_bundle"
    )

    $Tracked = @()
    $Git = Get-Command git -ErrorAction SilentlyContinue
    if ($Git) {
        $TrackedOutput = & $Git.Source "ls-files" "--" @GeneratedPaths
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect tracked generated state with git ls-files."
        }
        $Tracked = @($TrackedOutput | Where-Object { $_ })
    }
    else {
        throw "git is required for the generated state tracking scan."
    }

    if ($Tracked.Count -gt 0) {
        throw "Generated governance artifacts are tracked by Git: $($Tracked -join ', ')"
    }

    $Present = @()
    foreach ($RelativePath in $GeneratedPaths) {
        $FullPath = Join-Path $RepoRoot $RelativePath
        if (Test-Path -LiteralPath $FullPath) {
            $Present += $RelativePath
        }
    }

    if ($Present.Count -eq 0) {
        return
    }

    $Message = "Generated local governance artifacts are present: " + ($Present -join ", ")
    if (-not $AllowLocalGeneratedState) {
        Write-Warning "$Message. These paths are untracked/ignored; do not commit them."
    }
    else {
        Write-Warning "$Message. Allowed for this local run; do not commit these paths."
    }
}

if (-not $SkipInstall) {
    Invoke-External "Install editable SDK and CLI" $Python @(
        "-m", "pip", "install",
        "-e", "packages/python/keyhole-sdk",
        "-e", "packages/python/keyhole-cli",
        "pytest",
        "setuptools",
        "wheel"
    )
    Invoke-External "Install test runtime requirements" $Python @(
        "-m", "pip", "install",
        "-r", "services/test-runtime/requirements.txt"
    )
}

$Wheelhouse = Join-Path $RepoRoot ".release-wheelhouse"
if (Test-Path -LiteralPath $Wheelhouse) {
    Remove-Item -LiteralPath $Wheelhouse -Recurse -Force
}
New-Item -ItemType Directory -Path $Wheelhouse | Out-Null
try {
    Invoke-External "Package wheel smoke" $Python @(
        "-m", "pip", "wheel",
        "--no-build-isolation",
        "--no-cache-dir",
        "--no-deps",
        "--wheel-dir", $Wheelhouse,
        "packages/python/keyhole-sdk",
        "packages/python/keyhole-cli"
    )
}
finally {
    if (Test-Path -LiteralPath $Wheelhouse) {
        Remove-Item -LiteralPath $Wheelhouse -Recurse -Force
    }
}

Invoke-External "Unit tests" $Python @(
    "-m", "pytest",
    "tests/unit",
    "-q",
    "--basetemp", ".pytest-tmp"
)

Invoke-Keyhole "Validate blessed governed example" @(
    "validate",
    "examples/second-governed-app",
    "--json"
)

Invoke-Keyhole "Validate legacy evidence app" @(
    "validate",
    "my-first-app",
    "--json"
)

Assert-NoForbiddenPublicText
Assert-GeneratedStatePolicy

if ($IncludeLiveProof) {
    Invoke-Keyhole "Live identity preflight" @("whoami", "--json")
    Invoke-Keyhole "Live surface negotiation" @("surfaces", "--json", "--refresh")
    Invoke-Keyhole "Live launch doctor" @(
        "doctor",
        "launch",
        "--repo-dir",
        "examples/second-governed-app",
        "--json"
    )

    if ($RunGoverned) {
        Invoke-Keyhole "Live governed run" @(
            "governed",
            "run",
            "--repo-dir",
            "examples/second-governed-app",
            "--json"
        )
    }

    Invoke-Keyhole "Live governed status" @(
        "governed",
        "status",
        "--repo-dir",
        "examples/second-governed-app",
        "--last",
        "--json"
    )

    Invoke-Keyhole "Live governed receipt" @(
        "governed",
        "receipt",
        "--repo-dir",
        "examples/second-governed-app",
        "--last",
        "--json"
    )
}
else {
    Write-Host ""
    Write-Host ":: Live proof skipped"
    Write-Host "Run with -IncludeLiveProof after device login. Add -RunGoverned only when a new live governed receipt is intended."
}

Write-Host ""
Write-Host "Public release gate completed."
