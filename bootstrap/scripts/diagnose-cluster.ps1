# =============================================================================
# Cluster Diagnostics and Troubleshooting Script
# =============================================================================
# Version: 1.0.0
#
# Diagnoses issues with cluster nodes by testing connectivity, verifying
# prerequisites, and reporting configuration status.
#
# Usage:
#   .\diagnose-cluster.ps1 -ControlPlane "ubuntu@192.168.1.100" -Workers @("julian@192.168.1.101","julian@192.168.1.102")
#   .\diagnose-cluster.ps1 -ConfigFile "cluster-config.json"
#
# Prerequisites:
#   - PowerShell 5.1 or later
#   - SSH access to nodes
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
    [switch]$ShowDetails = $false
)

$ErrorActionPreference = "Continue"

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

# Test SSH connectivity
function Test-NodeConnectivity {
    param(
        [string]$ConnectionString,
        [string]$SshArgs = ""
    )
    
    $testCmd = "ssh $SshArgs $ConnectionString 'echo OK' 2>&1"
    
    try {
        $result = Invoke-Expression $testCmd 2>&1
        if ($LASTEXITCODE -eq 0 -and $result -like "*OK*") {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

# Run diagnostic command via SSH
function Invoke-DiagnosticCommand {
    param(
        [string]$ConnectionString,
        [string]$Command,
        [string]$SshArgs = ""
    )
    
    $sshCmd = "ssh $SshArgs $ConnectionString `"$Command`" 2>&1"
    
    try {
        $output = Invoke-Expression $sshCmd
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

# Check prerequisites on Raspberry Pi
function Test-RPiPrerequisites {
    param(
        [string]$ConnectionString,
        [string]$SshArgs = ""
    )
    
    $checks = @{
        "Architecture (aarch64)" = "uname -m"
        "Swap Disabled" = "free -h | grep -i swap | awk '{print \$2}'"
        "cgroups Enabled" = "cat /proc/cgroups | grep -E 'memory|cpuset' | awk '{print \$4}' | grep -q '1' && echo 'enabled' || echo 'disabled'"
        "Python3 Installed" = "which python3 && python3 --version"
        "SSH Server Running" = "systemctl is-active ssh || systemctl is-active sshd"
    }
    
    $results = @{}
    
    foreach ($check in $checks.GetEnumerator()) {
        $result = Invoke-DiagnosticCommand -ConnectionString $ConnectionString -Command $check.Value -SshArgs $SshArgs
        
        if ($check.Key -eq "Swap Disabled") {
            $swapValue = ($result.Output -join " ").Trim()
            $results[$check.Key] = @{
                Pass = ($swapValue -eq "0B" -or $swapValue -eq "0")
                Value = $swapValue
            }
        } elseif ($check.Key -eq "cgroups Enabled") {
            $cgValue = ($result.Output -join " ").Trim()
            $results[$check.Key] = @{
                Pass = ($cgValue -eq "enabled")
                Value = $cgValue
            }
        } else {
            $results[$check.Key] = @{
                Pass = $result.Success
                Value = ($result.Output -join " ").Trim()
            }
        }
    }
    
    return $results
}

# Check prerequisites on Ubuntu control plane
function Test-UbuntuPrerequisites {
    param(
        [string]$ConnectionString,
        [string]$SshArgs = ""
    )
    
    $checks = @{
        "Architecture (x86_64/amd64)" = "uname -m"
        "Swap Disabled" = "free -h | grep -i swap | awk '{print \$2}'"
        "Python3 Installed" = "which python3 && python3 --version"
        "SSH Server Running" = "systemctl is-active ssh || systemctl is-active sshd"
    }
    
    $results = @{}
    
    foreach ($check in $checks.GetEnumerator()) {
        $result = Invoke-DiagnosticCommand -ConnectionString $ConnectionString -Command $check.Value -SshArgs $SshArgs
        
        if ($check.Key -eq "Swap Disabled") {
            $swapValue = ($result.Output -join " ").Trim()
            $results[$check.Key] = @{
                Pass = ($swapValue -eq "0B" -or $swapValue -eq "0")
                Value = $swapValue
            }
        } else {
            $results[$check.Key] = @{
                Pass = $result.Success
                Value = ($result.Output -join " ").Trim()
            }
        }
    }
    
    return $results
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
            $privateKey = $key.Path -replace "\.pub$", ""
            if (Test-Path $privateKey) {
                return "-i `"$privateKey`" -o StrictHostKeyChecking=no"
            }
        }
    }
    return "-o StrictHostKeyChecking=no"
}

# Main execution
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "Cluster Diagnostics and Troubleshooting v1.0.0" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

