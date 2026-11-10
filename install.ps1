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

# hooks.json starts the hooks with `python3`, which the python.org installer
# does not create (it provides `python` and the `py` launcher). Write the first
# interpreter that really runs Python 3 into the installed copy. Bare names
# only, so the command reads the same in any shell Gemini runs it with. The
# Microsoft Store alias for an uninstalled Python exits non-zero and is skipped.
function Find-HookPython {
    foreach ($candidate in @("python3", "python", "py -3")) {
        $parts = @($candidate -split " ")
        $found = Get-Command $parts[0] -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $found) { continue }
        $rest = @($parts | Select-Object -Skip 1)
        try {
            $major = & $found.Source @rest -c "import sys; print(sys.version_info[0])" 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -eq 0 -and "$major".Trim() -eq "3") {
            return $candidate
        }
    }
    return $null
}

$hookPython = Find-HookPython
if (-not $hookPython) {
    Write-Warning "No Python 3 found (tried python3, python, py -3). The hooks need one on PATH."
} elseif ($hookPython -ne "python3") {
    $hooksJson = Join-Path $hooksTarget "hooks.json"
    $text = [System.IO.File]::ReadAllText($hooksJson)
    $text = $text -replace '("command":\s*")python3 ', ('${1}' + $hookPython + ' ')
    # UTF-8 without a BOM: JSON.parse rejects one.
    [System.IO.File]::WriteAllText($hooksJson, $text, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "Hooks will run with '$hookPython'."
}

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
