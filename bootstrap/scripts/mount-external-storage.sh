#!/bin/bash
# =============================================================================
# External Storage Auto-Mount Helper
# =============================================================================
# Safely auto-detects external disks, mounts them, and (optionally) formats
# them for use with the cluster. Designed for ad-hoc runs and boot checks.
#
# Usage:
#   sudo ./mount-external-storage.sh --auto --mount /mnt/storage --format
#   sudo ./mount-external-storage.sh --device /dev/sda --mount /mnt/storage
#   sudo ./mount-external-storage.sh --auto --check --mount /mnt/storage
# =============================================================================

set -euo pipefail

DEVICE=""
MOUNT_POINT="/mnt/storage"
FS_TYPE="ext4"
ALLOW_FORMAT="false"
CHECK_ONLY="false"
AUTO_DETECT="false"
PERSIST="true"
REQUIRE_DEVICE="false"

RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

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

show_help() {
    cat << 'EOF'
External Storage Auto-Mount Helper
==================================

USAGE:
  sudo ./mount-external-storage.sh [OPTIONS]

OPTIONS:
  --device PATH       Block device (e.g., /dev/sda, /dev/nvme0n1)
  --auto              Auto-detect external disk (default if --device not set)
  --mount PATH        Mount point (default: /mnt/storage)
  --fs TYPE           Filesystem type (default: ext4)
  --format            Allow partitioning/formatting when needed
  --check             Check/mount only (no partitioning or formatting)
  --no-persist        Do not modify /etc/fstab
  --require-device    Exit non-zero if no device detected
  --help, -h          Show help

EXAMPLES:
  # Auto-detect and set up storage (format if needed)
  sudo ./mount-external-storage.sh --auto --mount /mnt/storage --format

  # Check at boot (no formatting)
  sudo ./mount-external-storage.sh --auto --check --mount /mnt/storage

  # Explicit device
  sudo ./mount-external-storage.sh --device /dev/sda --mount /mnt/storage --format
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --device)
                DEVICE="$2"
                shift 2
                ;;
            --mount)
                MOUNT_POINT="$2"
                shift 2
                ;;
            --fs)
                FS_TYPE="$2"
                shift 2
                ;;
            --format)
                ALLOW_FORMAT="true"
                shift
                ;;
            --check)
                CHECK_ONLY="true"
                shift
                ;;
            --auto)
                AUTO_DETECT="true"
                shift
                ;;
            --no-persist)
                PERSIST="false"
                shift
                ;;
            --require-device)
                REQUIRE_DEVICE="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

