#!/usr/bin/env bash
# =============================================================================
# Build and Import Management Container Images into k3s
# =============================================================================
# Version: 1.0.0
#
# Builds the management backend (FastAPI) and frontend (Next.js) Docker images
# and imports them into k3s's containerd runtime so pods can use them with
# imagePullPolicy: IfNotPresent.
#
# Usage:
#   ./build-management.sh                      # Build both and import
#   ./build-management.sh --backend-only       # Build backend only
#   ./build-management.sh --frontend-only      # Build frontend only
#   ./build-management.sh --no-restart         # Build without restarting pods
#   ./build-management.sh --repo-dir /path     # Specify repo directory
#
# Prerequisites:
#   - Docker installed and running
#   - k3s installed (for ctr image import)
#   - Run on the control plane node
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_DIR="${DEFAULT_REPO_DIR}"

BACKEND_IMAGE="rpi-k8s-management:latest"
FRONTEND_IMAGE="rpi-k8s-control-panel:latest"
BACKEND_DIR="management/backend"
FRONTEND_DIR="management/frontend"
MANAGEMENT_NAMESPACE="management"

BUILD_BACKEND=true
BUILD_FRONTEND=true
RESTART_PODS=true

# =============================================================================
# Color helpers
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step()   { echo -e "\n${CYAN}======================================================================${NC}"; \
           echo -e "${CYAN}  $1${NC}"; \
           echo -e "${CYAN}======================================================================${NC}"; }
ok()     { echo -e "  ${GREEN}[OK]${NC}    $1"; }
fail()   { echo -e "  ${RED}[FAIL]${NC}  $1"; }
info()   { echo -e "  ${YELLOW}[INFO]${NC}  $1"; }

# =============================================================================
# Parse arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend-only)
            BUILD_FRONTEND=false
            shift
            ;;
        --frontend-only)
            BUILD_BACKEND=false
            shift
            ;;
        --no-restart)
            RESTART_PODS=false
            shift
            ;;
        --repo-dir)
            REPO_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --backend-only    Build backend image only"
            echo "  --frontend-only   Build frontend image only"
            echo "  --no-restart      Skip pod restart after build"
            echo "  --repo-dir DIR    Path to repository root (default: auto-detect)"
            echo "  -h, --help        Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# Pre-flight checks
# =============================================================================

step "Pre-flight checks"

# Check Docker
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed. Install Docker first."
    exit 1
fi
ok "Docker is available"

# Check Docker daemon
if ! docker info &>/dev/null; then
    fail "Docker daemon is not running. Start Docker first."
    exit 1
fi
ok "Docker daemon is running"

# Check k3s ctr
if ! command -v k3s &>/dev/null; then
    fail "k3s is not installed. This script must run on a k3s node."
    exit 1
fi
ok "k3s is available"

# Check repo directory
if [[ ! -d "$REPO_DIR/$BACKEND_DIR" ]] || [[ ! -d "$REPO_DIR/$FRONTEND_DIR" ]]; then
    fail "Repository directory not found at: $REPO_DIR"
    fail "Expected $BACKEND_DIR and $FRONTEND_DIR subdirectories"
    exit 1
fi
ok "Repository found at: $REPO_DIR"

# =============================================================================
# Build backend image
# =============================================================================

if $BUILD_BACKEND; then
    step "Building backend image: $BACKEND_IMAGE"

    cd "$REPO_DIR/$BACKEND_DIR"
    info "Context: $(pwd)"

    if docker build -t "$BACKEND_IMAGE" .; then
        ok "Backend image built successfully"
    else
        fail "Backend image build failed"
        exit 1
    fi

    # Import into k3s containerd
    step "Importing backend image into k3s containerd"
    if docker save "$BACKEND_IMAGE" | sudo k3s ctr images import -; then
        ok "Backend image imported into k3s"
    else
        fail "Failed to import backend image into k3s"
        exit 1
    fi

    cd "$REPO_DIR"
fi

# =============================================================================
# Build frontend image
# =============================================================================

if $BUILD_FRONTEND; then
    step "Building frontend image: $FRONTEND_IMAGE"

    cd "$REPO_DIR/$FRONTEND_DIR"
    info "Context: $(pwd)"

    # Browser API calls use relative /api paths routed by the Ingress.
    # No NEXT_PUBLIC_API_URL is baked; the pod's API_URL env var handles SSR.
    if docker build -t "$FRONTEND_IMAGE" .; then
        ok "Frontend image built successfully"
    else
        fail "Frontend image build failed"
        exit 1
    fi

    # Import into k3s containerd
    step "Importing frontend image into k3s containerd"
    if docker save "$FRONTEND_IMAGE" | sudo k3s ctr images import -; then
        ok "Frontend image imported into k3s"
    else
        fail "Failed to import frontend image into k3s"
        exit 1
    fi

    cd "$REPO_DIR"
fi

# =============================================================================
# Verify images in k3s
# =============================================================================

step "Verifying images in k3s containerd"

if $BUILD_BACKEND; then
    if sudo k3s ctr images list | grep -q "$BACKEND_IMAGE"; then
        ok "Backend image found in k3s: $BACKEND_IMAGE"
    else
        fail "Backend image NOT found in k3s"
    fi
fi

if $BUILD_FRONTEND; then
    if sudo k3s ctr images list | grep -q "$FRONTEND_IMAGE"; then
        ok "Frontend image found in k3s: $FRONTEND_IMAGE"
    else
        fail "Frontend image NOT found in k3s"
    fi
fi

# =============================================================================
# Restart management pods
# =============================================================================

if $RESTART_PODS; then
    step "Restarting management pods"

    if $BUILD_BACKEND; then
        info "Restarting management-api deployment..."
        if kubectl rollout restart deployment/management-api -n "$MANAGEMENT_NAMESPACE" 2>/dev/null; then
            ok "management-api restart triggered"
        else
            info "management-api deployment not found -- apply manifests first:"
            info "  kubectl apply -k kubernetes/base-services/management/"
        fi
    fi

    if $BUILD_FRONTEND; then
        info "Restarting management-ui deployment..."
        if kubectl rollout restart deployment/management-ui -n "$MANAGEMENT_NAMESPACE" 2>/dev/null; then
            ok "management-ui restart triggered"
        else
            info "management-ui deployment not found -- apply manifests first:"
            info "  kubectl apply -k kubernetes/base-services/management/"
        fi
    fi

    # Wait for rollout
    info "Waiting for rollout to complete (up to 120s)..."
    if $BUILD_BACKEND; then
        kubectl rollout status deployment/management-api -n "$MANAGEMENT_NAMESPACE" --timeout=120s 2>/dev/null || \
            info "management-api rollout still in progress"
    fi
    if $BUILD_FRONTEND; then
        kubectl rollout status deployment/management-ui -n "$MANAGEMENT_NAMESPACE" --timeout=120s 2>/dev/null || \
            info "management-ui rollout still in progress"
    fi

    # Show pod status
    info "Current management pod status:"
    kubectl get pods -n "$MANAGEMENT_NAMESPACE" 2>/dev/null || info "Could not get pods"
fi

# =============================================================================
# Summary
# =============================================================================

step "Build Complete"

echo ""
info "Images built and imported:"
$BUILD_BACKEND  && info "  - $BACKEND_IMAGE"
$BUILD_FRONTEND && info "  - $FRONTEND_IMAGE"
echo ""
info "To apply Kubernetes manifests:"
info "  kubectl apply -k kubernetes/base-services/management/"
echo ""
info "To check pod status:"
info "  kubectl get pods -n $MANAGEMENT_NAMESPACE"
echo ""
