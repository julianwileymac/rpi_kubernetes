#!/bin/bash
# =============================================================================
# Raspberry Pi 5 Bootstrap Script for Kubernetes
# =============================================================================
# Version: 1.0.0
#
# Prepares a Raspberry Pi 5 running Raspberry Pi OS for k3s Kubernetes.
# This script can be run standalone or via Ansible automation.
#
# Usage:
#   sudo ./prepare-rpi.sh [OPTIONS]
#   sudo ./prepare-rpi.sh --interactive
#   sudo ./prepare-rpi.sh --hostname rpi1 --ip 192.168.1.101/24 --storage auto
#
# Prerequisites:
#   - Raspberry Pi 5 (4GB or 8GB RAM)
#   - Raspberry Pi OS Lite (64-bit) - Bookworm or later
#   - SSH enabled
#   - Internet connectivity
#   - External USB SSD connected (auto-detected or via --storage)
#
# What this script does:
#   1. Updates system packages to latest versions
#   2. Sets hostname and static IP (optional)
#   3. Disables swap (required for Kubernetes)
#   4. Enables memory and cpuset cgroups (required for k3s)
#   5. Configures kernel for 64-bit operation
#   6. Minimizes GPU memory (headless operation)
#   7. Disables WiFi/Bluetooth (power saving)
#   8. Sets up external storage (optional, recommended)
#   9. Installs required packages (nfs-common, open-iscsi, etc.)
#  10. Configures kernel parameters for k8s networking
#  11. Sets up UFW firewall with k8s ports
#
# For more information, see:
#   https://github.com/your-repo/rpi_kubernetes/docs/raspberry-pi-setup.md
# =============================================================================

VERSION="1.0.0"
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# Configuration (can be overridden via command line)
# =============================================================================
HOSTNAME="${HOSTNAME:-}"
STATIC_IP="${STATIC_IP:-}"
GATEWAY="${GATEWAY:-192.168.1.1}"
DNS_SERVERS="${DNS_SERVERS:-8.8.8.8,1.1.1.1}"
STORAGE_DEVICE="${STORAGE_DEVICE:-}"
STORAGE_HELPER_PATH="/usr/local/sbin/mount-external-storage"
STORAGE_MOUNT="${STORAGE_MOUNT:-/mnt/storage}"
TIMEZONE="${TIMEZONE:-America/New_York}"
DRY_RUN=false
INTERACTIVE=false
SKIP_UPDATE=false
SKIP_REBOOT_PROMPT=false
SKIP_STORAGE=false
STORAGE_CONFIGURED=false

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

