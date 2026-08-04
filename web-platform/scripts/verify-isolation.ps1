$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$changed = git -C $root diff --name-only HEAD
$outside = $changed | Where-Object { $_ -and -not $_.StartsWith("web-platform/") }
if ($outside) {
    Write-Error ("Files outside web-platform changed:`n" + ($outside -join "`n"))
}
Write-Output "Isolation check passed: tracked changes are confined to web-platform/."
