# Fix Grafana Port 3000 Conflict
# Stops gpt-research process blocking Grafana

param(
    [string]$ControlPlaneIP = "192.168.12.112",
    [string]$User = "julia"
)

$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Fixing Port 3000 Conflict (Grafana vs gpt-research)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Function to run SSH command with timeout
function Invoke-SSHCommand {
    param(
        [string]$Command,
        [int]$TimeoutSeconds = 10
    )
    
    $job = Start-Job -ScriptBlock {
        param($ip, $user, $cmd)
        ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$user@$ip" $cmd 2>&1
    } -ArgumentList $ControlPlaneIP, $User, $Command
    
    $completed = Wait-Job $job -Timeout $TimeoutSeconds
    
    if ($completed) {
        $result = Receive-Job $job
        Remove-Job $job -Force
        return $result
    } else {
        Stop-Job $job -PassThru | Remove-Job -Force
        Write-Host "  Command timed out after $TimeoutSeconds seconds" -ForegroundColor Yellow
        return $null
    }
}

Write-Host "[1] Checking port 3000..." -ForegroundColor White
$result = Invoke-SSHCommand "sudo lsof -i :3000 -n -P 2>/dev/null" -TimeoutSeconds 15
if ($result) {
    Write-Host "  Port 3000 is in use:" -ForegroundColor Yellow
    $result | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  Could not check port (timeout or free)" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "[2] Finding gpt-research processes..." -ForegroundColor White
$result = Invoke-SSHCommand "pgrep -f gpt-research" -TimeoutSeconds 10
if ($result) {
    $pids = $result -split "`n" | Where-Object { $_ -match '^\d+$' }
    Write-Host "  Found PIDs: $($pids -join ', ')" -ForegroundColor Yellow
    
    Write-Host "[3] Terminating processes..." -ForegroundColor White
    foreach ($pid in $pids) {
        Write-Host "  Killing PID $pid..." -ForegroundColor Gray
        $killResult = Invoke-SSHCommand "sudo kill -9 $pid" -TimeoutSeconds 5
        if ($killResult -ne $null) {
            Write-Host "    Killed PID $pid" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  No gpt-research processes found (or timeout)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "[4] Finding any process on port 3000..." -ForegroundColor White
$result = Invoke-SSHCommand "sudo lsof -t -i :3000" -TimeoutSeconds 10
if ($result) {
    $pids = $result -split "`n" | Where-Object { $_ -match '^\d+$' }
    Write-Host "  Found PIDs on port 3000: $($pids -join ', ')" -ForegroundColor Yellow
    
    Write-Host "  Getting process details..." -ForegroundColor Gray
    foreach ($pid in $pids) {
        $details = Invoke-SSHCommand "ps -p $pid -o cmd --no-headers 2>/dev/null" -TimeoutSeconds 5
        if ($details) {
            Write-Host "    PID $pid : $details" -ForegroundColor Gray
        }
    }
    
    Write-Host ""
    Write-Host "  Killing processes on port 3000..." -ForegroundColor White
    foreach ($pid in $pids) {
        $killResult = Invoke-SSHCommand "sudo kill -9 $pid" -TimeoutSeconds 5
        Write-Host "    Killed PID $pid" -ForegroundColor Green
    }
} else {
    Write-Host "  No processes found on port 3000 (or timeout)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "[5] Verifying port 3000 is free..." -ForegroundColor White
$result = Invoke-SSHCommand "sudo lsof -i :3000 2>/dev/null" -TimeoutSeconds 10
if ($result) {
    Write-Host "  Port 3000 still in use:" -ForegroundColor Yellow
    $result | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  Port 3000 is now free!" -ForegroundColor Green
}
Write-Host ""

Write-Host "[6] Checking Grafana pod status..." -ForegroundColor White
$env:KUBECONFIG = "$PWD\kubeconfig.yaml"
$grafanaPods = kubectl get pods -A 2>&1 | Select-String "grafana"
if ($grafanaPods) {
    Write-Host "  Grafana pods:" -ForegroundColor White
    $grafanaPods | ForEach-Object { Write-Host "    $_" }
    
    # Check if pods need restart
    $needsRestart = $grafanaPods | Where-Object { $_ -match "Error|CrashLoop|0/" }
    if ($needsRestart) {
        Write-Host ""
        Write-Host "  Restarting problematic Grafana pods..." -ForegroundColor Yellow
        $needsRestart | ForEach-Object {
            $parts = $_.ToString().Split()
            if ($parts.Count -ge 2) {
                $namespace = $parts[0]
                $podName = $parts[1]
                Write-Host "    Deleting pod $podName in $namespace..." -ForegroundColor Gray
                kubectl delete pod $podName -n $namespace --force --grace-period=0 2>&1 | Out-Null
            }
        }
        Write-Host "    Pods deleted, waiting for recreation..." -ForegroundColor Gray
        Start-Sleep -Seconds 5
        
        Write-Host ""
        Write-Host "  New pod status:" -ForegroundColor White
        kubectl get pods -A 2>&1 | Select-String "grafana" | ForEach-Object { Write-Host "    $_" }
    }
} else {
    Write-Host "  No Grafana pods found" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Done! Port 3000 should now be available for Grafana" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "To verify Grafana is working:" -ForegroundColor White
Write-Host "  kubectl get pods -A | Select-String grafana" -ForegroundColor Gray
Write-Host "  kubectl logs -n observability <grafana-pod-name>" -ForegroundColor Gray
