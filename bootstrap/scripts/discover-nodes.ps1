# =============================================================================
# Network Discovery Script for Raspberry Pi Nodes
# =============================================================================
# Version: 2.0.0
#
# Discovers Raspberry Pi nodes using mDNS (.local) as the primary method
# with network scanning as a fallback for environments without mDNS support.
#
# Usage:
#   .\discover-nodes.ps1
#   .\discover-nodes.ps1 -Method "mdns" -Hostnames "rpi1,rpi2,rpi3,rpi4"
#   .\discover-nodes.ps1 -Method "scan" -NetworkRange "192.168.12.0/24"
#   .\discover-nodes.ps1 -Method "auto" -HostnamePattern "rpi*" -OutputFormat "json"
#
# Prerequisites:
#   - PowerShell 5.1 or later
#   - Network connectivity to local subnet
#   - For mDNS: Bonjour/mDNS responder or Avahi on target nodes
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("auto", "mdns", "scan")]
    [string]$Method = "auto",
    
    [Parameter(Mandatory=$false)]
    [string]$NetworkRange = "",
    
    [Parameter(Mandatory=$false)]
    [string]$HostnamePattern = "rpi*",
    
    [Parameter(Mandatory=$false)]
    [string[]]$Hostnames = @("rpi1", "rpi2", "rpi3", "rpi4"),
    
    [Parameter(Mandatory=$false)]
    [string]$ControlPlane = "k8s-control",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFormat = "table",  # table, json, hosts, config
    
    [Parameter(Mandatory=$false)]
    [switch]$IncludeControlPlane = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$CheckServices = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$UpdateConfig = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$ConfigFile = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

# =============================================================================
# Output Functions
# =============================================================================

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Debug {
    param([string]$Message)
    if ($Verbose) {
        Write-Host "[DEBUG] $Message" -ForegroundColor DarkGray
    }
}

# =============================================================================
# mDNS Resolution Functions
# =============================================================================

function Resolve-MDNSHostname {
    <#
    .SYNOPSIS
    Resolve a hostname via mDNS (.local domain)
    
    .DESCRIPTION
    Tries multiple methods to resolve a .local hostname:
    1. Resolve-DnsName cmdlet (Windows 10+)
    2. nslookup command
    3. Direct socket resolution (if libnss-mdns configured)
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$Hostname,
        
        [Parameter(Mandatory=$false)]
        [int]$TimeoutSeconds = 5
    )
    
    $fqdn = if ($Hostname.EndsWith(".local")) { $Hostname } else { "$Hostname.local" }
    
    Write-Debug "Resolving: $fqdn"
    
    # Method 1: Resolve-DnsName (Windows 10+, supports mDNS)
    try {
        $result = Resolve-DnsName -Name $fqdn -Type A -DnsOnly -ErrorAction Stop 2>$null
        if ($result -and $result.IPAddress) {
            $ip = $result.IPAddress | Select-Object -First 1
            Write-Debug "  Resolved via Resolve-DnsName: $ip"
            return $ip
        }
    } catch {
        Write-Debug "  Resolve-DnsName failed: $($_.Exception.Message)"
    }
    
    # Method 2: nslookup with multicast DNS
    try {
        $nslookup = nslookup $fqdn 224.0.0.251 2>$null
        if ($nslookup) {
            foreach ($line in $nslookup) {
                if ($line -match 'Address:\s*(\d+\.\d+\.\d+\.\d+)' -and $matches[1] -ne "224.0.0.251") {
                    Write-Debug "  Resolved via nslookup mDNS: $($matches[1])"
                    return $matches[1]
                }
            }
        }
    } catch {
        Write-Debug "  nslookup mDNS failed"
    }
    
    # Method 3: Standard DNS (some routers cache .local)
    try {
        $result = [System.Net.Dns]::GetHostAddresses($fqdn) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
        if ($result) {
            $ip = $result.IPAddressToString
            Write-Debug "  Resolved via DNS: $ip"
            return $ip
        }
    } catch {
        Write-Debug "  DNS resolution failed"
    }
    
    # Method 4: Try without .local suffix (hostname only)
    try {
        $shortname = $Hostname -replace '\.local$', ''
        $result = [System.Net.Dns]::GetHostAddresses($shortname) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
        if ($result) {
            $ip = $result.IPAddressToString
            Write-Debug "  Resolved via short hostname: $ip"
            return $ip
        }
    } catch {
        Write-Debug "  Short hostname resolution failed"
    }
    
    Write-Debug "  All resolution methods failed for $fqdn"
    return $null
}

