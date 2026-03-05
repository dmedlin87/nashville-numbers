<#
.SYNOPSIS
    Nashville Number System - runscript

.DESCRIPTION
    Handles venv setup, dependency installation, and launching the project.

.PARAMETER Command
    gui      Launch the browser GUI (default)
    convert  Run the CLI converter (pass remaining args as input)
    test     Run the test suite (pass remaining args to pytest)
    help     Show this help

.EXAMPLE
    .\run.ps1
    .\run.ps1 gui
    .\run.ps1 convert "C - F - G"
    .\run.ps1 convert "1 - 4 - 5 in G"
    .\run.ps1 test
    .\run.ps1 test -k golden
    .\run.ps1 test --cov
#>

param(
    [Parameter(Position = 0)]
    [string]$Command = "gui",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── paths ────────────────────────────────────────────────────────────────────
$ProjectRoot = $PSScriptRoot
$VenvDir     = Join-Path $ProjectRoot ".venv"
$VenvPython  = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip     = Join-Path $VenvDir "Scripts\pip.exe"

# ── helpers ──────────────────────────────────────────────────────────────────
function Write-Step([string]$msg) {
    Write-Host "  $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  $msg" -ForegroundColor Yellow
}

function Fail([string]$msg) {
    Write-Host "`n  ERROR: $msg" -ForegroundColor Red
    exit 1
}

# ── find a suitable Python (3.10+) ───────────────────────────────────────────
function Find-Python {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                    return $cmd
                }
            }
        } catch { }
    }

    # Try py launcher with explicit version
    foreach ($ver in @("3.12", "3.11", "3.10")) {
        try {
            $out = & py "-$ver" --version 2>&1
            if ($out -match "Python") { return "py -$ver" }
        } catch { }
    }

    return $null
}

# ── setup venv & deps ────────────────────────────────────────────────────────
function Initialize-Environment {
    # 1. Create venv if missing
    if (-not (Test-Path $VenvPython)) {
        Write-Step "Virtual environment not found - creating..."
        $pyCmd = Find-Python
        if (-not $pyCmd) {
            Fail "Python 3.10+ not found. Install from https://python.org and re-run."
        }
        $pyArgs = ($pyCmd -split " ") + @("-m", "venv", $VenvDir)
        & $pyArgs[0] $pyArgs[1..($pyArgs.Length-1)]
        if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment." }
        Write-Ok "Virtual environment created."
    }

    # 2. Install / sync the package if not present or pyproject.toml is newer
    $marker = Join-Path $VenvDir ".installed"
    $pyproject = Join-Path $ProjectRoot "pyproject.toml"
    $needsInstall = $false

    if (-not (Test-Path $marker)) {
        $needsInstall = $true
    } elseif ((Get-Item $pyproject).LastWriteTime -gt (Get-Item $marker).LastWriteTime) {
        Write-Warn "pyproject.toml changed - reinstalling..."
        $needsInstall = $true
    }

    if ($needsInstall) {
        Write-Step "Installing package and dev dependencies..."
        & $VenvPip install -q -e "$ProjectRoot[dev]"
        if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
        New-Item -ItemType File -Path $marker -Force | Out-Null
        Write-Ok "Dependencies installed."
    }
}

# ── show help ────────────────────────────────────────────────────────────────
function Show-Help {
    Write-Host ""
    Write-Host "  Nashville Number System - runscript" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  Usage:  .\run.ps1 [command] [args]" -ForegroundColor White
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor White
    Write-Host "    gui               Launch browser GUI (default)"
    Write-Host "    convert [input]   Convert a chord progression or NNS string"
    Write-Host "    test [args]       Run test suite (pytest args forwarded)"
    Write-Host "    help              Show this message"
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor White
    Write-Host '    .\run.ps1'
    Write-Host '    .\run.ps1 gui'
    Write-Host '    .\run.ps1 convert "C - F - G"'
    Write-Host '    .\run.ps1 convert "1 - 4 - 5 in G"'
    Write-Host '    .\run.ps1 test'
    Write-Host '    .\run.ps1 test --cov'
    Write-Host '    .\run.ps1 test -k golden'
    Write-Host ""
}

# ── main ─────────────────────────────────────────────────────────────────────
switch ($Command.ToLower()) {
    "help" {
        Show-Help
        exit 0
    }
    "gui" {
        Initialize-Environment
        Write-Ok "Launching GUI..."
        & $VenvPython -m nashville_numbers.gui
        exit $LASTEXITCODE
    }
    "convert" {
        Initialize-Environment
        if ($Rest.Count -eq 0) {
            Fail "No input provided. Example: .\run.ps1 convert `"C - F - G`""
        }
        & $VenvPython -m nashville_numbers.cli @Rest
        exit $LASTEXITCODE
    }
    "test" {
        Initialize-Environment
        Write-Ok "Running tests..."
        & $VenvPython -m pytest @Rest
        exit $LASTEXITCODE
    }
    default {
        Write-Warn "Unknown command: '$Command'"
        Show-Help
        exit 1
    }
}
