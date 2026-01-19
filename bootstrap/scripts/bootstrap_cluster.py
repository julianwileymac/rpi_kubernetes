#!/usr/bin/env python3
"""
Bootstrap Kubernetes cluster nodes via SSH.
This script prepares all nodes for k3s installation by:
1. Disabling swap
2. Enabling cgroups (for Raspberry Pi nodes)
3. Installing required packages
4. Optionally installing k3s
"""

import os
import sys
import time
import argparse

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

# Cluster configuration from ansible/inventory/cluster.yml
CONTROL_PLANE = {
    "name": "k8s-control",
    "host": "192.168.12.112", 
    "user": "julia",
    "type": "control_plane",
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
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian", "type": "worker"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian", "type": "worker"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian", "type": "worker"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian", "type": "worker"},
]

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"
K3S_VERSION = "v1.29.0+k3s1"


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


def run_command(client, cmd, sudo=False, timeout=300):
    """Run a command and return output."""
    if sudo:
        cmd = f"sudo bash -c '{cmd}'"
    
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    return out, err, exit_code


def bootstrap_ubuntu(node, dry_run=False):
    """Bootstrap Ubuntu control plane node."""
    print(f"\n{'='*60}")
    print(f"Bootstrapping {node['name']} (Ubuntu Control Plane)")
    print(f"{'='*60}")
    
    commands = [
        ("Disabling swap", "swapoff -a"),
        ("Removing swap from fstab", "sed -i '/\\bswap\\b/d' /etc/fstab"),
        ("Updating packages", "apt-get update -qq"),
        ("Installing prerequisites", "apt-get install -y -qq curl apt-transport-https ca-certificates software-properties-common"),
        ("Loading br_netfilter module", "modprobe br_netfilter"),
        ("Persisting br_netfilter", "echo 'br_netfilter' > /etc/modules-load.d/k8s.conf"),
        ("Setting sysctl params", """cat > /etc/sysctl.d/k8s.conf << 'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF"""),
        ("Applying sysctl", "sysctl --system > /dev/null 2>&1"),
    ]
    
    if dry_run:
        print("[DRY RUN] Would execute:")
        for desc, cmd in commands:
            print(f"  - {desc}")
        return True
    
    try:
        client = get_ssh_client(node)
        
        for desc, cmd in commands:
            print(f"  {desc}...", end=" ", flush=True)
            out, err, code = run_command(client, cmd, sudo=True)
            if code != 0:
                print(f"[FAILED]")
                print(f"    Error: {err}")
                return False
            print("[OK]")
        
        client.close()
        print(f"\n[SUCCESS] {node['name']} bootstrapped successfully!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to bootstrap {node['name']}: {e}")
        return False


def bootstrap_rpi(node, dry_run=False):
    """Bootstrap Raspberry Pi worker node."""
    print(f"\n{'='*60}")
    print(f"Bootstrapping {node['name']} (Raspberry Pi Worker)")
    print(f"{'='*60}")
    
    commands = [
        ("Disabling swap", "dphys-swapfile swapoff 2>/dev/null || swapoff -a"),
        ("Disabling swap service", "systemctl disable dphys-swapfile 2>/dev/null || true"),
        ("Removing swap from fstab", "sed -i '/\\bswap\\b/d' /etc/fstab"),
        ("Updating packages", "apt-get update -qq"),
        ("Installing prerequisites", "apt-get install -y -qq curl ca-certificates iptables"),
        ("Enabling cgroups in cmdline", """
CMDLINE_FILE=""
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
elif [ -f /boot/cmdline.txt ]; then
    CMDLINE_FILE="/boot/cmdline.txt"
fi
if [ -n "$CMDLINE_FILE" ]; then
    # Backup
    cp "$CMDLINE_FILE" "${CMDLINE_FILE}.bak"
    # Add cgroup params if not present
    if ! grep -q "cgroup_memory=1" "$CMDLINE_FILE"; then
        sed -i 's/$/ cgroup_memory=1 cgroup_enable=memory/' "$CMDLINE_FILE"
    fi
fi
"""),
        ("Loading br_netfilter module", "modprobe br_netfilter 2>/dev/null || true"),
        ("Persisting br_netfilter", "echo 'br_netfilter' > /etc/modules-load.d/k8s.conf"),
        ("Setting sysctl params", """cat > /etc/sysctl.d/k8s.conf << 'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF"""),
        ("Applying sysctl", "sysctl --system > /dev/null 2>&1 || true"),
    ]
    
    if dry_run:
        print("[DRY RUN] Would execute:")
        for desc, cmd in commands:
            print(f"  - {desc}")
        return True
    
    try:
        client = get_ssh_client(node)
        
        for desc, cmd in commands:
            print(f"  {desc}...", end=" ", flush=True)
            out, err, code = run_command(client, cmd, sudo=True)
            if code != 0 and "already" not in err.lower():
                print(f"[WARN]")
                if err:
                    print(f"    Note: {err[:100]}")
            else:
                print("[OK]")
        
        client.close()
        print(f"\n[SUCCESS] {node['name']} bootstrapped successfully!")
        print(f"[NOTE] Reboot required to enable cgroups")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to bootstrap {node['name']}: {e}")
        return False


