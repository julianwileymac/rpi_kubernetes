# Bootstrap Scripts

This directory contains scripts and configuration files for preparing cluster nodes.

## Overview

Before installing k3s, each node needs to be configured with:
- Disabled swap (Kubernetes requirement)
- Enabled cgroups (memory and cpuset)
- Required packages (including Avahi for mDNS)
- Network configuration
- Firewall rules
- External storage (optional but recommended)

## Key Features

- **mDNS Discovery**: Automatic node discovery without static IP addresses
- **Auto-Start Services**: k3s starts automatically on boot
- **Health Monitoring**: Continuous cluster health checks with recovery
- **Dynamic IP Support**: Handles IP address changes via mDNS resolution

## Directory Structure

```
bootstrap/
├── configs/
│   ├── node-common.yaml         # Shared configuration values
│   ├── control-plane.yaml       # Ubuntu desktop control plane config
│   └── worker-rpi5.yaml         # Raspberry Pi 5 worker template
├── scripts/
│   ├── prep-existing-os.sh      # Prep script for existing OS installations
│   ├── port-to-rpi.ps1          # PowerShell script to transfer and run prep scripts
│   ├── prepare-rpi.sh           # Bootstrap script for RPi5 nodes
│   ├── prepare-ubuntu.sh        # Bootstrap script for Ubuntu control plane
│   ├── discover-nodes.ps1       # PowerShell network/mDNS discovery
│   ├── discover_cluster.py      # Python mDNS discovery with fallback
│   ├── cluster_registry.py      # Node registry with health tracking
│   ├── cluster_health_monitor.py # Health monitoring daemon
│   ├── k3s-health-check.sh      # Health check script for systemd
│   ├── k3s-agent-recovery.sh    # Worker node recovery script
│   ├── bootstrap_cluster.py     # Python bootstrap with discovery integration
│   ├── bootstrap-cluster.ps1    # Windows-native bootstrap orchestrator
│   └── diagnose-cluster.ps1     # Cluster diagnostics and troubleshooting
└── README.md
```

## Quick Start

### 0. Prepare Existing OS Installations (If Needed)

If you have Raspberry Pi OS already flashed to your SD cards **without** the `julian` user configured, you need to prepare the OS first before running `prepare-rpi.sh`.

**Option A: Automated with Discovery (Windows - Recommended)**

```powershell
# Auto-discover nodes and prepare them (no IP addresses needed)
.\bootstrap\scripts\port-to-rpi.ps1 -Discover -AuthMethod "password" -DefaultUser "pi"

# Or use mDNS hostnames directly (after initial Avahi install)
.\bootstrap\scripts\port-to-rpi.ps1 -UseMDNS -Hostnames "rpi1,rpi2,rpi3,rpi4" -AuthMethod "password"
```

**Option B: Automated with IP Addresses (Windows)**

```powershell
# From your workstation, run the port-to-rpi script
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @("rpi1=192.168.1.101","rpi2=192.168.1.102","rpi3=192.168.1.103","rpi4=192.168.1.104") `
    -AuthMethod "key" `
    -SshKey "~\.ssh\id_ed25519" `
    -DefaultUser "pi"

# Or with password authentication:
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @("rpi1=192.168.1.101","rpi2=192.168.1.102","rpi3=192.168.1.103","rpi4=192.168.1.104") `
    -AuthMethod "password" `
    -DefaultUser "pi"
```

**Option C: Python Bootstrap with Discovery**

```bash
# Discover and bootstrap all nodes
python bootstrap/scripts/bootstrap_cluster.py --discover --bootstrap-only

# Or use existing cluster-config.yaml
python bootstrap/scripts/bootstrap_cluster.py --config cluster-config.yaml
```

This script will:
1. Copy `prep-existing-os.sh` to each Pi
2. Run it to create `julian` user and install prerequisites
3. Install Avahi for mDNS discovery
4. Copy `prepare-rpi.sh` to each Pi (to `julian` user's home)

**Option B: Manual (Single Node)**

```bash
# Copy prep script to Pi
scp bootstrap/scripts/prep-existing-os.sh pi@192.168.1.101:~/

