#!/bin/bash
# =============================================================================
# External Drive Auto-Detection and Mounting Script
# =============================================================================
# Automatically detects, partitions, formats, and mounts external USB drives
# on Kubernetes cluster nodes. Designed to run on boot via systemd service.
#
# Usage:
#   sudo ./mount-external-drive.sh [OPTIONS]
#
# Options:
#   --mount-point PATH    Mount point directory (default: /mnt/storage)
#   --device DEVICE      Specific device to use (e.g., /dev/sda)
#   --dry-run            Show what would be done without making changes
#   --verbose            Enable verbose output
#   --wait SECONDS       Wait up to SECONDS for device to appear (default: 60)
# =============================================================================

set -euo pipefail

# Configuration
MOUNT_POINT="${MOUNT_POINT:-/mnt/storage}"
STORAGE_DEVICE="${STORAGE_DEVICE:-}"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"
WAIT_TIME="${WAIT_TIME:-60}"
STORAGE_FS="ext4"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}[VERBOSE]${NC} $1" >&2
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --mount-point)
                MOUNT_POINT="$2"
                shift 2
                ;;
            --device)
                STORAGE_DEVICE="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --verbose)
                VERBOSE="true"
                shift
                ;;
            --wait)
                WAIT_TIME="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Get boot device (to exclude from USB detection)
get_boot_device() {
    local root_dev=$(findmnt -n -o SOURCE / | sed 's/p[0-9]*$//' | sed 's/[0-9]*$//')
    echo "$root_dev"
}

# Detect USB storage devices
detect_usb_devices() {
    local boot_dev=$(get_boot_device)
    log_verbose "Boot device: $boot_dev"
    
    # Get all block devices
    local devices=$(lsblk -dno NAME,TYPE | grep -E 'disk|loop' | awk '{print $1}' || true)
    
    if [[ -z "$devices" ]]; then
        log_warning "No block devices found"
        return 1
    fi
    
    # Filter USB devices (exclude boot device and loop devices)
    local usb_devices=""
    for dev in $devices; do
        local dev_path="/dev/$dev"
        
        # Skip loop devices
        if [[ "$dev" == loop* ]]; then
            log_verbose "Skipping loop device: $dev"
            continue
        fi
        
        # Skip boot device
        if [[ "$dev_path" == "$boot_dev"* ]] || [[ "/dev/$dev" == "$boot_dev"* ]]; then
            log_verbose "Skipping boot device: $dev"
            continue
        fi
        
        # Check if device is USB (check by ID_PATH or udev)
        local id_path=$(udevadm info --query=property --name="$dev_path" 2>/dev/null | grep -i "ID_PATH" | head -1 || true)
        local id_bus=$(udevadm info --query=property --name="$dev_path" 2>/dev/null | grep -i "ID_BUS" | head -1 || true)
        
        if [[ -n "$id_path" ]] && echo "$id_path" | grep -qi "usb"; then
            log_verbose "Found USB device: $dev_path ($id_path)"
            usb_devices="$usb_devices $dev_path"
        elif [[ -n "$id_bus" ]] && echo "$id_bus" | grep -qi "usb"; then
            log_verbose "Found USB device: $dev_path (bus: $id_bus)"
            usb_devices="$usb_devices $dev_path"
        else
            # Also check /sys/block for USB devices
            if [[ -d "/sys/block/$dev" ]] && readlink -f "/sys/block/$dev" | grep -qi "usb"; then
                log_verbose "Found USB device: $dev_path (via sysfs)"
                usb_devices="$usb_devices $dev_path"
            fi
        fi
    done
    
    # Trim whitespace
    usb_devices=$(echo "$usb_devices" | xargs)
    
    if [[ -z "$usb_devices" ]]; then
        log_warning "No USB storage devices detected"
        return 1
    fi
    
    # Return first USB device
    echo "$usb_devices" | awk '{print $1}'
    return 0
}

