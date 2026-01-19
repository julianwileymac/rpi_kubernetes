#!/bin/bash
# =============================================================================
# Raspberry Pi Existing OS Preparation Script
# =============================================================================
# Version: 1.0.0
#
# Prepares a Raspberry Pi with an existing OS installation for the bootstrap
# process. This script should be run BEFORE prepare-rpi.sh.
#
# Usage:
#   sudo ./prep-existing-os.sh [OPTIONS]
#   sudo ./prep-existing-os.sh --interactive
#   sudo ./prep-existing-os.sh --hostname rpi1 --ssh-key ~/.ssh/id_ed25519.pub
#
# Prerequisites:
#   - Raspberry Pi with Raspberry Pi OS (any variant) already flashed
#   - SSH access as default user (usually 'pi')
#   - Internet connectivity
#
# What this script does:
#   1. Creates 'julian' user if it doesn't exist
#   2. Adds 'julian' user to sudo group
#   3. Installs minimal prerequisites (sudo, curl, ca-certificates, etc.)
#   4. Ensures OpenSSH server is installed and enabled
#   5. Optionally sets hostname
#   6. Optionally sets timezone
#   7. Optionally adds SSH public key to julian user
#
# After running this script, you can SSH as 'julian' and run prepare-rpi.sh
# =============================================================================

VERSION="1.0.0"
set -euo pipefail

# =============================================================================
# Configuration (can be overridden via command line)
# =============================================================================
HOSTNAME="${HOSTNAME:-}"
TIMEZONE="${TIMEZONE:-America/New_York}"
SSH_KEY_FILE="${SSH_KEY_FILE:-}"
AUTH_METHOD="${AUTH_METHOD:-key}"
USERNAME="julian"
DRY_RUN=false
INTERACTIVE=false

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

