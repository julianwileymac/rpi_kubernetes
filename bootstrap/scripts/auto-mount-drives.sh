#!/bin/bash
# =============================================================================
# Multi-Drive Auto-Detection and Mount Script
# =============================================================================
# Discovers all external block devices, partitions/formats them if needed,
# mounts each one, persists via fstab, and writes a machine-readable manifest
# so Ansible/Kubernetes can create PersistentVolumes automatically.
#
# The first detected drive mounts at STORAGE_BASE (default /mnt/storage) for
# backward compatibility. Additional drives mount under STORAGE_BASE/disks/.
#
# Usage:
#   sudo ./auto-mount-drives.sh [OPTIONS]
#
# Options:
#   --base-path PATH   Base storage directory (default: /mnt/storage)
#   --format           Allow partitioning and formatting uninitialized drives
#   --node-name NAME   Kubernetes node name for manifest (default: hostname)
#   --wait SECONDS     Seconds to wait for devices on boot (default: 30)
#   --verbose          Enable verbose output
#   --dry-run          Show what would be done without making changes
# =============================================================================

set -euo pipefail

STORAGE_BASE="${STORAGE_BASE:-/mnt/storage}"
MANIFEST_DIR="/var/lib/auto-mount-drives"
MANIFEST="$MANIFEST_DIR/manifest.json"
FS_TYPE="ext4"
WAIT_TIMEOUT=30
FORMAT=false
VERBOSE=false
DRY_RUN=false
NODE_NAME=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1" >&2; }
log_success() { echo -e "${GREEN}[OK]${NC} $1" >&2; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_verbose() { [[ "$VERBOSE" == "true" ]] && echo -e "${BLUE}[VERBOSE]${NC} $1" >&2 || true; }

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --base-path)  STORAGE_BASE="$2"; shift 2 ;;
            --format)     FORMAT=true; shift ;;
            --node-name)  NODE_NAME="$2"; shift 2 ;;
            --wait)       WAIT_TIMEOUT="$2"; shift 2 ;;
            --verbose)    VERBOSE=true; shift ;;
            --dry-run)    DRY_RUN=true; VERBOSE=true; shift ;;
            --help|-h)
                head -n 20 "$0" | tail -n +2 | sed 's/^# \?//'
                exit 0 ;;
            *) log_error "Unknown option: $1"; exit 1 ;;
        esac
    done
    [[ -z "$NODE_NAME" ]] && NODE_NAME="$(hostname)"
}

check_root() {
    [[ $EUID -eq 0 ]] || { log_error "Must run as root"; exit 1; }
}

