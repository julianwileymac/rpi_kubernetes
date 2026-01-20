#!/bin/bash
# =============================================================================
# Control Panel Accessibility Verification Script
# =============================================================================
# Verifies that the management control panel is properly deployed and accessible.
#
# Usage:
#   ./verify-control-panel.sh [OPTIONS]
#
# Options:
#   --namespace NAMESPACE    Kubernetes namespace (default: management)
#   --host HOST             Hostname for ingress (default: control.local)
#   --verbose               Enable verbose output
#   --skip-ingress          Skip ingress verification
#   --skip-loadbalancer     Skip LoadBalancer verification
# =============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-management}"
HOST="${HOST:-control.local}"
VERBOSE="${VERBOSE:-false}"
SKIP_INGRESS="${SKIP_INGRESS:-false}"
SKIP_LOADBALANCER="${SKIP_LOADBALANCER:-false}"

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

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --host)
                HOST="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE="true"
                shift
                ;;
            --skip-ingress)
                SKIP_INGRESS="true"
                shift
                ;;
            --skip-loadbalancer)
                SKIP_LOADBALANCER="true"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
}

# Check if pod is running
check_pod_status() {
    local pod_name="$1"
    log_info "Checking pod status: $pod_name"
    
    local status=$(kubectl get pod -n "$NAMESPACE" -l app="$pod_name" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")
    
    if [[ "$status" == "Running" ]]; then
        log_success "Pod $pod_name is running"
        return 0
    elif [[ "$status" == "NotFound" ]]; then
        log_error "Pod $pod_name not found"
        return 1
    else
        log_warning "Pod $pod_name status: $status"
        return 1
    fi
}

# Check service endpoints
check_service_endpoints() {
    local service_name="$1"
    log_info "Checking service endpoints: $service_name"
    
    local endpoints=$(kubectl get endpoints -n "$NAMESPACE" "$service_name" -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null || echo "")
    
    if [[ -z "$endpoints" ]]; then
        log_error "Service $service_name has no endpoints"
        return 1
    else
        log_success "Service $service_name has endpoints: $endpoints"
        return 0
    fi
}

# Check ingress controller
check_ingress_controller() {
    log_info "Checking ingress-nginx controller"
    
    local controller_pod=$(kubectl get pods -n ingress -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$controller_pod" ]]; then
        log_error "ingress-nginx controller not found"
        return 1
    fi
    
    local controller_status=$(kubectl get pod -n ingress "$controller_pod" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    
    if [[ "$controller_status" == "Running" ]]; then
        log_success "ingress-nginx controller is running"
        
        # Check LoadBalancer IP
        local lb_ip=$(kubectl get svc -n ingress ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        if [[ -n "$lb_ip" ]]; then
            log_success "ingress-nginx LoadBalancer IP: $lb_ip"
        else
            log_warning "ingress-nginx LoadBalancer IP not assigned yet"
        fi
        return 0
    else
        log_error "ingress-nginx controller status: $controller_status"
        return 1
    fi
}

# Check ingress resource
check_ingress() {
    log_info "Checking ingress resource: management-ui"
    
    local ingress_exists=$(kubectl get ingress -n "$NAMESPACE" management-ui -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$ingress_exists" ]]; then
        log_error "Ingress management-ui not found"
        return 1
    fi
    
    log_success "Ingress management-ui exists"
    
    # Check ingress class
    local ingress_class=$(kubectl get ingress -n "$NAMESPACE" management-ui -o jsonpath='{.spec.ingressClassName}' 2>/dev/null || echo "")
    if [[ "$ingress_class" == "nginx" ]]; then
        log_success "Ingress uses correct ingress class: nginx"
    else
        log_warning "Ingress class: $ingress_class (expected: nginx)"
    fi
    
    # Check ingress address
    local ingress_address=$(kubectl get ingress -n "$NAMESPACE" management-ui -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$ingress_address" ]]; then
        log_success "Ingress address: $ingress_address"
    else
        log_warning "Ingress address not assigned yet"
    fi
    
    return 0
}

# Test ingress connectivity
test_ingress_connectivity() {
    log_info "Testing ingress connectivity to $HOST"
    
    # Get ingress controller LoadBalancer IP
    local ingress_ip=$(kubectl get svc -n ingress ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    
    if [[ -z "$ingress_ip" ]]; then
        log_warning "Cannot test ingress connectivity: LoadBalancer IP not available"
        return 1
    fi
    
    # Test with curl
    if command -v curl &> /dev/null; then
        log_verbose "Testing http://$HOST via ingress IP $ingress_ip"
        
        # Add host header for testing
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            --resolve "$HOST:80:$ingress_ip" \
            --max-time 10 \
            "http://$HOST/" || echo "000")
        
        if [[ "$http_code" == "200" ]] || [[ "$http_code" == "301" ]] || [[ "$http_code" == "302" ]]; then
            log_success "Ingress connectivity test passed (HTTP $http_code)"
            return 0
        else
            log_warning "Ingress connectivity test returned HTTP $http_code"
            return 1
        fi
    else
        log_warning "curl not available, skipping connectivity test"
        return 1
    fi
}

# Check LoadBalancer service
check_loadbalancer_service() {
    log_info "Checking LoadBalancer service: management-ui-external"
    
    local lb_exists=$(kubectl get svc -n "$NAMESPACE" management-ui-external -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$lb_exists" ]]; then
        log_error "LoadBalancer service management-ui-external not found"
        return 1
    fi
    
    log_success "LoadBalancer service exists"
    
    # Check LoadBalancer IP
    local lb_ip=$(kubectl get svc -n "$NAMESPACE" management-ui-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    
    if [[ -n "$lb_ip" ]]; then
        log_success "LoadBalancer IP: $lb_ip"
        
        # Test connectivity
        if command -v curl &> /dev/null && [[ "$SKIP_LOADBALANCER" != "true" ]]; then
            log_info "Testing LoadBalancer connectivity on port 8080"
            local http_code=$(curl -s -o /dev/null -w "%{http_code}" \
                --max-time 10 \
                "http://$lb_ip:8080/" || echo "000")
            
            if [[ "$http_code" == "200" ]] || [[ "$http_code" == "301" ]] || [[ "$http_code" == "302" ]]; then
                log_success "LoadBalancer connectivity test passed (HTTP $http_code)"
            else
                log_warning "LoadBalancer connectivity test returned HTTP $http_code"
            fi
        fi
        
        return 0
    else
        log_warning "LoadBalancer IP not assigned yet (may take a few minutes)"
        return 1
    fi
}

# Display access information
display_access_info() {
    echo ""
    log_info "=== Access Information ==="
    
    # Ingress access
    local ingress_ip=$(kubectl get svc -n ingress ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$ingress_ip" ]]; then
        echo ""
        log_info "Ingress Access:"
        echo "  URL: http://$HOST"
        echo "  Direct IP: http://$ingress_ip (add Host header: $HOST)"
        echo ""
        log_info "To access via ingress, ensure '$HOST' resolves to $ingress_ip"
        log_info "Add to /etc/hosts: $ingress_ip  $HOST"
    fi
    
    # LoadBalancer access
    local lb_ip=$(kubectl get svc -n "$NAMESPACE" management-ui-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$lb_ip" ]]; then
        echo ""
        log_info "LoadBalancer Access:"
        echo "  URL: http://$lb_ip:8080"
        echo ""
    fi
    
    # Pod access (for debugging)
    local pod_name=$(kubectl get pod -n "$NAMESPACE" -l app=management-ui -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$pod_name" ]]; then
        echo ""
        log_info "Debug Access (port-forward):"
        echo "  kubectl port-forward -n $NAMESPACE $pod_name 3000:3000"
        echo "  Then access: http://localhost:3000"
    fi
    echo ""
}

# Main function
main() {
    parse_args "$@"
    check_kubectl
    
    log_info "Verifying control panel accessibility"
    log_info "Namespace: $NAMESPACE"
    log_info "Host: $HOST"
    echo ""
    
    local errors=0
    
    # Check UI pod
    if ! check_pod_status "management-ui"; then
        errors=$((errors + 1))
    fi
    
    # Check API pod
    if ! check_pod_status "management-api"; then
        errors=$((errors + 1))
    fi
    
    # Check UI service endpoints
    if ! check_service_endpoints "management-ui"; then
        errors=$((errors + 1))
    fi
    
    # Check API service endpoints
    if ! check_service_endpoints "management-api"; then
        errors=$((errors + 1))
    fi
    
    # Check ingress controller
    if ! check_ingress_controller; then
        errors=$((errors + 1))
    fi
    
    # Check ingress resource
    if [[ "$SKIP_INGRESS" != "true" ]]; then
        if check_ingress; then
            test_ingress_connectivity || errors=$((errors + 1))
        else
            errors=$((errors + 1))
        fi
    fi
    
    # Check LoadBalancer service
    if [[ "$SKIP_LOADBALANCER" != "true" ]]; then
        check_loadbalancer_service || errors=$((errors + 1))
    fi
    
    # Display access information
    display_access_info
    
    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        log_success "All checks passed!"
        exit 0
    else
        log_error "Found $errors issue(s). See above for details."
        exit 1
    fi
}

# Run main function
main "$@"