# SSH into Pi
ssh pi@192.168.1.101

# Run prep script with key authentication
sudo chmod +x ~/prep-existing-os.sh
sudo ./prep-existing-os.sh --hostname rpi1 --auth-method key --ssh-key ~/.ssh/id_ed25519.pub

# Or with password authentication:
sudo ./prep-existing-os.sh --hostname rpi1 --auth-method password

# Test SSH as julian
exit
ssh julian@192.168.1.101

# Copy bootstrap script
scp bootstrap/scripts/prepare-rpi.sh julian@192.168.1.101:~/
```

For detailed instructions, see [docs/raspberry-pi-setup.md](../docs/raspberry-pi-setup.md#preparing-existing-os-installations).

### 1. Prepare Control Plane (Ubuntu Desktop)

```bash
# Copy script to Ubuntu machine
scp scripts/prepare-ubuntu.sh ubuntu@192.168.1.100:~/

# SSH into the machine
ssh ubuntu@192.168.1.100

# Run with options
sudo ./prepare-ubuntu.sh \
    --hostname k8s-control \
    --ip 192.168.1.100/24 \
    --gateway 192.168.1.1 \
    --gpu  # Optional: if you have an NVIDIA GPU

# Reboot to apply changes
sudo reboot
```

### 2. Prepare Worker Nodes (Raspberry Pi 5)

```bash
# For each RPi node, copy and run the script
scp scripts/prepare-rpi.sh julian@192.168.1.101:~/

ssh julian@192.168.1.101

sudo ./prepare-rpi.sh \
    --hostname rpi1 \
    --ip 192.168.1.101/24 \
    --storage /dev/sda  # External USB SSD

sudo reboot
```

Repeat for nodes 2-4, changing hostname and IP:
- Node 2: `--hostname rpi2 --ip 192.168.1.102/24`
- Node 3: `--hostname rpi3 --ip 192.168.1.103/24`
- Node 4: `--hostname rpi4 --ip 192.168.1.104/24`

## Configuration Files

### node-common.yaml

Shared configuration values used by all nodes:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cluster.name` | Cluster identifier | `rpi-k8s-cluster` |
| `cluster.domain` | DNS domain | `local` |
| `k3s.version` | k3s version to install | `v1.29.0+k3s1` |
| `storage.mount_point` | External storage mount | `/mnt/storage` |

### control-plane.yaml

Ubuntu desktop specific configuration:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `node.hostname` | Control plane hostname | `k8s-control` |
| `node.ip_address` | Static IP address | `192.168.1.100` |
| `gpu.enabled` | Enable NVIDIA GPU support | `true` |
| `metallb.address_pool` | LoadBalancer IP range | `192.168.1.200-192.168.1.250` |

### worker-rpi5.yaml

Raspberry Pi 5 worker configuration template:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `node.hostname` | Worker hostname | `rpi1` |
| `node.ip_address` | Static IP address | `192.168.1.101` |
| `storage.external_device` | USB SSD device | `/dev/sda` |
| `hardware.swap_disabled` | Disable swap | `true` |
| `hardware.cpu_governor` | CPU performance mode | `performance` |

## Script Parameters

### prepare-rpi.sh

| Option | Description |
|--------|-------------|
| `--hostname NAME` | Set system hostname |
| `--ip ADDRESS` | Set static IP (CIDR format, e.g., 192.168.1.101/24) |
| `--gateway ADDRESS` | Gateway IP (default: 192.168.1.1) |
| `--dns SERVERS` | DNS servers, comma-separated |
| `--storage DEVICE` | External storage device (e.g., /dev/sda) |
| `--storage-mount PATH` | Mount point (default: /mnt/storage) |
| `--timezone TZ` | Timezone (default: America/New_York) |

