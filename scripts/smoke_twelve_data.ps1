[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-SmokeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    Write-Host "`n> $($Command -join ' ')"
    if ($Command.Count -eq 1) {
        & $Command[0]
    }
    else {
        & $Command[0] @($Command[1..($Command.Count - 1)])
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

function Remove-SmokePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($env:TWELVE_DATA_API_KEY)) {
    throw "TWELVE_DATA_API_KEY must be set before running the smoke workflow."
}

$cacheRoot = Join-Path $repoRoot ".market-platform\cache"
$smokeOutputRoot = Join-Path $repoRoot "tmp\smoke_twelve_data"
$dailyStart = [DateTime]::UtcNow.Date.AddDays(-10).ToString("yyyy-MM-dd")
$dailyEnd = [DateTime]::UtcNow.Date.AddDays(-1).ToString("yyyy-MM-dd")

$dailyCachePath = Join-Path $cacheRoot "daily\twelvedata\MSFT\${dailyStart}__${dailyEnd}.csv"
$latestCachePath = Join-Path $cacheRoot "latest\twelvedata\MSFT\latest.csv"
$intradayCachePath = Join-Path $cacheRoot "intraday\twelvedata\AAPL\recent-1d__5min.csv"

$dailyOutput = Join-Path $smokeOutputRoot "daily.json"
$latestOutput = Join-Path $smokeOutputRoot "latest.txt"
$intradayOutput = Join-Path $smokeOutputRoot "intraday.csv"

Remove-SmokePath $dailyCachePath
Remove-SmokePath $latestCachePath
Remove-SmokePath $intradayCachePath
Remove-SmokePath $smokeOutputRoot

try {
    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "providers", "health",
        "--provider", "twelve_data",
        "--format", "table"
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "fetch",
        "--symbol", "MSFT",
        "--start", $dailyStart,
        "--end", $dailyEnd,
        "--provider", "twelve_data",
        "--format", "json",
        "--cache", "--refresh",
        "--output", $dailyOutput
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "fetch",
        "--symbol", "MSFT",
        "--start", $dailyStart,
        "--end", $dailyEnd,
        "--provider", "twelve_data",
        "--format", "json",
        "--cache",
        "--output", $dailyOutput
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "latest",
        "--symbol", "MSFT",
        "--provider", "twelve_data",
        "--format", "table",
        "--cache", "--refresh",
        "--output", $latestOutput
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "latest",
        "--symbol", "MSFT",
        "--provider", "twelve_data",
        "--format", "table",
        "--cache",
        "--output", $latestOutput
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "intraday",
        "--symbol", "AAPL",
        "--interval", "5min",
        "--provider", "twelve_data",
        "--format", "csv",
        "--cache", "--refresh",
        "--output", $intradayOutput
    )

    Invoke-SmokeCommand @(
        "uv", "run", "market-platform", "data", "intraday",
        "--symbol", "AAPL",
        "--interval", "5min",
        "--provider", "twelve_data",
        "--format", "csv",
        "--cache",
        "--output", $intradayOutput
    )
}
finally {
    Remove-SmokePath $dailyCachePath
    Remove-SmokePath $latestCachePath
    Remove-SmokePath $intradayCachePath
    Remove-SmokePath $smokeOutputRoot
}
