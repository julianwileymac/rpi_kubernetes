#!/bin/bash
# =============================================================================
# Ubuntu Desktop Bootstrap Script (Control Plane)
# =============================================================================
# Prepares an Ubuntu desktop for use as k3s control plane with GPU support.
#
# Usage:
#   sudo ./prepare-ubuntu.sh [--hostname NAME] [--ip ADDRESS] [--gpu]
#
# Prerequisites:
#   - Ubuntu 22.04+ Desktop
#   - SSH enabled
#   - Internet connectivity
#   - (Optional) NVIDIA GPU for ML workloads
#
# What this script does:
#   1. Updates system packages
#   2. Sets hostname and static IP (optional)
#   3. Disables swap
#   4. Installs required packages
#   5. Configures kernel parameters for k8s
#   6. Sets up NVIDIA GPU drivers and container toolkit (optional)
#   7. Configures firewall rules
#   8. Sets up storage directories
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
HOSTNAME="${HOSTNAME:-}"
STATIC_IP="${STATIC_IP:-}"
INTERFACE="${INTERFACE:-}"
GATEWAY="${GATEWAY:-192.168.1.1}"
DNS_SERVERS="${DNS_SERVERS:-8.8.8.8,1.1.1.1}"
STORAGE_MOUNT="${STORAGE_MOUNT:-/mnt/storage}"
TIMEZONE="${TIMEZONE:-America/New_York}"
INSTALL_GPU="${INSTALL_GPU:-false}"
METALLB_POOL="${METALLB_POOL:-192.168.1.200-192.168.1.250}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        log_warning "This doesn't appear to be Ubuntu"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --hostname)
                HOSTNAME="$2"
                shift 2
                ;;
            --ip)
                STATIC_IP="$2"
                shift 2
                ;;
            --interface)
                INTERFACE="$2"
                shift 2
                ;;
            --gateway)
                GATEWAY="$2"
                shift 2
                ;;
            --dns)
                DNS_SERVERS="$2"
                shift 2
                ;;
            --storage-mount)
                STORAGE_MOUNT="$2"
                shift 2
                ;;
            --timezone)
                TIMEZONE="$2"
                shift 2
                ;;
            --gpu)
                INSTALL_GPU=true
                shift
                ;;
            --metallb-pool)
                METALLB_POOL="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --hostname NAME       Set system hostname"
                echo "  --ip ADDRESS          Set static IP (e.g., 192.168.1.100/24)"
                echo "  --interface NAME      Network interface (auto-detect if empty)"
                echo "  --gateway ADDRESS     Set gateway (default: 192.168.1.1)"
                echo "  --dns SERVERS         Set DNS servers (comma-separated)"
                echo "  --storage-mount PATH  Storage mount point (default: /mnt/storage)"
                echo "  --timezone TZ         Set timezone (default: America/New_York)"
                echo "  --gpu                 Install NVIDIA GPU drivers"
                echo "  --metallb-pool RANGE  MetalLB IP pool (default: 192.168.1.200-192.168.1.250)"
                echo "  --help, -h            Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

update_system() {
    log_info "Updating system packages..."
    apt-get update
    apt-get upgrade -y
    apt-get dist-upgrade -y
    apt-get autoremove -y
    log_success "System updated"
}

set_hostname() {
    if [[ -n "$HOSTNAME" ]]; then
        log_info "Setting hostname to: $HOSTNAME"
        hostnamectl set-hostname "$HOSTNAME"
        
        # Update /etc/hosts
        if ! grep -q "$HOSTNAME" /etc/hosts; then
            echo "127.0.1.1 $HOSTNAME" >> /etc/hosts
        fi
        
        log_success "Hostname set to $HOSTNAME"
    fi
}

set_timezone() {
    log_info "Setting timezone to: $TIMEZONE"
    timedatectl set-timezone "$TIMEZONE"
    log_success "Timezone set"
}

configure_static_ip() {
    if [[ -n "$STATIC_IP" ]]; then
        log_info "Configuring static IP: $STATIC_IP"
        
        # Auto-detect interface if not specified
        if [[ -z "$INTERFACE" ]]; then
            INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
        fi
        
        # Extract IP without CIDR
        IP_ADDR=$(echo "$STATIC_IP" | cut -d'/' -f1)
        CIDR=$(echo "$STATIC_IP" | cut -d'/' -f2)
        [[ -z "$CIDR" ]] && CIDR="24"
        
        # Create netplan configuration
        cat > /etc/netplan/99-static-ip.yaml << EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    $INTERFACE:
      addresses:
        - $IP_ADDR/$CIDR
      routes:
        - to: default
          via: $GATEWAY
      nameservers:
        addresses: [$(echo $DNS_SERVERS | tr ',' ', ')]
EOF
        
        chmod 600 /etc/netplan/99-static-ip.yaml
        netplan apply || log_warning "Netplan apply failed - may need reboot"
        
        log_success "Static IP configured on $INTERFACE"
    fi
}

