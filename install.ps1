# Copyright 2026 Ix Infrastructure Inc.

[CmdletBinding()]
param(
    [string]$Repo,
    [switch]$Force,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Show-Help {
    @"
ix-gemini-plugin installer

Usage:
  .\install.ps1
  .\install.ps1 -Repo C:\path\to\project
  .\install.ps1 -Force
  .\install.ps1 -Help

Options:
  -Repo <path>   Install into <path>\.gemini\extensions\ix-memory\
  -Force         Overwrite an existing installation
  -Help          Show this message
"@
}

if ($Help) {
    Show-Help
    exit 0
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetBase = if ($Repo) {
    Join-Path (Resolve-Path $Repo).Path ".gemini"
} else {
    Join-Path $HOME ".gemini"
}
$targetDir = Join-Path $targetBase "extensions\ix-memory"

if ((Test-Path $targetDir) -and -not $Force) {
    Write-Host "Extension already installed at $targetDir"
    Write-Host "Use -Force to overwrite."
    exit 1
}

Write-Host "Installing ix-memory extension to $targetDir ..."

if (Test-Path $targetDir) {
    Remove-Item $targetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

Copy-Item (Join-Path $scriptDir "gemini-extension.json") $targetDir

$hooksTarget = Join-Path $targetDir "hooks"
New-Item -ItemType Directory -Path $hooksTarget -Force | Out-Null
Copy-Item (Join-Path $scriptDir "hooks\*.py") $hooksTarget
Copy-Item (Join-Path $scriptDir "hooks\hooks.json") $hooksTarget

$skillsTarget = Join-Path $targetDir "skills"
Get-ChildItem (Join-Path $scriptDir "skills") -Directory | ForEach-Object {
    $skillDoc = Join-Path $_.FullName "SKILL.md"
    if (Test-Path $skillDoc) {
        $destDir = Join-Path $skillsTarget $_.Name
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item $skillDoc (Join-Path $destDir "SKILL.md")
    }
}

$agentsTarget = Join-Path $targetDir "agents"
New-Item -ItemType Directory -Path $agentsTarget -Force | Out-Null
Copy-Item (Join-Path $scriptDir "agents\*.md") $agentsTarget

Copy-Item (Join-Path $scriptDir "GEMINI.md") $targetDir

# The MCP server is the Ix CLI's own (`ix mcp --tools=all`, declared in
# gemini-extension.json), so there is nothing to build. `--tools` arrived in
# Ix 0.11.0; an older CLI rejects it and the server never starts.
$ixPath = Get-Command "ix" -ErrorAction SilentlyContinue
if (-not $ixPath) {
    Write-Warning "ix not found on PATH. Install the Ix CLI (>= 0.11.0) for the MCP tools and hooks."
} elseif (-not ((& ix mcp --help 2>$null) -match "--tools")) {
    Write-Warning "This ix has no 'ix mcp --tools'. Run 'ix upgrade' (needs >= 0.11.0)."
}

Write-Host "Done. Restart Gemini CLI to activate the extension."
Write-Host ""
Write-Host "Verify with: gemini extensions list"