### prep-existing-os.sh

Prepares Raspberry Pi OS installations for the bootstrap process. Run this **before** `prepare-rpi.sh` if your SD cards were flashed with default settings.

| Option | Description |
|--------|-------------|
| `--hostname NAME` | Set system hostname |
| `--timezone TZ` | Set timezone |
| `--auth-method METHOD` | SSH authentication method (`key` or `password`) |
| `--ssh-key PATH` | Path to SSH public key (for `key` auth method) |
| `--interactive` | Interactive mode with prompts |
| `--dry-run` | Preview changes without applying |

### port-to-rpi.ps1

PowerShell script for Windows workstations to automate transferring and running prep scripts on multiple Pis.

| Parameter | Description |
|-----------|-------------|
| `-Hosts` | Array of hosts in format `"hostname=ip"` (optional if using `-Discover`) |
| `-Discover` | Auto-discover nodes on network using hostname pattern |
| `-NetworkRange` | Network range to scan (e.g., `192.168.1.0/24`) |
| `-AuthMethod` | SSH authentication method (`key` or `password`) |
| `-SshKey` | Path to SSH private key file (for `key` auth method) |
| `-DefaultUser` | Default user on Pi (usually `pi`) |
| `-RunBootstrap` | Also run bootstrap script after prep (runs `prepare-rpi.sh`) |
| `-Interactive` | Interactive mode for prompts |
| `-SkipPrep` | Skip prep step (if already done) |
| `-DryRun` | Preview without making changes |

### discover-nodes.ps1

PowerShell script that discovers nodes via mDNS or network scan.

| Parameter | Description |
|-----------|-------------|
| `-Method` | Discovery method: `auto`, `mdns`, or `scan` (default: `auto`) |
| `-NetworkRange` | Network range to scan (default: auto-detect) |
| `-HostnamePattern` | Hostname pattern to match (default: `rpi*`) |
| `-Hostnames` | Specific hostnames to resolve via mDNS |
| `-ControlPlane` | Control plane hostname (default: `k8s-control`) |
| `-OutputFormat` | Output format: `table`, `json`, `hosts`, or `config` |
| `-CheckServices` | Also check SSH and k3s port availability |
| `-UpdateConfig` | Update cluster-config.yaml with discovered IPs |
| `-IncludeControlPlane` | Include control plane in discovery |
| `-Verbose` | Show detailed progress |

**Examples:**

```powershell
# Auto-discover using mDNS with network scan fallback
.\discover-nodes.ps1 -Method auto

# mDNS-only discovery
.\discover-nodes.ps1 -Method mdns -Hostnames "rpi1,rpi2,rpi3,rpi4"

# Network scan discovery
.\discover-nodes.ps1 -Method scan -NetworkRange "192.168.12.0/24"

# Update cluster config with discovered IPs
.\discover-nodes.ps1 -UpdateConfig
```

### discover_cluster.py

Python discovery script with mDNS primary and network scan fallback.

| Parameter | Description |
|-----------|-------------|
| `--method` | Discovery method: `auto`, `mdns`, or `scan` |
| `--hostnames` | Comma-separated list of worker hostnames |
| `--control-plane` | Control plane hostname |
| `--network` | Network range for scanning |
| `--output` | Output format: `table`, `json`, `yaml`, or `hosts` |
| `--update-config` | Update cluster-config.yaml with discovered IPs |
| `--no-cache` | Disable caching |
| `--clear-cache` | Clear discovery cache |
| `--verbose` | Verbose output |

**Examples:**

```bash
# Auto-discover nodes
python discover_cluster.py --verbose

# mDNS discovery
python discover_cluster.py --method mdns --hostnames rpi1,rpi2,rpi3,rpi4

# Update config file
python discover_cluster.py --update-config --config ../cluster-config.yaml

# JSON output
python discover_cluster.py --output json
```

