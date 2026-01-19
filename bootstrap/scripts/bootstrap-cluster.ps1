# =============================================================================
# Windows Bootstrap Orchestrator for RPi Kubernetes Cluster
# =============================================================================
# Version: 1.0.0
#
# Replaces Ansible bootstrap.yml functionality using pure SSH/PowerShell.
# Bootstraps all cluster nodes (control plane and workers) for k3s installation.
#
# Usage:
#   .\bootstrap-cluster.ps1 -ControlPlane "ubuntu@192.168.1.100" -Workers @("julian@192.168.1.101","julian@192.168.1.102")
#   .\bootstrap-cluster.ps1 -ConfigFile "cluster-config.json"
#
# Prerequisites:
#   - PowerShell 5.1 or later
#   - SSH access to all nodes (password or key-based)
#   - bootstrap scripts (prepare-rpi.sh, prepare-ubuntu.sh) in same directory
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$ControlPlane = "",
    
    [Parameter(Mandatory=$false)]
    [string[]]$Workers = @(),
    
    [Parameter(Mandatory=$false)]
    [string]$ConfigFile = "",
    
    [Parameter(Mandatory=$false)]
    [string]$SshKey = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$Parallel = $true,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Script paths
$PrepareRpiScript = Join-Path $ScriptDir "prepare-rpi.sh"
$PrepareUbuntuScript = Join-Path $ScriptDir "prepare-ubuntu.sh"

# Colors for output
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Load configuration from JSON file
function Load-Config {
    param([string]$ConfigFilePath)
    
    if (-not (Test-Path $ConfigFilePath)) {
        Write-Error "Config file not found: $ConfigFilePath"
        exit 1
    }
    
    try {
        $config = Get-Content $ConfigFilePath | ConvertFrom-Json
        
        if ($config.control_plane) {
            $script:ControlPlane = $config.control_plane
        }
        
        if ($config.workers) {
            $script:Workers = $config.workers
        }
        
        if ($config.ssh_key) {
            $script:SshKey = $config.ssh_key
        }
        
        Write-Success "Loaded configuration from $ConfigFilePath"
        return $true
    } catch {
        Write-Error "Failed to parse config file: $_"
        return $false
    }
}

# Parse SSH connection string (user@ip)
function Parse-Connection {
    param([string]$ConnectionString)
    
    if ($ConnectionString -match "^(.+?)@(.+)$") {
        return @{
            User = $matches[1]
            Host = $matches[2]
            Full = $ConnectionString
        }
    } else {
        Write-Error "Invalid connection string format: $ConnectionString (expected: user@ip)"
        return $null
    }
}

