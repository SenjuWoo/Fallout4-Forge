[CmdletBinding()]
param(
  [switch]$RemoveHome,
  [switch]$KeepSkill
)
# Removes the launcher, the user PATH entry and the skill copies. The checkout, its .venv and the tools folder stay.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$forgeHome = $env:F4FORGE_HOME
if (-not $forgeHome) { $forgeHome = Join-Path $env:LOCALAPPDATA 'Fallout4Forge' }
$binDir = Join-Path $forgeHome 'bin'

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
  $parts = @($userPath -split ';' | Where-Object { $_ -and ($_ -ne $binDir) })
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}
if (Test-Path $binDir) { Remove-Item -Recurse -Force $binDir }
Write-Host 'launcher and PATH entry removed'

if (-not $KeepSkill) {
  $homes = @(
    (Join-Path $env:LOCALAPPDATA 'hermes\skills'),
    (Join-Path $env:USERPROFILE '.claude\skills'),
    (Join-Path $env:USERPROFILE '.codex\skills'),
    (Join-Path $env:USERPROFILE '.agents\skills'),
    (Join-Path $env:USERPROFILE '.grok\skills'),
    (Join-Path $env:USERPROFILE '.kimi-code\skills'),
    (Join-Path $env:USERPROFILE '.kimi\skills')
  )
  foreach ($h in $homes) {
    $t = Join-Path $h 'fallout4-forge'
    $skill = Join-Path $t 'SKILL.md'
    if ((Test-Path $skill) -and ((Get-Content $skill -Raw) -match 'name: fallout4-forge')) {
      Remove-Item -Recurse -Force $t
      Write-Host "skill removed: $t"
    }
  }
}

if ($RemoveHome -and (Test-Path $forgeHome)) {
  Remove-Item -Recurse -Force $forgeHome
  Write-Host "forge home removed: $forgeHome"
} else {
  Write-Host "kept config, caches, index and worker in $forgeHome (use -RemoveHome to delete)"
}
Write-Host "the checkout and its .venv stay in $root; the tools folder is untouched"
