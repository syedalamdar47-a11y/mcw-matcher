<#
    Pushes the gateway's secrets from .env.local into Fly, without ever printing
    them and without putting them in your PowerShell history.

    Why a script instead of typing `fly secrets set SP_Password=...` by hand:
    a password typed on a command line lands in PSReadLine's history file in
    your profile, in plain text, forever. This reads the values from the file
    you already created and passes them straight to flyctl.

    Usage (from the sp-gateway folder):
        .\deploy\set-secrets.ps1
        .\deploy\set-secrets.ps1 -App mcw-sp-gateway -EnvFile "D:\Clinican Modeliaitlities\.env.local"
#>

param(
    [string]$App = "mcw-sp-gateway",
    [string]$EnvFile = "$PSScriptRoot\..\..\.env.local",

    # The SimplePractice login is NOT pushed unless you ask for it explicitly.
    #
    # The moment this host holds credentials that can reach patient records, it
    # becomes a HIPAA business associate and the Fly BAA needs to be in place.
    # The public availability lane needs no login at all, so the whole platform
    # can be deployed and proven before that point. Making the safe path the
    # default means nobody has to remember the ordering.
    [switch]$IncludeSimplePracticeLogin
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
    exit 1
}

# Only these keys are forwarded. A stray variable in .env.local is not pushed to
# the cloud just because it happens to live in the same file.
$Wanted = @(
    "SP_SESSION_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY"
)
if ($IncludeSimplePracticeLogin) {
    $Wanted += @("SP_Email", "SP_Password")
    Write-Warning "Pushing the SimplePractice login to Fly. Confirm the Fly BAA is signed first."
}

$pairs = @{}
foreach ($line in Get-Content $EnvFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
    $idx = $trimmed.IndexOf("=")
    $key = $trimmed.Substring(0, $idx).Trim()
    $val = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
    if ($Wanted -contains $key -and $val -ne "") { $pairs[$key] = $val }
}

if ($pairs.Count -eq 0) {
    Write-Error "No recognised secrets found in $EnvFile"
    exit 1
}

# Report names only. Never values.
Write-Output "Setting $($pairs.Count) secret(s) on app '$App':"
foreach ($k in ($pairs.Keys | Sort-Object)) {
    Write-Output ("  - {0}  ({1} chars, value not shown)" -f $k, $pairs[$k].Length)
}

$missing = $Wanted | Where-Object { -not $pairs.ContainsKey($_) }
if ($missing.Count -gt 0) {
    Write-Output ""
    Write-Output "Not set (add to .env.local if needed): $($missing -join ', ')"
}

# Build args as an array so values are never interpolated into a command string
# that could be logged or echoed.
$flyArgs = @("secrets", "set", "--app", $App, "--stage")
foreach ($k in $pairs.Keys) { $flyArgs += ("{0}={1}" -f $k, $pairs[$k]) }

Write-Output ""
Write-Output "Staging secrets (they apply on the next deploy)..."
& fly @flyArgs
if ($LASTEXITCODE -ne 0) { Write-Error "flyctl failed with exit code $LASTEXITCODE"; exit $LASTEXITCODE }

Write-Output ""
Write-Output "Done. Verify names only with:  fly secrets list --app $App"
Write-Output "(Fly shows a digest, never the value - that is expected.)"
