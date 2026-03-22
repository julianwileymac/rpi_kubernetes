#!/usr/bin/env python3
"""
Diagnose and fix Grafana port 3000 conflict by stopping gpt-research process.
"""

import os
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

# Configuration
CONTROL_PLANE = {
    "host": "192.168.12.112",
    "user": "julia",
    "name": "k8s-control"
}

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"

def get_ssh_client(node):
    """Create SSH client for a node."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    key = None
    for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
        try:
            key = key_class.from_private_key_file(SSH_KEY, password=PASSPHRASE)
            break
        except paramiko.ssh_exception.SSHException:
            continue
    
    client.connect(
        hostname=node["host"],
        username=node["user"],
        pkey=key,
        timeout=30
    )
    return client

def run_command(client, cmd, sudo=False):
    """Run a command and return output."""
    if sudo:
        cmd = f"sudo bash -c '{cmd}'"
    
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    return out, err, exit_code

def main():
    print("="*70)
    print("Diagnosing Port 3000 Conflict (Grafana vs gpt-research)")
    print("="*70)
    print()
    
    try:
        client = get_ssh_client(CONTROL_PLANE)
        
        # Check what's on port 3000
        print("[1] Checking port 3000...")
        out, err, code = run_command(client, "lsof -i :3000 -n -P 2>/dev/null || ss -tulpn | grep :3000", sudo=True)
        if out:
            print("    Port 3000 is in use:")
            print("    " + out.replace("\n", "\n    "))
        else:
            print("    Port 3000 appears to be free")
        print()
        
        # Find gpt-research processes
        print("[2] Finding gpt-research processes...")
        out, err, code = run_command(client, "ps aux | grep -i gpt-research | grep -v grep")
        
        if out:
            print("    Found gpt-research process(es):")
            print("    " + out.replace("\n", "\n    "))
            print()
            
            # Extract PIDs
            pids = []
            for line in out.split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        pids.append(pid)
                    except ValueError:
                        continue
            
            if pids:
                print(f"[3] Found {len(pids)} PID(s): {', '.join(map(str, pids))}")
                print("    Terminating processes...")
                
                for pid in pids:
                    out, err, code = run_command(client, f"kill {pid}", sudo=True)
                    if code == 0:
                        print(f"    ✓ Killed PID {pid}")
                    else:
                        print(f"    Trying SIGKILL for PID {pid}...")
                        out, err, code = run_command(client, f"kill -9 {pid}", sudo=True)
                        if code == 0:
                            print(f"    ✓ Force killed PID {pid}")
                        else:
                            print(f"    ✗ Failed to kill PID {pid}: {err}")
                
                print()
                print("[4] Verifying port 3000 is now free...")
                out, err, code = run_command(client, "lsof -i :3000 -n -P 2>/dev/null || ss -tulpn | grep :3000", sudo=True)
                if out:
                    print("    ⚠ Port 3000 still in use:")
                    print("    " + out.replace("\n", "\n    "))
                else:
                    print("    ✓ Port 3000 is now free!")
            else:
                print("    Could not extract PIDs from process list")
        else:
            print("    No gpt-research processes found")
        
        print()
        
        # Check for other processes on port 3000
        print("[5] Checking for any process on port 3000...")
        out, err, code = run_command(client, "lsof -i :3000 -t", sudo=True)
        if out:
            pids = out.strip().split('\n')
            print(f"    Found process(es) on port 3000: {', '.join(pids)}")
            print("    Getting process details...")
            for pid in pids:
                out, err, code = run_command(client, f"ps -p {pid} -o pid,ppid,cmd --no-headers", sudo=True)
                if out:
                    print(f"    PID {pid}: {out}")
            
            print()
            response = input("    Kill these processes? [y/N]: ")
            if response.lower() == 'y':
                for pid in pids:
                    run_command(client, f"kill -9 {pid}", sudo=True)
                    print(f"    ✓ Killed PID {pid}")
        else:
            print("    ✓ No processes found on port 3000")
        
        print()
        print("[6] Checking Grafana pod status...")
        out, err, code = run_command(client, "kubectl get pods -A | grep grafana")
        if out:
            print("    Grafana pods:")
            print("    " + out.replace("\n", "\n    "))
            
            # Check if any pods are in error/crashloop
            if "Error" in out or "CrashLoop" in out or "0/" in out:
                print()
                print("    Grafana pod(s) appear to have issues. Restarting...")
                # Get pod names
                for line in out.split('\n'):
                    parts = line.split()
                    if len(parts) >= 2:
                        namespace = parts[0]
                        pod_name = parts[1]
                        print(f"    Restarting {pod_name} in namespace {namespace}...")
                        run_command(client, f"kubectl delete pod {pod_name} -n {namespace}")
        else:
            print("    No Grafana pods found")
        
        print()
        print("="*70)
        print("Diagnosis Complete!")
        print("="*70)
        
        client.close()
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