### cluster_health_monitor.py

Health monitoring daemon for cluster nodes.

| Parameter | Description |
|-----------|-------------|
| `--daemon` | Run as background daemon |
| `--check-once` | Run single health check |
| `--status` | Show daemon status |
| `--config` | Path to cluster-config.yaml |
| `--interval` | Check interval in seconds |
| `--output` | Output format: `text` or `json` |

**Examples:**

```bash
# Run single health check
python cluster_health_monitor.py --check-once

# Run as daemon
python cluster_health_monitor.py --daemon --interval 60

# Check daemon status
python cluster_health_monitor.py --status
```

### bootstrap-cluster.ps1

Windows-native bootstrap orchestrator that replaces Ansible for bootstrapping nodes.

| Parameter | Description |
|-----------|-------------|
| `-ControlPlane` | Control plane connection string (`user@ip`) |
| `-Workers` | Array of worker connection strings |
| `-ConfigFile` | JSON config file with node details |
| `-SshKey` | Path to SSH private key file |
| `-Parallel` | Run bootstrap in parallel for multiple nodes |
| `-DryRun` | Preview without making changes |
| `-Verbose` | Show detailed output |

### diagnose-cluster.ps1

Cluster diagnostics and troubleshooting tool that checks connectivity and prerequisites.

| Parameter | Description |
|-----------|-------------|
| `-ControlPlane` | Control plane connection string |
| `-Workers` | Array of worker connection strings |
| `-ConfigFile` | JSON config file with node details |
| `-SshKey` | Path to SSH private key file |
| `-Verbose` | Show detailed diagnostic output |

### prepare-ubuntu.sh

| Option | Description |
|--------|-------------|
| `--hostname NAME` | Set system hostname |
| `--ip ADDRESS` | Set static IP (CIDR format) |
| `--interface NAME` | Network interface (auto-detect if empty) |
| `--gateway ADDRESS` | Gateway IP |
| `--dns SERVERS` | DNS servers, comma-separated |
| `--gpu` | Install NVIDIA GPU drivers and container toolkit |
| `--metallb-pool RANGE` | MetalLB IP address pool |

## What the Scripts Do

### Existing OS Prep Script (prep-existing-os.sh)

Prepares Raspberry Pi nodes with existing OS installations for the bootstrap process.

1. **User Creation**: Creates `julian` user if it doesn't exist
2. **Sudo Access**: Adds `julian` to sudo group with passwordless sudo
3. **Prerequisites**: Installs sudo, curl, ca-certificates, python3, rsync, openssh-server
4. **SSH Server**: Ensures SSH server is enabled and running
5. **SSH Authentication** (based on `--auth-method`):
   - **Key auth**: Adds SSH public key to `julian` user
   - **Password auth**: Prompts for password and enables SSH password authentication
6. **Hostname** (optional): Sets system hostname
7. **Timezone** (optional): Sets system timezone

### Raspberry Pi Script (prepare-rpi.sh)

1. **System Update**: Updates all packages to latest versions
2. **Hostname**: Sets the system hostname
3. **Static IP**: Configures static IP via dhcpcd (optional with mDNS)
4. **Swap**: Disables swap completely (required by Kubernetes)
5. **cgroups**: Enables memory and cpuset cgroups in cmdline.txt
6. **64-bit Kernel**: Ensures 64-bit mode is enabled
7. **Packages**: Installs nfs-common, open-iscsi, jq, avahi-daemon, etc.
8. **mDNS/Avahi**: Configures hostname.local resolution
9. **Kernel Params**: Configures sysctl for Kubernetes networking
10. **External Storage**: Partitions, formats, and mounts USB SSD
11. **Firewall**: Configures UFW with required ports (including mDNS port 5353)
12. **Power Saving**: Disables WiFi and Bluetooth
13. **k3s Agent Recovery**: Installs service for reconnection after IP changes