# Wait for device to appear
wait_for_device() {
    local device="$1"
    local waited=0
    
    while [[ $waited -lt $WAIT_TIME ]]; do
        if [[ -b "$device" ]]; then
            log_verbose "Device $device is available"
            return 0
        fi
        log_verbose "Waiting for device $device... (${waited}s/${WAIT_TIME}s)"
        sleep 2
        waited=$((waited + 2))
    done
    
    log_error "Device $device did not appear within ${WAIT_TIME} seconds"
    return 1
}

# Check if device is already mounted
is_mounted() {
    local device="$1"
    mountpoint -q "$device" 2>/dev/null || grep -q "$device" /proc/mounts 2>/dev/null
}

# Get partition device (device1, device2, etc.)
get_partition_device() {
    local device="$1"
    
    # Check if device has partitions
    local partitions=$(lsblk -lno NAME "$device" | grep -E "${device##*/}[0-9]+" || true)
    
    if [[ -n "$partitions" ]]; then
        # Use first partition
        local first_part=$(echo "$partitions" | head -1)
        echo "/dev/$first_part"
    else
        # No partitions, check if device itself is a partition
        if [[ "$device" =~ [0-9]+$ ]]; then
            echo "$device"
        else
            # Need to create partition
            echo ""
        fi
    fi
}

# Create partition table and partition
create_partition() {
    local device="$1"
    
    log_info "Creating partition table on $device"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run: parted -s $device mklabel gpt"
        log_info "[DRY RUN] Would run: parted -s $device mkpart primary ext4 0% 100%"
        return 0
    fi
    
    # Create GPT partition table
    parted -s "$device" mklabel gpt || {
        log_error "Failed to create partition table"
        return 1
    }
    
    # Create partition
    parted -s "$device" mkpart primary ext4 0% 100% || {
        log_error "Failed to create partition"
        return 1
    }
    
    # Wait for partition to be available
    sleep 2
    
    # Get partition device
    local partition=$(get_partition_device "$device")
    if [[ -z "$partition" ]] || [[ ! -b "$partition" ]]; then
        log_error "Partition $partition not found after creation"
        return 1
    fi
    
    log_success "Partition created: $partition"
    echo "$partition"
}

# Format partition
format_partition() {
    local partition="$1"
    
    log_info "Formatting $partition as $STORAGE_FS"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run: mkfs.$STORAGE_FS -F $partition"
        return 0
    fi
    
    mkfs.$STORAGE_FS -F "$partition" || {
        log_error "Failed to format partition"
        return 1
    }
    
    log_success "Partition formatted"
}

# Get UUID of partition
get_partition_uuid() {
    local partition="$1"
    blkid -s UUID -o value "$partition" 2>/dev/null || {
        log_error "Failed to get UUID for $partition"
        return 1
    }
}

# Add to fstab
add_to_fstab() {
    local uuid="$1"
    local mount_point="$2"
    local fs_type="$3"
    
    log_info "Adding entry to /etc/fstab"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would add: UUID=$uuid $mount_point $fs_type defaults,noatime,nodiratime 0 2"
        return 0
    fi
    
    # Check if entry already exists
    if grep -q "UUID=$uuid" /etc/fstab 2>/dev/null; then
        log_warning "fstab entry already exists for UUID $uuid"
        return 0
    fi
    
    # Add entry
    echo "UUID=$uuid $mount_point $fs_type defaults,noatime,nodiratime 0 2" >> /etc/fstab || {
        log_error "Failed to add entry to fstab"
        return 1
    }
    
    log_success "Added to fstab"
}

# Mount storage
mount_storage() {
    local partition="$1"
    local mount_point="$2"
    
    # Create mount point if it doesn't exist
    if [[ ! -d "$mount_point" ]]; then
        log_info "Creating mount point: $mount_point"
        if [[ "$DRY_RUN" != "true" ]]; then
            mkdir -p "$mount_point"
        fi
    fi
    
    # Check if already mounted
    if mountpoint -q "$mount_point" 2>/dev/null; then
        log_warning "Mount point $mount_point is already mounted"
        return 0
    fi
    
    log_info "Mounting $partition to $mount_point"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run: mount $partition $mount_point"
        return 0
    fi
    
    mount "$partition" "$mount_point" || {
        log_error "Failed to mount partition"
        return 1
    }
    
    log_success "Mounted successfully"
}

