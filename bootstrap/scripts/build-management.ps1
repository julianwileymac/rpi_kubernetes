# =============================================================================
# Build Management Images - Windows Wrapper
# =============================================================================
# Version: 1.0.0
#
# Copies the repository to the control plane via SCP and triggers the
# build-management.sh script via SSH. Can also be run directly on the
# control plane in local mode.
#
# Usage:
#   .\build-management.ps1                                     # Full build via SSH
#   .\build-management.ps1 -ControlPlaneHost "julia@192.168.12.112"
#   .\build-management.ps1 -BackendOnly                        # Backend only
#   .\build-management.ps1 -FrontendOnly                       # Frontend only
#   .\build-management.ps1 -SkipSync                           # Skip rsync, just build
#   .\build-management.ps1 -LocalMode                          # Run locally (on control plane)
#
# Prerequisites:
#   - SSH access to control plane
#   - Docker installed on control plane
#   - k3s installed on control plane
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$ControlPlaneHost = "julia@192.168.12.112",

    [Parameter(Mandatory=$false)]
    [string]$SshKey = "",

    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = "~/rpi_kubernetes",

    [Parameter(Mandatory=$false)]
    [switch]$BackendOnly = $false,

    [Parameter(Mandatory=$false)]
    [switch]$FrontendOnly = $false,

    [Parameter(Mandatory=$false)]
    [switch]$SkipSync = $false,

    [Parameter(Mandatory=$false)]
    [switch]$NoRestart = $false,

    [Parameter(Mandatory=$false)]
    [switch]$LocalMode = $false
)

$ErrorActionPreference = "Continue"

# =============================================================================
# Helpers
# =============================================================================

function Write-Step {
    param([int]$Number, [string]$Message)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  Step $Number`: $Message" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "  [OK]   $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [INFO] $Message" -ForegroundColor White
}

function Get-SshArgs {
    $args_str = "-o StrictHostKeyChecking=no -o ConnectTimeout=15"
    if (-not [string]::IsNullOrEmpty($SshKey)) {
        $keyPath = $SshKey
        if ($keyPath.StartsWith("~")) { $keyPath = $keyPath.Replace("~", $HOME) }
        $args_str += " -i `"$keyPath`""
    }
    return $args_str
}

function Invoke-SSH {
    param([string]$Command)
    $sshArgs = Get-SshArgs
    $cmd = "ssh $sshArgs $ControlPlaneHost `"$Command`""
    try {
        $output = Invoke-Expression $cmd 2>&1
        return @{ Success = ($LASTEXITCODE -eq 0); Output = ($output -join "`n") }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

function Invoke-SCP {
    param([string]$Source, [string]$Destination)
    $sshArgs = Get-SshArgs
    $cmd = "scp -r $sshArgs `"$Source`" `"${ControlPlaneHost}:${Destination}`""
    try {
        $output = Invoke-Expression $cmd 2>&1
        return @{ Success = ($LASTEXITCODE -eq 0); Output = ($output -join "`n") }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

# =============================================================================
# Main
# =============================================================================

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "  Management Image Builder v1.0.0" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

# Locate repo root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path "$scriptDir\..\..").Path
Write-Info "Local repo root: $repoRoot"

if ($LocalMode) {
    Write-Info "Running in local mode"

    $buildArgs = ""
    if ($BackendOnly)  { $buildArgs += " --backend-only" }
    if ($FrontendOnly) { $buildArgs += " --frontend-only" }
    if ($NoRestart)    { $buildArgs += " --no-restart" }

    $buildScript = Join-Path $repoRoot "bootstrap\scripts\build-management.sh"
    if (Test-Path $buildScript) {
        bash "$buildScript" $buildArgs
    } else {
        Write-Fail "Build script not found at: $buildScript"
        exit 1
    }
    exit 0
}

# -------------------------------------------------------------------------
# Step 1: Test SSH connection
# -------------------------------------------------------------------------
Write-Step 1 "Test SSH connection to $ControlPlaneHost"

$result = Invoke-SSH "echo OK"
if ($result.Success -and $result.Output -match "OK") {
    Write-OK "SSH connection successful"
} else {
    Write-Fail "Cannot connect to $ControlPlaneHost via SSH"
    Write-Info "Ensure SSH key is configured and the host is reachable"
    exit 1
}

# -------------------------------------------------------------------------
# Step 2: Sync repository files
# -------------------------------------------------------------------------
if (-not $SkipSync) {
    Write-Step 2 "Sync repository to control plane"

    # Create remote directory
    Invoke-SSH "mkdir -p $RemoteDir"

    # Sync management directory
    Write-Info "Syncing management/backend..."
    $result = Invoke-SCP "$repoRoot\management\backend" "$RemoteDir/management/"
    if ($result.Success) {
        Write-OK "Backend synced"
    } else {
        Write-Fail "Backend sync failed: $($result.Output)"
        exit 1
    }

    Write-Info "Syncing management/frontend..."
    $result = Invoke-SCP "$repoRoot\management\frontend" "$RemoteDir/management/"
    if ($result.Success) {
        Write-OK "Frontend synced"
    } else {
        Write-Fail "Frontend sync failed: $($result.Output)"
        exit 1
    }

    # Sync build script
    Write-Info "Syncing build script..."
    Invoke-SSH "mkdir -p $RemoteDir/bootstrap/scripts"
    $result = Invoke-SCP "$repoRoot\bootstrap\scripts\build-management.sh" "$RemoteDir/bootstrap/scripts/"
    if ($result.Success) {
        Write-OK "Build script synced"
    } else {
        Write-Fail "Build script sync failed"
        exit 1
    }
} else {
    Write-Step 2 "Sync repository (skipped -- using existing files on control plane)"
}

# -------------------------------------------------------------------------
# Step 3: Run build on control plane
# -------------------------------------------------------------------------
Write-Step 3 "Build images on control plane"

$buildArgs = "--repo-dir $RemoteDir"
if ($BackendOnly)  { $buildArgs += " --backend-only" }
if ($FrontendOnly) { $buildArgs += " --frontend-only" }
if ($NoRestart)    { $buildArgs += " --no-restart" }

Write-Info "Running: bash $RemoteDir/bootstrap/scripts/build-management.sh $buildArgs"

$result = Invoke-SSH "chmod +x $RemoteDir/bootstrap/scripts/build-management.sh && bash $RemoteDir/bootstrap/scripts/build-management.sh $buildArgs"

# Stream output
if ($result.Output) {
    $result.Output -split "`n" | ForEach-Object { Write-Host "  $_" }
}

if ($result.Success) {
    Write-OK "Build completed successfully!"
} else {
    Write-Fail "Build failed on control plane"
    exit 1
}

# -------------------------------------------------------------------------
# Step 4: Verify
# -------------------------------------------------------------------------
Write-Step 4 "Verify pod status"

$statusResult = Invoke-Expression "kubectl get pods -n management 2>&1"
Write-Info "Management pod status:"
$statusResult -split "`n" | ForEach-Object { Write-Host "    $_" }

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  Build Complete" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""
Write-Info "If pods are still failing, check with:"
Write-Info "  .\debug-pods.ps1 -Namespace management"
Write-Host ""
