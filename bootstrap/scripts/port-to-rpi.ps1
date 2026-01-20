# =============================================================================
# Raspberry Pi Port-to-Pi Script (PowerShell)
# =============================================================================
# Version: 1.0.0
#
# Transfers and executes the prep-existing-os.sh and prepare-rpi.sh scripts
# to Raspberry Pi nodes with existing OS installations.
#
# Usage:
#   .\port-to-rpi.ps1 -Hosts "rpi1=192.168.1.101,rpi2=192.168.1.102" -SshKey "~\.ssh\id_ed25519"
#   .\port-to-rpi.ps1 -Hosts @("rpi1=192.168.1.101","rpi2=192.168.1.102") -Interactive
#
# Prerequisites:
#   - PowerShell 5.1 or later
#   - SSH access to Raspberry Pi nodes (default user, usually 'pi')
#   - Network connectivity to all Pi nodes
#
# What this script does:
#   1. Copies prep-existing-os.sh to each Pi node
#   2. Runs prep-existing-os.sh to create 'julian' user and install prerequisites
#   3. Copies prepare-rpi.sh to each Pi node (to julian user's home)
#   4. Provides next steps for running prepare-rpi.sh
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string[]]$Hosts = @(),
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("key", "password")]
    [string]$AuthMethod = "key",
    
    [Parameter(Mandatory=$false)]
    [string]$SshKey = "",
    
    [Parameter(Mandatory=$false)]
    [string]$DefaultUser = "pi",
    
    [Parameter(Mandatory=$false)]
    [switch]$Interactive = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipPrep = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$RunBootstrap = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$Discover = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$NetworkRange = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Script paths
$PrepScript = Join-Path $ScriptDir "prep-existing-os.sh"
$BootstrapScript = Join-Path $ScriptDir "prepare-rpi.sh"
$StorageHelperScript = Join-Path $ScriptDir "mount-external-storage.sh"
$DiscoverScript = Join-Path $ScriptDir "discover-nodes.ps1"

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

# Validate script files exist
if (-not (Test-Path $PrepScript)) {
    Write-Error "prep-existing-os.sh not found at: $PrepScript"
    exit 1
}

if (-not (Test-Path $BootstrapScript)) {
    Write-Error "prepare-rpi.sh not found at: $BootstrapScript"
    exit 1
}

if (-not (Test-Path $StorageHelperScript)) {
    Write-Error "mount-external-storage.sh not found at: $StorageHelperScript"
    exit 1
}

# Parse SSH key path
$SshKeyPath = ""
if ($SshKey) {
    $SshKeyPath = $SshKey
    if ($SshKeyPath.StartsWith("~")) {
        $SshKeyPath = $SshKeyPath.Replace("~", $HOME)
    }
    $SshKeyPath = Resolve-Path $SshKeyPath -ErrorAction SilentlyContinue
    if (-not $SshKeyPath) {
        Write-Warning "SSH key file not found: $SshKey (will continue without it)"
    } else {
        $SshKeyPath = $SshKeyPath.Path
    }
}

# Parse hosts
$HostList = @()
foreach ($hostEntry in $Hosts) {
    if ($hostEntry -match "^(.+?)=(.+)$") {
        $hostname = $matches[1]
        $ip = $matches[2]
        $HostList += @{
            Hostname = $hostname
            IP = $ip
        }
    } else {
        Write-Error "Invalid host format: $hostEntry (expected: hostname=ip)"
        exit 1
    }
}

Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "Raspberry Pi Port-to-Pi Script v1.0.0" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Warning "DRY RUN MODE - No changes will be made"
    Write-Host ""
}

Write-Info "Target nodes:"
foreach ($node in $HostList) {
    Write-Host "  - $($node.Hostname): $($node.IP)" -ForegroundColor White
}
Write-Host ""