disable_swap() {
    log_info "Disabling swap..."
    
    # Turn off swap immediately
    swapoff -a
    
    # Remove swap from fstab
    sed -i '/swap/d' /etc/fstab
    
    # Disable swap file if it exists
    if [[ -f /swapfile ]]; then
        rm -f /swapfile
    fi
    
    log_success "Swap disabled"
}

install_packages() {
    log_info "Installing required packages..."
    
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        nfs-common \
        nfs-kernel-server \
        open-iscsi \
        jq \
        htop \
        iotop \
        net-tools \
        iptables \
        python3 \
        python3-pip \
        python3-venv \
        git \
        make \
        gcc \
        build-essential
    
    log_success "Packages installed"
}

install_kubectl() {
    log_info "Installing kubectl..."
    
    # Add Kubernetes apt repository
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | \
        gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | \
        tee /etc/apt/sources.list.d/kubernetes.list
    
    apt-get update
    apt-get install -y kubectl
    
    log_success "kubectl installed"
}

install_helm() {
    log_info "Installing Helm..."
    
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    
    log_success "Helm installed"
}

configure_sysctl() {
    log_info "Configuring kernel parameters..."
    
    cat > /etc/sysctl.d/99-kubernetes.conf << EOF
# Kubernetes required settings
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# Performance tuning
vm.swappiness = 0
fs.inotify.max_user_instances = 8192
fs.inotify.max_user_watches = 524288

# Network tuning
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 10
EOF

    # Load required modules
    modprobe br_netfilter
    modprobe overlay
    
    cat > /etc/modules-load.d/kubernetes.conf << EOF
br_netfilter
overlay
EOF

    # Apply settings
    sysctl --system
    
    log_success "Kernel parameters configured"
}

install_nvidia_gpu() {
    if [[ "$INSTALL_GPU" == "true" ]]; then
        log_info "Installing NVIDIA GPU drivers and container toolkit..."
        
        # Check for NVIDIA GPU
        if ! lspci | grep -i nvidia > /dev/null; then
            log_warning "No NVIDIA GPU detected, skipping driver installation"
            return
        fi
        
        # Install NVIDIA drivers
        apt-get install -y nvidia-driver-535 nvidia-utils-535
        
        # Add NVIDIA container toolkit repository
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        
        apt-get update
        apt-get install -y nvidia-container-toolkit
        
        # Configure containerd for NVIDIA (will be used by k3s)
        mkdir -p /etc/rancher/k3s
        cat > /etc/rancher/k3s/config.yaml << EOF
# k3s configuration with NVIDIA GPU support
node-label:
  - "hardware/gpu=true"
  - "nvidia.com/gpu=true"
EOF
        
        log_success "NVIDIA GPU support installed"
        log_warning "A reboot is required to load NVIDIA drivers"
    fi
}

setup_storage_directories() {
    log_info "Setting up storage directories..."
    
    mkdir -p "$STORAGE_MOUNT"/{data,mlruns,postgresql,minio,jupyterhub,backups}
    chmod 755 "$STORAGE_MOUNT"
    
    log_success "Storage directories created at $STORAGE_MOUNT"
}

configure_firewall() {
    log_info "Configuring firewall rules..."
    
    # Install ufw if not present
    apt-get install -y ufw
    
    # Reset to defaults
    ufw --force reset
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH
    ufw allow 22/tcp
    
    # Kubernetes API server
    ufw allow 6443/tcp
    
    # etcd
    ufw allow 2379:2380/tcp
    
    # Kubelet API
    ufw allow 10250/tcp
    
    # kube-scheduler
    ufw allow 10259/tcp
    
    # kube-controller-manager
    ufw allow 10257/tcp
    
    # Flannel VXLAN
    ufw allow 8472/udp
    
    # Flannel Wireguard
    ufw allow 51820/udp
    ufw allow 51821/udp
    
    # NodePort range
    ufw allow 30000:32767/tcp
    
    # Node exporter (Prometheus)
    ufw allow 9100/tcp
    
    # MetalLB
    ufw allow 7946/tcp
    ufw allow 7946/udp
    
    # Allow pod and service CIDRs
    ufw allow from 10.42.0.0/16
    ufw allow from 10.43.0.0/16
    
    # Allow local network
    ufw allow from 192.168.1.0/24
    
    # Enable firewall
    ufw --force enable
    
    log_success "Firewall configured"
}

