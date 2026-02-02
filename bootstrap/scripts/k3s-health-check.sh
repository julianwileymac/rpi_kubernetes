#!/bin/bash
# =============================================================================
# k3s Cluster Health Check Script
# =============================================================================
# Performs comprehensive health checks on the k3s cluster:
# - Control plane API availability
# - Node status and readiness
# - Critical pod health
# - Worker node connectivity
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#   2 - Configuration error
#
# Usage:
#   ./k3s-health-check.sh [--verbose] [--json]
#
# This script is called by k3s-cluster-health.service
# =============================================================================

set -euo pipefail

# Configuration
KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
CLUSTER_CONFIG="${CLUSTER_CONFIG:-/home/julia/rpi_kubernetes/cluster-config.yaml}"
VERBOSE="${VERBOSE:-false}"
OUTPUT_JSON="${OUTPUT_JSON:-false}"
LOG_TAG="k3s-health"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose|-v)
            VERBOSE="true"
            shift
            ;;
        --json|-j)
            OUTPUT_JSON="true"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Logging functions
log_info() {
    if [[ "$OUTPUT_JSON" != "true" ]]; then
        echo "[INFO] $1"
        logger -t "$LOG_TAG" "INFO: $1"
    fi
}

log_warn() {
    if [[ "$OUTPUT_JSON" != "true" ]]; then
        echo "[WARN] $1" >&2
        logger -t "$LOG_TAG" "WARN: $1"
    fi
}

log_error() {
    if [[ "$OUTPUT_JSON" != "true" ]]; then
        echo "[ERROR] $1" >&2
        logger -t "$LOG_TAG" "ERROR: $1"
    fi
}

log_debug() {
    if [[ "$VERBOSE" == "true" && "$OUTPUT_JSON" != "true" ]]; then
        echo "[DEBUG] $1"
    fi
}

# Health check results
declare -A RESULTS
OVERALL_STATUS="healthy"
TIMESTAMP=$(date -Iseconds)

# =============================================================================
# Check Functions
# =============================================================================

check_kubeconfig() {
    log_debug "Checking kubeconfig at $KUBECONFIG"
    
    if [[ ! -f "$KUBECONFIG" ]]; then
        RESULTS["kubeconfig"]="missing"
        OVERALL_STATUS="unhealthy"
        log_error "Kubeconfig not found: $KUBECONFIG"
        return 1
    fi
    
    RESULTS["kubeconfig"]="present"
    return 0
}

check_api_server() {
    log_debug "Checking k3s API server"
    
    if kubectl --kubeconfig="$KUBECONFIG" cluster-info &>/dev/null; then
        RESULTS["api_server"]="healthy"
        log_info "API server is healthy"
        return 0
    else
        RESULTS["api_server"]="unhealthy"
        OVERALL_STATUS="unhealthy"
        log_error "API server is not responding"
        return 1
    fi
}

