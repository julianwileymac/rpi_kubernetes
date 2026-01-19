# =============================================================================
# Network Discovery Script for Raspberry Pi Nodes
# =============================================================================
# Version: 1.0.0
#
# Scans the local network to discover Raspberry Pi nodes by hostname pattern
# or MAC address prefix.
#
# Usage:
#   .\discover-nodes.ps1
#   .\discover-nodes.ps1 -NetworkRange "192.168.1.0/24"
#   .\discover-nodes.ps1 -HostnamePattern "rpi*" -OutputFormat "json"
#
# Prerequisites:
#   - PowerShell 5.1 or later
#   - Network connectivity to local subnet
#   - Admin rights (for some network operations)
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$NetworkRange = "",
    
    [Parameter(Mandatory=$false)]
    [string]$HostnamePattern = "rpi*",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFormat = "table",  # table, json, hosts
    
    [Parameter(Mandatory=$false)]
    [switch]$Verbose = $false
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

# Function to get local network range
function Get-LocalNetworkRange {
    $adapters = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.PrefixOrigin -eq "Dhcp" -or $_.PrefixOrigin -eq "Manual" }
    
    foreach ($adapter in $adapters) {
        $ip = $adapter.IPAddress
        $prefixLength = $adapter.PrefixLength
        
        if ($ip -match '^(\d+\.\d+\.\d+)\.\d+$') {
            $baseNetwork = $matches[1]
            return "$baseNetwork.0/$prefixLength"
        }
    }
    
    return "192.168.1.0/24"  # Default fallback
}

# Function to resolve IP range to scan
function Get-IPRange {
    param([string]$NetworkRange)
    
    if ([string]::IsNullOrEmpty($NetworkRange)) {
        $NetworkRange = Get-LocalNetworkRange
    }
    
    if ($NetworkRange -match '^(\d+\.\d+\.\d+)\.(\d+)/(\d+)$') {
        $base = $matches[1]
        $subnet = $matches[3]
        
        if ($subnet -eq "24") {
            # /24 subnet - scan .1 to .254
            return 1..254 | ForEach-Object { "$base.$_" }
        } elseif ($subnet -eq "16") {
            # /16 subnet - scan common ranges
            $third = $base -split '\.' | Select-Object -Last 1
            return 1..254 | ForEach-Object { "$($base -replace '\.\d+$', '').$third.$_" }
        }
    } elseif ($NetworkRange -match '^(\d+\.\d+\.\d+\.\d+)-(\d+\.\d+\.\d+\.\d+)$') {
        # IP range format
        $start = [System.Net.IPAddress]::Parse($matches[1])
        $end = [System.Net.IPAddress]::Parse($matches[2])
        $ips = @()
        $current = $start
        
        while ($current -le $end) {
            $ips += $current.ToString()
            $current = [System.Net.IPAddress]::new(($current.GetAddressBytes() | ForEach-Object { [uint32]$_ }) -join ',') + 1
        }
        return $ips
    }
    
    Write-Warning "Could not parse network range: $NetworkRange. Using default 192.168.1.1-254"
    return 1..254 | ForEach-Object { "192.168.1.$_" }
}

# Function to test hostname resolution
function Test-Hostname {
    param(
        [string]$IP,
        [string]$Pattern
    )
    
    try {
        # Try to resolve hostname
        $hostname = [System.Net.Dns]::GetHostEntry($IP).HostName -replace '\.$', ''
        
        if ($hostname -like $Pattern) {
            return $hostname
        }
        
        # Also check if IP matches pattern (for rpi1=192.168.1.101 format)
        if ($hostname -match '^rpi\d+$') {
            return $hostname
        }
    } catch {
        # Hostname resolution failed, but IP might still be valid
    }
    
    return $null
}

# Function to test SSH connection
function Test-SSHConnection {
    param(
        [string]$IP,
        [int]$TimeoutSeconds = 2
    )
    
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connection = $tcpClient.BeginConnect($IP, 22, $null, $null)
        $wait = $connection.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds), $false)
        
        if ($wait) {
            $tcpClient.EndConnect($connection)
            $tcpClient.Close()
            return $true
        } else {
            $tcpClient.Close()
            return $false
        }
    } catch {
        return $false
    }
}