show_help() {
    cat << 'EOF'
Raspberry Pi Existing OS Preparation Script
============================================

This script prepares your Raspberry Pi with an existing OS installation for
the bootstrap process. It sets up the 'julian' user, installs prerequisites,
and optionally configures hostname, timezone, and SSH keys.

USAGE:
    sudo ./prep-existing-os.sh [OPTIONS]
    sudo ./prep-existing-os.sh --interactive

OPTIONS:
    --hostname NAME         Set the system hostname
                            Example: --hostname rpi1

    --timezone TZ           Set system timezone
                            Example: --timezone America/New_York
                            Run 'timedatectl list-timezones' to see options

    --auth-method METHOD    SSH authentication method (key or password)
                            Example: --auth-method password
                            Default: key

    --ssh-key PATH          Path to SSH public key file (for key auth method)
                            Example: --ssh-key ~/.ssh/id_ed25519.pub
                            Ignored if --auth-method password

    --interactive           Run in interactive mode with prompts

    --dry-run               Show what would be done without making changes

    --version, -v           Show version number

    --help, -h              Show this help message

EXAMPLES:
    # Basic setup (creates user and installs prerequisites):
    sudo ./prep-existing-os.sh

    # Full setup with hostname and SSH key:
    sudo ./prep-existing-os.sh \
        --hostname rpi1 \
        --auth-method key \
        --ssh-key ~/.ssh/id_ed25519.pub \
        --timezone America/New_York

    # Setup with password authentication:
    sudo ./prep-existing-os.sh \
        --hostname rpi1 \
        --auth-method password \
        --timezone America/New_York

    # Interactive mode (prompts for each option):
    sudo ./prep-existing-os.sh --interactive

    # Preview changes without applying:
    sudo ./prep-existing-os.sh --hostname rpi1 --dry-run

WHAT THIS SCRIPT DOES:
    1. Creates 'julian' user (if doesn't exist)
    2. Adds 'julian' to sudo group
    3. Installs prerequisites: sudo, curl, ca-certificates, python3, rsync, openssh-server
    4. Ensures SSH server is enabled
    5. Sets hostname (if specified)
    6. Sets timezone (if specified)
    7. Configures SSH authentication:
       - Key auth: Adds SSH public key to julian user (if --ssh-key specified)
       - Password auth: Sets password for julian user (prompts interactively)
                      and enables SSH password authentication

NEXT STEPS:
    After running this script, you can:
    1. SSH as 'julian' user: ssh julian@<pi-ip>
    2. Run the bootstrap script: sudo ./prepare-rpi.sh --hostname rpi1 ...

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
    CURRENT_HOSTNAME=$(hostname)
    read -p "Enter hostname [leave empty to skip, current: $CURRENT_HOSTNAME]: " input
    HOSTNAME="${input:-}"
    
    # Timezone
    CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "America/New_York")
    read -p "Enter timezone [$CURRENT_TZ]: " input
    TIMEZONE="${input:-$CURRENT_TZ}"
    
    # Auth Method
    echo ""
    echo "SSH Authentication Method:"
    echo "  1) key (public key authentication)"
    echo "  2) password (password authentication)"
    read -p "Choose auth method [1]: " input
    case "${input:-1}" in
        1|key|KEY)
            AUTH_METHOD="key"
            ;;
        2|password|PASSWORD)
            AUTH_METHOD="password"
            ;;
        *)
            AUTH_METHOD="key"
            ;;
    esac
    
    # SSH Key (if key auth)
    SSH_KEY_FILE=""
    if [[ "$AUTH_METHOD" == "key" ]]; then
        if [[ -f ~/.ssh/id_ed25519.pub ]]; then
            DEFAULT_KEY="~/.ssh/id_ed25519.pub"
        elif [[ -f ~/.ssh/id_rsa.pub ]]; then
            DEFAULT_KEY="~/.ssh/id_rsa.pub"
        else
            DEFAULT_KEY=""
        fi
        
        read -p "Enter SSH public key path (leave empty to skip) [$DEFAULT_KEY]: " input
        SSH_KEY_FILE="${input:-$DEFAULT_KEY}"
        
        # Expand ~ if present
        if [[ -n "$SSH_KEY_FILE" ]]; then
            SSH_KEY_FILE="${SSH_KEY_FILE/#\~/$HOME}"
        fi
    fi
    
    echo ""
    echo "=== Configuration Summary ==="
    echo "  Hostname:     ${HOSTNAME:-<not set>}"
    echo "  Timezone:     $TIMEZONE"
    echo "  Auth Method:  $AUTH_METHOD"
    [[ "$AUTH_METHOD" == "key" ]] && echo "  SSH Key:      ${SSH_KEY_FILE:-<not set>}"
    [[ "$AUTH_METHOD" == "password" ]] && echo "  Password:     <will be prompted during setup>"
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
            --timezone)
                TIMEZONE="$2"
                shift 2
                ;;
            --auth-method)
                AUTH_METHOD="$2"
                if [[ "$AUTH_METHOD" != "key" && "$AUTH_METHOD" != "password" ]]; then
                    log_error "Invalid auth method: $AUTH_METHOD (must be 'key' or 'password')"
                    exit 1
                fi
                shift 2
                ;;
            --ssh-key)
                SSH_KEY_FILE="$2"
                # Expand ~ if present
                SSH_KEY_FILE="${SSH_KEY_FILE/#\~/$HOME}"
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
            --version|-v)
                echo "prep-existing-os.sh version $VERSION"
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