get_root_device() {
    local root_source
    root_source=$(findmnt -n -o SOURCE / 2>/dev/null || true)
    if [[ "$root_source" == /dev/* ]]; then
        local parent
        parent=$(lsblk -no PKNAME "$root_source" 2>/dev/null | head -1 || true)
        [[ -n "$parent" ]] && echo "$parent" && return
        basename "$root_source" | sed 's/p\?[0-9]*$//'
        return
    fi
    echo ""
}

wait_for_devices() {
    local waited=0
    while [[ $waited -lt $WAIT_TIMEOUT ]]; do
        local count
        count=$(lsblk -dn -o NAME,TYPE 2>/dev/null | awk '$2=="disk"' | wc -l)
        [[ $count -gt 1 ]] && return 0
        sleep 2
        waited=$((waited + 2))
        log_verbose "Waiting for devices... (${waited}s/${WAIT_TIMEOUT}s)"
    done
    log_verbose "Device wait timeout reached"
}

discover_drives() {
    local root_dev
    root_dev=$(get_root_device)
    log_verbose "Root device: $root_dev"

    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        [[ "$name" == "$root_dev" ]] && continue
        case "$name" in
            mmcblk*|loop*|ram*|zram*|nbd*) continue ;;
        esac
        log_verbose "Candidate drive: /dev/$name"
        echo "/dev/$name"
    done < <(lsblk -dn -o NAME,TYPE 2>/dev/null | awk '$2=="disk"{print $1}')
}

resolve_partition() {
    local device=$1
    local parts
    parts=$(lsblk -nr -o NAME,TYPE "$device" 2>/dev/null | awk '$2=="part"{print $1}')

    if [[ -n "$parts" ]]; then
        echo "/dev/$(echo "$parts" | head -1)"
        return 0
    fi

    if [[ "$FORMAT" != "true" ]]; then
        log_warn "No partition on $device (use --format to create one)"
        return 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would partition $device"
        echo "${device}1"
        return 0
    fi

    log_info "Creating GPT partition table on $device"
    parted -s "$device" mklabel gpt
    parted -s "$device" mkpart primary "$FS_TYPE" 0% 100%

    local wait_count=0
    local expected
    if [[ "$device" == *nvme* ]]; then expected="${device}p1"; else expected="${device}1"; fi
    while [[ ! -b "$expected" && $wait_count -lt 10 ]]; do
        sleep 1
        ((wait_count++))
    done

    [[ -b "$expected" ]] || { log_error "Partition did not appear: $expected"; return 1; }
    log_success "Created partition: $expected"
    echo "$expected"
}

ensure_filesystem() {
    local partition=$1
    local current_fs
    current_fs=$(blkid -s TYPE -o value "$partition" 2>/dev/null || true)

    if [[ "$current_fs" == "$FS_TYPE" ]]; then
        log_verbose "$partition already formatted as $FS_TYPE"
        return 0
    fi

    if [[ -n "$current_fs" && "$current_fs" != "$FS_TYPE" ]]; then
        log_warn "$partition has filesystem $current_fs (expected $FS_TYPE)"
        [[ "$FORMAT" == "true" ]] || return 1
    fi

    [[ "$FORMAT" == "true" ]] || { log_warn "$partition has no filesystem (use --format)"; return 1; }

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would format $partition as $FS_TYPE"
        return 0
    fi

    log_info "Formatting $partition as $FS_TYPE"
    mkfs."$FS_TYPE" -F -L "k8s-storage" "$partition"
    log_success "Formatted $partition"
}

is_already_mounted() {
    local partition=$1
    grep -q "^$partition " /proc/mounts 2>/dev/null
}

get_partition_uuid() {
    blkid -s UUID -o value "$1" 2>/dev/null || true
}

mount_drive() {
    local partition=$1
    local mount_path=$2

    if is_already_mounted "$partition"; then
        local current_mount
        current_mount=$(grep "^$partition " /proc/mounts | awk '{print $2}' | head -1)
        log_info "$partition already mounted at $current_mount"
        echo "$current_mount"
        return 0
    fi

    if mountpoint -q "$mount_path" 2>/dev/null; then
        log_warn "$mount_path is already a mount point"
        echo "$mount_path"
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would mount $partition at $mount_path"
        echo "$mount_path"
        return 0
    fi

    mkdir -p "$mount_path"
    mount -t "$FS_TYPE" -o defaults,noatime,nodiratime "$partition" "$mount_path"
    log_success "Mounted $partition at $mount_path"

    local uuid
    uuid=$(get_partition_uuid "$partition")
    if [[ -n "$uuid" ]] && ! grep -q "UUID=$uuid" /etc/fstab 2>/dev/null; then
        echo "UUID=$uuid $mount_path $FS_TYPE defaults,noatime,nodiratime 0 2" >> /etc/fstab
        log_info "Added fstab entry for $partition (UUID=$uuid)"
    fi

    echo "$mount_path"
}

create_subdirectories() {
    local mount_path=$1
    local is_primary=$2

    local dirs=("volumes")
    if [[ "$is_primary" == "true" ]]; then
        dirs+=("containers" "logs" "k3s")
    fi

    for dir in "${dirs[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_verbose "[DRY RUN] Would create $mount_path/$dir"
        else
            mkdir -p "$mount_path/$dir"
            chmod 755 "$mount_path/$dir"
        fi
    done
}

write_manifest() {
    local -n entries=$1
    local count=${#entries[@]}

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would write manifest with $count drive(s)"
        return 0
    fi

    mkdir -p "$MANIFEST_DIR"

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local drives_json="["
    local first=true
    for entry in "${entries[@]}"; do
        $first || drives_json+=","
        drives_json+="$entry"
        first=false
    done
    drives_json+="]"

    local json
    json=$(cat <<EOF
{"hostname":"$NODE_NAME","timestamp":"$timestamp","storage_base":"$STORAGE_BASE","drives":$drives_json}
EOF
)

    if command -v jq &>/dev/null; then
        echo "$json" | jq '.' > "$MANIFEST"
    else
        echo "$json" > "$MANIFEST"
    fi

    chmod 644 "$MANIFEST"
    log_success "Manifest written to $MANIFEST ($count drive(s))"
}

main() {
    parse_args "$@"
    check_root

    log_info "Auto-mount drives starting (node: $NODE_NAME, base: $STORAGE_BASE)"

    wait_for_devices

    local -a drives
    mapfile -t drives < <(discover_drives)

    if [[ ${#drives[@]} -eq 0 ]]; then
        log_warn "No external drives detected"
        local -a empty=()
        write_manifest empty
        exit 0
    fi

    log_info "Found ${#drives[@]} external drive(s): ${drives[*]}"

    local -a manifest_entries=()
    local index=0

    for device in "${drives[@]}"; do
        log_info "Processing $device"

        local partition
        partition=$(resolve_partition "$device") || { log_warn "Skipping $device (no partition)"; continue; }
        ensure_filesystem "$partition" || { log_warn "Skipping $device (no filesystem)"; continue; }

        local uuid
        uuid=$(get_partition_uuid "$partition")
        [[ -z "$uuid" ]] && { log_warn "Skipping $device (no UUID)"; continue; }

        local mount_path
        local is_primary="false"
        if [[ $index -eq 0 ]]; then
            mount_path="$STORAGE_BASE"
            is_primary="true"
        else
            local short_id="${uuid:0:8}"
            mount_path="$STORAGE_BASE/disks/$short_id"
        fi

        local actual_mount
        actual_mount=$(mount_drive "$partition" "$mount_path") || { log_warn "Skipping $device (mount failed)"; continue; }

        create_subdirectories "$actual_mount" "$is_primary"

        local size_bytes size_gi
        size_bytes=$(lsblk -bno SIZE "$partition" 2>/dev/null | head -1 || echo "0")
        size_gi=$(( size_bytes / 1073741824 ))
        [[ $size_gi -lt 1 ]] && size_gi=1

        manifest_entries+=("{\"device\":\"$device\",\"partition\":\"$partition\",\"uuid\":\"$uuid\",\"mount_path\":\"$actual_mount\",\"size_gi\":$size_gi,\"primary\":$is_primary}")

        index=$((index + 1))
    done

    write_manifest manifest_entries

    log_info "Drive summary:"
    for device in "${drives[@]}"; do
        local parts
        parts=$(lsblk -nr -o NAME,TYPE "$device" 2>/dev/null | awk '$2=="part"{print "/dev/"$1}')
        for p in $parts; do
            if grep -q "^$p " /proc/mounts 2>/dev/null; then
                local mp
                mp=$(grep "^$p " /proc/mounts | awk '{print $2}' | head -1)
                df -h "$mp" 2>/dev/null | tail -1 | awk -v dev="$p" '{printf "  %s -> %s (%s used of %s)\n", dev, $6, $3, $2}'
            fi
        done
    done

    log_success "Auto-mount complete: ${#manifest_entries[@]} drive(s) active"
}

main "$@"