function Discover-NodesViaMDNS {
    <#
    .SYNOPSIS
    Discover nodes by resolving their mDNS hostnames
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Hostnames,
        
        [Parameter(Mandatory=$false)]
        [string]$ControlPlaneHostname = ""
    )
    
    $discoveredNodes = @()
    $errors = @()
    
    # Resolve control plane if specified
    if ($ControlPlaneHostname -and $IncludeControlPlane) {
        Write-Info "Resolving control plane: $ControlPlaneHostname"
        $ip = Resolve-MDNSHostname -Hostname $ControlPlaneHostname
        if ($ip) {
            $node = @{
                Hostname = $ControlPlaneHostname
                IP = $ip
                Role = "control_plane"
                Arch = "amd64"
                Status = "Online"
                SSHAvailable = $false
                K3SAvailable = $false
            }
            
            if ($CheckServices) {
                $node.SSHAvailable = Test-TCPPort -IP $ip -Port 22
                $node.K3SAvailable = Test-TCPPort -IP $ip -Port 6443
            }
            
            $discoveredNodes += $node
            Write-Success "  Found: $ControlPlaneHostname -> $ip"
        } else {
            $errors += "Failed to resolve control plane: $ControlPlaneHostname"
            Write-Warn "  Not found: $ControlPlaneHostname"
        }
    }
    
    # Resolve worker nodes
    Write-Info "Resolving $($Hostnames.Count) worker node(s)..."
    foreach ($hostname in $Hostnames) {
        $ip = Resolve-MDNSHostname -Hostname $hostname
        if ($ip) {
            $node = @{
                Hostname = $hostname
                IP = $ip
                Role = "worker"
                Arch = "arm64"
                Status = "Online"
                SSHAvailable = $false
                K3SAvailable = $false
            }
            
            if ($CheckServices) {
                $node.SSHAvailable = Test-TCPPort -IP $ip -Port 22
                $node.K3SAvailable = Test-TCPPort -IP $ip -Port 10250
            }
            
            $discoveredNodes += $node
            Write-Success "  Found: $hostname -> $ip"
        } else {
            $errors += "Failed to resolve: $hostname"
            Write-Warn "  Not found: $hostname"
        }
    }
    
    return @{
        Nodes = $discoveredNodes
        Errors = $errors
        Method = "mdns"
    }
}

# =============================================================================
# Network Scan Functions
# =============================================================================

function Get-LocalNetworkRange {
    $adapters = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
        $_.InterfaceAlias -notlike "*Loopback*" -and 
        ($_.PrefixOrigin -eq "Dhcp" -or $_.PrefixOrigin -eq "Manual")
    }
    
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

function Get-IPRange {
    param([string]$Network)
    
    if ([string]::IsNullOrEmpty($Network)) {
        $Network = Get-LocalNetworkRange
        Write-Debug "Auto-detected network: $Network"
    }
    
    if ($Network -match '^(\d+\.\d+\.\d+)\.(\d+)/(\d+)$') {
        $base = $matches[1]
        $subnet = $matches[3]
        
        if ($subnet -eq "24") {
            return 1..254 | ForEach-Object { "$base.$_" }
        } elseif ($subnet -eq "16") {
            $third = $base -split '\.' | Select-Object -Last 1
            return 1..254 | ForEach-Object { "$($base -replace '\.\d+$', '').$third.$_" }
        }
    }
    
    Write-Warn "Could not parse network range: $Network. Using default 192.168.1.1-254"
    return 1..254 | ForEach-Object { "192.168.1.$_" }
}

function Test-TCPPort {
    param(
        [string]$IP,
        [int]$Port,
        [int]$TimeoutMs = 2000
    )
    
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connection = $tcpClient.BeginConnect($IP, $Port, $null, $null)
        $wait = $connection.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        
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

function Get-HostnameFromIP {
    param([string]$IP)
    
    try {
        $hostname = [System.Net.Dns]::GetHostEntry($IP).HostName -replace '\.$', ''
        return $hostname.Split('.')[0]  # Return short hostname
    } catch {
        return $null
    }
}

function Discover-NodesViaScan {
    <#
    .SYNOPSIS
    Discover nodes by scanning the network
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$IPRange,
        
        [Parameter(Mandatory=$true)]
        [string]$Pattern,
        
        [Parameter(Mandatory=$false)]
        [string]$ControlPlanePattern = "k8s-control"
    )
    
    $discoveredNodes = @()
    $totalIPs = $IPRange.Count
    $current = 0
    
    Write-Info "Scanning $totalIPs IP addresses for nodes matching pattern: $Pattern"
    Write-Info "This may take a few minutes..."
    
    foreach ($ip in $IPRange) {
        $current++
        
        if ($current % 50 -eq 0) {
            Write-Progress -Activity "Scanning network" -Status "Checking $ip ($current/$totalIPs)" -PercentComplete (($current / $totalIPs) * 100)
        }
        
        # Test SSH port first (faster than hostname resolution)
        if (Test-TCPPort -IP $ip -Port 22 -TimeoutMs 1000) {
            $hostname = Get-HostnameFromIP -IP $ip
            
            if ($hostname) {
                $isControlPlane = $hostname -like "*$ControlPlanePattern*"
                $isWorker = $hostname -like $Pattern
                
                if ($isControlPlane -or $isWorker) {
                    $node = @{
                        Hostname = $hostname
                        IP = $ip
                        Role = if ($isControlPlane) { "control_plane" } else { "worker" }
                        Arch = if ($isControlPlane) { "amd64" } else { "arm64" }
                        Status = "Online"
                        SSHAvailable = $true
                        K3SAvailable = $false
                    }
                    
                    if ($CheckServices) {
                        $k3sPort = if ($isControlPlane) { 6443 } else { 10250 }
                        $node.K3SAvailable = Test-TCPPort -IP $ip -Port $k3sPort
                    }
                    
                    $discoveredNodes += $node
                    Write-Debug "Found: $hostname ($ip) - $($node.Role)"
                }
            }
        }
    }
    
    Write-Progress -Activity "Scanning network" -Completed
    
    return @{
        Nodes = $discoveredNodes
        Errors = @()
        Method = "network_scan"
    }
}

