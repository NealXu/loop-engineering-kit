param(
  [ValidateSet("Codex","Claude","Both")][string]$Target = "Both",
  [ValidateSet("User","Project")][string]$Scope = "User",
  [string]$ProjectRoot = (Get-Location).Path,
  [switch]$Upgrade
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackupStamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ($Scope -eq "User") {
  $CodexRoot = Join-Path $HOME ".codex"
  $CodexSkills = Join-Path $HOME ".agents\skills"
  $ClaudeRoot = Join-Path $HOME ".claude"
} else {
  $CodexRoot = Join-Path $ProjectRoot ".codex"
  $CodexSkills = Join-Path $ProjectRoot ".agents\skills"
  $ClaudeRoot = Join-Path $ProjectRoot ".claude"
}
function Copy-TreeFilesSafe($Source, $Destination) {
  Get-ChildItem -Path $Source -File -Recurse | Where-Object {
    $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -ne '.pyc'
  } | ForEach-Object {
    $Relative = $_.FullName.Substring($Source.Length).TrimStart([char[]]@('\','/'))
    $DestFile = Join-Path $Destination $Relative
    if (Test-Path $DestFile) {
      if (-not $Upgrade) { Write-Warning "Skipped existing file: $DestFile"; return }
      $Backup = "$DestFile.bak-$BackupStamp"
      Copy-Item $DestFile $Backup
      Write-Host "Backed up: $Backup"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestFile) | Out-Null
    Copy-Item $_.FullName $DestFile -Force
    Write-Host "Installed: $DestFile"
  }
}
function Retire-LegacyFile($Path) {
  if (-not $Upgrade -or -not (Test-Path $Path)) { return }
  $Backup = "$Path.bak-$BackupStamp"
  Move-Item -LiteralPath $Path -Destination $Backup
  Write-Host "Retired legacy file: $Backup"
}
if ($Target -in @("Codex","Both")) {
  Copy-TreeFilesSafe (Join-Path $RepoRoot ".codex\agents") (Join-Path $CodexRoot "agents")
  Retire-LegacyFile (Join-Path $CodexRoot "agents\implementer.toml")
  Copy-TreeFilesSafe (Join-Path $RepoRoot ".agents\skills\loop-engineering") (Join-Path $CodexSkills "loop-engineering")
  foreach ($Package in @("core","roles","workflows","packs","loop_engineering")) {
    Copy-TreeFilesSafe (Join-Path $RepoRoot $Package) (Join-Path $CodexSkills "loop-engineering\$Package")
  }
}
if ($Target -in @("Claude","Both")) {
  Copy-TreeFilesSafe (Join-Path $RepoRoot ".claude\agents") (Join-Path $ClaudeRoot "agents")
  Retire-LegacyFile (Join-Path $ClaudeRoot "agents\implementer.md")
  Copy-TreeFilesSafe (Join-Path $RepoRoot ".claude\skills\loop-engineering") (Join-Path $ClaudeRoot "skills\loop-engineering")
  foreach ($Package in @("core","roles","workflows","packs","loop_engineering")) {
    Copy-TreeFilesSafe (Join-Path $RepoRoot $Package) (Join-Path $ClaudeRoot "skills\loop-engineering\$Package")
  }
}
if ($Upgrade) {
  Write-Host "Done. Existing managed files were backed up and upgraded."
} else {
  Write-Host "Done. Existing files were not overwritten."
}
Write-Host "Merge AGENTS.md / CLAUDE.md manually; this installer does not replace them."