show_help() {
    cat << 'EOF'
Raspberry Pi 5 Bootstrap Script for Kubernetes
===============================================

This script prepares your Raspberry Pi 5 for joining a k3s Kubernetes cluster
by configuring system settings, installing packages, and setting up storage.

USAGE:
    sudo ./prepare-rpi.sh [OPTIONS]
    sudo ./prepare-rpi.sh --interactive
    sudo ./prepare-rpi.sh --hostname rpi1 --ip 192.168.1.101/24

OPTIONS:
    --hostname NAME         Set the system hostname
                            Example: --hostname rpi1

    --ip ADDRESS            Set static IP with CIDR notation
                            Example: --ip 192.168.1.101/24

    --gateway ADDRESS       Set default gateway (default: 192.168.1.1)
                            Example: --gateway 192.168.1.1

    --dns SERVERS           Set DNS servers, comma-separated
                            Example: --dns 8.8.8.8,1.1.1.1

    --storage DEVICE        Configure external USB storage device
                            Use "auto" to auto-detect
                            Example: --storage /dev/sda

    --storage-mount PATH    Storage mount point (default: /mnt/storage)
                            Example: --storage-mount /mnt/data

    --no-storage            Skip external storage setup entirely

    --timezone TZ           Set system timezone
                            Example: --timezone America/New_York
                            Run 'timedatectl list-timezones' to see options

    --interactive           Run in interactive mode with prompts

    --dry-run               Show what would be done without making changes

    --skip-update           Skip apt update/upgrade (faster for testing)

    --skip-reboot-prompt    Don't prompt for reboot at the end

    --version, -v           Show version number

    --help, -h              Show this help message

EXAMPLES:
    # Basic setup with just hostname:
    sudo ./prepare-rpi.sh --hostname rpi1

    # Full setup with static IP and storage:
    sudo ./prepare-rpi.sh \
        --hostname rpi1 \
        --ip 192.168.1.101/24 \
        --gateway 192.168.1.1 \
        --storage auto \
        --timezone America/New_York

    # Interactive mode (prompts for each option):
    sudo ./prepare-rpi.sh --interactive

    # Preview changes without applying:
    sudo ./prepare-rpi.sh --hostname rpi1 --dry-run

WHAT THIS SCRIPT DOES:
    1. Updates system packages
    2. Sets hostname and timezone
    3. Configures static IP (if specified)
    4. Disables swap (required for Kubernetes)
    5. Enables memory cgroups (required for k3s)
    6. Enables 64-bit kernel mode
    7. Minimizes GPU memory (headless)
    8. Disables WiFi/Bluetooth (power saving)
    9. Installs required packages
    10. Configures kernel networking parameters
    11. Auto-detects and mounts external storage (if available)
    12. Configures UFW firewall

POST-SCRIPT:
    After running this script, you MUST reboot:
        sudo reboot

    Then verify the setup:
        uname -m                    # Should show: aarch64
        free -h                     # Swap should be 0
        cat /proc/cgroups           # memory should show 1

For detailed documentation, see:
    docs/raspberry-pi-setup.md
EOF
    exit 0
}

run_interactive() {
    echo ""
    echo "=== Interactive Configuration ==="
    echo ""
    
    # Hostname
    read -p "Enter hostname [$(hostname)]: " input
    HOSTNAME="${input:-$(hostname)}"
    
    # Static IP
    CURRENT_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}/\d+' || echo "")
    read -p "Enter static IP with CIDR (leave empty for DHCP) [$CURRENT_IP]: " input
    STATIC_IP="${input:-}"
    
    if [[ -n "$STATIC_IP" ]]; then
        read -p "Enter gateway [192.168.1.1]: " input
        GATEWAY="${input:-192.168.1.1}"
        
        read -p "Enter DNS servers (comma-separated) [8.8.8.8,1.1.1.1]: " input
        DNS_SERVERS="${input:-8.8.8.8,1.1.1.1}"
    fi
    
    # Timezone
    CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "America/New_York")
    read -p "Enter timezone [$CURRENT_TZ]: " input
    TIMEZONE="${input:-$CURRENT_TZ}"
    
    # Storage
    echo ""
    echo "Available block devices:"
    lsblk -d -o NAME,SIZE,TYPE,MODEL | grep disk
    echo ""
    read -p "Enter external storage device (e.g., /dev/sda), 'auto' to detect, leave empty to skip: " input
    if [[ -z "$input" ]]; then
        SKIP_STORAGE=true
        STORAGE_DEVICE=""
    else
        SKIP_STORAGE=false
        STORAGE_DEVICE="$input"
    fi
    
    if [[ "$SKIP_STORAGE" != "true" ]]; then
        read -p "Enter mount point [/mnt/storage]: " input
        STORAGE_MOUNT="${input:-/mnt/storage}"
    fi
    
    echo ""
    echo "=== Configuration Summary ==="
    echo "  Hostname:     ${HOSTNAME:-<current>}"
    echo "  Static IP:    ${STATIC_IP:-<DHCP>}"
    [[ -n "$STATIC_IP" ]] && echo "  Gateway:      $GATEWAY"
    [[ -n "$STATIC_IP" ]] && echo "  DNS:          $DNS_SERVERS"
    echo "  Timezone:     $TIMEZONE"
    if [[ "$SKIP_STORAGE" == "true" ]]; then
        echo "  Storage:      <skipped>"
    else
        echo "  Storage:      ${STORAGE_DEVICE:-auto}"
        echo "  Mount Point:  $STORAGE_MOUNT"
    fi
    echo ""
    
    read -p "Proceed with these settings? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
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
                SKIP_STORAGE=false
                shift 2
                ;;
            --storage-mount)
                STORAGE_MOUNT="$2"
                shift 2
                ;;
            --no-storage)
                SKIP_STORAGE=true
                STORAGE_DEVICE=""
                shift
                ;;
            --timezone)
                TIMEZONE="$2"
                shift 2
                ;;
            --interactive)
                INTERACTIVE=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-update)
                SKIP_UPDATE=true
                shift
                ;;
            --skip-reboot-prompt)
                SKIP_REBOOT_PROMPT=true
                shift
                ;;
            --version|-v)
                echo "prepare-rpi.sh version $VERSION"
                exit 0
                ;;
            --help|-h)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Run '$0 --help' for usage information."
                exit 1
                ;;
        esac
    done
}

