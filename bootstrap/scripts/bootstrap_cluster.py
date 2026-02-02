#!/usr/bin/env python3
"""
=============================================================================
Bootstrap Kubernetes Cluster Nodes via SSH
=============================================================================
Prepares all nodes for k3s installation with integrated service discovery.

Features:
- Automatic node discovery via mDNS (no static IPs required)
- Configuration loading from cluster-config.yaml
- SSH-based remote execution
- Bootstrap all nodes with required packages
- Install k3s server and agents
- Integration with cluster registry for IP tracking

Usage:
    python bootstrap_cluster.py --discover --bootstrap-only
    python bootstrap_cluster.py --config cluster-config.yaml
    python bootstrap_cluster.py --k3s-only --workers-only
=============================================================================
"""

import os
import sys
import time
import argparse
import socket
from pathlib import Path

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Try to import discovery module
try:
    from discover_cluster import discover_cluster, MDNSDiscovery
    from cluster_registry import ClusterRegistry
    DISCOVERY_AVAILABLE = True
except ImportError:
    DISCOVERY_AVAILABLE = False

# =============================================================================
# Default Configuration (used if no config file or discovery)
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "cluster-config.yaml"

DEFAULT_CONTROL_PLANE = {
    "name": "k8s-control",
    "host": "192.168.12.112",
    "user": "julia",
    "type": "control_plane",
    "arch": "amd64",
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

DEFAULT_WORKERS = [
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian", "type": "worker", "arch": "arm64"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian", "type": "worker", "arch": "arm64"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian", "type": "worker", "arch": "arm64"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian", "type": "worker", "arch": "arm64"},
]

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"
K3S_VERSION = "v1.29.0+k3s1"


# =============================================================================
# Configuration Loading
# =============================================================================

def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    if not YAML_AVAILABLE:
        print("[WARNING] PyYAML not available, using defaults")
        return {}
    
    if not config_path.exists():
        print(f"[WARNING] Config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[WARNING] Failed to load config: {e}")
        return {}


def config_to_nodes(config: dict) -> tuple[dict, list]:
    """Convert config dict to node definitions."""
    control_plane = DEFAULT_CONTROL_PLANE.copy()
    workers = []
    
    # Control plane
    cp_config = config.get("control_plane", {})
    if cp_config:
        control_plane = {
            "name": cp_config.get("hostname", "k8s-control"),
            "host": cp_config.get("ip", ""),
            "user": cp_config.get("user", "ubuntu"),
            "type": "control_plane",
            "arch": cp_config.get("arch", "amd64"),
            "k3s_args": [
                "--disable=traefik",
                "--disable=local-storage",
                "--flannel-backend=vxlan",
                "--write-kubeconfig-mode=644",
                f"--tls-san={cp_config.get('ip', '')}",
                f"--tls-san={cp_config.get('hostname', 'k8s-control')}",
                f"--tls-san={cp_config.get('hostname', 'k8s-control')}.local",
            ]
        }
    
    # Workers
    workers_config = config.get("workers", [])
    for w in workers_config:
        workers.append({
            "name": w.get("name", ""),
            "host": w.get("ip", ""),
            "user": w.get("user", "julian"),
            "type": "worker",
            "arch": w.get("arch", "arm64"),
        })
    
    return control_plane, workers if workers else DEFAULT_WORKERS


# =============================================================================
# Discovery Integration
# =============================================================================

