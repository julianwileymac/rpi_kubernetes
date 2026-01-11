#!/bin/bash
# =============================================================================
# Raspberry Pi 5 Bootstrap Script
# =============================================================================
# Prepares a Raspberry Pi 5 running Raspberry Pi OS for k3s Kubernetes.
#
# Usage:
#   sudo ./prepare-rpi.sh [--hostname NAME] [--ip ADDRESS] [--storage DEVICE]
#
# Prerequisites:
#   - Raspberry Pi OS 64-bit (Bookworm or later)
#   - SSH enabled
#   - Internet connectivity
#
# What this script does:
#   1. Updates system packages
#   2. Sets hostname and static IP (optional)
#   3. Disables swap (required for Kubernetes)
#   4. Enables cgroups (memory and cpuset)
#   5. Configures kernel for 64-bit operation
#   6. Sets up external storage (optional)
#   7. Installs required packages
#   8. Configures system parameters for k8s
#   9. Sets up firewall rules
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration (can be overridden via command line)
# =============================================================================
HOSTNAME="${HOSTNAME:-}"
STATIC_IP="${STATIC_IP:-}"
GATEWAY="${GATEWAY:-192.168.1.1}"
DNS_SERVERS="${DNS_SERVERS:-8.8.8.8,1.1.1.1}"
STORAGE_DEVICE="${STORAGE_DEVICE:-}"
STORAGE_MOUNT="${STORAGE_MOUNT:-/mnt/storage}"
TIMEZONE="${TIMEZONE:-America/New_York}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

check_rpi() {
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        log_warning "This doesn't appear to be a Raspberry Pi"
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
            --gateway)
                GATEWAY="$2"
                shift 2
                ;;
            --dns)
                DNS_SERVERS="$2"
                shift 2
                ;;
            --storage)
                STORAGE_DEVICE="$2"
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
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --hostname NAME       Set system hostname"
                echo "  --ip ADDRESS          Set static IP (e.g., 192.168.1.101/24)"
                echo "  --gateway ADDRESS     Set gateway (default: 192.168.1.1)"
                echo "  --dns SERVERS         Set DNS servers (comma-separated)"
                echo "  --storage DEVICE      External storage device (e.g., /dev/sda)"
                echo "  --storage-mount PATH  Storage mount point (default: /mnt/storage)"
                echo "  --timezone TZ         Set timezone (default: America/New_York)"
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
    log_success "System updated"
}

set_hostname() {
    if [[ -n "$HOSTNAME" ]]; then
        log_info "Setting hostname to: $HOSTNAME"
        hostnamectl set-hostname "$HOSTNAME"
        
        # Update /etc/hosts
        sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/g" /etc/hosts
        
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
        
        # Get interface name
        INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
        
        # Create dhcpcd configuration
        cat >> /etc/dhcpcd.conf << EOF

# Static IP configuration for k3s cluster
interface $INTERFACE
static ip_address=$STATIC_IP
static routers=$GATEWAY
static domain_name_servers=$DNS_SERVERS
EOF
        
        log_success "Static IP configured on $INTERFACE"
    fi
}

disable_swap() {
    log_info "Disabling swap..."
    
    # Turn off swap immediately
    swapoff -a || true
    
    # Disable dphys-swapfile service
    if systemctl is-active --quiet dphys-swapfile; then
        systemctl stop dphys-swapfile
        systemctl disable dphys-swapfile
    fi
    
    # Set swap size to 0
    if [[ -f /etc/dphys-swapfile ]]; then
        sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=0/g' /etc/dphys-swapfile
    fi
    
    # Remove swap from fstab
    sed -i '/swap/d' /etc/fstab || true
    
    log_success "Swap disabled"
}

enable_cgroups() {
    log_info "Enabling cgroups (memory and cpuset)..."
    
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
    # Fallback for older RPi OS
    [[ ! -f "$CMDLINE_FILE" ]] && CMDLINE_FILE="/boot/cmdline.txt"
    
    if [[ -f "$CMDLINE_FILE" ]]; then
        CURRENT=$(cat "$CMDLINE_FILE")
        
        # Add cgroup parameters if not present
        if ! echo "$CURRENT" | grep -q "cgroup_memory=1"; then
            echo "$CURRENT cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset" > "$CMDLINE_FILE"
            log_success "cgroups enabled in $CMDLINE_FILE"
        else
            log_info "cgroups already enabled"
        fi
    else
        log_warning "Could not find cmdline.txt"
    fi
}