update_system() {
    if [[ "$SKIP_UPDATE" == "true" ]]; then
        log_info "Skipping system update (--skip-update)"
        return
    fi
    
    log_info "Updating system packages..."
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run: apt-get update && apt-get upgrade -y"
        return
    fi
    apt-get update
    apt-get upgrade -y
    apt-get dist-upgrade -y
    log_success "System updated"
}

set_hostname() {
    if [[ -z "$HOSTNAME" ]]; then
        return
    fi
    
    log_info "Setting hostname to: $HOSTNAME"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would set hostname to: $HOSTNAME"
        return
    fi
    
    hostnamectl set-hostname "$HOSTNAME"
    
    # Update /etc/hosts
    if grep -q "127.0.1.1" /etc/hosts; then
        sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/g" /etc/hosts
    else
        echo "127.0.1.1	$HOSTNAME" >> /etc/hosts
    fi
    
    log_success "Hostname set to $HOSTNAME"
}

set_timezone() {
    log_info "Setting timezone to: $TIMEZONE"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would set timezone to: $TIMEZONE"
        return
    fi
    
    timedatectl set-timezone "$TIMEZONE"
    log_success "Timezone set"
}

configure_static_ip() {
    if [[ -z "$STATIC_IP" ]]; then
        return
    fi
    
    log_info "Configuring static IP: $STATIC_IP"
    
    # Get interface name
    INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
    INTERFACE="${INTERFACE:-eth0}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would configure static IP $STATIC_IP on $INTERFACE"
        return
    fi
    
    # Check if already configured
    if grep -q "static ip_address=$STATIC_IP" /etc/dhcpcd.conf 2>/dev/null; then
        log_info "Static IP already configured in dhcpcd.conf"
        return
    fi
    
    # Create dhcpcd configuration
    cat >> /etc/dhcpcd.conf << EOF

# Static IP configuration for k3s cluster
interface $INTERFACE
static ip_address=$STATIC_IP
static routers=$GATEWAY
static domain_name_servers=${DNS_SERVERS//,/ }
EOF
    
    log_success "Static IP configured on $INTERFACE"
}

disable_swap() {
    log_info "Disabling swap..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would disable swap and dphys-swapfile service"
        return
    fi
    
    # Turn off swap immediately
    swapoff -a || true
    
    # Disable dphys-swapfile service
    if systemctl list-unit-files | grep -q dphys-swapfile; then
        systemctl stop dphys-swapfile 2>/dev/null || true
        systemctl disable dphys-swapfile 2>/dev/null || true
    fi
    
    # Set swap size to 0
    if [[ -f /etc/dphys-swapfile ]]; then
        sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=0/g' /etc/dphys-swapfile
    fi
    
    # Remove swap entries from fstab
    sed -i '/\sswap\s/d' /etc/fstab || true
    
    # Remove swap file if exists
    rm -f /var/swap 2>/dev/null || true
    
    log_success "Swap disabled"
}

enable_cgroups() {
    log_info "Enabling cgroups (memory and cpuset)..."
    
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
    # Fallback for older RPi OS
    [[ ! -f "$CMDLINE_FILE" ]] && CMDLINE_FILE="/boot/cmdline.txt"
    
    if [[ ! -f "$CMDLINE_FILE" ]]; then
        log_warning "Could not find cmdline.txt - cgroups may not be configured"
        return
    fi
    
    CURRENT=$(cat "$CMDLINE_FILE")
    
    # Check if already configured
    if echo "$CURRENT" | grep -q "cgroup_memory=1"; then
        log_info "cgroups already enabled"
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would add cgroup parameters to $CMDLINE_FILE"
        return
    fi
    
    # Backup original
    cp "$CMDLINE_FILE" "${CMDLINE_FILE}.backup"
    
    # Add cgroup parameters (must be on single line)
    echo "$CURRENT cgroup_memory=1 cgroup_enable=memory cgroup_enable=cpuset" > "$CMDLINE_FILE"
    log_success "cgroups enabled in $CMDLINE_FILE"
}

configure_kernel_64bit() {
    log_info "Configuring kernel and hardware settings..."
    
    CONFIG_FILE="/boot/firmware/config.txt"
    # Fallback for older RPi OS
    [[ ! -f "$CONFIG_FILE" ]] && CONFIG_FILE="/boot/config.txt"
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_warning "Could not find config.txt - kernel config may not be complete"
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would configure 64-bit mode, GPU memory, disable WiFi/BT in $CONFIG_FILE"
        return
    fi
    
    # Backup original
    [[ ! -f "${CONFIG_FILE}.backup" ]] && cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
    
    # Enable 64-bit kernel mode
    if ! grep -q "^arm_64bit=1" "$CONFIG_FILE"; then
        echo "" >> "$CONFIG_FILE"
        echo "# Kubernetes cluster configuration" >> "$CONFIG_FILE"
        echo "arm_64bit=1" >> "$CONFIG_FILE"
        log_success "64-bit kernel enabled"
    else
        log_info "64-bit kernel already enabled"
    fi
    
    # Minimize GPU memory for headless operation
    if ! grep -q "^gpu_mem=" "$CONFIG_FILE"; then
        echo "gpu_mem=16" >> "$CONFIG_FILE"
        log_success "GPU memory minimized (16MB)"
    fi
    
    # Disable WiFi (power saving, using Ethernet)
    if ! grep -q "^dtoverlay=disable-wifi" "$CONFIG_FILE"; then
        echo "dtoverlay=disable-wifi" >> "$CONFIG_FILE"
        log_success "WiFi disabled"
    fi
    
    # Disable Bluetooth (power saving)
    if ! grep -q "^dtoverlay=disable-bt" "$CONFIG_FILE"; then
        echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
        log_success "Bluetooth disabled"
    fi
}

install_packages() {
    log_info "Installing required packages..."
    
    PACKAGES=(
        apt-transport-https
        ca-certificates
        curl
        gnupg
        lsb-release
        nfs-common
        open-iscsi
        jq
        htop
        iotop
        net-tools
        iptables
        libraspberrypi-bin
        python3
        python3-pip
        parted
        ufw
    )
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would install: ${PACKAGES[*]}"
        return
    fi
    
    apt-get install -y "${PACKAGES[@]}"
    
    log_success "Packages installed"
}

configure_sysctl() {
    log_info "Configuring kernel parameters..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would configure sysctl for Kubernetes networking"
        return
    fi
    
    cat > /etc/sysctl.d/99-kubernetes.conf << EOF
# Kubernetes required settings
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# Disable swap behavior
vm.swappiness = 0

# Increase inotify limits for kubectl, IDEs, and file watchers
fs.inotify.max_user_instances = 8192
fs.inotify.max_user_watches = 524288

# Network tuning for high connection counts
net.core.somaxconn = 32768
net.ipv4.tcp_max_syn_backlog = 32768
net.core.netdev_max_backlog = 32768

# Allow more connections
net.ipv4.ip_local_port_range = 10000 65535
net.netfilter.nf_conntrack_max = 131072
EOF

    # Load br_netfilter module (required for bridge networking)
    modprobe br_netfilter 2>/dev/null || true
    echo "br_netfilter" > /etc/modules-load.d/br_netfilter.conf
    
    # Load overlay module (for containerd)
    modprobe overlay 2>/dev/null || true
    echo "overlay" >> /etc/modules-load.d/br_netfilter.conf
    
    # Apply sysctl settings
    sysctl --system > /dev/null
    
    log_success "Kernel parameters configured"
}

install_storage_helper() {
    local source_script="$SCRIPT_DIR/mount-external-storage.sh"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would install storage helper to $STORAGE_HELPER_PATH"
        return 0
    fi

    if [[ ! -f "$source_script" ]]; then
        log_warning "Storage helper script not found at $source_script"
        return 1
    fi

    install -m 0755 "$source_script" "$STORAGE_HELPER_PATH"
    log_success "Installed storage helper to $STORAGE_HELPER_PATH"
}

configure_storage_autocheck() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would configure storage auto-check systemd unit"
        return
    fi

    if [[ ! -x "$STORAGE_HELPER_PATH" ]]; then
        log_warning "Storage helper not installed; skipping auto-check configuration"
        return
    fi

    local exec_args="--check --mount $STORAGE_MOUNT"
    if [[ -n "$STORAGE_DEVICE" && "$STORAGE_DEVICE" != "auto" ]]; then
        exec_args="$exec_args --device $STORAGE_DEVICE"
    else
        exec_args="$exec_args --auto"
    fi

    cat > /etc/systemd/system/mount-external-storage.service << EOF
[Unit]
Description=Mount external storage for k3s
After=network-online.target local-fs.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$STORAGE_HELPER_PATH $exec_args
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable mount-external-storage.service
    systemctl start mount-external-storage.service || true
    log_success "Enabled external storage auto-check on boot"
}