def discover_nodes(config: dict) -> tuple[dict, list]:
    """Discover nodes using mDNS and update configuration."""
    if not DISCOVERY_AVAILABLE:
        print("[WARNING] Discovery module not available, using config file")
        return config_to_nodes(config)
    
    print("[INFO] Running node discovery...")
    
    # Get hostnames from config or defaults
    worker_hostnames = [w.get("name", "") for w in config.get("workers", [])]
    if not worker_hostnames:
        worker_hostnames = ["rpi1", "rpi2", "rpi3", "rpi4"]
    
    cp_hostname = config.get("control_plane", {}).get("hostname", "k8s-control")
    
    # Run discovery
    try:
        result = discover_cluster(
            method="auto",
            hostnames=worker_hostnames,
            control_plane_hostname=cp_hostname,
            use_cache=True
        )
        
        print(f"[INFO] Discovery completed in {result.discovery_time:.2f}s")
        print(f"[INFO] Found: {len(result.all_nodes())} nodes")
        
        # Convert to node format
        control_plane = None
        workers = []
        
        if result.control_plane:
            cp = result.control_plane
            control_plane = {
                "name": cp.hostname,
                "host": cp.ip,
                "user": config.get("control_plane", {}).get("user", "julia"),
                "type": "control_plane",
                "arch": cp.arch,
                "k3s_args": [
                    "--disable=traefik",
                    "--disable=local-storage",
                    "--flannel-backend=vxlan",
                    "--write-kubeconfig-mode=644",
                    f"--tls-san={cp.ip}",
                    f"--tls-san={cp.hostname}",
                    f"--tls-san={cp.hostname}.local",
                ]
            }
        
        for worker in result.workers:
            # Find matching config for user
            user = "julian"
            for w in config.get("workers", []):
                if w.get("name") == worker.hostname:
                    user = w.get("user", "julian")
                    break
            
            workers.append({
                "name": worker.hostname,
                "host": worker.ip,
                "user": user,
                "type": "worker",
                "arch": worker.arch,
            })
        
        if control_plane:
            return control_plane, workers
        else:
            print("[WARNING] Control plane not discovered, using config")
            cp, _ = config_to_nodes(config)
            return cp, workers
            
    except Exception as e:
        print(f"[WARNING] Discovery failed: {e}")
        return config_to_nodes(config)


def resolve_hostname_mdns(hostname: str) -> str:
    """Resolve hostname via mDNS."""
    if DISCOVERY_AVAILABLE:
        mdns = MDNSDiscovery()
        ip = mdns.resolve_hostname(hostname)
        if ip:
            return ip
    
    # Fallback to standard resolution
    try:
        return socket.gethostbyname(f"{hostname}.local")
    except socket.gaierror:
        return ""


# =============================================================================
# SSH Functions
# =============================================================================

def get_ssh_client(node, ssh_key=None, passphrase=None):
    """Create SSH client for a node."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    key = None
    key_path = ssh_key or SSH_KEY
    key_pass = passphrase or PASSPHRASE
    
    for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
        try:
            key = key_class.from_private_key_file(key_path, password=key_pass)
            break
        except (paramiko.ssh_exception.SSHException, FileNotFoundError):
            continue
    
    # Try connection with hostname.local if direct IP fails
    host = node["host"]
    try:
        client.connect(
            hostname=host,
            username=node["user"],
            pkey=key,
            timeout=30
        )
        return client
    except Exception as e:
        # Try mDNS resolution
        if not host.replace(".", "").isdigit():  # Not an IP
            pass  # Already a hostname
        else:
            # Try resolving hostname via mDNS
            mdns_ip = resolve_hostname_mdns(node["name"])
            if mdns_ip and mdns_ip != host:
                print(f"  [INFO] Using mDNS resolved IP: {mdns_ip}")
                client.connect(
                    hostname=mdns_ip,
                    username=node["user"],
                    pkey=key,
                    timeout=30
                )
                # Update node host for future use
                node["host"] = mdns_ip
                return client
        raise


def run_command(client, cmd, sudo=False, timeout=300):
    """Run a command and return output."""
    if sudo:
        cmd = f"sudo bash -c '{cmd}'"
    
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    return out, err, exit_code


# =============================================================================
# Bootstrap Functions
# =============================================================================

def bootstrap_ubuntu(node, dry_run=False):
    """Bootstrap Ubuntu control plane node."""
    print(f"\n{'='*60}")
    print(f"Bootstrapping {node['name']} (Ubuntu Control Plane)")
    print(f"{'='*60}")
    
    commands = [
        ("Disabling swap", "swapoff -a"),
        ("Removing swap from fstab", "sed -i '/\\bswap\\b/d' /etc/fstab"),
        ("Updating packages", "apt-get update -qq"),
        ("Installing prerequisites", "apt-get install -y -qq curl apt-transport-https ca-certificates software-properties-common avahi-daemon avahi-utils libnss-mdns"),
        ("Enabling Avahi", "systemctl enable --now avahi-daemon"),
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
        ("Installing prerequisites", "apt-get install -y -qq curl ca-certificates iptables avahi-daemon avahi-utils libnss-mdns"),
        ("Enabling Avahi", "systemctl enable --now avahi-daemon"),
        ("Enabling cgroups in cmdline", """
