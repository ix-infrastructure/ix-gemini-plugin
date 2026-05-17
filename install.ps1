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

# Build and install MCP server
$nodePath = Get-Command "node" -ErrorAction SilentlyContinue
$npmPath = Get-Command "npm" -ErrorAction SilentlyContinue

if (-not $nodePath) {
    Write-Warning "node not found — skipping MCP server build. Install Node.js >= 18 and re-run."
} elseif (-not $npmPath) {
    Write-Warning "npm not found — skipping MCP server build."
} else {
    Write-Host "Building MCP server..."
    $mcpSrc = Join-Path $scriptDir "mcp"
    $mcpDest = Join-Path $targetDir "mcp"
    New-Item -ItemType Directory -Path $mcpDest -Force | Out-Null

    Push-Location $mcpSrc
    npm ci --silent
    npm run build --silent
    Pop-Location

    Copy-Item -Recurse (Join-Path $mcpSrc "dist") $mcpDest -Force
    Copy-Item (Join-Path $mcpSrc "package.json") $mcpDest
    Copy-Item (Join-Path $mcpSrc "package-lock.json") $mcpDest

    Push-Location $mcpDest
    npm ci --omit=dev --silent
    Pop-Location

    Write-Host "MCP server installed to $mcpDest"
}

Write-Host "Done. Restart Gemini CLI to activate the extension."
Write-Host ""
Write-Host "Verify with: gemini extensions list"