def install_k3s_server(node, dry_run=False):
    """Install k3s server on control plane."""
    print(f"\n{'='*60}")
    print(f"Installing k3s Server on {node['name']}")
    print(f"{'='*60}")
    
    k3s_args = " ".join(node.get("k3s_args", []))
    install_cmd = f"curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={K3S_VERSION} sh -s - server {k3s_args}"
    
    if dry_run:
        print(f"[DRY RUN] Would run: {install_cmd}")
        return True
    
    try:
        client = get_ssh_client(node)
        
        print(f"  Downloading and installing k3s {K3S_VERSION}...")
        print(f"  This may take a few minutes...")
        
        out, err, code = run_command(client, install_cmd, sudo=True, timeout=600)
        
        if code != 0:
            print(f"[FAILED] Exit code: {code}")
            print(f"Error: {err}")
            return False
        
        print("  [OK] k3s installed")
        
        # Wait for k3s to start
        print("  Waiting for k3s to start...", end=" ", flush=True)
        time.sleep(10)
        
        out, err, code = run_command(client, "systemctl is-active k3s", sudo=False)
        if out == "active":
            print("[OK]")
        else:
            print(f"[WARN] Status: {out}")
        
        # Get node token for workers
        out, err, code = run_command(client, "cat /var/lib/rancher/k3s/server/node-token", sudo=True)
        if code == 0:
            print(f"\n  [INFO] Node token retrieved successfully")
            print(f"  Token: {out[:20]}...{out[-20:]}")
            
            # Save token for workers
            with open("k3s_token.txt", "w") as f:
                f.write(out)
            print(f"  Token saved to k3s_token.txt")
        
        # Get kubeconfig
        out, err, code = run_command(client, "cat /etc/rancher/k3s/k3s.yaml", sudo=True)
        if code == 0:
            # Replace localhost with actual IP
            kubeconfig = out.replace("127.0.0.1", node["host"]).replace("localhost", node["host"])
            with open("kubeconfig.yaml", "w") as f:
                f.write(kubeconfig)
            print(f"  Kubeconfig saved to kubeconfig.yaml")
        
        client.close()
        print(f"\n[SUCCESS] k3s server installed on {node['name']}!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to install k3s on {node['name']}: {e}")
        return False


def install_k3s_agent(node, server_url, token, dry_run=False):
    """Install k3s agent on worker node."""
    print(f"\n{'='*60}")
    print(f"Installing k3s Agent on {node['name']}")
    print(f"{'='*60}")
    
    install_cmd = f"curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={K3S_VERSION} K3S_URL={server_url} K3S_TOKEN={token} sh -s - agent"
    
    if dry_run:
        print(f"[DRY RUN] Would run k3s agent install")
        return True
    
    try:
        client = get_ssh_client(node)
        
        print(f"  Downloading and installing k3s agent {K3S_VERSION}...")
        
        out, err, code = run_command(client, install_cmd, sudo=True, timeout=600)
        
        if code != 0:
            print(f"[FAILED] Exit code: {code}")
            print(f"Error: {err}")
            return False
        
        print("  [OK] k3s agent installed")
        
        # Wait and check status
        time.sleep(5)
        out, err, code = run_command(client, "systemctl is-active k3s-agent", sudo=False)
        print(f"  Agent status: {out}")
        
        client.close()
        print(f"\n[SUCCESS] k3s agent installed on {node['name']}!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to install k3s agent on {node['name']}: {e}")
        return False


def reboot_node(node, dry_run=False):
    """Reboot a node."""
    if dry_run:
        print(f"[DRY RUN] Would reboot {node['name']}")
        return True
    
    try:
        client = get_ssh_client(node)
        print(f"  Rebooting {node['name']}...", end=" ", flush=True)
        run_command(client, "reboot", sudo=True)
        print("[INITIATED]")
        client.close()
        return True
    except Exception as e:
        # Connection closed is expected during reboot
        if "Socket is closed" in str(e) or "Connection reset" in str(e):
            print("[INITIATED]")
            return True
        print(f"[ERROR] {e}")
        return False