setup_external_storage() {
    if [[ "$SKIP_STORAGE" == "true" ]]; then
        log_info "Skipping external storage setup (--no-storage)"
        return
    fi

    if ! install_storage_helper; then
        log_warning "Storage helper not available; skipping storage setup"
        return
    fi

    local helper="$STORAGE_HELPER_PATH"
    local args=(--mount "$STORAGE_MOUNT" --format)

    if [[ -n "$STORAGE_DEVICE" && "$STORAGE_DEVICE" != "auto" ]]; then
        args+=(--device "$STORAGE_DEVICE")
    else
        args+=(--auto)
    fi

    log_info "Setting up external storage (auto-detect if needed)"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run: $helper ${args[*]}"
        return
    fi

    if ! "$helper" "${args[@]}"; then
        log_warning "External storage setup did not complete"
        return 1
    fi

    if mount | grep -q " $STORAGE_MOUNT "; then
        mkdir -p "$STORAGE_MOUNT"/{containers,volumes,logs,rancher}
        chmod 755 "$STORAGE_MOUNT"
        STORAGE_CONFIGURED=true
        log_success "External storage mounted at $STORAGE_MOUNT"
        log_info "Storage subdirectories created: containers, volumes, logs, rancher"
    else
        log_warning "Storage mount not detected at $STORAGE_MOUNT"
    fi

    configure_storage_autocheck
}

