#!/bin/bash
# =============================================================================
# k3s Agent Recovery Script
# =============================================================================
# Monitors k3s-agent health and handles reconnection to control plane.
# Useful for dynamic IP environments where control plane IP may change.
#
# Features:
# - Periodic health check of k3s-agent service
# - mDNS resolution of control plane hostname
# - Automatic reconnection when control plane IP changes
# - Integration with systemd for service management
#
# Environment variables:
#   CONTROL_PLANE_HOSTNAME - Hostname of control plane (default: k8s-control)
#   K3S_TOKEN_FILE - Path to k3s token file
#   CHECK_INTERVAL - Interval between health checks in seconds (default: 30)
#   MAX_RETRIES - Maximum reconnection attempts (default: 5)
#
# Usage:
#   ./k3s-agent-recovery.sh
#   CONTROL_PLANE_HOSTNAME=k8s-control ./k3s-agent-recovery.sh
# =============================================================================

set -euo pipefail

# Configuration
CONTROL_PLANE_HOSTNAME="${CONTROL_PLANE_HOSTNAME:-k8s-control}"
K3S_TOKEN_FILE="${K3S_TOKEN_FILE:-/etc/rancher/k3s/k3s-token}"
K3S_AGENT_ENV="/etc/rancher/k3s/k3s-agent.env"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
MAX_RETRIES="${MAX_RETRIES:-5}"
LOG_TAG="k3s-agent-recovery"

# State tracking
CURRENT_CONTROL_PLANE_IP=""
LAST_KNOWN_IP=""
CONSECUTIVE_FAILURES=0

# =============================================================================
# Logging Functions
# =============================================================================

log_info() {
    echo "[INFO] $1"
    logger -t "$LOG_TAG" "INFO: $1" || true
}

log_warn() {
    echo "[WARN] $1" >&2
    logger -t "$LOG_TAG" "WARN: $1" || true
}

log_error() {
    echo "[ERROR] $1" >&2
    logger -t "$LOG_TAG" "ERROR: $1" || true
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo "[DEBUG] $1"
    fi
}

# =============================================================================
# mDNS Resolution
# =============================================================================

resolve_control_plane() {
    local hostname="$1"
    local fqdn="${hostname}.local"
    local ip=""
    
    log_debug "Resolving control plane: $fqdn"
    
    # Method 1: avahi-resolve (most reliable for mDNS)
    if command -v avahi-resolve &>/dev/null; then
        ip=$(avahi-resolve -n "$fqdn" 2>/dev/null | awk '{print $2}' | head -1)
        if [[ -n "$ip" ]]; then
            log_debug "Resolved via avahi-resolve: $ip"
            echo "$ip"
            return 0
        fi
    fi
    
    # Method 2: getent hosts (uses nsswitch.conf)
    ip=$(getent hosts "$fqdn" 2>/dev/null | awk '{print $1}' | head -1)
    if [[ -n "$ip" ]]; then
        log_debug "Resolved via getent: $ip"
        echo "$ip"
        return 0
    fi
    
    # Method 3: nslookup
    ip=$(nslookup "$fqdn" 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)
    if [[ -n "$ip" ]]; then
        log_debug "Resolved via nslookup: $ip"
        echo "$ip"
        return 0
    fi
    
    # Method 4: dig with multicast
    if command -v dig &>/dev/null; then
        ip=$(dig +short @224.0.0.251 -p 5353 "$fqdn" 2>/dev/null | head -1)
        if [[ -n "$ip" ]]; then
            log_debug "Resolved via dig mDNS: $ip"
            echo "$ip"
            return 0
        fi
    fi
    
    log_warn "Failed to resolve $fqdn"
    return 1
}

# =============================================================================
# Health Check Functions
# =============================================================================

check_k3s_agent_health() {
    # Check if k3s-agent service is running
    if ! systemctl is-active --quiet k3s-agent; then
        log_warn "k3s-agent service is not running"
        return 1
    fi
    
    # Check if kubelet is responsive
    if ! curl -sk --max-time 5 "https://localhost:10250/healthz" &>/dev/null; then
        log_warn "Kubelet health check failed"
        return 1
    fi
    
    return 0
}

check_control_plane_connectivity() {
    local ip="$1"
    
    # Check if we can reach the API server
    if ! timeout 5 bash -c "echo >/dev/tcp/$ip/6443" 2>/dev/null; then
        log_warn "Cannot reach control plane API at $ip:6443"
        return 1
    fi
    
    return 0
}

get_current_server_url() {
    # Get the currently configured server URL from k3s-agent
    if [[ -f "$K3S_AGENT_ENV" ]]; then
        grep "K3S_URL" "$K3S_AGENT_ENV" 2>/dev/null | cut -d= -f2 | tr -d '"' | sed 's|https://||; s|:6443||'
    elif systemctl show k3s-agent -p Environment --value 2>/dev/null | grep -q "K3S_URL"; then
        systemctl show k3s-agent -p Environment --value 2>/dev/null | grep -o 'K3S_URL=[^ ]*' | cut -d= -f2 | tr -d '"' | sed 's|https://||; s|:6443||'
    else
        # Try to extract from process
        ps aux | grep k3s-agent | grep -o 'K3S_URL=[^ ]*' | head -1 | cut -d= -f2 | tr -d '"' | sed 's|https://||; s|:6443||'
    fi
}

