# =============================================================================
# Build management images locally and load them into k3s without SSH.
# =============================================================================
# Companion to bootstrap/scripts/build-management.ps1, which assumes SSH
# access to the control plane node.  This variant runs entirely from a
# developer laptop using:
#
#   1. Local Docker Desktop (with Linux containers / buildx) for building
#      the linux/amd64 backend + frontend images.
#   2. A privileged in-cluster Pod (`image-loader` in `kube-system`) that
#      we apply via kubectl, mounting the control plane node's containerd
#      socket.
#   3. `docker save | kubectl exec -i image-loader -- ctr images import -`
#      streamed through cmd.exe (PowerShell mangles binary pipelines).
#   4. `kubectl rollout restart deployment/management-api` and
#      `deployment/management-ui` to pick up the new images.
#
# Usage:
#   .\bootstrap\scripts\build-management-no-ssh.ps1
#   .\bootstrap\scripts\build-management-no-ssh.ps1 -BackendOnly
#   .\bootstrap\scripts\build-management-no-ssh.ps1 -FrontendOnly -SkipRestart
#   .\bootstrap\scripts\build-management-no-ssh.ps1 -KeepLoader
#
# Prereqs:
#   - Docker Desktop running with linux/amd64 buildx
#   - kubectl pointed at the cluster (KUBECONFIG=...\kubeconfig.yaml)
# =============================================================================
[CmdletBinding()]
param(
    [string]$KubeConfig = "$PSScriptRoot\..\..\kubeconfig.yaml",
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$SkipRestart,
    [switch]$KeepLoader
)

$ErrorActionPreference = "Stop"
# PowerShell 7's strict-error model treats every native command stderr line
# as a terminating error, which breaks `docker buildx build` (its progress
# UI writes to stderr).  Disable the strict behaviour for native commands
# and rely on $LASTEXITCODE checks instead.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$env:KUBECONFIG = (Resolve-Path $KubeConfig).Path
$repoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$buildDir = Join-Path $repoRoot 'build'
if (-not (Test-Path $buildDir)) { New-Item -ItemType Directory -Path $buildDir | Out-Null }

$buildBackend  = -not $FrontendOnly
$buildFrontend = -not $BackendOnly

function Step($msg) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# 1. Bring up the image-loader Pod (idempotent).
# ---------------------------------------------------------------------------
Step "Ensuring image-loader Pod is up"
kubectl apply -f (Join-Path $PSScriptRoot 'image-loader-pod.yaml')
kubectl wait --for=condition=Ready pod/image-loader -n kube-system --timeout=300s

# ---------------------------------------------------------------------------
# 2. Build + push backend.
# ---------------------------------------------------------------------------
if ($buildBackend) {
    Step "Building backend image (linux/amd64)"
    # Disable PowerShell's "stop on stderr" globally for the docker run -
    # buildx writes its TUI to stderr and PowerShell would otherwise abort
    # on the first frame.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $bDockerfile = (Join-Path $repoRoot 'management\backend\Dockerfile')
        cmd.exe /c "docker buildx build --platform linux/amd64 --load -f ""$bDockerfile"" -t rpi-k8s-management:latest ""$repoRoot"" 2>&1"
        if ($LASTEXITCODE -ne 0) { throw "backend build failed" }

        Step "Pushing backend image into k3s containerd"
        cmd.exe /c "$PSScriptRoot\push-image-to-cluster.cmd rpi-k8s-management:latest 2>&1"
        if ($LASTEXITCODE -ne 0) { throw "backend push failed" }
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

# ---------------------------------------------------------------------------
# 3. Build + push frontend.
# ---------------------------------------------------------------------------
if ($buildFrontend) {
    Step "Building frontend image (linux/amd64)"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $fDockerfile = (Join-Path $repoRoot 'management\frontend\Dockerfile')
        $fContext    = (Join-Path $repoRoot 'management\frontend')
        cmd.exe /c "docker buildx build --platform linux/amd64 --load -f ""$fDockerfile"" -t rpi-k8s-control-panel:latest ""$fContext"" 2>&1"
        if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }

        Step "Pushing frontend image into k3s containerd"
        cmd.exe /c "$PSScriptRoot\push-image-to-cluster.cmd rpi-k8s-control-panel:latest 2>&1"
        if ($LASTEXITCODE -ne 0) { throw "frontend push failed" }
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

# ---------------------------------------------------------------------------
# 4. Roll out new deployments.
# ---------------------------------------------------------------------------
if (-not $SkipRestart) {
    Step "Rolling out management deployments"
    if ($buildBackend) {
        kubectl rollout restart deployment/management-api -n management
        kubectl rollout status  deployment/management-api -n management --timeout=180s
    }
    if ($buildFrontend) {
        kubectl rollout restart deployment/management-ui -n management
        kubectl rollout status  deployment/management-ui -n management --timeout=180s
    }
    Write-Host ""
    kubectl get pods -n management
}

# ---------------------------------------------------------------------------
# 5. Cleanup loader Pod (unless asked to keep it for follow-up pushes).
# ---------------------------------------------------------------------------
if (-not $KeepLoader) {
    Step "Cleaning up image-loader Pod"
    kubectl delete pod image-loader -n kube-system --ignore-not-found --wait=false
}
else {
    Write-Host ""
    Write-Host "  -KeepLoader was set; image-loader Pod left running for follow-up pushes."
}

Step "Done."
Write-Host "  Open the new console at: http://control.local/  (or via NodePort 31280)"
