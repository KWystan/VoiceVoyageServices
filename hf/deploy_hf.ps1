# Deploy a service to a Hugging Face Docker Space.
#
# Each Space is a standalone repo with a root `Dockerfile` + the service
# directory.  This script assembles that repo in a temp folder (OUTSIDE the
# monorepo, so the nested .git never conflicts) and pushes it to the Space.
#
# Usage (PowerShell):
#   .\hf\deploy_hf.ps1 -Username KWystan -SpaceName voice-voyage-phoneme -Service phoneme
#   .\hf\deploy_hf.ps1 -Username KWystan -SpaceName voice-voyage-modules -Service modules
#
# Requirements:
#   1. Create each Space first in the browser:
#      https://huggingface.co/new-space  ->  SDK: Docker, Hardware: CPU Basic (free)
#   2. `huggingface-cli login` (or `hf auth login`) once — pushes use your token.
#   3. For the MODULES Space: add ZEN_API_KEY under Settings -> Variables and secrets.
#
# Prereq check:
param(
    [Parameter(Mandatory=$true)][string]$Username,
    [Parameter(Mandatory=$true)][string]$SpaceName,
    [Parameter(Mandatory=$true)][ValidateSet("phoneme","modules")][string]$Service,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$spaceDir = Join-Path (Split-Path $repoRoot -Parent) "hf-space-$SpaceName"

# --- 1. Which service files + Dockerfile template ---------------------------
switch ($Service) {
    "phoneme" {
        $serviceDir  = Join-Path $repoRoot "phoneme_service"
        $dockerTpl   = Join-Path $PSScriptRoot "Dockerfile.phoneme"
        $title       = "Voice Voyage - Phoneme Assessment"
    }
    "modules" {
        $serviceDir  = Join-Path $repoRoot "dynamic_modules_service"
        $dockerTpl   = Join-Path $PSScriptRoot "Dockerfile.modules"
        $title       = "Voice Voyage - Dynamic Practice Modules"
    }
}

Write-Host "==> Building Space repo for '$SpaceName' (service: $Service)"
Write-Host "    local folder: $spaceDir"

# --- 2. Assemble the Space repo ---------------------------------------------
if (Test-Path $spaceDir) { Remove-Item -Recurse -Force $spaceDir }
New-Item -ItemType Directory -Path $spaceDir | Out-Null
Copy-Item -Recurse -Force $serviceDir (Join-Path $spaceDir ($serviceDir | Split-Path -Leaf))
Copy-Item -Force $dockerTpl (Join-Path $spaceDir "Dockerfile")

# README.md with the Docker Space frontmatter
if ($Service -eq 'phoneme') { $emoji = 'mic' } else { $emoji = 'puzzle' }
@"
---
title: $title
emoji: $emoji
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# $title

Serverless container for the Voice Voyage thesis backend ($Service service).
"@ | Set-Content -Path (Join-Path $spaceDir "README.md") -Encoding utf8

# Keep secrets/build junk out of the Space repo
@"
.env
__pycache__/
*.py[cod]
.pytest_cache/
tests/
records/
scripts/
docs/
models/
archive/
.agents/
"@ | Set-Content -Path (Join-Path $spaceDir ".gitignore") -Encoding utf8

Write-Host "    files staged:"
Get-ChildItem $spaceDir | Select-Object -ExpandProperty Name | ForEach-Object { Write-Host "      $_" }

# --- 3. Git init + push ------------------------------------------------------
if ($DryRun) {
    Write-Host ""
    Write-Host "==> DRY RUN: Space repo assembled. Push skipped."
    Write-Host "    Public URL once built: https://$($Username.ToLower())-$($SpaceName.ToLower()).hf.space"
    exit 0
}

git -C $spaceDir init -q
git -C $spaceDir add -A
git -C $spaceDir -c user.name=$Username -c user.email="$Username@users.noreply.huggingface.co" commit -q -m "Deploy $Service service"
git -C $spaceDir remote add origin "https://huggingface.co/spaces/$Username/$SpaceName"
Write-Host "==> Pushing to https://huggingface.co/spaces/$Username/$SpaceName"
Write-Host "    (enter your HF token when prompted, or use 'git credential' from hf auth login)"
git -C $spaceDir push -u origin main

Write-Host ""
Write-Host "==> Done. Your Space builds automatically:"
Write-Host "    https://huggingface.co/spaces/$Username/$SpaceName"
Write-Host "    Public URL once built: https://$($Username.ToLower())-$($SpaceName.ToLower()).hf.space"