# Build SSH arguments
function Get-SshArgs {
    param([string]$KeyPath)
    
    if (-not [string]::IsNullOrEmpty($KeyPath)) {
        $key = $KeyPath
        if ($key.StartsWith("~")) {
            $key = $key.Replace("~", $HOME)
        }
        $key = Resolve-Path $key -ErrorAction SilentlyContinue
        if ($key) {
            return "-i `"$($key.Path)`" -o StrictHostKeyChecking=no"
        }
    }
    return "-o StrictHostKeyChecking=no"
}

# Execute command via SSH
function Invoke-RemoteCommand {
    param(
        [hashtable]$Connection,
        [string]$Command,
        [string]$SshArgs = "",
        [int]$TimeoutSeconds = 300
    )
    
    $sshCmd = "ssh $SshArgs $($Connection.Full) `"$Command`""
    
    if ($Verbose) {
        Write-Info "Executing: $sshCmd"
    }
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would execute: $sshCmd"
        return @{ Success = $true; Output = "DRY RUN"; ExitCode = 0 }
    }
    
    try {
        $output = Invoke-Expression $sshCmd 2>&1
        $exitCode = $LASTEXITCODE
        
        return @{
            Success = ($exitCode -eq 0)
            Output = $output
            ExitCode = $exitCode
        }
    } catch {
        return @{
            Success = $false
            Output = $_.Exception.Message
            ExitCode = -1
        }
    }
}

# Copy file via SCP
function Copy-RemoteFile {
    param(
        [hashtable]$Connection,
        [string]$LocalPath,
        [string]$RemotePath,
        [string]$ScpArgs = ""
    )
    
    $scpCmd = "scp $ScpArgs `"$LocalPath`" $($Connection.Full):`"$RemotePath`""
    
    if ($Verbose) {
        Write-Info "Copying: $scpCmd"
    }
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would copy: $scpCmd"
        return $true
    }
    
    try {
        Invoke-Expression $scpCmd | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

# Bootstrap a worker node (Raspberry Pi)
function Bootstrap-Worker {
    param(
        [hashtable]$Connection,
        [string]$Hostname,
        [string]$IP,
        [string]$Gateway = "192.168.1.1",
        [string]$StorageDevice = "",
        [string]$SshArgs = ""
    )
    
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Info "Bootstrapping worker: $Hostname ($($Connection.Full))"
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    
    # Step 1: Copy bootstrap script
    Write-Info "Copying prepare-rpi.sh to node..."
    if (-not (Copy-RemoteFile -Connection $Connection -LocalPath $PrepareRpiScript -RemotePath "~/prepare-rpi.sh" -ScpArgs $SshArgs)) {
        Write-Error "Failed to copy prepare-rpi.sh to $Hostname"
        return $false
    }
    Write-Success "Script copied"
    
    # Step 2: Make executable and run bootstrap
    Write-Info "Running bootstrap script on $Hostname..."
    
    $bootstrapCmd = "chmod +x ~/prepare-rpi.sh && sudo ~/prepare-rpi.sh --hostname $Hostname --ip $IP/24 --gateway $Gateway --timezone America/New_York"
    if (-not [string]::IsNullOrEmpty($StorageDevice)) {
        $bootstrapCmd += " --storage $StorageDevice"
    }
    $bootstrapCmd += " --skip-reboot-prompt"
    
    $result = Invoke-RemoteCommand -Connection $Connection -Command $bootstrapCmd -SshArgs $SshArgs
    
    if (-not $result.Success) {
        Write-Error "Bootstrap failed on $Hostname"
        if ($Verbose) {
            Write-Host $result.Output
        }
        return $false
    }
    
    Write-Success "Bootstrap completed on $Hostname"
    Write-Host ""
    
    return $true
}

# Bootstrap control plane (Ubuntu)
function Bootstrap-ControlPlane {
    param(
        [hashtable]$Connection,
        [string]$Hostname = "k8s-control",
        [string]$IP,
        [string]$Gateway = "192.168.1.1",
        [string]$SshArgs = ""
    )
    
    Write-Host "=============================================================================" -ForegroundColor Cyan
    Write-Info "Bootstrapping control plane: $Hostname ($($Connection.Full))"
    Write-Host "=============================================================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Step 1: Copy bootstrap script
    Write-Info "Copying prepare-ubuntu.sh to node..."
    if (-not (Copy-RemoteFile -Connection $Connection -LocalPath $PrepareUbuntuScript -RemotePath "~/prepare-ubuntu.sh" -ScpArgs $SshArgs)) {
        Write-Error "Failed to copy prepare-ubuntu.sh to $Hostname"
        return $false
    }
    Write-Success "Script copied"
    
    # Step 2: Make executable and run bootstrap
    Write-Info "Running bootstrap script on $Hostname..."
    
    $bootstrapCmd = "chmod +x ~/prepare-ubuntu.sh && sudo ~/prepare-ubuntu.sh --hostname $Hostname --ip $IP/24 --gateway $Gateway --timezone America/New_York --skip-reboot-prompt"
    
    $result = Invoke-RemoteCommand -Connection $Connection -Command $bootstrapCmd -SshArgs $SshArgs
    
    if (-not $result.Success) {
        Write-Error "Bootstrap failed on $Hostname"
        if ($Verbose) {
            Write-Host $result.Output
        }
        return $false
    }
    
    Write-Success "Bootstrap completed on $Hostname"
    Write-Host ""
    
    return $true
}

# Main execution
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "Windows Bootstrap Orchestrator for RPi Kubernetes Cluster v1.0.0" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

# Load config if provided
if (-not [string]::IsNullOrEmpty($ConfigFile)) {
    if (-not (Load-Config -ConfigFilePath $ConfigFile)) {
        exit 1
    }
}

# Validate inputs
if ([string]::IsNullOrEmpty($ControlPlane) -and ($Workers.Count -eq 0)) {
    Write-Error "Either -ControlPlane and -Workers must be specified, or -ConfigFile must be provided"
    Write-Host ""
    Write-Host "Usage examples:"
    Write-Host "  .\bootstrap-cluster.ps1 -ControlPlane `"ubuntu@192.168.1.100`" -Workers @(`"julian@192.168.1.101`",`"julian@192.168.1.102`")"
    Write-Host "  .\bootstrap-cluster.ps1 -ConfigFile `"cluster-config.json`""
    exit 1
}

# Validate script files exist
if (-not (Test-Path $PrepareRpiScript)) {
    Write-Error "prepare-rpi.sh not found at: $PrepareRpiScript"
    exit 1
}

if (-not [string]::IsNullOrEmpty($ControlPlane) -and -not (Test-Path $PrepareUbuntuScript)) {
    Write-Error "prepare-ubuntu.sh not found at: $PrepareUbuntuScript"
    exit 1
}

# Build SSH arguments
$sshArgs = Get-SshArgs -KeyPath $SshKey

# Parse connections
$controlPlaneConn = $null
if (-not [string]::IsNullOrEmpty($ControlPlane)) {
    $controlPlaneConn = Parse-Connection -ConnectionString $ControlPlane
    if (-not $controlPlaneConn) {
        exit 1
    }
}

$workerConns = @()
foreach ($worker in $Workers) {
    $conn = Parse-Connection -ConnectionString $worker
    if ($conn) {
        $workerConns += $conn
    }
}

# Dry run notice
if ($DryRun) {
    Write-Warning "DRY RUN MODE - No changes will be made"
    Write-Host ""
}

# Bootstrap control plane
$controlPlaneSuccess = $true
if ($controlPlaneConn) {
    $cpIP = $controlPlaneConn.Host
    $cpHostname = "k8s-control"
    
    # Extract hostname from connection if in format hostname@ip
    if ($ControlPlane -match "^(.+?)@") {
        $cpHostname = $matches[1]
    }
    
    $controlPlaneSuccess = Bootstrap-ControlPlane -Connection $controlPlaneConn -Hostname $cpHostname -IP $cpIP -SshArgs $sshArgs
}

# Bootstrap workers
$workerResults = @()
if ($Parallel -and ($workerConns.Count -gt 1)) {
    Write-Info "Bootstrap workers in parallel..."
    
    $jobs = @()
    foreach ($worker in $workerConns) {
        $hostname = $worker.User
        $ip = $worker.Host
        
        # Extract hostname from IP or connection
        if ($ip -match "^192\.168\.1\.(\d+)$") {
            $lastOctet = [int]$matches[1]
            $hostname = "rpi$($lastOctet - 100)"
        }
        
        $job = Start-Job -ScriptBlock {
            param($Connection, $Hostname, $IP, $SshArgs, $PrepareRpiScript, $DryRun)
            # Note: Jobs would need proper serialization - for now, run sequentially
        }
    }
    
    # Fall back to sequential for now
    $Parallel = $false
}

if (-not $Parallel) {
    foreach ($worker in $workerConns) {
        $hostname = $worker.User
        $ip = $worker.Host
        
        # Extract hostname from IP (assuming pattern 192.168.1.10X for rpiX)
        if ($ip -match "^192\.168\.1\.(\d+)$") {
            $lastOctet = [int]$matches[1]
            if ($lastOctet -ge 101 -and $lastOctet -le 104) {
                $hostname = "rpi$($lastOctet - 100)"
            }
        }
        
        $result = Bootstrap-Worker -Connection $worker -Hostname $hostname -IP $ip -SshArgs $sshArgs
        $workerResults += @{ Connection = $worker; Success = $result }
    }
}

# Summary
Write-Host "=============================================================================" -ForegroundColor Green
Write-Success "Bootstrap Summary"
Write-Host "=============================================================================" -ForegroundColor Green
Write-Host ""

if ($controlPlaneConn) {
    $status = if ($controlPlaneSuccess) { "✓" } else { "✗" }
    Write-Host "  $status Control Plane ($($controlPlaneConn.Full))" -ForegroundColor $(if ($controlPlaneSuccess) { "Green" } else { "Red" })
}

foreach ($result in $workerResults) {
    $status = if ($result.Success) { "✓" } else { "✗" }
    Write-Host "  $status Worker ($($result.Connection.Full))" -ForegroundColor $(if ($result.Success) { "Green" } else { "Red" })
}

Write-Host ""

$allSuccess = $controlPlaneSuccess -and ($workerResults | Where-Object { -not $_.Success }).Count -eq 0

if ($allSuccess) {
    Write-Success "All nodes bootstrapped successfully!"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  1. Reboot all nodes to apply kernel changes"
    Write-Host "  2. Verify nodes are ready: ssh <node> && uname -m && free -h"
    Write-Host "  3. Proceed with k3s installation"
    exit 0
} else {
    Write-Error "Some nodes failed to bootstrap. Check output above for details."
    exit 1
}