configure_firewall() {
    log_info "Configuring firewall rules..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would configure UFW with k8s ports (22, 6443, 10250, 8472, etc.)"
        return
    fi
    
    # Allow SSH (must be first!)
    ufw allow 22/tcp comment 'SSH'
    
    # Kubernetes API server
    ufw allow 6443/tcp comment 'Kubernetes API'
    
    # Kubelet API
    ufw allow 10250/tcp comment 'Kubelet API'
    
    # Flannel VXLAN
    ufw allow 8472/udp comment 'Flannel VXLAN'
    
    # Flannel Wireguard
    ufw allow 51820/udp comment 'Flannel WireGuard'
    ufw allow 51821/udp comment 'Flannel WireGuard IPv6'
    
    # Node exporter (Prometheus)
    ufw allow 9100/tcp comment 'Node Exporter'
    
    # etcd (for multi-master setups)
    ufw allow 2379:2380/tcp comment 'etcd'
    
    # NodePort range
    ufw allow 30000:32767/tcp comment 'NodePort Services'
    
    # Allow pod and service CIDRs (k3s defaults)
    ufw allow from 10.42.0.0/16 comment 'Pod CIDR'
    ufw allow from 10.43.0.0/16 comment 'Service CIDR'
    
    # Enable firewall (non-interactive)
    ufw --force enable
    
    log_success "Firewall configured and enabled"
}

