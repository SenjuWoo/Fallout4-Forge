[CmdletBinding()]
param(
  [string]$ToolsRoot,
  [string]$WorkspaceRoot,
  [switch]$SkipTools,
  [switch]$SkipTests,
  [switch]$NoAgentIntegration,
  [switch]$NoPath,
  [switch]$DryRun
)
# Fallout 4 Forge installer. The checkout is the install: a .venv here, a launcher under the forge home,
# one user PATH entry, the agent skill copied into the AI tools that exist. Running it again converges.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$forgeHome = $env:F4FORGE_HOME
if (-not $forgeHome) { $forgeHome = Join-Path $env:LOCALAPPDATA 'Fallout4Forge' }
$binDir = Join-Path $forgeHome 'bin'
$launcher = Join-Path $binDir 'f4forge.cmd'
$skillSrc = Join-Path $root 'skills\fallout4-forge'
# Same provider list as the bundle's most complete skill fan-out (Hermes, Claude, Codex, Grok, Kimi) plus ~/.agents.
$skillHomes = @(
  (Join-Path $env:LOCALAPPDATA 'hermes\skills'),
  (Join-Path $env:USERPROFILE '.claude\skills'),
  (Join-Path $env:USERPROFILE '.codex\skills'),
  (Join-Path $env:USERPROFILE '.agents\skills'),
  (Join-Path $env:USERPROFILE '.grok\skills'),
  (Join-Path $env:USERPROFILE '.kimi-code\skills'),
  (Join-Path $env:USERPROFILE '.kimi\skills')
) | Where-Object { Test-Path $_ }

function Step($text) { Write-Host "== $text" }

Step 'Fallout 4 Forge install'
Write-Host "checkout:   $root"
Write-Host "forge home: $forgeHome"
if ($DryRun) {
  Write-Host 'Dry run: nothing will be changed.'
  Write-Host "  venv:      $root\.venv (pip install -e this folder)"
  if (-not $SkipTests) { Write-Host '  tests:     tests\run_tests.py' }
  Write-Host "  launcher:  $launcher"
  if (-not $NoPath) { Write-Host "  user PATH: add $binDir once" }
  if ($ToolsRoot) { Write-Host "  config:    tools_root = $ToolsRoot" }
  if ($WorkspaceRoot) { Write-Host "  config:    workspace_root = $WorkspaceRoot" }
  if (-not $SkipTools) { Write-Host '  tools:     f4forge tools sync --approve' }
  Write-Host '  worker:    f4forge worker build (when a .NET SDK is present)'
  if ($NoAgentIntegration) { Write-Host '  skill:     skipped (-NoAgentIntegration)' }
  else { foreach ($t in $skillHomes) { Write-Host "  skill:     $t\fallout4-forge (a previous copy is backed up)" } }
  return
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'Python 3.10+ was not found on PATH. Install it from python.org and run this again.' }
& $py.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or newer is required.' }

Step 'virtual environment'
$venv = Join-Path $root '.venv'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
  & $py.Source -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed ($LASTEXITCODE)" }
}
& $vpy -m pip install --disable-pip-version-check --quiet -e $root
if ($LASTEXITCODE -ne 0) { throw "pip install failed ($LASTEXITCODE)" }

if (-not $SkipTests) {
  Step 'tests'
  & $vpy (Join-Path $root 'tests\run_tests.py')
  if ($LASTEXITCODE -ne 0) { throw "tests failed ($LASTEXITCODE)" }
}

Step 'launcher'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$lines = @(
  '@echo off',
  'setlocal EnableExtensions DisableDelayedExpansion',
  ('if not exist "{0}" goto :moved' -f $vpy),
  ('"{0}" -m f4forge %*' -f $vpy),
  'exit /b %ERRORLEVEL%',
  ':moved',
  'echo Fallout 4 Forge is no longer in the folder this launcher points to. 1>&2',
  'echo Run Install.ps1 from its current folder to repair the launcher. 1>&2',
  'exit /b 3'
)
[IO.File]::WriteAllText($launcher, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))
Write-Host "launcher: $launcher"
if (-not $NoPath) {
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not $userPath) { $userPath = '' }
  $parts = @($userPath -split ';' | Where-Object { $_ })
  if ($parts -notcontains $binDir) {
    [Environment]::SetEnvironmentVariable('Path', (($parts + $binDir) -join ';'), 'User')
    Write-Host "added $binDir to the user PATH; open a new terminal to use 'f4forge'"
  } else {
    Write-Host 'user PATH already has the launcher folder'
  }
}

Step 'config'
$cfgArgs = @('config')
if ($ToolsRoot) { $cfgArgs += @('--set', "tools_root=$ToolsRoot") }
if ($WorkspaceRoot) { $cfgArgs += @('--set', "workspace_root=$WorkspaceRoot") }
& $vpy -m f4forge @cfgArgs | Out-Null
if ($LASTEXITCODE -ne 0) { throw "f4forge config failed ($LASTEXITCODE)" }
if ($WorkspaceRoot -and -not (Test-Path (Join-Path $WorkspaceRoot 'WORKSPACE.md'))) {
  New-Item -ItemType Directory -Force -Path $WorkspaceRoot | Out-Null
  $ws = "# Fallout 4 mod workspace`n`nOne folder per mod (f4forge new). Game inputs are read-only.`n`n| Mod | Folder | Kinds | Version | State |`n|---|---|---|---|---|`n"
  [IO.File]::WriteAllText((Join-Path $WorkspaceRoot 'WORKSPACE.md'), $ws, (New-Object Text.UTF8Encoding($false)))
}

if (-not $SkipTools) {
  Step 'tools'
  & $vpy -m f4forge tools sync --approve | Out-Null
  if ($LASTEXITCODE -gt 1) { throw "tools sync failed ($LASTEXITCODE); see f4forge tools status" }
  if ($LASTEXITCODE -eq 1) { Write-Warning 'some tools did not sync; f4forge tools status names them' }
}

if (Get-Command dotnet -ErrorAction SilentlyContinue) {
  Step 'records worker'
  & $vpy -m f4forge worker build | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Warning "worker build failed ($LASTEXITCODE); records commands stay degraded until f4forge worker build succeeds" }
} else {
  Write-Host 'no .NET SDK: records worker skipped (records commands report degraded)'
}

if (-not $NoAgentIntegration) {
  Step 'agent skill'
  foreach ($t in $skillHomes) {
    $dest = Join-Path $t 'fallout4-forge'
    if (Test-Path $dest) {
      $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
      $backup = Join-Path $forgeHome ('skill-backup\' + (Split-Path (Split-Path $t -Parent) -Leaf) + "-$stamp")
      New-Item -ItemType Directory -Force -Path $backup | Out-Null
      Copy-Item -Recurse -Force $dest $backup
      Remove-Item -Recurse -Force $dest
    }
    Copy-Item -Recurse $skillSrc $dest
    Write-Host "skill: $dest"
  }
}

Step 'doctor'
& $vpy -m f4forge doctor | Out-Null
Write-Host "doctor exit code: $LASTEXITCODE (0 = ready; run f4forge doctor --pretty for details)"
Write-Host 'Done. Next: f4forge papyrus sources build, then f4forge index'
