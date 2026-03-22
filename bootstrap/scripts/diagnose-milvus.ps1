# =============================================================================
# Milvus Deployment Diagnostics
# =============================================================================
# Version: 1.0.0
#
# Targeted diagnostic tool for the Milvus vector database deployment.
# Checks pod scheduling, etcd health, MinIO bucket, PVC binding, and
# trace pipeline connectivity, then provides actionable fix suggestions.
#
# Usage:
#   .\diagnose-milvus.ps1                          # Full diagnostics
#   .\diagnose-milvus.ps1 -Fix                     # Attempt automatic fixes
#   .\diagnose-milvus.ps1 -Kubeconfig .\kube.yaml  # Custom kubeconfig
#
# Prerequisites:
#   - kubectl configured and working
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [switch]$Fix = $false,

    [Parameter(Mandatory=$false)]
    [string]$Kubeconfig = "",

    [Parameter(Mandatory=$false)]
    [int]$LogTail = 80
)

$ErrorActionPreference = "Continue"
$NS = "data-services"

# =============================================================================
# Helper functions
# =============================================================================

function Write-Header {
    param([string]$Title)
    $line = "=" * 80
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host $line -ForegroundColor Cyan
}

function Write-SubHeader {
    param([string]$Title)
    $line = "-" * 60
    Write-Host ""
    Write-Host $line -ForegroundColor Yellow
    Write-Host "  $Title" -ForegroundColor Yellow
    Write-Host $line -ForegroundColor Yellow
}