create_user() {
    log_info "Ensuring '$USERNAME' user exists..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        if id "$USERNAME" &>/dev/null; then
            log_info "[DRY RUN] User '$USERNAME' already exists"
        else
            log_info "[DRY RUN] Would create user '$USERNAME'"
        fi
        return
    fi
    
    if id "$USERNAME" &>/dev/null; then
        log_info "User '$USERNAME' already exists"
    else
        log_info "Creating user '$USERNAME'..."
        useradd -m -s /bin/bash "$USERNAME"
        log_success "User '$USERNAME' created"
    fi
    
    # Set password based on auth method
    if [[ "$AUTH_METHOD" == "password" ]]; then
        set_password
    elif [[ "$AUTH_METHOD" == "key" ]]; then
        # Set a random password (will be locked if SSH key is added)
        PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        echo "$USERNAME:$PASSWORD" | chpasswd
        # If SSH key is added later, password won't be needed
    fi
    
    # Ensure user is in sudo group
    if groups "$USERNAME" | grep -q "\bsudo\b"; then
        log_info "User '$USERNAME' already in sudo group"
    else
        usermod -aG sudo "$USERNAME"
        log_success "Added '$USERNAME' to sudo group"
    fi
    
    # Ensure sudoers allows passwordless sudo (common on Raspberry Pi OS)
    if [[ -f /etc/sudoers.d/010_pi-nopasswd ]] && ! grep -q "^$USERNAME" /etc/sudoers.d/010_pi-nopasswd 2>/dev/null; then
        echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers.d/010_julian-nopasswd
        chmod 0440 /etc/sudoers.d/010_julian-nopasswd
        log_success "Configured passwordless sudo for '$USERNAME'"
    fi
}

set_password() {
    log_info "Setting password for '$USERNAME' user..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would prompt for password for '$USERNAME' user"
        return
    fi
    
    # Prompt for password (twice for confirmation)
    while true; do
        read -sp "Enter password for '$USERNAME' user: " PASSWORD
        echo ""
        read -sp "Confirm password: " PASSWORD_CONFIRM
        echo ""
        
        if [[ -z "$PASSWORD" ]]; then
            log_error "Password cannot be empty"
            continue
        fi
        
        if [[ "$PASSWORD" != "$PASSWORD_CONFIRM" ]]; then
            log_error "Passwords do not match. Please try again."
            continue
        fi
        
        break
    done
    
    # Set the password
    echo "$USERNAME:$PASSWORD" | chpasswd
    unset PASSWORD
    unset PASSWORD_CONFIRM
    log_success "Password set for '$USERNAME' user"
}

enable_password_auth() {
    log_info "Ensuring SSH password authentication is enabled..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would enable SSH password authentication in sshd_config"
        return
    fi
    
    SSHD_CONFIG="/etc/ssh/sshd_config"
    
    # Backup sshd_config
    if [[ ! -f "${SSHD_CONFIG}.backup" ]]; then
        cp "$SSHD_CONFIG" "${SSHD_CONFIG}.backup"
    fi
    
    # Enable password authentication (set to yes)
    if grep -q "^PasswordAuthentication" "$SSHD_CONFIG"; then
        # Replace existing setting
        sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' "$SSHD_CONFIG"
    elif grep -q "^#PasswordAuthentication" "$SSHD_CONFIG"; then
        # Uncomment and set to yes
        sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' "$SSHD_CONFIG"
    else
        # Add new setting
        echo "PasswordAuthentication yes" >> "$SSHD_CONFIG"
    fi
    
    # Disable password authentication override (if present)
    if grep -q "^Match" "$SSHD_CONFIG"; then
        # Check for Match blocks that might override password auth
        sed -i '/^Match/,/^$/ s/.*PasswordAuthentication.*/# &/' "$SSHD_CONFIG" || true
    fi
    
    # Restart SSH service to apply changes
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true
    
    log_success "SSH password authentication enabled"
}

install_prerequisites() {
    log_info "Installing prerequisites..."
    
    PACKAGES=(
        sudo
        curl
        ca-certificates
        python3
        python3-pip
        rsync
        openssh-server
    )
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would install: ${PACKAGES[*]}"
        return
    fi
    
    apt-get update
    apt-get install -y "${PACKAGES[@]}"
    
    log_success "Prerequisites installed"
}