### Ubuntu Script (prepare-ubuntu.sh)

1. **System Update**: Full system upgrade
2. **Hostname**: Sets hostname via hostnamectl
3. **Static IP**: Configures netplan for static IP
4. **Swap**: Disables swap
5. **Packages**: Installs kubectl, helm, development tools
6. **Kernel Params**: Configures sysctl for Kubernetes
7. **NVIDIA GPU** (optional): Installs drivers and container toolkit
8. **Storage**: Creates directory structure for services
9. **Firewall**: Configures UFW with control plane ports
10. **k3s Config**: Pre-creates /etc/rancher/k3s/config.yaml

## Verification

After rebooting, verify the configuration:

### Check cgroups (RPi)
```bash
cat /proc/cgroups | grep -E 'memory|cpuset'
# Should show both enabled (1 in the enabled column)
```

### Check swap is disabled
```bash
free -h
# Swap should show 0B
```

### Check architecture (RPi)
```bash
uname -m
# Should show aarch64
```

### Check external storage
```bash
df -h /mnt/storage
# Should show your USB SSD
```

### Check firewall
```bash
sudo ufw status
# Should show active with allowed ports
```

### Check mDNS/Avahi
```bash
# Check Avahi service
sudo systemctl status avahi-daemon

# Test mDNS resolution
avahi-resolve -n rpi1.local
ping rpi2.local

# Browse advertised services
avahi-browse -a

# Check mDNS firewall rule
sudo ufw status | grep 5353
```

### Check auto-start services (control plane)
```bash
# Check k3s server startup service
sudo systemctl status k3s-server-startup.service

# Check health monitoring
sudo systemctl status k3s-cluster-health.timer

# View health check logs
sudo journalctl -u k3s-cluster-health -f
```

### Check recovery service (workers)
```bash
# Check agent recovery service
sudo systemctl status k3s-agent-recovery.service

# View recovery logs
sudo journalctl -u k3s-agent-recovery -f
```

## Troubleshooting

### mDNS hostname.local not resolving
```bash
# Check Avahi is running
sudo systemctl status avahi-daemon

# Restart Avahi
sudo systemctl restart avahi-daemon

# Check nsswitch.conf has mdns
grep hosts /etc/nsswitch.conf
# Should include: mdns4_minimal [NOTFOUND=return] dns mdns4

# Check firewall allows mDNS
sudo ufw allow 5353/udp

# Test from another node
avahi-resolve -n hostname.local
```

### IP address changed and cluster is disconnected
```bash
# On control plane - rediscover nodes
python bootstrap/scripts/discover_cluster.py --update-config

# The health monitor should auto-detect changes
sudo journalctl -u k3s-cluster-health -f

# On workers - the recovery service handles reconnection
sudo journalctl -u k3s-agent-recovery -f

# Force rediscovery
python bootstrap/scripts/cluster_health_monitor.py --check-once
```

### cgroups not enabled
Edit `/boot/firmware/cmdline.txt` (or `/boot/cmdline.txt` on older OS) and add:
```
cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset
```

### Swap keeps coming back
```bash
sudo systemctl disable dphys-swapfile
sudo rm /var/swap
```

### External storage not mounting
```bash
# Check device exists
lsblk

# Check partition
sudo fdisk -l /dev/sda

# Check fstab entry
cat /etc/fstab | grep storage
```

### Static IP not working
```bash
# Check dhcpcd config (RPi)
cat /etc/dhcpcd.conf

# Check netplan config (Ubuntu)
cat /etc/netplan/99-static-ip.yaml
```

## Next Steps

After all nodes are bootstrapped and rebooted:

1. Run the Ansible playbooks to install k3s
2. Verify cluster with `kubectl get nodes`
3. Deploy base services

See [../ansible/README.md](../ansible/README.md) for cluster installation instructions.