# Interactive mode for auth method and SSH key
if ($Interactive) {
    $authInput = Read-Host "Enter auth method (key or password) [$AuthMethod]"
    if ($authInput) {
        if ($authInput -eq "key" -or $authInput -eq "password") {
            $AuthMethod = $authInput
        } else {
            Write-Warning "Invalid auth method: $authInput. Using default: $AuthMethod"
        }
    }
    
    if ($AuthMethod -eq "key" -and -not $SshKeyPath) {
        $keyInput = Read-Host "Enter path to SSH public key (or press Enter to skip) [~\.ssh\id_ed25519.pub]"
        if ($keyInput) {
            $SshKeyPath = $keyInput
            if ($SshKeyPath.StartsWith("~")) {
                $SshKeyPath = $SshKeyPath.Replace("~", $HOME)
            }
            $SshKeyPath = Resolve-Path $SshKeyPath -ErrorAction SilentlyContinue
            if (-not $SshKeyPath) {
                Write-Warning "SSH key file not found: $keyInput"
                $SshKeyPath = ""
            } else {
                $SshKeyPath = $SshKeyPath.Path
            }
        }
    }
}

# Build SSH command prefix
$SshArgs = ""
$ScpArgs = ""
if ($SshKeyPath) {
    # For SSH on Windows, use -i with the private key (remove .pub if present)
    $PrivateKeyPath = $SshKeyPath -replace "\.pub$", ""
    if (Test-Path $PrivateKeyPath) {
        $SshArgs = "-i `"$PrivateKeyPath`""
        $ScpArgs = "-i `"$PrivateKeyPath`""
    }
}

# Process each host
foreach ($node in $HostList) {
    $hostname = $node.Hostname
    $ip = $node.IP
    $targetUser = $DefaultUser
    
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Info "Processing: $hostname ($ip)"
    Write-Host "---------------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would connect to $targetUser@$ip and run prep script"
        continue
    }
    
    # Step 1: Copy prep script
    Write-Info "Copying prep-existing-os.sh to $targetUser@$ip..."
    $copyPrepCmd = "scp $ScpArgs `"$PrepScript`" ${targetUser}@${ip}:~/prep-existing-os.sh"
    try {
        Invoke-Expression $copyPrepCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to copy prep script to $hostname"
            continue
        }
        Write-Success "Prep script copied"
    } catch {
        Write-Error "Error copying prep script: $_"
        continue
    }
    
    # Step 2: Make prep script executable and run it
    if (-not $SkipPrep) {
        Write-Info "Running prep-existing-os.sh on $hostname..."
        
        $prepCmd = @"
chmod +x ~/prep-existing-os.sh && sudo ~/prep-existing-os.sh --hostname $hostname --timezone America/New_York --auth-method $AuthMethod $(
    if ($AuthMethod -eq "key" -and $SshKeyPath) {
        " --ssh-key `"$SshKeyPath`""
    }
)
"@
        
        $sshCmd = "ssh $SshArgs -o StrictHostKeyChecking=no ${targetUser}@${ip} `"$prepCmd`""
        
        try {
            Invoke-Expression $sshCmd
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Prep script returned non-zero exit code on $hostname (may still have worked)"
            } else {
                Write-Success "Prep script completed on $hostname"
            }
        } catch {
            Write-Error "Error running prep script: $_"
            continue
        }
        
        # Wait a moment for user creation to complete
        Start-Sleep -Seconds 2
    } else {
        Write-Info "Skipping prep script (--SkipPrep specified)"
    }
    
    # Step 3: Copy bootstrap script to julian user
    Write-Info "Copying prepare-rpi.sh to julian@$ip..."
    $copyBootstrapCmd = "scp $ScpArgs `"$BootstrapScript`" julian@${ip}:~/prepare-rpi.sh"
    try {
        Invoke-Expression $copyBootstrapCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to copy bootstrap script to julian user (may need to run prep script first)"
            Write-Info "You can copy it manually later: scp `"$BootstrapScript`" julian@${ip}:~/"
        } else {
            Write-Success "Bootstrap script copied to julian user"
        }
    } catch {
        Write-Warning "Error copying bootstrap script: $_"
        Write-Info "You can copy it manually later: scp `"$BootstrapScript`" julian@${ip}:~/"
    }

    # Step 3b: Copy storage helper script to julian user
    Write-Info "Copying mount-external-storage.sh to julian@$ip..."
    $copyHelperCmd = "scp $ScpArgs `"$StorageHelperScript`" julian@${ip}:~/mount-external-storage.sh"
    try {
        Invoke-Expression $copyHelperCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to copy storage helper script to julian user"
            Write-Info "You can copy it manually later: scp `"$StorageHelperScript`" julian@${ip}:~/"
        } else {
            Write-Success "Storage helper script copied to julian user"
        }
    } catch {
        Write-Warning "Error copying storage helper script: $_"
        Write-Info "You can copy it manually later: scp `"$StorageHelperScript`" julian@${ip}:~/"
    }
    
    # Step 4: Run bootstrap script if -RunBootstrap is set
    if ($RunBootstrap) {
        Write-Info "Running bootstrap script on $hostname..."
        
        $lastOctet = $ip.Split('.')[-1]
        $bootstrapCmd = @"
chmod +x ~/prepare-rpi.sh ~/mount-external-storage.sh && sudo ~/prepare-rpi.sh --hostname $hostname --ip 192.168.1.$lastOctet/24 --gateway 192.168.1.1 --timezone America/New_York --storage auto --skip-reboot-prompt
"@
        
        $runBootstrapCmd = "ssh $SshArgs -o StrictHostKeyChecking=no julian@${ip} `"$bootstrapCmd`""
        
        try {
            Invoke-Expression $runBootstrapCmd
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Bootstrap script returned non-zero exit code on $hostname (may still have worked)"
            } else {
                Write-Success "Bootstrap script completed on $hostname"
            }
        } catch {
            Write-Error "Error running bootstrap script: $_"
        }
    }
    
    Write-Host ""
}