function Write-OK    { param([string]$Message); Write-Host "  [OK]    $Message" -ForegroundColor Green }
function Write-Warn  { param([string]$Message); Write-Host "  [WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail  { param([string]$Message); Write-Host "  [FAIL]  $Message" -ForegroundColor Red }
function Write-Info  { param([string]$Message); Write-Host "  [INFO]  $Message" -ForegroundColor White }
function Write-FixAction { param([string]$Message); Write-Host "  [FIX]   $Message" -ForegroundColor Magenta }

function Get-KubectlBase {
    if (-not [string]::IsNullOrEmpty($Kubeconfig)) {
        return "kubectl --kubeconfig `"$Kubeconfig`""
    }
    return "kubectl"
}

function Invoke-Kubectl {
    param([string]$Arguments)
    $base = Get-KubectlBase
    $cmd = "$base $Arguments"
    try {
        $output = Invoke-Expression $cmd 2>&1
        return @{ Success = ($LASTEXITCODE -eq 0); Output = $output }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

function Invoke-KubectlJson {
    param([string]$Arguments)
    $result = Invoke-Kubectl -Arguments "$Arguments -o json"
    if ($result.Success -and $result.Output) {
        try {
            $parsed = $result.Output | ConvertFrom-Json
            return @{ Success = $true; Data = $parsed }
        } catch {
            return @{ Success = $false; Data = $null }
        }
    }
    return @{ Success = $false; Data = $null }
}

$issues = @()
$fixes = @()

# =============================================================================
# 1. Cluster connectivity
# =============================================================================

Write-Header "Milvus Deployment Diagnostics v1.0.0"

$clusterResult = Invoke-Kubectl -Arguments "cluster-info"
if (-not $clusterResult.Success) {
    Write-Fail "Cannot connect to Kubernetes cluster"
    exit 1
}
Write-OK "Connected to cluster"

# =============================================================================
# 2. Namespace check
# =============================================================================

Write-SubHeader "Namespace: $NS"
$nsResult = Invoke-KubectlJson -Arguments "get namespace $NS"
if ($nsResult.Success) {
    Write-OK "Namespace '$NS' exists"
} else {
    Write-Fail "Namespace '$NS' does not exist"
    $issues += "Namespace $NS missing"
    $fixes += "kubectl create namespace $NS"
}

# =============================================================================
# 3. Milvus pods
# =============================================================================

Write-SubHeader "Milvus Pod Status"
$podsResult = Invoke-KubectlJson -Arguments "get pods -n $NS -l app.kubernetes.io/instance=milvus"
$milvusPods = @()
if ($podsResult.Success -and $podsResult.Data.items) {
    $milvusPods = $podsResult.Data.items
}

if ($milvusPods.Count -eq 0) {
    $allPodsResult = Invoke-KubectlJson -Arguments "get pods -n $NS"
    if ($allPodsResult.Success -and $allPodsResult.Data.items) {
        $milvusPods = $allPodsResult.Data.items | Where-Object { $_.metadata.name -match "milvus" }
    }
}

if ($milvusPods.Count -eq 0) {
    Write-Fail "No Milvus pods found in namespace $NS"
    $issues += "No Milvus pods deployed"
    $fixes += "helm upgrade --install milvus milvus/milvus --namespace $NS -f kubernetes/base-services/milvus/values.yaml"
} else {
    foreach ($pod in $milvusPods) {
        $name = $pod.metadata.name
        $phase = $pod.status.phase
        $nodeName = $pod.spec.nodeName
        $restarts = 0

        $statusDisplay = $phase
        foreach ($cs in $pod.status.containerStatuses) {
            $restarts += $cs.restartCount
            if ($cs.state.waiting) { $statusDisplay = $cs.state.waiting.reason }
        }
        foreach ($cs in $pod.status.initContainerStatuses) {
            if ($cs.state.waiting) { $statusDisplay = "Init:$($cs.state.waiting.reason)"; break }
            if ($cs.state.terminated -and $cs.state.terminated.exitCode -ne 0) { $statusDisplay = "Init:Error"; break }
        }

        $isHealthy = ($statusDisplay -eq "Running" -or $statusDisplay -eq "Completed" -or $statusDisplay -eq "Succeeded")
        $color = if ($isHealthy) { "Green" } else { "Red" }

        Write-Host ("  {0,-45} {1,-22} Restarts: {2,-4} Node: {3}" -f $name, $statusDisplay, $restarts, $nodeName) -ForegroundColor $color

        if (-not $isHealthy) {
            $issues += "Pod $name is in state: $statusDisplay"
        }

        # Architecture check
        if ($nodeName) {
            $nodeResult = Invoke-KubectlJson -Arguments "get node $nodeName"
            if ($nodeResult.Success) {
                $arch = $nodeResult.Data.status.nodeInfo.architecture
                if ($arch -eq "arm64" -and $name -match "milvus") {
                    Write-Fail "Pod $name scheduled on ARM64 node ($nodeName) -- Milvus requires amd64"
                    $issues += "Milvus pod on ARM64 node"
                    $fixes += "Ensure nodeSelector 'kubernetes.io/arch: amd64' is set in values.yaml"
                } else {
                    Write-OK "Correct architecture: $arch on $nodeName"
                }
            }
        }

        if ($restarts -gt 5) {
            Write-Warn "High restart count ($restarts) -- check logs below"
        }
    }
}

# =============================================================================
# 4. etcd health
# =============================================================================

Write-SubHeader "etcd Health"
$etcdPods = @()
$etcdResult = Invoke-KubectlJson -Arguments "get pods -n $NS -l app.kubernetes.io/name=etcd"
if ($etcdResult.Success -and $etcdResult.Data.items) {
    $etcdPods = $etcdResult.Data.items
}

if ($etcdPods.Count -eq 0) {
    $allPodsResult2 = Invoke-KubectlJson -Arguments "get pods -n $NS"
    if ($allPodsResult2.Success -and $allPodsResult2.Data.items) {
        $etcdPods = $allPodsResult2.Data.items | Where-Object { $_.metadata.name -match "etcd" }
    }
}

if ($etcdPods.Count -eq 0) {
    Write-Fail "No etcd pods found -- Milvus requires etcd for metadata"
    $issues += "etcd not running"
} else {
    foreach ($ep in $etcdPods) {
        $eName = $ep.metadata.name
        $ePhase = $ep.status.phase
        $eNode = $ep.spec.nodeName
        $eReady = ($ep.status.containerStatuses | Where-Object { $_.ready }).Count
        $eTotal = ($ep.status.containerStatuses).Count
        $color = if ($ePhase -eq "Running" -and $eReady -eq $eTotal) { "Green" } else { "Red" }

        Write-Host ("  {0,-45} {1,-10} Ready: {2}/{3}  Node: {4}" -f $eName, $ePhase, $eReady, $eTotal, $eNode) -ForegroundColor $color

        if ($ePhase -ne "Running") {
            $issues += "etcd pod $eName not running ($ePhase)"
            $fixes += "Check etcd logs: kubectl logs -n $NS $eName --tail=50"
        }

        if ($eNode) {
            $enResult = Invoke-KubectlJson -Arguments "get node $eNode"
            if ($enResult.Success -and $enResult.Data.status.nodeInfo.architecture -eq "arm64") {
                Write-Fail "etcd scheduled on ARM64 -- bitnami/etcd may not have ARM images"
                $issues += "etcd on ARM64 node"
            }
        }
    }
}

# =============================================================================
# 5. PVC binding
# =============================================================================

Write-SubHeader "PVC Status"
$pvcResult = Invoke-KubectlJson -Arguments "get pvc -n $NS"
$milvusPvcs = @()
if ($pvcResult.Success -and $pvcResult.Data.items) {
    $milvusPvcs = $pvcResult.Data.items | Where-Object { $_.metadata.name -match "milvus|etcd" }
}

if ($milvusPvcs.Count -eq 0) {
    Write-Warn "No Milvus/etcd PVCs found"
} else {
    foreach ($pvc in $milvusPvcs) {
        $pName = $pvc.metadata.name
        $pStatus = $pvc.status.phase
        $pSize = if ($pvc.status.capacity) { $pvc.status.capacity.storage } else { "pending" }
        $pSC = $pvc.spec.storageClassName
        $color = if ($pStatus -eq "Bound") { "Green" } else { "Red" }

        Write-Host ("  {0,-40} {1,-10} Size: {2,-8} SC: {3}" -f $pName, $pStatus, $pSize, $pSC) -ForegroundColor $color

        if ($pStatus -ne "Bound") {
            $issues += "PVC $pName not bound ($pStatus)"
            $fixes += "Check StorageClass '$pSC' exists: kubectl get sc"
        }
    }
}

# =============================================================================
# 6. MinIO bucket verification
# =============================================================================

Write-SubHeader "MinIO Bucket Check"
$minioResult = Invoke-KubectlJson -Arguments "get pods -n $NS -l app=minio"
$minioPods = @()
if ($minioResult.Success -and $minioResult.Data.items) {
    $minioPods = $minioResult.Data.items | Where-Object { $_.status.phase -eq "Running" }
}

if ($minioPods.Count -eq 0) {
    $minioResult2 = Invoke-KubectlJson -Arguments "get deploy -n $NS minio"
    if ($minioResult2.Success) {
        Write-Warn "MinIO deployment exists but no running pods found"
    } else {
        Write-Fail "MinIO not deployed in $NS -- Milvus requires MinIO for object storage"
        $issues += "MinIO not available"
    }
} else {
    Write-OK "MinIO is running"
    $bucketCheck = Invoke-Kubectl -Arguments "exec -n $NS deploy/minio -- sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin123 2>/dev/null && mc ls local/milvus-bucket 2>&1'"
    if ($bucketCheck.Success -and $bucketCheck.Output -notmatch "does not exist|ERROR") {
        Write-OK "Bucket 'milvus-bucket' exists"
    } else {
        Write-Fail "Bucket 'milvus-bucket' not found or inaccessible"
        $issues += "MinIO bucket 'milvus-bucket' missing"
        $fixes += "kubectl exec -n $NS deploy/minio -- sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin123 && mc mb local/milvus-bucket --ignore-existing'"
    }
}

# =============================================================================
# 7. OTel trace pipeline check
# =============================================================================

Write-SubHeader "Trace Pipeline (OTel Collector)"
$otelResult = Invoke-KubectlJson -Arguments "get pods -n observability -l app=otel-collector"
if ($otelResult.Success -and $otelResult.Data.items) {
    $runningOtel = $otelResult.Data.items | Where-Object { $_.status.phase -eq "Running" }
    if ($runningOtel.Count -gt 0) {
        Write-OK "OTel Collector running ($($runningOtel.Count) instance(s))"
    } else {
        Write-Warn "OTel Collector pods exist but none are Running"
        $issues += "OTel Collector not healthy"
    }
} else {
    Write-Warn "OTel Collector not found in observability namespace"
    $issues += "OTel Collector not deployed"
}

$jaegerResult = Invoke-KubectlJson -Arguments "get pods -n observability -l app=jaeger"
if ($jaegerResult.Success -and $jaegerResult.Data.items) {
    $runningJaeger = $jaegerResult.Data.items | Where-Object { $_.status.phase -eq "Running" }
    if ($runningJaeger.Count -gt 0) {
        Write-OK "Jaeger running"
    } else {
        Write-Warn "Jaeger pods exist but none are Running"
    }
} else {
    Write-Warn "Jaeger not found in observability namespace"
}

# =============================================================================
# 8. Pod events and logs for failing pods
# =============================================================================

$failingMilvus = $milvusPods | Where-Object {
    $phase = $_.status.phase
    $phase -ne "Running" -and $phase -ne "Succeeded" -and $phase -ne "Completed"
}
$failingEtcd = $etcdPods | Where-Object {
    $phase = $_.status.phase
    $phase -ne "Running" -and $phase -ne "Succeeded" -and $phase -ne "Completed"
}

$allFailing = @()
if ($failingMilvus) { $allFailing += $failingMilvus }
if ($failingEtcd) { $allFailing += $failingEtcd }

if ($allFailing.Count -gt 0) {
    Write-Header "Logs and Events for Failing Pods"

    foreach ($fp in $allFailing) {
        $fpName = $fp.metadata.name
        $fpNS = $fp.metadata.namespace

        Write-SubHeader "Events: $fpName"
        $evResult = Invoke-KubectlJson -Arguments "get events -n $fpNS --field-selector involvedObject.name=$fpName --sort-by=.lastTimestamp"
        if ($evResult.Success -and $evResult.Data.items) {
            foreach ($ev in $evResult.Data.items | Select-Object -Last 10) {
                $evColor = if ($ev.type -eq "Warning") { "Yellow" } else { "White" }
                Write-Host ("  [{0}] {1} (x{2}): {3}" -f $ev.type, $ev.reason, $ev.count, $ev.message) -ForegroundColor $evColor
            }
        } else {
            Write-Info "No events found"
        }

        Write-SubHeader "Logs: $fpName (tail $LogTail)"
        foreach ($container in $fp.spec.containers) {
            $logResult = Invoke-Kubectl -Arguments "logs -n $fpNS $fpName -c $($container.name) --tail=$LogTail"
            if ($logResult.Success -and $logResult.Output) {
                $logResult.Output | ForEach-Object { Write-Host "    $_" }
            } else {
                Write-Warn "No current logs for $($container.name)"
            }

            $prevResult = Invoke-Kubectl -Arguments "logs -n $fpNS $fpName -c $($container.name) --tail=$LogTail --previous"
            if ($prevResult.Success -and $prevResult.Output) {
                Write-SubHeader "Previous crash logs: $($container.name)"
                $prevResult.Output | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            }
        }
    }
}

# =============================================================================
# 9. Summary
# =============================================================================

Write-Header "Diagnostics Summary"

if ($issues.Count -eq 0) {
    Write-OK "Milvus deployment looks healthy"
} else {
    Write-Fail "$($issues.Count) issue(s) found:"
    foreach ($issue in $issues) {
        Write-Warn "  - $issue"
    }
}

if ($fixes.Count -gt 0) {
    Write-SubHeader "Suggested Fix Commands"
    foreach ($f in $fixes) {
        Write-FixAction $f
    }

    if ($Fix) {
        Write-Header "Applying Automatic Fixes"

        foreach ($f in $fixes) {
            Write-Info "Running: $f"
            $base = Get-KubectlBase
            $fixCmd = $f -replace "^kubectl", $base
            try {
                $fixOutput = Invoke-Expression $fixCmd 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-OK "Success"
                } else {
                    Write-Fail "Command returned non-zero exit code"
                    $fixOutput | ForEach-Object { Write-Host "    $_" }
                }
            } catch {
                Write-Fail "Error: $($_.Exception.Message)"
            }
        }

        Write-Info "Re-run without -Fix to verify"
    } else {
        Write-Host ""
        Write-Info "Run with -Fix to attempt automatic fixes"
    }
}

Write-Host ""