# Load config if provided
if (-not [string]::IsNullOrEmpty($ConfigFile) -and (Test-Path $ConfigFile)) {
    try {
        $config = Get-Content $ConfigFile | ConvertFrom-Json
        if ($config.control_plane) {
            $ControlPlane = $config.control_plane
        }
        if ($config.workers) {
            $Workers = $config.workers
        }
        Write-Success "Loaded configuration from $ConfigFile"
    } catch {
        Write-Warning "Failed to load config file: $_"
    }
}

# Build SSH arguments
$sshArgs = Get-SshArgs -KeyPath $SshKey

# Validate inputs
if ([string]::IsNullOrEmpty($ControlPlane) -and ($Workers.Count -eq 0)) {
    Write-Error "Either -ControlPlane and -Workers must be specified, or -ConfigFile must be provided"
    exit 1
}

$allNodes = @()
if (-not [string]::IsNullOrEmpty($ControlPlane)) {
    $allNodes += @{ Type = "Control Plane"; Connection = $ControlPlane }
}
foreach ($worker in $Workers) {
    $allNodes += @{ Type = "Worker"; Connection = $worker }
}

# Test connectivity
Write-Host "=============================================================================" -ForegroundColor Yellow
Write-Info "Testing Connectivity"
Write-Host "=============================================================================" -ForegroundColor Yellow
Write-Host ""

$connectivityResults = @()
foreach ($node in $allNodes) {
    Write-Info "Testing SSH connection to $($node.Connection)..."
    $isConnected = Test-NodeConnectivity -ConnectionString $node.Connection -SshArgs $sshArgs
    
    if ($isConnected) {
        Write-Success "[PASS] SSH connection successful"
        $connectivityResults += @{ Node = $node; Connected = $true }
    } else {
        Write-Error "[FAIL] SSH connection failed"
        $connectivityResults += @{ Node = $node; Connected = $false }
    }
}

Write-Host ""

# Check prerequisites for connected nodes
Write-Host "=============================================================================" -ForegroundColor Yellow
Write-Info "Checking Prerequisites"
Write-Host "=============================================================================" -ForegroundColor Yellow
Write-Host ""

$allPass = $true

foreach ($result in $connectivityResults) {
    if (-not $result.Connected) {
        continue
    }
    
    $node = $result.Node
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Info "$($node.Type): $($node.Connection)"
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    
    if ($node.Type -eq "Control Plane") {
        $prereqs = Test-UbuntuPrerequisites -ConnectionString $node.Connection -SshArgs $sshArgs
    } else {
        $prereqs = Test-RPiPrerequisites -ConnectionString $node.Connection -SshArgs $sshArgs
    }
    
    foreach ($check in $prereqs.GetEnumerator()) {
        if ($check.Value.Pass) {
            $status = "[PASS]"
            $color = "Green"
        } else {
            $status = "[FAIL]"
            $color = "Red"
            $allPass = $false
        }
        
        Write-Host "  $status $($check.Key): $($check.Value.Value)" -ForegroundColor $color
    }
    
    Write-Host ""
}

# Summary and recommendations
Write-Host "=============================================================================" -ForegroundColor $(if ($allPass) { "Green" } else { "Red" })
Write-Host "Diagnostics Summary"
Write-Host "=============================================================================" -ForegroundColor $(if ($allPass) { "Green" } else { "Red" })
Write-Host ""

$connectedCount = ($connectivityResults | Where-Object { $_.Connected }).Count
$totalCount = $connectivityResults.Count

Write-Host "  Connectivity: $connectedCount/$totalCount nodes accessible via SSH"
Write-Host "  Prerequisites: $(if ($allPass) { 'All checks passed' } else { 'Some checks failed' })"
Write-Host ""

if (-not $allPass) {
    Write-Warning "Recommendations:"
    Write-Host ""
    
    $failedNodes = $connectivityResults | Where-Object { -not $_.Connected }
    if ($failedNodes.Count -gt 0) {
        Write-Host "  Connectivity Issues:"
        foreach ($failed in $failedNodes) {
            Write-Host "    - Check SSH is enabled on $($failed.Node.Connection)"
            Write-Host "    - Verify network connectivity: ping $($failed.Node.Connection -replace '.*@', '')"
            Write-Host "    - Test SSH manually: ssh $($failed.Node.Connection)"
        }
        Write-Host ""
    }
    
    Write-Host "  Prerequisite Issues:"
    Write-Host "    - Run bootstrap script on failed nodes: .\bootstrap-cluster.ps1 ..."
    Write-Host "    - Verify swap is disabled: ssh <node> 'free -h'"
    Write-Host "    - Check cgroups (RPi): ssh <node> 'cat /proc/cgroups'"
    Write-Host ""
}

if ($allPass -and $connectedCount -eq $totalCount) {
    Write-Success "All nodes are ready for k3s installation!"
    exit 0
} else {
    exit 1
}