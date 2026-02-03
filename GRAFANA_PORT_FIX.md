# Grafana Port 3000 Conflict - Manual Fix Guide

**Issue:** Grafana cannot run on port 3000 because gpt-research is using it on the control plane.

**Grafana Pod Status:** `Init:Error` (as of check)

## Quick Fix - Run on Control Plane

SSH into the control plane and run these commands:

```bash
ssh julia@192.168.12.112
# or
ssh julia@k8s-control.local
```

### Step 1: Find and Kill gpt-research Process

```bash
# Find gpt-research processes
ps aux | grep -i gpt-research | grep -v grep

# Get PIDs using port 3000
sudo lsof -i :3000 -t

# Or use pgrep
pgrep -f gpt-research

# Kill by name (replace with actual PID)
sudo pkill -9 -f gpt-research

# Or kill specific PID
sudo kill -9 <PID>

# Verify port 3000 is free
sudo lsof -i :3000
# Should return nothing if port is free
```

### Step 2: Check What's on Port 3000

```bash
# Detailed view of what's using port 3000
sudo lsof -i :3000 -n -P

# Alternative using ss
sudo ss -tulpn | grep :3000

# Get process details
sudo netstat -tulpn | grep :3000
```

### Step 3: Force Kill Any Process on Port 3000

```bash
# Get PID and kill
PID=$(sudo lsof -t -i :3000)
if [ ! -z "$PID" ]; then
    echo "Killing PID: $PID"
    sudo kill -9 $PID
    echo "Process killed"
else
    echo "Port 3000 is free"
fi
```

### Step 4: Restart Grafana Pod

```bash
# Check current Grafana pod status
kubectl get pods -n observability | grep grafana

# Delete the problematic pod (it will auto-restart)
kubectl delete pod prometheus-grafana-677b864985-2n2fc -n observability --force --grace-period=0

# Wait a few seconds, then check new pod
sleep 10
kubectl get pods -n observability | grep grafana

# Check pod logs if still failing
kubectl logs -n observability $(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') --all-containers=true

# Describe pod for detailed error info
kubectl describe pod -n observability $(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
```

### Step 5: Check Grafana Service

```bash
# Verify Grafana service is configured correctly
kubectl get svc -n observability prometheus-grafana

# Should show:
# TYPE: LoadBalancer
# PORT: 3000:30148/TCP
# EXTERNAL-IP: Should have IPs listed
```

### Step 6: Test Grafana Access

```bash
# From control plane
curl -I http://localhost:3000

# Or from your workstation
curl -I http://192.168.12.112:3000
```

## Alternative: Stop gpt-research Service (if it's a systemd service)

```bash
# Check if gpt-research is a systemd service
sudo systemctl status gpt-research

# If it exists, stop and disable it
sudo systemctl stop gpt-research
sudo systemctl disable gpt-research
```

## Alternative: Change Grafana Port (if you want to keep gpt-research)

If you want to keep gpt-research on port 3000, you can change Grafana's port:

```bash
# Edit Grafana service
kubectl edit svc prometheus-grafana -n observability

# Change port from 3000 to something else (e.g., 3001)
# Update the NodePort or create a new service
```

## One-Liner Fix (Run on Control Plane)

```bash
# Kill everything on port 3000 and restart Grafana
sudo kill -9 $(sudo lsof -t -i :3000) 2>/dev/null; \
kubectl delete pod -n observability $(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') --force --grace-period=0; \
sleep 5; \
kubectl get pods -n observability | grep grafana
```

## Verification

After fixing, verify Grafana is working:

```bash
# 1. Check pod is running
kubectl get pods -n observability | grep grafana
# Should show: 3/3 Running

# 2. Check port 3000 is in use by Grafana
sudo lsof -i :3000
# Should show grafana process

# 3. Test HTTP access
curl -I http://localhost:3000
# Should return HTTP 302 (redirect to login)

# 4. Check logs
kubectl logs -n observability $(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') -c grafana
```

## Common Issues

### Issue: Port still in use after killing process
**Solution:** Check for zombie processes or parent processes
```bash
# Find parent process
ps -ef | grep gpt-research
# Kill parent process too
```

### Issue: Grafana pod still in Init:Error
**Solution:** Check init container logs
```bash
kubectl logs -n observability <grafana-pod-name> -c grafana-sc-dashboard
kubectl logs -n observability <grafana-pod-name> -c grafana-sc-datasources
```

### Issue: Permission denied killing process
**Solution:** Use sudo
```bash
sudo kill -9 <PID>
```

## Quick Status Check

Run this command to see everything at once:

```bash
echo "=== Port 3000 Status ==="
sudo lsof -i :3000 2>/dev/null || echo "Port 3000 is free"
echo ""
echo "=== gpt-research Processes ==="
pgrep -fa gpt-research || echo "No gpt-research processes"
echo ""
echo "=== Grafana Pod Status ==="
kubectl get pods -n observability | grep grafana
echo ""
echo "=== Grafana Service ==="
kubectl get svc -n observability prometheus-grafana
```

## After Fix - Prevent gpt-research from Starting

If you don't want gpt-research to start automatically:

```bash
# Check if it's a systemd service
systemctl list-units --type=service | grep gpt

# If found, disable it
sudo systemctl disable gpt-research

# Check crontab
crontab -l | grep gpt

# Check user crontab
crontab -u julia -l | grep gpt

# Check system-wide cron
sudo grep -r "gpt-research" /etc/cron*

# Check if it's in startup applications (Ubuntu Desktop)
ls -la ~/.config/autostart/ | grep gpt
```

## Summary of Commands to Run

**Quick fix (copy and paste this into control plane terminal):**

```bash
# 1. Kill gpt-research and free port 3000
echo "Killing processes on port 3000..."
sudo pkill -9 -f gpt-research 2>/dev/null
sudo kill -9 $(sudo lsof -t -i :3000) 2>/dev/null
echo "Port 3000 freed"

# 2. Verify port is free
echo "Checking port 3000..."
sudo lsof -i :3000 || echo "✓ Port 3000 is free"

# 3. Restart Grafana pod
echo "Restarting Grafana pod..."
kubectl delete pod -n observability $(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') --force --grace-period=0

# 4. Wait and check status
echo "Waiting for pod to restart..."
sleep 15

# 5. Verify Grafana is running
echo "Grafana pod status:"
kubectl get pods -n observability | grep grafana

echo ""
echo "If pod shows 3/3 Running, Grafana is working!"
echo "Access Grafana at: http://192.168.12.112:3000"
```