# Create storage subdirectories
create_storage_directories() {
    local mount_point="$1"
    
    log_info "Creating storage subdirectories"
    
    local dirs=("containers" "volumes" "logs" "k3s")
    
    for dir in "${dirs[@]}"; do
        local full_path="$mount_point/$dir"
        if [[ ! -d "$full_path" ]]; then
            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[DRY RUN] Would create: $full_path"
            else
                mkdir -p "$full_path"
                chmod 755 "$full_path"
            fi
        fi
    done
    
    log_success "Storage directories created"
}

# Configure k3s to use external storage
configure_k3s_storage() {
    local mount_point="$1"
    
    log_info "Configuring k3s to use external storage"
    
    local k3s_config="/etc/rancher/k3s/config.yaml"
    local k3s_data_dir="$mount_point/k3s"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would add to $k3s_config: data-dir: $k3s_data_dir"
        return 0
    fi
    
    # Create config directory if it doesn't exist
    mkdir -p "$(dirname "$k3s_config")"
    
    # Check if data-dir already configured
    if [[ -f "$k3s_config" ]] && grep -q "data-dir:" "$k3s_config"; then
        log_warning "k3s data-dir already configured"
        return 0
    fi
    
    # Add data-dir configuration
    echo "data-dir: $k3s_data_dir" >> "$k3s_config" || {
        log_error "Failed to configure k3s data-dir"
        return 1
    }
    
    log_success "k3s configured to use external storage"
}

# Main function
main() {
    parse_args "$@"
    check_root
    
    log_info "Starting external drive auto-detection and mounting"
    log_info "Mount point: $MOUNT_POINT"
    
    # Determine device
    if [[ -n "$STORAGE_DEVICE" ]]; then
        log_info "Using specified device: $STORAGE_DEVICE"
        device="$STORAGE_DEVICE"
    else
        log_info "Auto-detecting USB storage device..."
        device=$(detect_usb_devices) || {
            log_error "No USB storage device found"
            exit 1
        }
        log_success "Detected USB device: $device"
    fi
    
    # Wait for device if needed
    if ! wait_for_device "$device"; then
        exit 1
    fi
    
    # Get partition device
    partition=$(get_partition_device "$device")
    
    if [[ -z "$partition" ]]; then
        log_info "No partition found, creating partition..."
        partition=$(create_partition "$device") || exit 1
    else
        log_info "Using existing partition: $partition"
    fi
    
    # Check if partition is formatted
    fs_type=$(blkid -s TYPE -o value "$partition" 2>/dev/null || echo "")
    
    if [[ -z "$fs_type" ]] || [[ "$fs_type" != "$STORAGE_FS" ]]; then
        log_info "Partition not formatted or wrong filesystem, formatting..."
        format_partition "$partition" || exit 1
    else
        log_info "Partition already formatted as $fs_type"
    fi
    
    # Get UUID
    uuid=$(get_partition_uuid "$partition") || exit 1
    log_info "Partition UUID: $uuid"
    
    # Add to fstab if not present
    if ! grep -q "UUID=$uuid" /etc/fstab 2>/dev/null; then
        add_to_fstab "$uuid" "$MOUNT_POINT" "$STORAGE_FS" || exit 1
    fi
    
    # Mount storage
    mount_storage "$partition" "$MOUNT_POINT" || exit 1
    
    # Create subdirectories
    create_storage_directories "$MOUNT_POINT"
    
    # Configure k3s if k3s is installed
    if command -v k3s &>/dev/null || [[ -f "/usr/local/bin/k3s" ]]; then
        configure_k3s_storage "$MOUNT_POINT"
    fi
    
    # Display mount info
    log_info "Storage mounted successfully:"
    df -h "$MOUNT_POINT" | tail -1
    
    log_success "External drive setup complete"
}

# Run main function
main "$@"