# =============================================================================
# Configuration Update
# =============================================================================

function Update-ClusterConfig {
    param(
        [Parameter(Mandatory=$true)]
        [array]$Nodes,
        
        [Parameter(Mandatory=$true)]
        [string]$ConfigPath
    )
    
    if (-not (Test-Path $ConfigPath)) {
        Write-Err "Config file not found: $ConfigPath"
        return $false
    }
    
    try {
        $content = Get-Content $ConfigPath -Raw
        
        # Update worker IPs using regex
        foreach ($node in $Nodes) {
            if ($node.Role -eq "worker") {
                # Match the worker entry and update the IP
                $pattern = "(?<=- name: $($node.Hostname)\s+ip: )\d+\.\d+\.\d+\.\d+"
                $content = $content -replace $pattern, $node.IP
            } elseif ($node.Role -eq "control_plane") {
                # Update control plane IP
                $pattern = "(?<=control_plane:\s+hostname: [^\r\n]+\s+ip: )\d+\.\d+\.\d+\.\d+"
                $content = $content -replace $pattern, $node.IP
            }
        }
        
        Set-Content -Path $ConfigPath -Value $content
        Write-Success "Updated $ConfigPath with discovered IPs"
        return $true
    } catch {
        Write-Err "Failed to update config: $($_.Exception.Message)"
        return $false
    }
}

# =============================================================================
# Main Execution
# =============================================================================

Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "Raspberry Pi Network Discovery v2.0.0" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

$startTime = Get-Date
$result = $null

# Perform discovery based on method
switch ($Method.ToLower()) {
    "auto" {
        Write-Info "Using auto discovery (mDNS -> network scan)"
        
        # Try mDNS first
        $result = Discover-NodesViaMDNS -Hostnames $Hostnames -ControlPlaneHostname $ControlPlane
        
        # Check if we found all nodes
        $foundHostnames = $result.Nodes | ForEach-Object { $_.Hostname }
        $missingHostnames = $Hostnames | Where-Object { $_ -notin $foundHostnames }
        
        if ($missingHostnames.Count -gt 0) {
            Write-Info "mDNS discovery incomplete, trying network scan for missing nodes..."
            
            # Scan network for missing nodes
            $ipRange = Get-IPRange -Network $NetworkRange
            $scanResult = Discover-NodesViaScan -IPRange $ipRange -Pattern $HostnamePattern
            
            # Merge results
            foreach ($node in $scanResult.Nodes) {
                if ($node.Hostname -in $missingHostnames -or $node.Hostname -notin $foundHostnames) {
                    $result.Nodes += $node
                }
            }
            
            $result.Method = "auto (mdns + scan)"
        }
    }
    
    "mdns" {
        Write-Info "Using mDNS discovery"
        $result = Discover-NodesViaMDNS -Hostnames $Hostnames -ControlPlaneHostname $ControlPlane
    }
    
    "scan" {
        Write-Info "Using network scan discovery"
        $ipRange = Get-IPRange -Network $NetworkRange
        $result = Discover-NodesViaScan -IPRange $ipRange -Pattern $HostnamePattern -ControlPlanePattern $ControlPlane
    }
}

$elapsedTime = (Get-Date) - $startTime

# Update config if requested
if ($UpdateConfig) {
    $configPath = if ($ConfigFile) { $ConfigFile } else { Join-Path $RepoRoot "cluster-config.yaml" }
    Update-ClusterConfig -Nodes $result.Nodes -ConfigPath $configPath
}