get_root_device() {
    local root_source
    root_source=$(findmnt -n -o SOURCE / 2>/dev/null || true)
    if [[ "$root_source" == /dev/* ]]; then
        local parent
        parent=$(lsblk -no PKNAME "$root_source" 2>/dev/null || true)
        if [[ -n "$parent" ]]; then
            echo "$parent"
            return
        fi
        echo "$(basename "$root_source")"
        return
    fi
    echo ""
}

detect_device() {
    local root_device
    root_device=$(get_root_device)

    local candidates=()
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local name
        name=$(echo "$line" | awk '{print $1}')

        # Skip boot/root device
        if [[ -n "$root_device" && "$name" == "$root_device" ]]; then
            continue
        fi

        # Skip SD card and virtual disks
        if [[ "$name" == mmcblk* || "$name" == loop* || "$name" == ram* || "$name" == zram* ]]; then
            continue
        fi

        candidates+=("$name")
    done < <(lsblk -dn -o NAME,TYPE | awk '$2=="disk"{print $1}')

    if [[ ${#candidates[@]} -eq 0 ]]; then
        log_warning "No external storage devices detected"
        if [[ "$REQUIRE_DEVICE" == "true" ]]; then
            exit 1
        fi
        exit 0
    fi

    if [[ ${#candidates[@]} -gt 1 ]]; then
        log_error "Multiple candidate devices found: ${candidates[*]}"
        log_error "Specify a device with --device /dev/<name>"
        exit 1
    fi

    DEVICE="/dev/${candidates[0]}"
    log_info "Auto-detected device: $DEVICE"
}

resolve_partition() {
    local partitions=()
    while IFS= read -r part; do
        [[ -z "$part" ]] && continue
        partitions+=("$part")
    done < <(lsblk -nr -o NAME,TYPE "$DEVICE" | awk '$2=="part"{print $1}')

    if [[ ${#partitions[@]} -gt 0 ]]; then
        echo "/dev/${partitions[0]}"
        return
    fi

    if [[ "$DEVICE" == *"nvme"* ]]; then
        echo "${DEVICE}p1"
    else
        echo "${DEVICE}1"
    fi
}

ensure_partition() {
    local partition="$1"
    if [[ -b "$partition" ]]; then
        return
    fi

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_warning "No partition exists on $DEVICE (check-only mode)"
        exit 1
    fi

    if [[ "$ALLOW_FORMAT" != "true" ]]; then
        log_error "No partition found on $DEVICE and formatting is disabled"
        exit 1
    fi

    log_info "Creating GPT partition table on $DEVICE..."
    parted -s "$DEVICE" mklabel gpt
    parted -s "$DEVICE" mkpart primary "$FS_TYPE" 0% 100%

    local wait_count=0
    while [[ ! -b "$partition" && $wait_count -lt 10 ]]; do
        sleep 1
        ((wait_count++))
    done

    if [[ ! -b "$partition" ]]; then
        log_error "Partition $partition did not appear after creation"
        exit 1
    fi
}

ensure_filesystem() {
    local partition="$1"
    local current_fs
    current_fs=$(blkid -s TYPE -o value "$partition" 2>/dev/null || true)

    if [[ -z "$current_fs" ]]; then
        if [[ "$CHECK_ONLY" == "true" ]]; then
            log_warning "Partition $partition has no filesystem (check-only)"
            exit 1
        fi
        if [[ "$ALLOW_FORMAT" != "true" ]]; then
            log_error "Partition $partition has no filesystem and formatting is disabled"
            exit 1
        fi
        log_info "Formatting $partition as $FS_TYPE..."
        mkfs."$FS_TYPE" -F "$partition"
        return
    fi

    if [[ "$current_fs" != "$FS_TYPE" ]]; then
        if [[ "$CHECK_ONLY" == "true" ]]; then
            log_warning "Partition $partition is $current_fs (expected $FS_TYPE)"
            exit 1
        fi
        if [[ "$ALLOW_FORMAT" != "true" ]]; then
            log_error "Partition $partition is $current_fs and formatting is disabled"
            exit 1
        fi
        log_warning "Reformatting $partition from $current_fs to $FS_TYPE..."
        mkfs."$FS_TYPE" -F "$partition"
    fi
}

ensure_mount() {
    local partition="$1"

    mkdir -p "$MOUNT_POINT"

    if mountpoint -q "$MOUNT_POINT"; then
        log_info "Already mounted at $MOUNT_POINT"
        return
    fi

    local uuid
    uuid=$(blkid -s UUID -o value "$partition" 2>/dev/null || true)
    if [[ -z "$uuid" ]]; then
        log_error "Could not determine UUID for $partition"
        exit 1
    fi

    if [[ "$PERSIST" == "true" && "$CHECK_ONLY" != "true" ]]; then
        if ! grep -q "$uuid" /etc/fstab; then
            echo "UUID=$uuid $MOUNT_POINT $FS_TYPE defaults,noatime,nodiratime 0 2" >> /etc/fstab
            log_info "Added fstab entry for $partition"
        fi
    fi

    mount -t "$FS_TYPE" -o defaults,noatime,nodiratime "$partition" "$MOUNT_POINT"
    log_success "Mounted $partition at $MOUNT_POINT"
}

main() {
    parse_args "$@"
    check_root

    if [[ "$DEVICE" == "auto" ]]; then
        DEVICE=""
        AUTO_DETECT="true"
    fi

    if [[ -z "$DEVICE" ]]; then
        AUTO_DETECT="true"
    fi

    if [[ "$AUTO_DETECT" == "true" ]]; then
        detect_device
    fi

    if [[ -z "$DEVICE" ]]; then
        log_error "No device specified and auto-detect disabled"
        exit 1
    fi

    if [[ ! -b "$DEVICE" ]]; then
        log_error "Device $DEVICE not found"
        exit 1
    fi

    local partition
    partition=$(resolve_partition)

    ensure_partition "$partition"
    ensure_filesystem "$partition"
    ensure_mount "$partition"

    log_success "External storage ready on $MOUNT_POINT"
}

main "$@"