# =============================================================================
# Recovery Functions
# =============================================================================

update_server_url() {
    local new_ip="$1"
    local new_url="https://${new_ip}:6443"
    
    log_info "Updating k3s-agent server URL to $new_url"
    
    # Update environment file if it exists
    if [[ -f "$K3S_AGENT_ENV" ]]; then
        sed -i "s|K3S_URL=.*|K3S_URL=\"$new_url\"|g" "$K3S_AGENT_ENV"
    else
        # Create environment file
        echo "K3S_URL=\"$new_url\"" > "$K3S_AGENT_ENV"
        if [[ -f "$K3S_TOKEN_FILE" ]]; then
            echo "K3S_TOKEN=\"$(cat "$K3S_TOKEN_FILE")\"" >> "$K3S_AGENT_ENV"
        fi
    fi
    
    return 0
}

restart_k3s_agent() {
    log_info "Restarting k3s-agent service..."
    
    # Stop the agent
    systemctl stop k3s-agent || true
    sleep 2
    
    # Start the agent
    if systemctl start k3s-agent; then
        log_info "k3s-agent restarted successfully"
        return 0
    else
        log_error "Failed to restart k3s-agent"
        return 1
    fi
}

attempt_reconnection() {
    local new_ip="$1"
    local retry=0
    
    while [[ $retry -lt $MAX_RETRIES ]]; do
        log_info "Reconnection attempt $((retry + 1))/$MAX_RETRIES"
        
        # Update server URL
        update_server_url "$new_ip"
        
        # Restart agent
        if restart_k3s_agent; then
            sleep 10  # Wait for agent to initialize
            
            # Verify health
            if check_k3s_agent_health; then
                log_info "Successfully reconnected to control plane at $new_ip"
                return 0
            fi
        fi
        
        ((retry++))
        sleep 10
    done
    
    log_error "Failed to reconnect after $MAX_RETRIES attempts"
    return 1
}

# =============================================================================
# Main Loop
# =============================================================================

main() {
    log_info "Starting k3s-agent recovery service"
    log_info "Control plane hostname: $CONTROL_PLANE_HOSTNAME"
    log_info "Check interval: ${CHECK_INTERVAL}s"
    
    # Initial resolution
    CURRENT_CONTROL_PLANE_IP=$(resolve_control_plane "$CONTROL_PLANE_HOSTNAME")
    if [[ -z "$CURRENT_CONTROL_PLANE_IP" ]]; then
        log_error "Cannot resolve control plane hostname. Waiting..."
    else
        log_info "Control plane resolved to: $CURRENT_CONTROL_PLANE_IP"
        LAST_KNOWN_IP="$CURRENT_CONTROL_PLANE_IP"
    fi
    
    while true; do
        # Resolve control plane (detect IP changes)
        new_ip=$(resolve_control_plane "$CONTROL_PLANE_HOSTNAME")
        
        if [[ -n "$new_ip" ]]; then
            # Check for IP change
            if [[ -n "$LAST_KNOWN_IP" && "$new_ip" != "$LAST_KNOWN_IP" ]]; then
                log_warn "Control plane IP changed: $LAST_KNOWN_IP -> $new_ip"
                
                # Attempt reconnection with new IP
                if attempt_reconnection "$new_ip"; then
                    LAST_KNOWN_IP="$new_ip"
                    CONSECUTIVE_FAILURES=0
                else
                    ((CONSECUTIVE_FAILURES++))
                fi
            else
                LAST_KNOWN_IP="$new_ip"
            fi
            
            # Check agent health
            if check_k3s_agent_health; then
                log_debug "k3s-agent is healthy"
                CONSECUTIVE_FAILURES=0
            else
                ((CONSECUTIVE_FAILURES++))
                log_warn "k3s-agent health check failed (failures: $CONSECUTIVE_FAILURES)"
                
                if [[ $CONSECUTIVE_FAILURES -ge 3 ]]; then
                    log_info "Attempting recovery..."
                    
                    # Check if control plane is reachable
                    if check_control_plane_connectivity "$new_ip"; then
                        # Control plane is up, try restarting agent
                        if restart_k3s_agent; then
                            sleep 10
                            if check_k3s_agent_health; then
                                CONSECUTIVE_FAILURES=0
                                log_info "Recovery successful"
                            fi
                        fi
                    else
                        log_warn "Control plane not reachable, will retry later"
                    fi
                fi
            fi
        else
            log_warn "Cannot resolve control plane hostname"
            ((CONSECUTIVE_FAILURES++))
        fi
        
        # Sleep until next check
        sleep "$CHECK_INTERVAL"
    done
}

# Handle signals
trap 'log_info "Received shutdown signal"; exit 0' SIGTERM SIGINT

main "$@"