CMDLINE_FILE=""
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
elif [ -f /boot/cmdline.txt ]; then
    CMDLINE_FILE="/boot/cmdline.txt"
fi
if [ -n "$CMDLINE_FILE" ]; then
    cp "$CMDLINE_FILE" "${CMDLINE_FILE}.bak"
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
            
            with open("k3s_token.txt", "w") as f:
                f.write(out)
            print(f"  Token saved to k3s_token.txt")
        
        # Get kubeconfig
        out, err, code = run_command(client, "cat /etc/rancher/k3s/k3s.yaml", sudo=True)
        if code == 0:
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


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap Kubernetes cluster with service discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--config", "-c", type=Path, default=DEFAULT_CONFIG_PATH,
                        help=f"Path to cluster-config.yaml (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--discover", "-d", action="store_true",
                        help="Discover nodes via mDNS before bootstrapping")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without making changes")
    parser.add_argument("--bootstrap-only", action="store_true",
                        help="Only run bootstrap, skip k3s install")
    parser.add_argument("--k3s-only", action="store_true",
                        help="Only install k3s, skip bootstrap")
    parser.add_argument("--skip-reboot", action="store_true",
                        help="Skip reboot after bootstrap")
    parser.add_argument("--workers-only", action="store_true",
                        help="Only bootstrap/install on workers")
    parser.add_argument("--control-plane-only", action="store_true",
                        help="Only bootstrap/install on control plane")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Get nodes (either from discovery or config)
    if args.discover or config.get("discovery", {}).get("enabled", False):
        control_plane, workers = discover_nodes(config)
    else:
        control_plane, workers = config_to_nodes(config)
    
    # Fallback to defaults if needed
    if not control_plane.get("host"):
        control_plane = DEFAULT_CONTROL_PLANE
    if not workers:
        workers = DEFAULT_WORKERS
    
    print("=" * 70)
    print("Kubernetes Cluster Bootstrap & Installation")
    print("=" * 70)
    print()
    print(f"Control Plane: {control_plane['name']} ({control_plane['host']})")
    print(f"Workers:       {', '.join(w['name'] + '(' + w['host'] + ')' for w in workers)}")
    print(f"k3s Version:   {K3S_VERSION}")
    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")
    print()
    
    all_nodes = []
    if not args.workers_only:
        all_nodes.append(control_plane)
    if not args.control_plane_only:
        all_nodes.extend(workers)
    
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
        
        if needs_reboot and not args.skip_reboot and not args.dry_run:
            print("\n" + "-" * 60)
            print("Rebooting worker nodes to enable cgroups...")
            print("-" * 60)
            
            for node in needs_reboot:
                reboot_node(node, args.dry_run)
            
            time.sleep(10)
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
    
    if not args.workers_only:
        if not install_k3s_server(control_plane, args.dry_run):
            print("[ERROR] Failed to install k3s server")
            return 1
    
    token = None
    # Use mDNS hostname for server URL (more resilient to IP changes)
    server_url = f"https://{control_plane['name']}.local:6443"
    
    if not args.control_plane_only:
        if os.path.exists("k3s_token.txt"):
            with open("k3s_token.txt", "r") as f:
                token = f.read().strip()
        else:
            print("[ERROR] k3s token not found. Run control plane install first.")
            return 1
        
        for worker in workers:
            if not install_k3s_agent(worker, server_url, token, args.dry_run):
                print(f"[WARNING] Failed to install k3s agent on {worker['name']}")
    
    print("\n" + "=" * 70)
    print("Installation Complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Set KUBECONFIG: set KUBECONFIG=%CD%\\kubeconfig.yaml")
    print("  2. Verify cluster: kubectl get nodes")
    print("  3. Deploy services: kubectl apply -k kubernetes/")
    print()
    print("Discovery note: Nodes can now be accessed via hostname.local")
    print(f"  Example: ssh {control_plane['user']}@{control_plane['name']}.local")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