configure_kernel_64bit() {
    log_info "Ensuring 64-bit kernel mode..."
    
    CONFIG_FILE="/boot/firmware/config.txt"
    # Fallback for older RPi OS
    [[ ! -f "$CONFIG_FILE" ]] && CONFIG_FILE="/boot/config.txt"
    
    if [[ -f "$CONFIG_FILE" ]]; then
        # Add arm_64bit if not present
        if ! grep -q "arm_64bit=1" "$CONFIG_FILE"; then
            echo "arm_64bit=1" >> "$CONFIG_FILE"
            log_success "64-bit kernel enabled"
        else
            log_info "64-bit kernel already enabled"
        fi
        
        # Minimize GPU memory for headless operation
        if ! grep -q "gpu_mem=16" "$CONFIG_FILE"; then
            echo "gpu_mem=16" >> "$CONFIG_FILE"
            log_success "GPU memory minimized for headless operation"
        fi
        
        # Disable WiFi and Bluetooth (power saving)
        if ! grep -q "dtoverlay=disable-wifi" "$CONFIG_FILE"; then
            echo "dtoverlay=disable-wifi" >> "$CONFIG_FILE"
            log_success "WiFi disabled"
        fi
        
        if ! grep -q "dtoverlay=disable-bt" "$CONFIG_FILE"; then
            echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
            log_success "Bluetooth disabled"
        fi
    else
        log_warning "Could not find config.txt"
    fi
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
        open-iscsi \
        jq \
        htop \
        iotop \
        net-tools \
        iptables \
        libraspberrypi-bin \
        python3 \
        python3-pip
    
    log_success "Packages installed"
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
net.core.somaxconn = 32768
net.ipv4.tcp_max_syn_backlog = 32768
net.core.netdev_max_backlog = 32768
EOF

    # Load br_netfilter module
    modprobe br_netfilter || true
    echo "br_netfilter" > /etc/modules-load.d/br_netfilter.conf
    
    # Apply sysctl settings
    sysctl --system
    
    log_success "Kernel parameters configured"
}

setup_external_storage() {
    if [[ -n "$STORAGE_DEVICE" ]]; then
        log_info "Setting up external storage: $STORAGE_DEVICE"
        
        # Check if device exists
        if [[ ! -b "$STORAGE_DEVICE" ]]; then
            log_error "Storage device $STORAGE_DEVICE not found"
            return 1
        fi
        
        # Create partition if needed (first partition)
        PARTITION="${STORAGE_DEVICE}1"
        if [[ ! -b "$PARTITION" ]]; then
            log_info "Creating partition on $STORAGE_DEVICE..."
            parted -s "$STORAGE_DEVICE" mklabel gpt
            parted -s "$STORAGE_DEVICE" mkpart primary ext4 0% 100%
            sleep 2
        fi
        
        # Format if needed
        if ! blkid "$PARTITION" | grep -q "ext4"; then
            log_info "Formatting $PARTITION as ext4..."
            mkfs.ext4 -F "$PARTITION"
        fi
        
        # Create mount point
        mkdir -p "$STORAGE_MOUNT"
        
        # Add to fstab if not present
        UUID=$(blkid -s UUID -o value "$PARTITION")
        if ! grep -q "$UUID" /etc/fstab; then
            echo "UUID=$UUID $STORAGE_MOUNT ext4 defaults,noatime,nodiratime 0 2" >> /etc/fstab
        fi
        
        # Mount
        mount -a
        
        # Create subdirectories
        mkdir -p "$STORAGE_MOUNT"/{containers,volumes,logs}
        chmod 755 "$STORAGE_MOUNT"
        
        log_success "External storage mounted at $STORAGE_MOUNT"
    fi
}

configure_firewall() {
    log_info "Configuring firewall rules..."
    
    # Install ufw if not present
    apt-get install -y ufw
    
    # Allow SSH
    ufw allow 22/tcp
    
    # Kubernetes API server
    ufw allow 6443/tcp
    
    # Kubelet API
    ufw allow 10250/tcp
    
    # Flannel VXLAN
    ufw allow 8472/udp
    
    # Flannel Wireguard
    ufw allow 51820/udp
    ufw allow 51821/udp
    
    # Node exporter (Prometheus)
    ufw allow 9100/tcp
    
    # Allow pod and service CIDRs
    ufw allow from 10.42.0.0/16
    ufw allow from 10.43.0.0/16
    
    # Enable firewall
    ufw --force enable
    
    log_success "Firewall configured"
}

enable_services() {
    log_info "Enabling required services..."
    
    # Enable and start iscsid for storage
    systemctl enable iscsid
    systemctl start iscsid
    
    log_success "Services enabled"
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
    echo "  - cgroups enabled (memory, cpuset)"
    echo "  - 64-bit kernel mode enabled"
    echo "  - Required packages installed"
    echo "  - Kernel parameters configured"
    [[ -n "$STORAGE_DEVICE" ]] && echo "  - External storage mounted at: $STORAGE_MOUNT"
    echo "  - Firewall configured"
    echo ""
    echo -e "${YELLOW}IMPORTANT: A reboot is required to apply all changes.${NC}"
    echo ""
    echo "Run: sudo reboot"
    echo ""
    echo "After reboot, verify with:"
    echo "  cat /proc/cgroups | grep -E 'memory|cpuset'"
    echo "  free -h (should show no swap)"
    echo "  uname -m (should show aarch64)"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================================================="
    echo "Raspberry Pi 5 Bootstrap Script for Kubernetes"
    echo "============================================================================="
    echo ""
    
    check_root
    check_rpi
    parse_args "$@"
    
    update_system
    set_hostname
    set_timezone
    configure_static_ip
    disable_swap
    enable_cgroups
    configure_kernel_64bit
    install_packages
    configure_sysctl
    setup_external_storage
    configure_firewall
    enable_services
    
    print_summary
}

main "$@"
