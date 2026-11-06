# Import a disc dump: verify it, then point the title config at it.
#
#   .\tools\import-disc.ps1 -Gdi "D:\dumps\draconus.gdi"
#   .\tools\import-disc.ps1 -Gdi "..." -WhatIf      # verify only
#
# The dump stays where it is; only the (git-ignored) engine-side config is written.
param(
    [Parameter(Mandatory = $true)][string]$Gdi,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tool = Join-Path $root "tools\draconus-disc"
$toml = Join-Path $root "engine\games\draconus\draconus.toml"

if (-not (Test-Path -LiteralPath $Gdi)) { throw "no such dump: $Gdi" }
$Gdi = (Resolve-Path -LiteralPath $Gdi).Path

Write-Host "verifying $Gdi"
Push-Location $tool
try {
    python -m dracdisc verify $Gdi
    if ($LASTEXITCODE -ne 0) { throw "verification failed: this is not a Draconus (USA V1.000) dump" }
} finally {
    Pop-Location
}

if ($WhatIf) {
    Write-Host "verified; not writing the config (-WhatIf)"
    return
}

if (-not (Test-Path -LiteralPath $toml)) {
    Write-Host "no engine config yet: run .\setup.ps1 first"
    return
}

# Only the image line is touched, and only in the engine copy, which is git-ignored.
$lines = Get-Content -LiteralPath $toml
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*image\s*=') {
        $lines[$i] = 'image = "' + $Gdi.Replace('\', '/') + '"'
        $found = $true
        break
    }
}
if (-not $found) { throw "no image line in $toml" }
Set-Content -LiteralPath $toml -Value $lines -Encoding UTF8

Write-Host "configured: $toml"
Write-Host "next: .\play-draconus.bat"
