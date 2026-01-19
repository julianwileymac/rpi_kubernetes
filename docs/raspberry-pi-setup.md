# Raspberry Pi Setup Guide

This comprehensive guide covers everything you need to set up Raspberry Pi 5 nodes for your Kubernetes cluster, including initial imaging, bootstrapping, and reimaging procedures.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial SD Card Imaging](#initial-sd-card-imaging)
3. [First Boot Configuration](#first-boot-configuration)
4. [Network Setup](#network-setup)
5. [Preparing Existing OS Installations](#preparing-existing-os-installations)
6. [Running the Bootstrap Script](#running-the-bootstrap-script)
7. [Verifying the Setup](#verifying-the-setup)
8. [Reimaging a Node](#reimaging-a-node)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Hardware Checklist

For **each** Raspberry Pi 5 node:

| Item | Specification | Notes |
|------|---------------|-------|
| Raspberry Pi 5 | 8GB RAM recommended | 4GB minimum |
| MicroSD Card | 32GB+ Class 10/A2 | Samsung EVO or SanDisk Extreme recommended |
| USB SSD | 256GB+ SATA or NVMe | For persistent storage |
| Power Supply | Official 27W USB-C | Third-party may cause throttling |
| Ethernet Cable | Cat6 | For gigabit speeds |
| Active Cooler | Fan + Heatsink | Essential for sustained workloads |

### Software Requirements

On your **workstation** (Windows, Mac, or Linux):

1. **Raspberry Pi Imager** - [Download here](https://www.raspberrypi.com/software/)
2. **SSH Client** - Built into Mac/Linux, use PuTTY or Windows Terminal on Windows
3. **SD Card Reader** - USB or built-in

### Network Information

Before starting, gather:
- [ ] Your network's IP range (e.g., `192.168.1.x`)
- [ ] Gateway IP (usually `192.168.1.1`)
- [ ] Available static IPs for each node
- [ ] DNS servers (e.g., `8.8.8.8, 1.1.1.1`)

**Recommended IP Assignment:**

| Node | Hostname | IP Address |
|------|----------|------------|
| Control Plane | k8s-control | 192.168.1.100 |
| Worker 1 | rpi1 | 192.168.1.101 |
| Worker 2 | rpi2 | 192.168.1.102 |
| Worker 3 | rpi3 | 192.168.1.103 |
| Worker 4 | rpi4 | 192.168.1.104 |

---

## Initial SD Card Imaging

### Step 1: Download Raspberry Pi Imager

1. Go to [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Download and install Raspberry Pi Imager for your OS
3. Insert your microSD card into your computer

### Step 2: Select Operating System

1. Open Raspberry Pi Imager
2. Click **"Choose OS"**
3. Select **"Raspberry Pi OS (other)"**
4. Select **"Raspberry Pi OS Lite (64-bit)"**
   
   > ⚠️ **Important**: Must be the **64-bit Lite** version (no desktop)

### Step 3: Configure Advanced Options

1. Click **"Choose Storage"** and select your SD card
2. Click the **gear icon** (⚙️) or press `Ctrl+Shift+X` to open Advanced Options

Configure the following settings:

#### Set Hostname
```
☑ Set hostname: rpi1
```
(Change for each node: rpi1, rpi2, rpi3, rpi4)

#### Enable SSH
```
☑ Enable SSH
  ○ Use password authentication
  ● Allow public-key authentication only
    [Paste your public SSH key here]
```

To get your SSH public key:
```bash
# On Mac/Linux
cat ~/.ssh/id_ed25519.pub

# On Windows (PowerShell)
Get-Content ~\.ssh\id_ed25519.pub

# If you don't have a key, generate one:
ssh-keygen -t ed25519 -C "your-email@example.com"
```

#### Set Username and Password
```
☑ Set username and password
  Username: julian
  Password: [choose a strong password]
```

#### Configure Wireless LAN (Optional)
```
☐ Configure wireless LAN
```
(Leave unchecked - we'll use Ethernet)

#### Set Locale Settings
```
☑ Set locale settings
  Time zone: America/New_York  (adjust to your timezone)
  Keyboard layout: us
```

### Step 4: Write the Image

1. Click **"Save"** to save the advanced options
2. Click **"Write"**
3. Confirm when prompted (this will erase the SD card)
4. Wait for writing and verification to complete (~5-10 minutes)
5. Remove the SD card when done

### Step 5: Repeat for Each Node

Repeat steps 2-4 for each Raspberry Pi, changing only the hostname:
- `rpi1`
- `rpi2`
- `rpi3`
- `rpi4`

> 💡 **Tip**: Label your SD cards with the hostname to avoid confusion

---

## First Boot Configuration

### Step 1: Assemble the Hardware

1. Install the active cooler on the Raspberry Pi
2. Insert the imaged SD card
3. Connect the USB SSD to a USB 3.0 port (blue)
4. Connect the Ethernet cable
5. Connect power last

### Step 2: Wait for Boot

The first boot takes 1-2 minutes. The green LED will flash during boot.

### Step 3: Find the IP Address

**Option A: Check your router's DHCP list**
- Log into your router admin page
- Look for devices named `rpi1`, `rpi2`, etc.

**Option B: Use network scanning**
```bash
# On Mac
arp -a | grep -i "raspberry\|dc:a6:32\|e4:5f:01"

# On Linux
nmap -sn 192.168.1.0/24 | grep -B 2 "Raspberry"

# On Windows (PowerShell)
arp -a
```

**Option C: Connect a monitor temporarily**
```bash
# The IP will be shown on the login screen
```

### Step 4: Test SSH Connection

```bash
# Replace with your node's IP
ssh julian@192.168.1.101

# If using password authentication
# Enter the password you set in Imager

# If successful, you'll see:
# julian@rpi1:~ $
```

### Step 5: Verify Basic System Info

```bash
# Check hostname
hostname

# Check architecture (should be aarch64)
uname -m

# Check memory
free -h

# Check disk
lsblk
```

---

## Network Setup

### Option A: Static IP via DHCP Reservation (Recommended)

Configure your router to always assign the same IP to each Raspberry Pi based on its MAC address. This is the cleanest approach.

1. Log into your router
2. Find DHCP reservation or static DHCP settings
3. Add entries for each Pi's MAC address

### Option B: Static IP on the Pi

If you can't configure DHCP reservation, set a static IP on each Pi:

```bash
# SSH into the Pi
ssh julian@<current-ip>

# Edit dhcpcd.conf
sudo nano /etc/dhcpcd.conf

# Add these lines at the end (adjust IPs for your network):
interface eth0
static ip_address=192.168.1.101/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8 1.1.1.1

# Save: Ctrl+O, Enter, Ctrl+X

# Reboot to apply
sudo reboot
```

### Verify Network Configuration

After setting static IP:

```bash
# Check IP address
ip addr show eth0

# Test gateway connectivity
ping -c 3 192.168.1.1

# Test internet connectivity
ping -c 3 8.8.8.8

# Test DNS resolution
ping -c 3 google.com
```

---

## Preparing Existing OS Installations

If you have Raspberry Pi OS already flashed to your SD cards (or used Raspberry Pi Imager with default settings), you'll need to prepare the OS before running the bootstrap script. This section covers preparing nodes with existing OS installations.

> **Note**: If you followed the [Initial SD Card Imaging](#initial-sd-card-imaging) section and configured the `julian` user during imaging, you can skip this section and go directly to [Running the Bootstrap Script](#running-the-bootstrap-script).

### What Needs to Be Done

Before running `prepare-rpi.sh`, each Pi must have:
- ✅ The `julian` user created and in the `sudo` group
- ✅ Prerequisites installed (curl, ca-certificates, python3, rsync, openssh-server)
- ✅ SSH server enabled and running
- ✅ Optional: Hostname set (e.g., `rpi1`, `rpi2`, etc.)
- ✅ SSH authentication configured (either password or public key)

### Method 1: Automated Preparation (Recommended)

Use the PowerShell script from your **Windows workstation** to automate the entire process:

```powershell
# Navigate to the repository
cd C:\Users\Julian Wiley\Documents\GitHub\rpi_kubernetes

# Run the port-to-rpi script with SSH key authentication
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @(
        "rpi1=192.168.1.101",
        "rpi2=192.168.1.102",
        "rpi3=192.168.1.103",
        "rpi4=192.168.1.104"
    ) `
    -AuthMethod "key" `
    -SshKey "~\.ssh\id_ed25519" `
    -DefaultUser "pi"

# Or with password authentication
.\bootstrap\scripts\port-to-rpi.ps1 `
    -Hosts @(
        "rpi1=192.168.1.101",
        "rpi2=192.168.1.102",
        "rpi3=192.168.1.103",
        "rpi4=192.168.1.104"
    ) `
    -AuthMethod "password" `
    -DefaultUser "pi"
```

**What the script does:**
1. Copies `prep-existing-os.sh` to each Pi (as the default user, usually `pi`)
2. Runs `prep-existing-os.sh` to create `julian` user and install prerequisites
   - With `--auth-method key`: Adds SSH public key for passwordless access
   - With `--auth-method password`: Prompts for password and enables SSH password auth
3. Copies `prepare-rpi.sh` to each Pi (to the `julian` user's home directory)
4. Provides next steps for running the bootstrap script

**Interactive mode:**
```powershell
.\bootstrap\scripts\port-to-rpi.ps1 -Hosts "rpi1=192.168.1.101" -Interactive
```

**Skip prep step (if already done):**
```powershell
.\bootstrap\scripts\port-to-rpi.ps1 -Hosts "rpi1=192.168.1.101" -SkipPrep
```

### Method 2: Manual Preparation (Single Node)

If you prefer to prepare each node manually:

#### Step 1: Copy the Prep Script

```bash
# From your workstation, copy the prep script to the Pi
scp bootstrap/scripts/prep-existing-os.sh pi@192.168.1.101:~/
```

Replace `192.168.1.101` with your Pi's current IP address.

#### Step 2: SSH into the Pi

```bash
# SSH as the default user (usually 'pi')
ssh pi@192.168.1.101
```

#### Step 3: Run the Prep Script

**Basic usage (creates user and installs prerequisites only):**
```bash
sudo chmod +x ~/prep-existing-os.sh
sudo ./prep-existing-os.sh
```

**With hostname and SSH key authentication:**
```bash
sudo ./prep-existing-os.sh \
    --hostname rpi1 \
    --auth-method key \
    --ssh-key ~/.ssh/id_ed25519.pub \
    --timezone America/New_York
```

**With hostname and password authentication:**
```bash
sudo ./prep-existing-os.sh \
    --hostname rpi1 \
    --auth-method password \
    --timezone America/New_York
# You will be prompted to enter and confirm a password for the julian user
```

**Interactive mode (prompts for each option):**
```bash
sudo ./prep-existing-os.sh --interactive
```

#### Step 4: Test SSH Access as julian

```bash
# Exit the current SSH session
exit

# Test SSH as julian user
ssh julian@192.168.1.101

# If successful, you should see:
# julian@rpi1:~ $
```

#### Step 5: Copy Bootstrap Script

```bash
# From your workstation
scp bootstrap/scripts/prepare-rpi.sh julian@192.168.1.101:~/
```

### Prep Script Options

| Option | Description | Example |
|--------|-------------|---------|
| `--hostname NAME` | Set system hostname | `--hostname rpi1` |
| `--timezone TZ` | Set timezone | `--timezone America/New_York` |
| `--ssh-key PATH` | Add SSH public key for julian | `--ssh-key ~/.ssh/id_ed25519.pub` |
| `--interactive` | Interactive mode with prompts | `--interactive` |
| `--dry-run` | Preview changes without applying | `--dry-run` |
| `--help` | Show help message | `--help` |

### What the Prep Script Does

The `prep-existing-os.sh` script performs these steps:

1. **Creates `julian` user** (if it doesn't exist)
2. **Adds `julian` to sudo group** with passwordless sudo
3. **Installs prerequisites:**
   - `sudo`
   - `curl`
   - `ca-certificates`
   - `python3` and `python3-pip`
   - `rsync`
   - `openssh-server`
4. **Enables and starts SSH server**
5. **Configures SSH authentication** (based on `--auth-method`):
   - **Key auth** (`--auth-method key`): Adds SSH public key to `~julian/.ssh/authorized_keys`
   - **Password auth** (`--auth-method password`): Prompts for password and enables SSH password authentication
6. **Sets hostname** (if `--hostname` specified)
7. **Sets timezone** (if `--timezone` specified)

### Verification After Prep

After running the prep script, verify the setup:

```bash
# SSH as julian
ssh julian@192.168.1.101

# Check user exists
id julian
# Should show: uid=1001(julian) gid=1001(julian) groups=1001(julian),27(sudo)

# Check sudo access
sudo whoami
# Should output: root

# Check hostname (if set)
hostname
# Should show: rpi1 (or your specified hostname)

# Check timezone
timedatectl show --property=Timezone --value
# Should show: America/New_York (or your specified timezone)

# Check SSH authentication (depending on auth method used):
# For key auth:
cat ~/.ssh/authorized_keys

# For password auth:
sudo grep -i "PasswordAuthentication" /etc/ssh/sshd_config
# Should show: PasswordAuthentication yes
```

### Troubleshooting Prep Script

**User already exists:**
- The script will skip user creation but ensure the user is in the sudo group

**SSH key not added:**
- Check that the public key file path is correct and accessible
- Verify the file contains a valid public key (starts with `ssh-ed25519` or `ssh-rsa`)

**Can't SSH as julian after prep:**
- Wait a few seconds for user creation to complete
- Verify SSH server is running: `sudo systemctl status ssh`
- Check `/etc/passwd` for the julian user entry

---

## Running the Bootstrap Script

The bootstrap script prepares your Raspberry Pi for Kubernetes by:
- Disabling swap (required by Kubernetes)
- Enabling cgroups (memory and CPU isolation)
- Installing required packages
- Configuring kernel parameters
- Setting up external storage
- Configuring the firewall

### Method 1: Automated (Recommended)

From your **workstation**, use Ansible:

```bash
# Clone the repository
git clone https://github.com/your-repo/rpi_kubernetes.git
cd rpi_kubernetes

# Copy and edit inventory
cp ansible/inventory/cluster.example.yml ansible/inventory/cluster.yml
nano ansible/inventory/cluster.yml  # Edit with your IPs

# Run bootstrap playbook
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/bootstrap.yml
```

### Method 2: Manual (Single Node)

SSH into the Raspberry Pi and run the bootstrap script directly:

```bash
# SSH into the node
ssh julian@192.168.1.101

# Download the bootstrap script
curl -O https://raw.githubusercontent.com/your-repo/rpi_kubernetes/main/bootstrap/scripts/prepare-rpi.sh

# Make it executable
chmod +x prepare-rpi.sh

# Run with your configuration
sudo ./prepare-rpi.sh \
  --hostname rpi1 \
  --ip 192.168.1.101/24 \
  --gateway 192.168.1.1 \
  --storage /dev/sda \
  --timezone America/New_York
```

### Bootstrap Script Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--hostname` | Set system hostname | `rpi1` |
| `--ip` | Static IP with CIDR | `192.168.1.101/24` |
| `--gateway` | Default gateway | `192.168.1.1` |
| `--dns` | DNS servers (comma-separated) | `8.8.8.8,1.1.1.1` |
| `--storage` | External USB SSD device | `/dev/sda` |
| `--storage-mount` | Mount point for storage | `/mnt/storage` |
| `--timezone` | System timezone | `America/New_York` |

### What the Bootstrap Script Does

```
✓ Updates system packages
✓ Sets hostname and timezone
✓ Configures static IP (if specified)
✓ Disables swap completely
✓ Enables cgroups (memory, cpuset) in cmdline.txt
✓ Enables 64-bit kernel mode
✓ Minimizes GPU memory (headless operation)
✓ Disables WiFi and Bluetooth (power saving)
✓ Installs required packages (nfs-common, open-iscsi, jq, etc.)
✓ Configures kernel parameters for Kubernetes
✓ Partitions and mounts external storage
✓ Configures UFW firewall
```

### Reboot After Bootstrap

**Important**: You must reboot after running the bootstrap script:

```bash
sudo reboot
```

Wait 1-2 minutes for the Pi to come back online.

---

## Verifying the Setup

After rebooting, verify everything is configured correctly:

### Check 1: Hostname

```bash
hostname
# Should output: rpi1
```

### Check 2: Architecture

```bash
uname -m
# Should output: aarch64 (64-bit)
```

### Check 3: Swap Disabled

```bash
free -h
# Swap line should show: 0B 0B 0B
```

### Check 4: cgroups Enabled

```bash
cat /proc/cgroups | grep -E 'memory|cpuset'
# Should show enabled (1) for both:
# memory  0  92  1
# cpuset  0  10  1
```

### Check 5: External Storage Mounted

```bash
df -h /mnt/storage
# Should show your USB SSD
```

### Check 6: Kernel Parameters

```bash
cat /proc/cmdline | grep cgroup
# Should contain: cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset
```

### Check 7: Firewall Active

```bash
sudo ufw status
# Should show: Status: active
# With rules for ports 22, 6443, 10250, etc.
```

### Quick Verification Script

Run this one-liner to check everything:

```bash
echo "=== System Verification ===" && \
echo "Hostname: $(hostname)" && \
echo "Arch: $(uname -m)" && \
echo "Swap: $(free -h | grep Swap | awk '{print $2}')" && \
echo "cgroups: $(cat /proc/cgroups | grep -E 'memory|cpuset' | awk '{print $1": "$4}')" && \
echo "Storage: $(df -h /mnt/storage 2>/dev/null | tail -1 | awk '{print $2}' || echo 'Not mounted')" && \
echo "UFW: $(sudo ufw status | head -1)"
```

---

## Reimaging a Node

If a node becomes corrupted or you need to start fresh, follow these steps:

### When to Reimage

- Node won't boot
- Filesystem corruption
- Major misconfiguration
- Upgrading to new OS version
- Hardware changes (new SD card)

### Step 1: Remove Node from Cluster

If the node is part of the Kubernetes cluster:

```bash
# From the control plane or your workstation
kubectl drain rpi1 --ignore-daemonsets --delete-emptydir-data
kubectl delete node rpi1
```

### Step 2: Backup Important Data (Optional)

If the node is still accessible:

```bash
# SSH into the node
ssh julian@192.168.1.101

# Backup any important data from external storage
# (k3s data, custom configs, etc.)
tar -czvf /tmp/node-backup.tar.gz /mnt/storage/volumes

# Copy backup to your workstation
scp julian@192.168.1.101:/tmp/node-backup.tar.gz ./
```

### Step 3: Power Off and Remove SD Card

```bash
# Graceful shutdown
ssh julian@192.168.1.101 "sudo shutdown -h now"

# Wait 30 seconds, then remove power
# Remove the SD card
```

### Step 4: Reimage the SD Card

Follow the [Initial SD Card Imaging](#initial-sd-card-imaging) section above.

> ⚠️ **Important**: Use the same hostname as before to maintain cluster configuration

### Step 5: Handle External Storage

The USB SSD may already have data. You have two options:

**Option A: Preserve existing data**
```bash
# After first boot, SSH in and check if data exists
ssh julian@192.168.1.101
lsblk
sudo mount /dev/sda1 /mnt/storage
ls /mnt/storage  # Check contents
```

**Option B: Fresh start (wipe storage)**
```bash
# The bootstrap script with --storage will reformat if needed
# Or manually wipe:
sudo wipefs -a /dev/sda
```

### Step 6: Run Bootstrap Script

```bash
# SSH into the new node
ssh julian@192.168.1.101

# Run bootstrap (will detect existing storage if not wiped)
sudo ./prepare-rpi.sh \
  --hostname rpi1 \
  --ip 192.168.1.101/24 \
  --storage /dev/sda

# Reboot
sudo reboot
```

### Step 7: Rejoin the Cluster

After the node is bootstrapped:

```bash
# Get the join token from control plane
ssh ubuntu@192.168.1.100 "sudo cat /var/lib/rancher/k3s/server/node-token"

# On the reimaged node, install k3s agent
curl -sfL https://get.k3s.io | \
  K3S_URL="https://192.168.1.100:6443" \
  K3S_TOKEN="<token-from-above>" \
  sh -s - agent
```

Or use Ansible to rejoin:

```bash
ansible-playbook -i ansible/inventory/cluster.yml ansible/playbooks/k3s-install.yml \
  --limit rpi1
```

### Step 8: Verify Node Rejoined

```bash
kubectl get nodes
# rpi1 should appear with Ready status
```

---

## Troubleshooting

### Node Won't Boot

**Symptoms**: No green LED activity, no network

**Solutions**:
1. Try a different power supply (must be 27W USB-C)
2. Reimage the SD card
3. Try a different SD card
4. Check for physical damage

### Can't SSH to Node

**Symptoms**: Connection refused or timeout

**Solutions**:
```bash
# Check if node is on the network
ping 192.168.1.101

# If ping works but SSH doesn't, SSH may not be enabled
# Re-image and ensure SSH is enabled in Imager settings

# Check if firewall is blocking (from another Pi or via HDMI)
sudo ufw status
sudo ufw allow 22/tcp
```

### cgroups Not Enabled After Reboot

**Symptoms**: `cat /proc/cgroups` shows 0 for memory

**Solutions**:
```bash
# Check cmdline.txt
cat /boot/firmware/cmdline.txt  # or /boot/cmdline.txt

# Should contain: cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset
# If missing, add manually:
sudo nano /boot/firmware/cmdline.txt
# Add to the END of the single line (don't create new line):
# cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset

sudo reboot
```

### Swap Keeps Coming Back

**Symptoms**: `free -h` shows swap after reboot

**Solutions**:
```bash
# Disable the swap service
sudo systemctl disable dphys-swapfile
sudo systemctl stop dphys-swapfile

# Remove swap file
sudo rm -f /var/swap

# Set swap size to 0
sudo nano /etc/dphys-swapfile
# Change CONF_SWAPSIZE to 0

sudo reboot
```

### USB SSD Not Detected

**Symptoms**: `lsblk` doesn't show /dev/sda

**Solutions**:
1. Try a different USB 3.0 port (the blue ones)
2. Try a different USB cable
3. Check if SSD needs more power:
   ```bash
   # Check kernel messages
   dmesg | grep -i usb
   ```
4. Try a powered USB hub
5. Test SSD on another computer

### Node Overheating / Throttling

**Symptoms**: Poor performance, high temperature

**Solutions**:
```bash
# Check temperature
vcgencmd measure_temp

# Check throttling status
vcgencmd get_throttled
# 0x0 = OK
# 0x50000 = Previously throttled
# 0x50005 = Currently throttled

# If throttling:
# 1. Improve cooling (better heatsink/fan)
# 2. Improve airflow in case
# 3. Reduce workload
```

### k3s Agent Won't Start

**Symptoms**: Node shows NotReady in kubectl

**Solutions**:
```bash
# Check agent status
sudo systemctl status k3s-agent

# Check logs
sudo journalctl -u k3s-agent -f

# Common fixes:
# 1. Verify token is correct
# 2. Verify control plane IP is reachable
ping 192.168.1.100

# 3. Check firewall allows 6443
sudo ufw allow 6443/tcp

# 4. Restart agent
sudo systemctl restart k3s-agent
```

---

## Quick Reference

### Common Commands

```bash
# System info
hostnamectl
uname -a
free -h
df -h
lsblk

# Temperature
vcgencmd measure_temp

# Throttling status
vcgencmd get_throttled

# Network
ip addr
ip route
cat /etc/resolv.conf

# Services
sudo systemctl status k3s-agent
sudo journalctl -u k3s-agent -n 50

# Firewall
sudo ufw status verbose

# Reboot/Shutdown
sudo reboot
sudo shutdown -h now
```

### Important File Locations

| File | Purpose |
|------|---------|
| `/boot/firmware/cmdline.txt` | Kernel command line (cgroups) |
| `/boot/firmware/config.txt` | Hardware configuration |
| `/etc/dhcpcd.conf` | Network configuration |
| `/etc/rancher/k3s/` | k3s configuration |
| `/var/lib/rancher/k3s/` | k3s data directory |
| `/mnt/storage/` | External SSD mount point |

### Support Resources

- [Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/)
- [k3s Documentation](https://docs.k3s.io/)
- [Project Issues](https://github.com/your-repo/rpi_kubernetes/issues)
