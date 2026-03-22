# =============================================================================
# Pod Debugging and Diagnostics Tool
# =============================================================================
# Version: 1.0.0
#
# Comprehensive pod debugging tool for the RPi Kubernetes cluster.
# Inspects pod status, events, logs, PVCs, images, and node resources,
# then provides actionable recommendations.
#
# Usage:
#   .\debug-pods.ps1                                  # All namespaces
#   .\debug-pods.ps1 -Namespace observability         # Specific namespace
#   .\debug-pods.ps1 -Namespace management -Pod management-api-xxx
#   .\debug-pods.ps1 -Label "app=grafana"             # By label selector
#   .\debug-pods.ps1 -FailingOnly                     # Only non-Running pods
#   .\debug-pods.ps1 -Namespace data-services -Logs   # Include container logs
#
# Prerequisites:
#   - kubectl configured and working
# =============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$Namespace = "",

    [Parameter(Mandatory=$false)]
    [string]$Pod = "",

    [Parameter(Mandatory=$false)]
    [string]$Label = "",

    [Parameter(Mandatory=$false)]
    [switch]$FailingOnly = $false,

    [Parameter(Mandatory=$false)]
    [switch]$Logs = $false,

    [Parameter(Mandatory=$false)]
    [int]$LogTail = 50,

    [Parameter(Mandatory=$false)]
    [switch]$Wide = $false,

    [Parameter(Mandatory=$false)]
    [string]$Kubeconfig = ""
)

$ErrorActionPreference = "Continue"

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

function Write-OK {
    param([string]$Message)
    Write-Host "  [OK]    $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [WARN]  $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL]  $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [INFO]  $Message" -ForegroundColor White
}

function Write-Recommendation {
    param([string]$Message)
    Write-Host "  [FIX]   $Message" -ForegroundColor Magenta
}

