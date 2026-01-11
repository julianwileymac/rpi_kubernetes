# Bootstrap Scripts

This directory contains scripts and configuration files for preparing cluster nodes.

## Overview

Before installing k3s, each node needs to be configured with:
- Disabled swap (Kubernetes requirement)
- Enabled cgroups (memory and cpuset)
- Required packages
- Network configuration
- Firewall rules
- External storage (optional but recommended)

## Directory Structure

```
bootstrap/
├── configs/
│   ├── node-common.yaml      # Shared configuration values
│   ├── control-plane.yaml    # Ubuntu desktop control plane config
│   └── worker-rpi5.yaml      # Raspberry Pi 5 worker template
├── scripts/
│   ├── prepare-rpi.sh        # Bootstrap script for RPi5 nodes
│   └── prepare-ubuntu.sh     # Bootstrap script for Ubuntu control plane
└── README.md
```

## Quick Start

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
scp scripts/prepare-rpi.sh pi@192.168.1.101:~/

ssh pi@192.168.1.101

sudo ./prepare-rpi.sh \
    --hostname rpi5-node-1 \
    --ip 192.168.1.101/24 \
    --storage /dev/sda  # External USB SSD

sudo reboot
```

Repeat for nodes 2-4, changing hostname and IP:
- Node 2: `--hostname rpi5-node-2 --ip 192.168.1.102/24`
- Node 3: `--hostname rpi5-node-3 --ip 192.168.1.103/24`
- Node 4: `--hostname rpi5-node-4 --ip 192.168.1.104/24`

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
| `node.hostname` | Worker hostname | `rpi5-node-1` |
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

### Raspberry Pi Script (prepare-rpi.sh)

1. **System Update**: Updates all packages to latest versions
2. **Hostname**: Sets the system hostname
3. **Static IP**: Configures static IP via dhcpcd
4. **Swap**: Disables swap completely (required by Kubernetes)
5. **cgroups**: Enables memory and cpuset cgroups in cmdline.txt
6. **64-bit Kernel**: Ensures 64-bit mode is enabled
7. **Packages**: Installs nfs-common, open-iscsi, jq, etc.
8. **Kernel Params**: Configures sysctl for Kubernetes networking
9. **External Storage**: Partitions, formats, and mounts USB SSD
10. **Firewall**: Configures UFW with required ports
11. **Power Saving**: Disables WiFi and Bluetooth

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

## Troubleshooting

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