ensure_ssh_enabled() {
    log_info "Ensuring SSH server is enabled..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would enable and start ssh service"
        return
    fi
    
    systemctl enable ssh 2>/dev/null || systemctl enable sshd 2>/dev/null || true
    systemctl start ssh 2>/dev/null || systemctl start sshd 2>/dev/null || true
    
    log_success "SSH server enabled and started"
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

add_ssh_key() {
    if [[ -z "$SSH_KEY_FILE" ]]; then
        return
    fi
    
    if [[ ! -f "$SSH_KEY_FILE" ]]; then
        log_warning "SSH key file not found: $SSH_KEY_FILE"
        return
    fi
    
    log_info "Adding SSH key from $SSH_KEY_FILE to $USERNAME user..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would add SSH key from $SSH_KEY_FILE to ~$USERNAME/.ssh/authorized_keys"
        return
    fi
    
    # Create .ssh directory
    mkdir -p "/home/$USERNAME/.ssh"
    chmod 700 "/home/$USERNAME/.ssh"
    
    # Add key to authorized_keys if not already present
    KEY_CONTENT=$(cat "$SSH_KEY_FILE")
    if [[ -f "/home/$USERNAME/.ssh/authorized_keys" ]]; then
        if grep -Fxq "$KEY_CONTENT" "/home/$USERNAME/.ssh/authorized_keys"; then
            log_info "SSH key already present in authorized_keys"
            return
        fi
    fi
    
    echo "$KEY_CONTENT" >> "/home/$USERNAME/.ssh/authorized_keys"
    chmod 600 "/home/$USERNAME/.ssh/authorized_keys"
    chown -R "$USERNAME:$USERNAME" "/home/$USERNAME/.ssh"
    
    log_success "SSH key added to $USERNAME user"
}

print_summary() {
    echo ""
    echo "============================================================================="
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}DRY RUN Complete - No changes were made${NC}"
    else
        echo -e "${GREEN}OS Preparation Complete!${NC}"
    fi
    echo "============================================================================="
    echo ""
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "The following changes WOULD be made:"
    else
        echo "The following changes were made:"
    fi
    
    echo "  [x] User '$USERNAME' created and added to sudo group"
    echo "  [x] Prerequisites installed (sudo, curl, ca-certificates, python3, rsync, openssh-server)"
    echo "  [x] SSH server enabled and started"
    [[ -n "$HOSTNAME" ]] && echo "  [x] Hostname set to: $HOSTNAME"
    echo "  [x] Timezone set to: $TIMEZONE"
    if [[ "$AUTH_METHOD" == "key" ]]; then
        [[ -n "$SSH_KEY_FILE" && -f "$SSH_KEY_FILE" ]] && echo "  [x] SSH key added to $USERNAME user"
    elif [[ "$AUTH_METHOD" == "password" ]]; then
        echo "  [x] Password authentication configured for $USERNAME user"
        echo "  [x] SSH password authentication enabled"
    fi
    echo ""
    
    if [[ "$DRY_RUN" != "true" ]]; then
        echo -e "${GREEN}Next Steps:${NC}"
        echo ""
        echo "1. Test SSH access as '$USERNAME' user:"
        if [[ "$AUTH_METHOD" == "password" ]]; then
            echo "   ssh $USERNAME@<pi-ip-address>"
            echo "   (You will be prompted for the password you set)"
        else
            echo "   ssh $USERNAME@<pi-ip-address>"
            echo "   (Using SSH key authentication)"
        fi
        echo ""
        echo "2. Copy the bootstrap script to the Pi:"
        echo "   scp bootstrap/scripts/prepare-rpi.sh $USERNAME@<pi-ip>:~/"
        echo ""
        echo "3. SSH into the Pi and run the bootstrap script:"
        echo "   ssh $USERNAME@<pi-ip>"
        echo "   sudo ./prepare-rpi.sh --hostname rpi1 --ip 192.168.1.101/24"
        echo ""
        echo "Or use the port-to-rpi.ps1 script from your workstation to automate steps 2-3."
        echo ""
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================================================="
    echo "Raspberry Pi Existing OS Preparation Script v$VERSION"
    echo "============================================================================="
    echo ""
    
    parse_args "$@"
    
    # Check requirements
    check_root
    
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
    create_user
    install_prerequisites
    ensure_ssh_enabled
    
    # Configure authentication method
    if [[ "$AUTH_METHOD" == "password" ]]; then
        enable_password_auth
    elif [[ "$AUTH_METHOD" == "key" ]]; then
        add_ssh_key
    fi
    
    set_hostname
    set_timezone
    
    print_summary
}

main "$@"