# Build kubectl base command with optional kubeconfig
function Get-KubectlBase {
    if (-not [string]::IsNullOrEmpty($Kubeconfig)) {
        return "kubectl --kubeconfig `"$Kubeconfig`""
    }
    return "kubectl"
}

# Run kubectl and return output
function Invoke-Kubectl {
    param([string]$Arguments)
    $base = Get-KubectlBase
    $cmd = "$base $Arguments"
    try {
        $output = Invoke-Expression $cmd 2>&1
        return @{
            Success = ($LASTEXITCODE -eq 0)
            Output  = $output
        }
    } catch {
        return @{
            Success = $false
            Output  = $_.Exception.Message
        }
    }
}

# Run kubectl and return parsed JSON
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

# =============================================================================
# Diagnostic functions
# =============================================================================

function Get-PodList {
    param([string]$NS, [string]$PodName, [string]$LabelSelector)

    $args_str = "get pods"
    if (-not [string]::IsNullOrEmpty($NS)) {
        $args_str += " -n $NS"
    } else {
        $args_str += " -A"
    }
    if (-not [string]::IsNullOrEmpty($PodName)) {
        $args_str += " $PodName"
    }
    if (-not [string]::IsNullOrEmpty($LabelSelector)) {
        $args_str += " -l $LabelSelector"
    }

    return Invoke-KubectlJson -Arguments $args_str
}

function Show-PodStatus {
    param($PodItem)

    $name = $PodItem.metadata.name
    $ns = $PodItem.metadata.namespace
    $phase = $PodItem.status.phase
    $nodeName = $PodItem.spec.nodeName
    $restarts = 0
    $ready = 0
    $total = 0

    foreach ($cs in $PodItem.status.containerStatuses) {
        $total++
        if ($cs.ready) { $ready++ }
        $restarts += $cs.restartCount
    }

    # Determine display status
    $statusDisplay = $phase
    $statusColor = "White"

    # Check for waiting containers
    foreach ($cs in $PodItem.status.containerStatuses) {
        if ($cs.state.waiting) {
            $statusDisplay = $cs.state.waiting.reason
            break
        }
    }
    # Check init containers
    foreach ($cs in $PodItem.status.initContainerStatuses) {
        if ($cs.state.waiting) {
            $statusDisplay = "Init:" + $cs.state.waiting.reason
            break
        }
        if ($cs.state.terminated -and $cs.state.terminated.exitCode -ne 0) {
            $statusDisplay = "Init:Error"
            break
        }
    }

    switch -Wildcard ($statusDisplay) {
        "Running"           { $statusColor = "Green" }
        "Completed"         { $statusColor = "Gray" }
        "Succeeded"         { $statusColor = "Green" }
        "Pending"           { $statusColor = "Yellow" }
        "*BackOff*"         { $statusColor = "Red" }
        "*Error*"           { $statusColor = "Red" }
        "*CrashLoop*"       { $statusColor = "Red" }
        "*ImagePull*"       { $statusColor = "Red" }
        "*ErrImagePull*"    { $statusColor = "Red" }
        "*OOMKilled*"       { $statusColor = "Red" }
        default             { $statusColor = "Yellow" }
    }

    $line = "  {0,-50} {1,-20} {2}/{3}  Restarts: {4}  Node: {5}" -f "$ns/$name", $statusDisplay, $ready, $total, $restarts, $nodeName
    Write-Host $line -ForegroundColor $statusColor

    return @{
        Name       = $name
        Namespace  = $ns
        Status     = $statusDisplay
        Phase      = $phase
        Ready      = $ready
        Total      = $total
        Restarts   = $restarts
        Node       = $nodeName
        IsFailing  = ($statusDisplay -ne "Running" -and $statusDisplay -ne "Completed" -and $statusDisplay -ne "Succeeded")
    }
}

function Show-PodEvents {
    param([string]$NS, [string]$PodName)

    Write-SubHeader "Events for $NS/$PodName"
    $result = Invoke-KubectlJson -Arguments "get events -n $NS --field-selector involvedObject.name=$PodName --sort-by=.lastTimestamp"

    if ($result.Success -and $result.Data.items) {
        foreach ($event in $result.Data.items) {
            $type = $event.type
            $reason = $event.reason
            $message = $event.message
            $count = $event.count
            $color = if ($type -eq "Warning") { "Yellow" } else { "White" }
            Write-Host ("  [{0}] {1} (x{2}): {3}" -f $type, $reason, $count, $message) -ForegroundColor $color
        }
    } else {
        Write-Info "No events found"
    }
}

function Show-PodLogs {
    param([string]$NS, [string]$PodName, [int]$Tail, $PodItem)

    # Current container logs
    foreach ($container in $PodItem.spec.containers) {
        Write-SubHeader "Logs: $($container.name) (current) -- tail $Tail"
        $result = Invoke-Kubectl -Arguments "logs -n $NS $PodName -c $($container.name) --tail=$Tail"
        if ($result.Success -and $result.Output) {
            $result.Output | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Warn "No logs available (container may not have started)"
        }

        # Previous logs
        $prevResult = Invoke-Kubectl -Arguments "logs -n $NS $PodName -c $($container.name) --tail=$Tail --previous"
        if ($prevResult.Success -and $prevResult.Output) {
            Write-SubHeader "Logs: $($container.name) (previous crash)"
            $prevResult.Output | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        }
    }

    # Init container logs
    foreach ($initContainer in $PodItem.spec.initContainers) {
        Write-SubHeader "Logs: init/$($initContainer.name)"
        $result = Invoke-Kubectl -Arguments "logs -n $NS $PodName -c $($initContainer.name) --tail=$Tail"
        if ($result.Success -and $result.Output) {
            $result.Output | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Warn "No init container logs available"
        }
    }
}

function Show-PodConditions {
    param($PodItem)

    $name = $PodItem.metadata.name
    Write-SubHeader "Conditions for $name"

    if ($PodItem.status.conditions) {
        foreach ($cond in $PodItem.status.conditions) {
            $icon = if ($cond.status -eq "True") { "[OK]  " } else { "[FAIL]" }
            $color = if ($cond.status -eq "True") { "Green" } else { "Red" }
            $msg = if ($cond.message) { " -- $($cond.message)" } else { "" }
            Write-Host ("  $icon {0}: {1}{2}" -f $cond.type, $cond.status, $msg) -ForegroundColor $color
        }
    } else {
        Write-Warn "No conditions available"
    }
}

function Show-ImageStatus {
    param($PodItem)

    Write-SubHeader "Image Pull Status"

    $allContainers = @()
    if ($PodItem.spec.initContainers) { $allContainers += $PodItem.spec.initContainers }
    if ($PodItem.spec.containers) { $allContainers += $PodItem.spec.containers }

    foreach ($container in $allContainers) {
        $image = $container.image
        $pullPolicy = $container.imagePullPolicy

        # Check container status for image-related errors
        $statusInfo = ""
        $color = "White"

        # Search in containerStatuses and initContainerStatuses
        $allStatuses = @()
        if ($PodItem.status.containerStatuses) { $allStatuses += $PodItem.status.containerStatuses }
        if ($PodItem.status.initContainerStatuses) { $allStatuses += $PodItem.status.initContainerStatuses }

        foreach ($cs in $allStatuses) {
            if ($cs.name -eq $container.name) {
                if ($cs.state.waiting -and $cs.state.waiting.reason -match "ImagePull|ErrImage") {
                    $statusInfo = " ** $($cs.state.waiting.reason): $($cs.state.waiting.message)"
                    $color = "Red"
                } elseif ($cs.imageID) {
                    $statusInfo = " (pulled)"
                    $color = "Green"
                }
                break
            }
        }

        Write-Host ("  Container: {0}" -f $container.name) -ForegroundColor $color
        Write-Host ("    Image:       {0}" -f $image) -ForegroundColor $color
        Write-Host ("    PullPolicy:  {0}" -f $pullPolicy) -ForegroundColor $color
        if ($statusInfo) {
            Write-Host ("    Status:      {0}" -f $statusInfo) -ForegroundColor $color
        }
    }
}

function Show-PvcStatus {
    param([string]$NS)

    Write-SubHeader "PVC Status in namespace: $NS"
    $result = Invoke-KubectlJson -Arguments "get pvc -n $NS"

    if ($result.Success -and $result.Data.items -and $result.Data.items.Count -gt 0) {
        foreach ($pvc in $result.Data.items) {
            $name = $pvc.metadata.name
            $status = $pvc.status.phase
            $capacity = if ($pvc.status.capacity) { $pvc.status.capacity.storage } else { "N/A" }
            $sc = $pvc.spec.storageClassName

            $color = if ($status -eq "Bound") { "Green" } else { "Red" }
            Write-Host ("  {0,-35} {1,-10} {2,-10} StorageClass: {3}" -f $name, $status, $capacity, $sc) -ForegroundColor $color
        }
    } else {
        Write-Info "No PVCs in namespace $NS"
    }
}

function Show-NodeResources {
    Write-SubHeader "Node Resource Summary"
    $result = Invoke-Kubectl -Arguments "top nodes"
    if ($result.Success -and $result.Output) {
        $result.Output | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Warn "Metrics server may not be available (kubectl top nodes failed)"
        # Fallback: show node conditions
        $nodesResult = Invoke-KubectlJson -Arguments "get nodes"
        if ($nodesResult.Success -and $nodesResult.Data.items) {
            foreach ($node in $nodesResult.Data.items) {
                $nodeName = $node.metadata.name
                $conditions = $node.status.conditions
                $pressures = @()
                foreach ($c in $conditions) {
                    if ($c.type -match "Pressure" -and $c.status -eq "True") {
                        $pressures += $c.type
                    }
                }
                $readyCond = $conditions | Where-Object { $_.type -eq "Ready" }
                $readyStatus = if ($readyCond.status -eq "True") { "Ready" } else { "NotReady" }
                $color = if ($readyStatus -eq "Ready") { "Green" } else { "Red" }

                $pressureStr = if ($pressures.Count -gt 0) { " PRESSURE: $($pressures -join ', ')" } else { "" }
                Write-Host ("  {0,-35} {1}{2}" -f $nodeName, $readyStatus, $pressureStr) -ForegroundColor $color
            }
        }
    }
}

function Get-Recommendations {
    param($PodInfo, $PodItem)

    $recs = @()

    switch -Wildcard ($PodInfo.Status) {
        "*ImagePull*" {
            $recs += "Image pull failed. Check if the image exists and is accessible."
            foreach ($c in $PodItem.spec.containers) {
                if ($c.imagePullPolicy -eq "IfNotPresent" -and $c.image -match ":latest$|^[^/]+$") {
                    $recs += "Image '$($c.image)' uses IfNotPresent policy -- it must be pre-built and imported into k3s containerd."
                    $recs += "Build and import: docker build -t $($c.image) . && docker save $($c.image) | sudo k3s ctr images import -"
                }
            }
        }
        "*ErrImage*" {
            $recs += "Image pull error. The image may not exist in any accessible registry."
            $recs += "For local images, build on the node and import: docker save <image> | sudo k3s ctr images import -"
        }
        "CrashLoopBackOff" {
            $recs += "Container is crash-looping. Check logs with: kubectl logs -n $($PodInfo.Namespace) $($PodInfo.Name) --previous"
            if ($PodInfo.Restarts -gt 10) {
                $recs += "High restart count ($($PodInfo.Restarts)). The application may have a fatal startup error."
            }
        }
        "Init:Error" {
            $recs += "Init container failed. Check init container logs."
            $recs += "Common causes: port conflicts, missing dependencies, permission issues."
        }
        "Pending" {
            $recs += "Pod is Pending. Common causes:"
            $recs += "  - Insufficient node resources (CPU/memory)"
            $recs += "  - PVC not bound (storage class or capacity issue)"
            $recs += "  - Node selector/affinity mismatch"
            $recs += "  - Taints preventing scheduling"
            # Check for unschedulable condition
            if ($PodItem.status.conditions) {
                foreach ($c in $PodItem.status.conditions) {
                    if ($c.type -eq "PodScheduled" -and $c.status -eq "False") {
                        $recs += "Scheduler message: $($c.message)"
                    }
                }
            }
        }
        "*OOMKilled*" {
            $recs += "Container was killed due to Out Of Memory. Increase memory limits in the deployment spec."
        }
    }

    # Architecture check
    $nodeArch = ""
    if ($PodInfo.Node) {
        $nodeResult = Invoke-KubectlJson -Arguments "get node $($PodInfo.Node) -o json"
        if ($nodeResult.Success) {
            $nodeArch = $nodeResult.Data.status.nodeInfo.architecture
        }
    }
    foreach ($c in $PodItem.spec.containers) {
        if ($c.image -match "milvus" -and $nodeArch -eq "arm64") {
            $recs += "Milvus does NOT support ARM64. Add nodeSelector 'kubernetes.io/arch: amd64' to schedule on the control plane."
        }
    }

    return $recs
}

# =============================================================================
# Main execution
# =============================================================================

Write-Header "Pod Debugging and Diagnostics Tool v1.0.0"

# Verify kubectl connectivity
$clusterResult = Invoke-Kubectl -Arguments "cluster-info"
if (-not $clusterResult.Success) {
    Write-Fail "Cannot connect to Kubernetes cluster. Check your kubeconfig."
    exit 1
}
Write-OK "Connected to cluster"

# Get pods
$podsResult = Get-PodList -NS $Namespace -PodName $Pod -LabelSelector $Label

if (-not $podsResult.Success -or -not $podsResult.Data.items) {
    Write-Fail "No pods found matching the criteria"
    exit 1
}

$pods = $podsResult.Data.items
Write-Info "Found $($pods.Count) pod(s)"

# Show pod status overview
Write-Header "Pod Status Overview"

$failingPods = @()
$allPodInfo = @()

foreach ($pod_item in $pods) {
    $info = Show-PodStatus -PodItem $pod_item
    $allPodInfo += @{ Info = $info; Item = $pod_item }
    if ($info.IsFailing) {
        $failingPods += @{ Info = $info; Item = $pod_item }
    }
}

# Summary
Write-Host ""
$runningCount = ($allPodInfo | Where-Object { -not $_.Info.IsFailing }).Count
$failingCount = $failingPods.Count
Write-Info "Running: $runningCount | Failing: $failingCount | Total: $($pods.Count)"

# If FailingOnly, filter to just failing pods
$podsToInspect = if ($FailingOnly) { $failingPods } else { $allPodInfo | Where-Object { $_.Info.IsFailing } }

if ($podsToInspect.Count -eq 0 -and $FailingOnly) {
    Write-OK "No failing pods found!"
    exit 0
}

# Detailed inspection of failing/selected pods
if ($podsToInspect.Count -gt 0) {
    Write-Header "Detailed Diagnostics for Failing Pods"

    foreach ($podEntry in $podsToInspect) {
        $info = $podEntry.Info
        $item = $podEntry.Item

        Write-Header "$($info.Namespace)/$($info.Name) -- $($info.Status)"

        # Conditions
        Show-PodConditions -PodItem $item

        # Image status
        Show-ImageStatus -PodItem $item

        # Events
        Show-PodEvents -NS $info.Namespace -PodName $info.Name

        # Logs (if requested or always for failing pods)
        if ($Logs -or $info.IsFailing) {
            Show-PodLogs -NS $info.Namespace -PodName $info.Name -Tail $LogTail -PodItem $item
        }

        # PVC status for the namespace
        Show-PvcStatus -NS $info.Namespace

        # Recommendations
        $recs = Get-Recommendations -PodInfo $info -PodItem $item
        if ($recs.Count -gt 0) {
            Write-SubHeader "Recommendations"
            foreach ($rec in $recs) {
                Write-Recommendation $rec
            }
        }
    }
}

# Node resources
Show-NodeResources

# Overall summary
Write-Header "Diagnostics Summary"

if ($failingCount -eq 0) {
    Write-OK "All pods are healthy!"
} else {
    Write-Fail "$failingCount pod(s) need attention"

    # Group by failure type
    $byStatus = $failingPods | Group-Object { $_.Info.Status }
    foreach ($group in $byStatus) {
        Write-Warn "$($group.Count) pod(s) in state: $($group.Name)"
        foreach ($p in $group.Group) {
            Write-Info "  - $($p.Info.Namespace)/$($p.Info.Name)"
        }
    }
}

Write-Host ""
