@echo off
REM ============================================================================
REM Push a local Docker image into k3s containerd via the image-loader Pod.
REM ============================================================================
REM Why this is a CMD batch and not a PowerShell script:
REM   PowerShell rewrites binary streams when they cross the `|` operator,
REM   which corrupts the docker-save tar going through `kubectl exec -i`.
REM   CMD's pipeline is byte-clean, so we drop into cmd.exe for the actual
REM   transfer.  The PowerShell wrapper invokes us with `cmd.exe /c`.
REM
REM Args:
REM   %1  Local Docker image reference (e.g. rpi-k8s-management:latest)
REM Env:
REM   KUBECONFIG  (must already be set by the caller)
REM ============================================================================
SETLOCAL
IF "%~1"=="" (
    echo usage: push-image-to-cluster.cmd ^<local-image:tag^>
    exit /b 2
)
SET IMAGE=%~1
echo === Streaming docker save %IMAGE% ^-^> kubectl exec ^-^> ctr import ===
docker save "%IMAGE%" | kubectl exec -n kube-system -i image-loader -- ctr -a /run/k3s/containerd/containerd.sock -n k8s.io images import -
IF ERRORLEVEL 1 (
    echo === FAILED ===
    exit /b 1
)
echo === Verifying ===
REM Pass the image tag through an env var so the inner shell sees a normal $IMAGE.
SET INNER_IMAGE=%IMAGE%
kubectl exec -n kube-system -e "INNER_IMAGE=%INNER_IMAGE%" image-loader -- sh -c "ctr -a /run/k3s/containerd/containerd.sock -n k8s.io images ls 2>&1 | grep -F \"$INNER_IMAGE\" || true"
ENDLOCAL
