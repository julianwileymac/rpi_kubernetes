#!/usr/bin/env python3
"""
Install k3s on the cluster.
1. Install k3s server on control plane
2. Get the node token
3. Install k3s agents on workers
"""

import os
import sys
import time
import argparse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

# Cluster configuration
CONTROL_PLANE = {
    "name": "k8s-control",
    "host": "192.168.12.112", 
    "user": "julia",
    "k3s_args": [
        "--disable=traefik",
        "--disable=local-storage", 
        "--flannel-backend=vxlan",
        "--write-kubeconfig-mode=644",
        "--tls-san=192.168.12.112",
        "--tls-san=k8s-control",
        "--tls-san=k8s-control.local",
    ]
}

WORKERS = [
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian"},
]

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"
K3S_VERSION = "v1.29.0+k3s1"


def get_ssh_client(node):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    key = None
    for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
        try:
            key = key_class.from_private_key_file(SSH_KEY, password=PASSPHRASE)
            break
        except:
            continue
    
    client.connect(hostname=node["host"], username=node["user"], pkey=key, timeout=30)
    return client


def run(client, cmd, timeout=600):
    """Run command and return output."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err, exit_code


def install_k3s_server(node):
    """Install k3s server on control plane."""
    print(f"\n{'='*70}")
    print(f"Installing k3s Server on {node['name']} ({node['host']})")
    print(f"{'='*70}")
    
    k3s_args = " ".join(node.get("k3s_args", []))
    install_cmd = f"curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={K3S_VERSION} sh -s - server {k3s_args}"
    
    try:
        client = get_ssh_client(node)
        
        # Check if already installed
        out, err, code = run(client, "which k3s")
        if code == 0:
            print("  k3s is already installed, checking status...")
            out, err, code = run(client, "sudo systemctl is-active k3s")
            if out == "active":
                print("  [OK] k3s server is already running!")
                # Get token
                out, err, code = run(client, "sudo cat /var/lib/rancher/k3s/server/node-token")
                if code == 0:
                    return True, out.strip()
                return True, None
        
        print(f"  Installing k3s {K3S_VERSION}...")
        print(f"  Command: curl -sfL https://get.k3s.io | ... server {k3s_args[:50]}...")
        print("  This may take 2-5 minutes...")
        
        out, err, code = run(client, f"sudo bash -c '{install_cmd}'", timeout=600)
        
        if code != 0:
            print(f"  [FAILED] Exit code: {code}")
            if err:
                print(f"  Error: {err[:500]}")
            return False, None
        
        print("  [OK] k3s installed")
        
        # Wait for k3s to start
        print("  Waiting for k3s to start...", end=" ", flush=True)
        for i in range(30):
            time.sleep(2)
            out, err, code = run(client, "sudo systemctl is-active k3s")
            if out == "active":
                print("[OK]")
                break
        else:
            print("[TIMEOUT]")
            out, err, code = run(client, "sudo journalctl -u k3s --no-pager -n 20")
            print(f"  Recent logs:\n{out}")
        
        # Get node token
        print("  Retrieving node token...", end=" ", flush=True)
        out, err, code = run(client, "sudo cat /var/lib/rancher/k3s/server/node-token")
        if code == 0:
            token = out.strip()
            print("[OK]")
            
            # Save token
            with open("k3s_token.txt", "w") as f:
                f.write(token)
            print(f"  Token saved to k3s_token.txt")
        else:
            print(f"[FAILED] {err}")
            token = None
        
        # Get kubeconfig
        print("  Retrieving kubeconfig...", end=" ", flush=True)
        out, err, code = run(client, "sudo cat /etc/rancher/k3s/k3s.yaml")
        if code == 0:
            # Replace localhost with actual IP
            kubeconfig = out.replace("127.0.0.1", node["host"]).replace("localhost", node["host"])
            with open("kubeconfig.yaml", "w") as f:
                f.write(kubeconfig)
            print("[OK]")
            print("  Kubeconfig saved to kubeconfig.yaml")
        else:
            print(f"[FAILED] {err}")
        
        # Check nodes
        print("  Checking cluster status...", end=" ", flush=True)
        out, err, code = run(client, "sudo k3s kubectl get nodes")
        if code == 0:
            print("[OK]")
            print(f"\n  {out}")
        else:
            print(f"[FAILED] {err}")
        
        client.close()
        print(f"\n[SUCCESS] k3s server installed on {node['name']}!")
        return True, token
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False, None


def install_k3s_agent(node, server_url, token):
    """Install k3s agent on worker node."""
    print(f"\n{'='*70}")
    print(f"Installing k3s Agent on {node['name']} ({node['host']})")
    print(f"{'='*70}")
    
    install_cmd = f"curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={K3S_VERSION} K3S_URL={server_url} K3S_TOKEN={token} sh -s - agent"
    
    try:
        client = get_ssh_client(node)
        
        # Check if already installed
        out, err, code = run(client, "which k3s")
        if code == 0:
            out, err, code = run(client, "sudo systemctl is-active k3s-agent")
            if out == "active":
                print("  [OK] k3s agent is already running!")
                client.close()
                return True
        
        print(f"  Installing k3s agent {K3S_VERSION}...")
        print("  This may take 1-2 minutes...")
        
        out, err, code = run(client, f"sudo bash -c '{install_cmd}'", timeout=300)
        
        if code != 0:
            print(f"  [FAILED] Exit code: {code}")
            if err:
                print(f"  Error: {err[:300]}")
            client.close()
            return False
        
        print("  [OK] k3s agent installed")
        
        # Wait for agent to start
        print("  Waiting for agent to start...", end=" ", flush=True)
        time.sleep(5)
        out, err, code = run(client, "sudo systemctl is-active k3s-agent")
        if out == "active":
            print("[OK]")
        else:
            print(f"[{out}]")
        
        client.close()
        print(f"[SUCCESS] k3s agent installed on {node['name']}!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


def verify_cluster():
    """Verify all nodes have joined the cluster."""
    print(f"\n{'='*70}")
    print("Verifying Cluster")
    print(f"{'='*70}")
    
    try:
        client = get_ssh_client(CONTROL_PLANE)
        
        print("  Waiting for all nodes to be Ready...", flush=True)
        for attempt in range(12):  # 2 minutes max
            out, err, code = run(client, "sudo k3s kubectl get nodes -o wide")
            if code == 0:
                lines = out.strip().split('\n')
                ready_count = sum(1 for line in lines[1:] if 'Ready' in line and 'NotReady' not in line)
                total_expected = 1 + len(WORKERS)  # control plane + workers
                
                print(f"\n  Nodes Ready: {ready_count}/{total_expected}")
                print(f"  {out}")
                
                if ready_count >= total_expected:
                    break
            
            time.sleep(10)
        
        client.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Install k3s on cluster")
    parser.add_argument("--server-only", action="store_true", help="Only install k3s server")
    parser.add_argument("--agents-only", action="store_true", help="Only install k3s agents")
    parser.add_argument("--token", type=str, help="k3s token (for agents-only)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("k3s Cluster Installation")
    print("=" * 70)
    print()
    print(f"Control Plane: {CONTROL_PLANE['name']} ({CONTROL_PLANE['host']})")
    print(f"Workers:       {', '.join(w['name'] for w in WORKERS)}")
    print(f"k3s Version:   {K3S_VERSION}")
    print()
    
    token = args.token
    server_url = f"https://{CONTROL_PLANE['host']}:6443"
    
    # Install k3s server
    if not args.agents_only:
        success, token = install_k3s_server(CONTROL_PLANE)
        if not success:
            print("\n[ERROR] Failed to install k3s server. Aborting.")
            return 1
    
    if args.server_only:
        print("\n[INFO] Server installed. Run with --agents-only --token <token> to install agents.")
        return 0
    
    # Get token if not provided
    if not token:
        if os.path.exists("k3s_token.txt"):
            with open("k3s_token.txt", "r") as f:
                token = f.read().strip()
        else:
            print("\n[ERROR] No k3s token available. Run server install first.")
            return 1
    
    # Install k3s agents on workers
    print(f"\n{'='*70}")
    print("Installing k3s Agents on Workers")
    print(f"{'='*70}")
    
    failed_workers = []
    for worker in WORKERS:
        if not install_k3s_agent(worker, server_url, token):
            failed_workers.append(worker['name'])
    
    if failed_workers:
        print(f"\n[WARNING] Failed to install on: {', '.join(failed_workers)}")
    
    # Verify cluster
    verify_cluster()
    
    # Final summary
    print("\n" + "=" * 70)
    print("Installation Complete!")
    print("=" * 70)
    print()
    print("To use kubectl from your workstation:")
    print()
    print("  # Set KUBECONFIG environment variable")
    print(f"  $env:KUBECONFIG = '{os.path.abspath('kubeconfig.yaml')}'")
    print()
    print("  # Or copy to default location")
    print("  copy kubeconfig.yaml $HOME\\.kube\\config")
    print()
    print("  # Verify cluster")
    print("  kubectl get nodes")
    print("  kubectl get pods -A")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
