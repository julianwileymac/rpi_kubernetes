#!/bin/bash
# =============================================================================
# Local Ad-Hoc External Drive Mounting Script
# =============================================================================
# Standalone script for manually mounting external drives on nodes.
# Can be run directly on nodes without Ansible automation.
#
# Usage:
#   sudo ./mount-drive-local.sh [OPTIONS]
#
# Options:
#   --mount-point PATH    Mount point directory (default: /mnt/storage)
#   --device DEVICE       Specific device to use (e.g., /dev/sda)
#   --dry-run            Show what would be done without making changes
#   --verbose            Enable verbose output
#   --help               Show this help message
# =============================================================================

set -euo pipefail

# Configuration
MOUNT_POINT="${MOUNT_POINT:-/mnt/storage}"
STORAGE_DEVICE="${STORAGE_DEVICE:-}"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
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

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${CYAN}[VERBOSE]${NC} $1"
    fi
}

show_help() {
    cat << EOF
External Drive Mounting Script

This script automatically detects, partitions, formats, and mounts external USB drives.

Usage:
    sudo ./mount-drive-local.sh [OPTIONS]

Options:
    --mount-point PATH    Mount point directory (default: /mnt/storage)
    --device DEVICE       Specific device to use (e.g., /dev/sda)
                          If not specified, auto-detects first USB device
    --dry-run            Show what would be done without making changes
    --verbose            Enable verbose output
    --help               Show this help message

Examples:
    # Auto-detect and mount USB drive
    sudo ./mount-drive-local.sh

    # Mount specific device
    sudo ./mount-drive-local.sh --device /dev/sda

    # Dry run to see what would happen
    sudo ./mount-drive-local.sh --dry-run --verbose

    # Custom mount point
    sudo ./mount-drive-local.sh --mount-point /mnt/data

Environment Variables:
    MOUNT_POINT          Mount point directory
    STORAGE_DEVICE       Specific device to use
    DRY_RUN              Set to 'true' for dry run mode
    VERBOSE              Set to 'true' for verbose output

EOF
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
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                echo ""
                show_help
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

# List available block devices
list_devices() {
    log_info "Available block devices:"
    echo ""
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL | grep -E "NAME|disk" || true
    echo ""
}

# Main function - delegates to mount-external-drive.sh if available
main() {
    parse_args "$@"
    
    # Check if main mount script exists
    local main_script="/usr/local/bin/mount-external-drive.sh"
    
    if [[ -f "$main_script" ]]; then
        log_info "Using system mount script: $main_script"
        exec "$main_script" "$@"
    else
        log_warning "System mount script not found at $main_script"
        log_info "This script is a wrapper for mount-external-drive.sh"
        log_info "For standalone operation, ensure mount-external-drive.sh is available"
        echo ""
        
        # Check if script exists in same directory
        local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        local local_script="$script_dir/mount-external-drive.sh"
        
        if [[ -f "$local_script" ]]; then
            log_info "Using local mount script: $local_script"
            exec "$local_script" "$@"
        else
            log_error "mount-external-drive.sh not found"
            log_info "Please ensure mount-external-drive.sh is in the same directory"
            log_info "or install it via Ansible bootstrap playbook"
            exit 1
        fi
    fi
}

# Run main function
main "$@"