# Print summary and next steps
Write-Host "=============================================================================" -ForegroundColor Green
Write-Success "Port-to-Pi Complete!"
Write-Host "=============================================================================" -ForegroundColor Green
Write-Host ""

if (-not $RunBootstrap) {
    Write-Info "Next Steps:"
    Write-Host ""
    Write-Host "For each Pi node, SSH as 'julian' and run the bootstrap script:" -ForegroundColor White
    Write-Host ""
    
    foreach ($node in $HostList) {
        $hostname = $node.Hostname
        $ip = $node.IP
        $lastOctet = $ip.Split('.')[-1]
        
        Write-Host "  # $hostname" -ForegroundColor Yellow
        Write-Host "  ssh julian@$ip" -ForegroundColor White
        Write-Host "  sudo chmod +x ~/prepare-rpi.sh ~/mount-external-storage.sh" -ForegroundColor White
        Write-Host "  sudo ~/prepare-rpi.sh --hostname $hostname --ip 192.168.1.$lastOctet/24 --timezone America/New_York --storage auto" -ForegroundColor White
        Write-Host ""
    }
    
    Write-Info "Or use -RunBootstrap flag to automatically run bootstrap script after prep"
    Write-Host ""
} else {
    Write-Info "All nodes have been prepped and bootstrapped!"
    Write-Host ""
    Write-Info "Next step: Reboot all nodes to apply kernel changes"
    Write-Host ""
    Write-Host "  For each node:" -ForegroundColor White
    Write-Host "    ssh julian@<ip>" -ForegroundColor White
    Write-Host "    sudo reboot" -ForegroundColor White
    Write-Host ""
}

Write-Info "To run bootstrap with additional options (e.g., --storage auto or /dev/sda), use:"
Write-Host "  .\bootstrap-cluster.ps1 -Workers @(<node-list>) ..."
Write-Host ""