# Main discovery function
function Discover-Nodes {
    param(
        [string[]]$IPRange,
        [string]$HostnamePattern
    )
    
    $discoveredNodes = @()
    $totalIPs = $IPRange.Count
    $current = 0
    
    Write-Info "Scanning $totalIPs IP addresses for nodes matching pattern: $HostnamePattern"
    Write-Info "This may take a few minutes..."
    Write-Host ""
    
    foreach ($ip in $IPRange) {
        $current++
        
        if ($Verbose -or ($current % 50 -eq 0)) {
            Write-Progress -Activity "Scanning network" -Status "Checking $ip ($current/$totalIPs)" -PercentComplete (($current / $totalIPs) * 100)
        }
        
        # Test SSH port first (faster than hostname resolution)
        if (Test-SSHConnection -IP $ip -TimeoutSeconds 1) {
            $hostname = Test-Hostname -IP $ip -Pattern $HostnamePattern
            
            if ($hostname) {
                $node = @{
                    Hostname = $hostname
                    IP = $ip
                    Status = "Online"
                }
                $discoveredNodes += $node
                
                if ($Verbose) {
                    Write-Success "Found: $hostname ($ip)"
                }
            } elseif ($Verbose) {
                Write-Info "SSH open at $ip but hostname doesn't match pattern"
            }
        }
    }
    
    Write-Progress -Activity "Scanning network" -Completed
    
    return $discoveredNodes
}

# Main execution
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "Raspberry Pi Network Discovery v1.0.0" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

# Determine IP range to scan
$ipRange = Get-IPRange -NetworkRange $NetworkRange

if ($Verbose) {
    Write-Info "Network range: $NetworkRange"
    Write-Info "IPs to scan: $($ipRange.Count)"
    Write-Info "Hostname pattern: $HostnamePattern"
    Write-Host ""
}

# Discover nodes
$discoveredNodes = Discover-Nodes -IPRange $ipRange -HostnamePattern $HostnamePattern

# Output results
Write-Host ""
Write-Host "=============================================================================" -ForegroundColor Green
if ($discoveredNodes.Count -eq 0) {
    Write-Warning "No nodes discovered matching pattern: $HostnamePattern"
    Write-Host ""
    Write-Info "Troubleshooting tips:"
    Write-Host "  1. Check that nodes are powered on and connected to the network"
    Write-Host "  2. Verify SSH is enabled on the nodes (port 22)"
    Write-Host "  3. Try a broader hostname pattern: .\discover-nodes.ps1 -HostnamePattern '*'"
    Write-Host "  4. Check firewall settings on your workstation"
} else {
    Write-Success "Discovered $($discoveredNodes.Count) node(s)"
    Write-Host "=============================================================================" -ForegroundColor Green
    Write-Host ""
    
    # Format output based on requested format
    switch ($OutputFormat.ToLower()) {
        "json" {
            $discoveredNodes | ConvertTo-Json -Depth 3
        }
        "hosts" {
            # Output in format compatible with port-to-rpi.ps1
            foreach ($node in $discoveredNodes) {
                Write-Host "$($node.Hostname)=$($node.IP)"
            }
        }
        default {
            # Table format
            $discoveredNodes | Format-Table -AutoSize -Property @(
                @{Label="Hostname"; Expression={$_.Hostname}},
                @{Label="IP Address"; Expression={$_.IP}},
                @{Label="Status"; Expression={$_.Status}}
            )
            
            Write-Host ""
            Write-Info "To use these nodes with port-to-rpi.ps1, use:"
            Write-Host "  .\port-to-rpi.ps1 -Hosts @("
            foreach ($node in $discoveredNodes) {
                Write-Host "    `"$($node.Hostname)=$($node.IP)`","
            }
            Write-Host "  )"
        }
    }
}

# Exit with appropriate code
if ($discoveredNodes.Count -eq 0) {
    exit 1
} else {
    exit 0
}