def wait_for_nodes(nodes, timeout=180):
    """Wait for nodes to come back online."""
    print(f"\nWaiting for nodes to come back online (timeout: {timeout}s)...")
    
    start_time = time.time()
    pending = list(nodes)
    
    while pending and (time.time() - start_time) < timeout:
        for node in list(pending):
            try:
                client = get_ssh_client(node)
                client.close()
                print(f"  {node['name']} is back online")
                pending.remove(node)
            except:
                pass
        
        if pending:
            time.sleep(5)
    
    if pending:
        print(f"[WARNING] Nodes still not reachable: {[n['name'] for n in pending]}")
        return False
    
    print("[SUCCESS] All nodes are back online!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Kubernetes cluster")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--bootstrap-only", action="store_true", help="Only run bootstrap, skip k3s install")
    parser.add_argument("--k3s-only", action="store_true", help="Only install k3s, skip bootstrap")
    parser.add_argument("--skip-reboot", action="store_true", help="Skip reboot after bootstrap")
    parser.add_argument("--workers-only", action="store_true", help="Only bootstrap/install on workers")
    parser.add_argument("--control-plane-only", action="store_true", help="Only bootstrap/install on control plane")
    args = parser.parse_args()
    
    print("=" * 70)
    print("Kubernetes Cluster Bootstrap & Installation")
    print("=" * 70)
    print()
    print(f"Control Plane: {CONTROL_PLANE['name']} ({CONTROL_PLANE['host']})")
    print(f"Workers:       {', '.join(w['name'] for w in WORKERS)}")
    print(f"k3s Version:   {K3S_VERSION}")
    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")
    print()
    
    all_nodes = []
    if not args.workers_only:
        all_nodes.append(CONTROL_PLANE)
    if not args.control_plane_only:
        all_nodes.extend(WORKERS)
    
    # Phase 1: Bootstrap
    if not args.k3s_only:
        print("\n" + "=" * 70)
        print("PHASE 1: Bootstrap Nodes")
        print("=" * 70)
        
        bootstrap_success = True
        needs_reboot = []
        
        for node in all_nodes:
            if node["type"] == "control_plane":
                success = bootstrap_ubuntu(node, args.dry_run)
            else:
                success = bootstrap_rpi(node, args.dry_run)
                if success:
                    needs_reboot.append(node)
            
            if not success:
                bootstrap_success = False
        
        # Reboot workers if needed (for cgroups)
        if needs_reboot and not args.skip_reboot and not args.dry_run:
            print("\n" + "-" * 60)
            print("Rebooting worker nodes to enable cgroups...")
            print("-" * 60)
            
            for node in needs_reboot:
                reboot_node(node, args.dry_run)
            
            # Wait for nodes to come back
            time.sleep(10)  # Initial wait
            if not wait_for_nodes(needs_reboot):
                print("[ERROR] Some nodes didn't come back online")
                return 1
    
    if args.bootstrap_only:
        print("\n[INFO] Bootstrap complete. Run with --k3s-only to install k3s.")
        return 0
    
    # Phase 2: Install k3s
    print("\n" + "=" * 70)
    print("PHASE 2: Install k3s")
    print("=" * 70)
    
    # Install k3s server on control plane
    if not args.workers_only:
        if not install_k3s_server(CONTROL_PLANE, args.dry_run):
            print("[ERROR] Failed to install k3s server")
            return 1
    
    # Read token for workers
    token = None
    server_url = f"https://{CONTROL_PLANE['host']}:6443"
    
    if not args.control_plane_only:
        if os.path.exists("k3s_token.txt"):
            with open("k3s_token.txt", "r") as f:
                token = f.read().strip()
        else:
            print("[ERROR] k3s token not found. Run control plane install first.")
            return 1
        
        # Install k3s agents on workers
        for worker in WORKERS:
            if not install_k3s_agent(worker, server_url, token, args.dry_run):
                print(f"[WARNING] Failed to install k3s agent on {worker['name']}")
    
    # Final summary
    print("\n" + "=" * 70)
    print("Installation Complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Set KUBECONFIG: set KUBECONFIG=%CD%\\kubeconfig.yaml")
    print("  2. Verify cluster: kubectl get nodes")
    print("  3. Deploy services: kubectl apply -k kubernetes/")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