enable_services() {
    log_info "Enabling required services..."
    
    # Enable and start iscsid
    systemctl enable iscsid
    systemctl start iscsid
    
    # Enable NFS server (for sharing storage with workers)
    systemctl enable nfs-kernel-server
    systemctl start nfs-kernel-server
    
    log_success "Services enabled"
}

create_k3s_config() {
    log_info "Creating k3s server configuration..."
    
    mkdir -p /etc/rancher/k3s
    
    # Get current IP if not set
    if [[ -z "$STATIC_IP" ]]; then
        CURRENT_IP=$(hostname -I | awk '{print $1}')
    else
        CURRENT_IP=$(echo "$STATIC_IP" | cut -d'/' -f1)
    fi
    
    cat > /etc/rancher/k3s/config.yaml << EOF
# k3s Server Configuration
# Generated by prepare-ubuntu.sh

# Disable components we'll replace
disable:
  - traefik
  - local-storage

# Networking
flannel-backend: vxlan
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16

# TLS SANs for API server
tls-san:
  - $CURRENT_IP
  - ${HOSTNAME:-k8s-control}
  - ${HOSTNAME:-k8s-control}.local
  - localhost
  - 127.0.0.1

# Write kubeconfig with readable permissions
write-kubeconfig-mode: "0644"

# Node labels
node-label:
  - "node.kubernetes.io/role=control-plane"
  - "hardware/type=desktop"
EOF

    log_success "k3s configuration created at /etc/rancher/k3s/config.yaml"
}

save_cluster_info() {
    log_info "Saving cluster information..."
    
    mkdir -p /etc/rpi-k8s-cluster
    
    cat > /etc/rpi-k8s-cluster/cluster-info.yaml << EOF
# Cluster Information
# Generated by prepare-ubuntu.sh

cluster:
  name: rpi-k8s-cluster
  domain: local
  
control_plane:
  hostname: ${HOSTNAME:-k8s-control}
  ip: ${STATIC_IP:-$(hostname -I | awk '{print $1}')}
  
network:
  pod_cidr: 10.42.0.0/16
  service_cidr: 10.43.0.0/16
  metallb_pool: $METALLB_POOL
  
storage:
  mount_point: $STORAGE_MOUNT
  
gpu:
  enabled: $INSTALL_GPU
EOF

    log_success "Cluster info saved to /etc/rpi-k8s-cluster/cluster-info.yaml"
}

print_summary() {
    echo ""
    echo "============================================================================="
    echo -e "${GREEN}Bootstrap Complete!${NC}"
    echo "============================================================================="
    echo ""
    echo "The following changes were made:"
    echo "  - System packages updated"
    [[ -n "$HOSTNAME" ]] && echo "  - Hostname set to: $HOSTNAME"
    [[ -n "$STATIC_IP" ]] && echo "  - Static IP configured: $STATIC_IP"
    echo "  - Swap disabled"
    echo "  - Required packages installed (kubectl, helm)"
    echo "  - Kernel parameters configured"
    [[ "$INSTALL_GPU" == "true" ]] && echo "  - NVIDIA GPU drivers installed"
    echo "  - Storage directories created at: $STORAGE_MOUNT"
    echo "  - Firewall configured"
    echo "  - k3s configuration prepared"
    echo ""
    echo -e "${YELLOW}IMPORTANT: A reboot is required to apply all changes.${NC}"
    echo ""
    echo "Run: sudo reboot"
    echo ""
    echo "After reboot, install k3s with:"
    echo "  curl -sfL https://get.k3s.io | sh -"
    echo ""
    echo "Then get the node token for workers:"
    echo "  sudo cat /var/lib/rancher/k3s/server/node-token"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================================================="
    echo "Ubuntu Desktop Bootstrap Script for Kubernetes Control Plane"
    echo "============================================================================="
    echo ""
    
    check_root
    check_ubuntu
    parse_args "$@"
    
    update_system
    set_hostname
    set_timezone
    configure_static_ip
    disable_swap
    install_packages
    install_kubectl
    install_helm
    configure_sysctl
    install_nvidia_gpu
    setup_storage_directories
    configure_firewall
    enable_services
    create_k3s_config
    save_cluster_info
    
    print_summary
}

main "$@"