enable_services() {
    log_info "Enabling required services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would enable iscsid service"
        return
    fi
    
    # Enable and start iscsid for iSCSI storage support
    if systemctl list-unit-files | grep -q iscsid; then
        systemctl enable iscsid
        systemctl start iscsid
        log_success "iSCSI daemon enabled"
    fi
    
    log_success "Services enabled"
}

print_summary() {
    echo ""
    echo "============================================================================="
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}DRY RUN Complete - No changes were made${NC}"
    else
        echo -e "${GREEN}Bootstrap Complete!${NC}"
    fi
    echo "============================================================================="
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "The following changes WOULD be made:"
    else
        echo "The following changes were made:"
    fi
    
    [[ "$SKIP_UPDATE" != "true" ]] && echo "  [x] System packages updated"
    [[ -n "$HOSTNAME" ]] && echo "  [x] Hostname set to: $HOSTNAME"
    echo "  [x] Timezone set to: $TIMEZONE"
    [[ -n "$STATIC_IP" ]] && echo "  [x] Static IP configured: $STATIC_IP (gateway: $GATEWAY)"
    echo "  [x] Swap disabled"
    echo "  [x] cgroups enabled (memory, cpuset)"
    echo "  [x] 64-bit kernel mode enabled"
    echo "  [x] GPU memory minimized (16MB)"
    echo "  [x] WiFi and Bluetooth disabled"
    echo "  [x] Required packages installed"
    echo "  [x] Kernel parameters configured"
    if [[ "$SKIP_STORAGE" == "true" ]]; then
        echo "  [ ] External storage skipped"
    elif [[ "$STORAGE_CONFIGURED" == "true" ]]; then
        echo "  [x] External storage mounted at: $STORAGE_MOUNT"
    else
        echo "  [ ] External storage not mounted (check logs)"
    fi
    echo "  [x] Firewall configured and enabled"
    echo ""
    
    if [[ "$DRY_RUN" != "true" ]]; then
        echo -e "${YELLOW}IMPORTANT: A reboot is required to apply kernel changes.${NC}"
        echo ""
        echo "After reboot, verify the setup with:"
        echo ""
        echo "  # Check architecture (should be aarch64)"
        echo "  uname -m"
        echo ""
        echo "  # Check swap is disabled (should show 0)"
        echo "  free -h | grep Swap"
        echo ""
        echo "  # Check cgroups are enabled (memory should show 1)"
        echo "  cat /proc/cgroups | grep memory"
        echo ""
        [[ "$SKIP_STORAGE" != "true" ]] && echo "  # Check storage is mounted" && echo "  df -h $STORAGE_MOUNT"
        echo ""
        echo "Or run this verification one-liner:"
        echo '  echo "Arch: $(uname -m), Swap: $(free -h | grep Swap | awk '"'"'{print $2}'"'"'), cgroups: $(cat /proc/cgroups | grep memory | awk '"'"'{print $4}'"'"')"'
        echo ""
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================================================="
    echo "Raspberry Pi 5 Bootstrap Script for Kubernetes v$VERSION"
    echo "============================================================================="
    echo ""
    
    parse_args "$@"
    
    # Check requirements
    check_root
    check_rpi
    
    # Interactive mode
    if [[ "$INTERACTIVE" == "true" ]]; then
        run_interactive
    fi
    
    # Dry run notice
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warning "DRY RUN MODE - No changes will be made"
        echo ""
    fi
    
    # Run setup steps
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
    
    # Prompt for reboot
    if [[ "$DRY_RUN" != "true" && "$SKIP_REBOOT_PROMPT" != "true" ]]; then
        echo ""
        read -p "Reboot now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Rebooting in 5 seconds..."
            sleep 5
            reboot
        fi
    fi
}

main "$@"