# Output results
Write-Host ""
Write-Host "=============================================================================" -ForegroundColor Green

if ($result.Nodes.Count -eq 0) {
    Write-Warn "No nodes discovered"
    Write-Host ""
    Write-Info "Troubleshooting tips:"
    Write-Host "  1. Ensure nodes are powered on and connected to the network"
    Write-Host "  2. Verify SSH is enabled on the nodes (port 22)"
    Write-Host "  3. For mDNS: Ensure Avahi/Bonjour is running on nodes"
    Write-Host "  4. Try network scan: .\discover-nodes.ps1 -Method scan"
    Write-Host "  5. Check firewall settings on your workstation"
    
    if ($result.Errors.Count -gt 0) {
        Write-Host ""
        Write-Warn "Errors encountered:"
        foreach ($err in $result.Errors) {
            Write-Host "  - $err" -ForegroundColor Yellow
        }
    }
} else {
    Write-Success "Discovered $($result.Nodes.Count) node(s)"
    Write-Host "=============================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Info "Method: $($result.Method)"
    Write-Info "Time: $($elapsedTime.TotalSeconds.ToString('0.00'))s"
    Write-Host ""
    
    # Format output
    switch ($OutputFormat.ToLower()) {
        "json" {
            $output = @{
                nodes = $result.Nodes
                method = $result.Method
                discovery_time = $elapsedTime.TotalSeconds
                errors = $result.Errors
            }
            $output | ConvertTo-Json -Depth 3
        }
        
        "hosts" {
            # Output in hosts file format
            foreach ($node in $result.Nodes) {
                Write-Host "$($node.IP)`t$($node.Hostname)`t$($node.Hostname).local"
            }
        }
        
        "config" {
            # Output in cluster-config.yaml format
            Write-Host "control_plane:"
            $cp = $result.Nodes | Where-Object { $_.Role -eq "control_plane" } | Select-Object -First 1
            if ($cp) {
                Write-Host "  hostname: $($cp.Hostname)"
                Write-Host "  ip: $($cp.IP)"
            }
            Write-Host ""
            Write-Host "workers:"
            $workers = $result.Nodes | Where-Object { $_.Role -eq "worker" } | Sort-Object Hostname
            foreach ($worker in $workers) {
                Write-Host "  - name: $($worker.Hostname)"
                Write-Host "    ip: $($worker.IP)"
            }
        }
        
        default {
            # Table format
            $tableData = $result.Nodes | Sort-Object @{Expression={$_.Role}; Descending=$true}, Hostname
            
            Write-Host "Discovered Nodes:" -ForegroundColor White
            Write-Host "-" * 70
            
            foreach ($node in $tableData) {
                $statusIcon = if ($node.SSHAvailable) { "[OK]" } else { "[--]" }
                $k3sIcon = if ($node.K3SAvailable) { "[k3s]" } else { "[---]" }
                $roleLabel = if ($node.Role -eq "control_plane") { "(CP)" } else { "(W) " }
                
                if ($CheckServices) {
                    Write-Host ("  {0} {1,-15} {2,-15} {3} {4}" -f $roleLabel, $node.Hostname, $node.IP, $statusIcon, $k3sIcon)
                } else {
                    Write-Host ("  {0} {1,-15} {2,-15}" -f $roleLabel, $node.Hostname, $node.IP)
                }
            }
            
            Write-Host ""
            Write-Info "To use these nodes with port-to-rpi.ps1:"
            Write-Host "  .\port-to-rpi.ps1 -Hosts @("
            foreach ($node in ($result.Nodes | Where-Object { $_.Role -eq "worker" })) {
                Write-Host "    `"$($node.Hostname)=$($node.IP)`","
            }
            Write-Host "  )"
            Write-Host ""
            
            Write-Info "To update cluster-config.yaml:"
            Write-Host "  .\discover-nodes.ps1 -Method auto -UpdateConfig"
        }
    }
    
    # Show errors if any
    if ($result.Errors.Count -gt 0) {
        Write-Host ""
        Write-Warn "Warnings:"
        foreach ($err in $result.Errors) {
            Write-Host "  - $err" -ForegroundColor Yellow
        }
    }
}

Write-Host ""

# Exit with appropriate code
$expectedWorkers = $Hostnames.Count
$foundWorkers = ($result.Nodes | Where-Object { $_.Role -eq "worker" }).Count

if ($result.Nodes.Count -eq 0) {
    exit 1
} elseif ($foundWorkers -lt $expectedWorkers) {
    Write-Warn "Only found $foundWorkers/$expectedWorkers workers"
    exit 2
} else {
    exit 0
}