check_nodes() {
    log_debug "Checking node status"
    
    local node_output
    node_output=$(kubectl --kubeconfig="$KUBECONFIG" get nodes -o json 2>/dev/null) || {
        RESULTS["nodes"]="error"
        OVERALL_STATUS="unhealthy"
        log_error "Failed to get node list"
        return 1
    }
    
    local total_nodes ready_nodes not_ready_nodes
    total_nodes=$(echo "$node_output" | jq '.items | length')
    ready_nodes=$(echo "$node_output" | jq '[.items[] | select(.status.conditions[] | select(.type=="Ready" and .status=="True"))] | length')
    not_ready_nodes=$((total_nodes - ready_nodes))
    
    RESULTS["nodes_total"]="$total_nodes"
    RESULTS["nodes_ready"]="$ready_nodes"
    RESULTS["nodes_not_ready"]="$not_ready_nodes"
    
    if [[ "$not_ready_nodes" -gt 0 ]]; then
        OVERALL_STATUS="degraded"
        log_warn "$not_ready_nodes node(s) not ready"
        
        # List not ready nodes
        local not_ready_list
        not_ready_list=$(echo "$node_output" | jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | .metadata.name')
        RESULTS["not_ready_nodes"]="$not_ready_list"
        
        for node in $not_ready_list; do
            log_warn "Node not ready: $node"
        done
    else
        log_info "All $total_nodes nodes are ready"
    fi
    
    return 0
}

check_system_pods() {
    log_debug "Checking system pods"
    
    local namespaces=("kube-system" "metallb-system" "ingress" "cert-manager")
    local unhealthy_pods=0
    
    for ns in "${namespaces[@]}"; do
        local pod_status
        pod_status=$(kubectl --kubeconfig="$KUBECONFIG" get pods -n "$ns" -o json 2>/dev/null) || continue
        
        local ns_unhealthy
        ns_unhealthy=$(echo "$pod_status" | jq '[.items[] | select(.status.phase != "Running" and .status.phase != "Succeeded")] | length')
        
        if [[ "$ns_unhealthy" -gt 0 ]]; then
            unhealthy_pods=$((unhealthy_pods + ns_unhealthy))
            log_warn "$ns_unhealthy unhealthy pod(s) in namespace $ns"
        fi
    done
    
    RESULTS["system_pods_unhealthy"]="$unhealthy_pods"
    
    if [[ "$unhealthy_pods" -gt 0 ]]; then
        OVERALL_STATUS="degraded"
        return 1
    fi
    
    log_info "All system pods are healthy"
    return 0
}

check_worker_ssh() {
    log_debug "Checking worker SSH connectivity"
    
    # Try to get worker IPs from cluster config or nodes
    local worker_ips=()
    
    # Method 1: From cluster-config.yaml
    if [[ -f "$CLUSTER_CONFIG" ]]; then
        while IFS= read -r ip; do
            [[ -n "$ip" ]] && worker_ips+=("$ip")
        done < <(grep -A2 "workers:" "$CLUSTER_CONFIG" | grep "ip:" | awk '{print $2}' 2>/dev/null || true)
    fi
    
    # Method 2: From Kubernetes nodes (if no config)
    if [[ ${#worker_ips[@]} -eq 0 ]]; then
        while IFS= read -r ip; do
            [[ -n "$ip" ]] && worker_ips+=("$ip")
        done < <(kubectl --kubeconfig="$KUBECONFIG" get nodes -l 'node-role.kubernetes.io/control-plane notin ()' -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null | tr ' ' '\n' || true)
    fi
    
    if [[ ${#worker_ips[@]} -eq 0 ]]; then
        RESULTS["worker_ssh"]="no_workers"
        log_debug "No worker IPs found to check"
        return 0
    fi
    
    local reachable=0 unreachable=0
    for ip in "${worker_ips[@]}"; do
        if timeout 2 bash -c "echo >/dev/tcp/$ip/22" 2>/dev/null; then
            ((reachable++))
            log_debug "Worker $ip: SSH reachable"
        else
            ((unreachable++))
            log_warn "Worker $ip: SSH unreachable"
        fi
    done
    
    RESULTS["workers_ssh_reachable"]="$reachable"
    RESULTS["workers_ssh_unreachable"]="$unreachable"
    
    if [[ "$unreachable" -gt 0 ]]; then
        OVERALL_STATUS="degraded"
        return 1
    fi
    
    log_info "All $reachable workers are SSH reachable"
    return 0
}

check_etcd() {
    log_debug "Checking etcd health (k3s embedded)"
    
    # k3s uses embedded etcd/sqlite, check via kubectl
    if kubectl --kubeconfig="$KUBECONFIG" get --raw='/readyz' &>/dev/null; then
        RESULTS["etcd"]="healthy"
        log_info "k3s datastore is healthy"
        return 0
    else
        RESULTS["etcd"]="unhealthy"
        OVERALL_STATUS="unhealthy"
        log_error "k3s datastore health check failed"
        return 1
    fi
}

check_disk_space() {
    log_debug "Checking disk space"
    
    local storage_path="${STORAGE_MOUNT:-/mnt/storage}"
    local root_usage data_usage
    
    root_usage=$(df -h / | awk 'NR==2 {gsub(/%/,""); print $5}')
    RESULTS["disk_root_usage"]="${root_usage}%"
    
    if [[ -d "$storage_path" ]]; then
        data_usage=$(df -h "$storage_path" | awk 'NR==2 {gsub(/%/,""); print $5}')
        RESULTS["disk_data_usage"]="${data_usage}%"
    fi
    
    if [[ "$root_usage" -gt 90 ]]; then
        OVERALL_STATUS="degraded"
        log_warn "Root disk usage is high: ${root_usage}%"
        return 1
    fi
    
    log_info "Disk usage is acceptable (root: ${root_usage}%)"
    return 0
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_info "Starting k3s cluster health check"
    log_debug "Timestamp: $TIMESTAMP"
    
    # Run all checks
    check_kubeconfig || true
    check_api_server || true
    check_etcd || true
    check_nodes || true
    check_system_pods || true
    check_worker_ssh || true
    check_disk_space || true
    
    # Set overall status
    RESULTS["overall_status"]="$OVERALL_STATUS"
    RESULTS["timestamp"]="$TIMESTAMP"
    
    # Output results
    if [[ "$OUTPUT_JSON" == "true" ]]; then
        # JSON output
        echo "{"
        local first=true
        for key in "${!RESULTS[@]}"; do
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo ","
            fi
            echo -n "  \"$key\": \"${RESULTS[$key]}\""
        done
        echo ""
        echo "}"
    else
        # Summary output
        echo ""
        echo "=========================================="
        echo "Cluster Health Check Summary"
        echo "=========================================="
        echo "Timestamp:    $TIMESTAMP"
        echo "Status:       $OVERALL_STATUS"
        echo ""
        echo "Nodes:        ${RESULTS[nodes_ready]:-0}/${RESULTS[nodes_total]:-0} ready"
        echo "System Pods:  ${RESULTS[system_pods_unhealthy]:-0} unhealthy"
        echo "Workers SSH:  ${RESULTS[workers_ssh_reachable]:-0} reachable, ${RESULTS[workers_ssh_unreachable]:-0} unreachable"
        echo "Disk (root):  ${RESULTS[disk_root_usage]:-unknown}"
        echo "=========================================="
    fi
    
    # Exit with appropriate code
    case "$OVERALL_STATUS" in
        "healthy")
            log_info "Health check completed: HEALTHY"
            exit 0
            ;;
        "degraded")
            log_warn "Health check completed: DEGRADED"
            exit 0  # Don't fail for degraded, just warn
            ;;
        "unhealthy")
            log_error "Health check completed: UNHEALTHY"
            exit 1
            ;;
        *)
            exit 2
            ;;
    esac
}

main "$@"
