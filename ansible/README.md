# Ansible Playbooks

Automated cluster provisioning and management using Ansible.

## Overview

These playbooks automate:
1. **Bootstrap**: Prepare nodes for Kubernetes (swap, cgroups, packages)
2. **k3s Install**: Install k3s server and agents
3. **Storage Setup**: Configure external USB SSDs
4. **Base Services**: Deploy core services via Helm

## Prerequisites

### On Your Workstation

```bash
# Install Ansible
pip install ansible ansible-lint

# Install required collections
ansible-galaxy collection install kubernetes.core
ansible-galaxy collection install community.general
ansible-galaxy collection install ansible.posix
```

### SSH Key Setup

```bash
# Generate SSH key if needed
ssh-keygen -t ed25519 -C "ansible@rpi-cluster"

# Copy to all nodes
ssh-copy-id pi@192.168.1.101
ssh-copy-id pi@192.168.1.102
ssh-copy-id pi@192.168.1.103
ssh-copy-id pi@192.168.1.104
ssh-copy-id ubuntu@192.168.1.100
```

## Quick Start

### 1. Configure Inventory

```bash
# Copy example inventory
cp inventory/cluster.example.yml inventory/cluster.yml

# Edit with your node details
vim inventory/cluster.yml
```

Update the following:
- Node IP addresses
- SSH usernames
- k3s version
- MetalLB IP pool range

### 2. Test Connectivity

```bash
# Ping all nodes
ansible all -m ping

# Check node facts
ansible all -m setup -a "filter=ansible_distribution*"
```

### 3. Run Playbooks

```bash
# Step 1: Bootstrap all nodes
ansible-playbook playbooks/bootstrap.yml

# Step 2: Reboot nodes to apply kernel changes
ansible all -m reboot

# Step 3: Setup external storage (if applicable)
ansible-playbook playbooks/storage-setup.yml

# Step 4: Install k3s cluster
ansible-playbook playbooks/k3s-install.yml
```

## Playbooks

### bootstrap.yml

Prepares nodes for Kubernetes:

| Task | Description |
|------|-------------|
| Update packages | Full system upgrade |
| Install dependencies | nfs-common, open-iscsi, jq, etc. |
| Disable swap | Required by Kubernetes |
| Enable cgroups | Memory and cpuset (RPi) |
| Configure sysctl | Network and kernel parameters |
| Setup firewall | UFW with required ports |

**Tags:**
- `common` - All nodes
- `control` - Control plane only
- `workers` - Worker nodes only
- `network` - Firewall configuration

```bash
# Run specific tags
ansible-playbook playbooks/bootstrap.yml --tags "common,workers"
```

### k3s-install.yml

Installs k3s cluster:

| Task | Description |
|------|-------------|
| Install k3s server | Control plane with API server |
| Install k3s agents | Worker nodes join cluster |
| Install MetalLB | Bare-metal load balancer |
| Install ingress-nginx | Ingress controller |
| Install cert-manager | TLS certificate management |

**Tags:**
- `server` - k3s server installation
- `agent` - k3s agent installation
- `helm` - Helm chart installations
- `verify` - Cluster health check

### storage-setup.yml

Configures external storage:

| Task | Description |
|------|-------------|
| Partition device | GPT partition table |
| Format filesystem | ext4 |
| Mount storage | fstab entry |
| Create directories | containers, volumes, logs |
| Install local-path | Storage provisioner |

## Inventory Structure

```yaml
all:
  vars:
    # Global variables
    k3s_version: "v1.29.0+k3s1"
    cluster_name: rpi-k8s-cluster
    
  children:
    control_plane:
      hosts:
        k8s-control:
          ansible_host: 192.168.1.100
          ansible_user: ubuntu
          node_ip: 192.168.1.100
          
    workers:
      hosts:
        rpi5-node-1:
          ansible_host: 192.168.1.101
          node_ip: 192.168.1.101
        # ... more nodes
```

## Variables Reference

### Global Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `k3s_version` | k3s version to install | `v1.29.0+k3s1` |
| `cluster_name` | Cluster identifier | `rpi-k8s-cluster` |
| `cluster_domain` | DNS domain | `local` |
| `pod_cidr` | Pod network CIDR | `10.42.0.0/16` |
| `service_cidr` | Service network CIDR | `10.43.0.0/16` |

### Host Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ansible_host` | SSH address | `192.168.1.101` |
| `ansible_user` | SSH user | `pi` |
| `node_ip` | Node's cluster IP | `192.168.1.101` |
| `node_arch` | CPU architecture | `arm64` |
| `external_storage_device` | USB SSD device | `/dev/sda` |
| `gpu_enabled` | Enable GPU support | `true` |
| `metallb_pool` | LoadBalancer IP range | `192.168.1.200-192.168.1.250` |

## Common Operations

### Check Cluster Status

```bash
# From control plane
ansible control_plane -a "kubectl get nodes -o wide"

# Check all pods
ansible control_plane -a "kubectl get pods -A"
```

### Restart k3s

```bash
# Restart server
ansible control_plane -m systemd -a "name=k3s state=restarted"

# Restart agents
ansible workers -m systemd -a "name=k3s-agent state=restarted"
```

### Drain and Cordon Nodes

```bash
# Drain a node for maintenance
ansible control_plane -a "kubectl drain rpi5-node-1 --ignore-daemonsets --delete-emptydir-data"

# Uncordon after maintenance
ansible control_plane -a "kubectl uncordon rpi5-node-1"
```

### Update k3s

```bash
# Update k3s version in inventory
vim inventory/cluster.yml

# Re-run install playbook
ansible-playbook playbooks/k3s-install.yml --tags "server,agent"
```

## Troubleshooting

### Connection Issues

```bash
# Test SSH
ssh -v pi@192.168.1.101

# Check ansible connectivity
ansible all -m ping -vvv
```

### Bootstrap Failures

```bash
# Check specific node
ansible rpi5-node-1 -m setup

# Run with verbose output
ansible-playbook playbooks/bootstrap.yml -vvv --limit rpi5-node-1
```

### k3s Installation Issues

```bash
# Check k3s server logs
ansible control_plane -a "journalctl -u k3s -n 50"

# Check k3s agent logs
ansible workers -a "journalctl -u k3s-agent -n 50"
```

### Storage Issues

```bash
# Check disk devices
ansible workers -a "lsblk"

# Check mounts
ansible workers -a "df -h /mnt/storage"
```

## Security Considerations

1. **SSH Keys**: Use key-based authentication only
2. **Secrets**: Never commit `cluster.yml` with real IPs to git
3. **Firewall**: UFW is enabled with minimal required ports
4. **k3s Token**: The node token is sensitive - rotate if compromised

## Directory Structure

```
ansible/
├── ansible.cfg           # Ansible configuration
├── inventory/
│   ├── cluster.example.yml  # Example inventory (commit this)
│   └── cluster.yml          # Your inventory (gitignored)
├── playbooks/
│   ├── bootstrap.yml        # Node preparation
│   ├── k3s-install.yml      # k3s installation
│   └── storage-setup.yml    # External storage
├── templates/
│   └── k3s-server-config.yaml.j2
├── roles/                   # (future: modular roles)
└── README.md
```
