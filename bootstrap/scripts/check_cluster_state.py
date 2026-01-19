#!/usr/bin/env python3
"""Check the current state of cluster nodes."""

import os
import sys

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

# Cluster configuration
NODES = [
    {"name": "k8s-control", "host": "192.168.12.112", "user": "julia", "type": "control_plane"},
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian", "type": "worker"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian", "type": "worker"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian", "type": "worker"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian", "type": "worker"},
]

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
        timeout=10
    )
    return client


def run_command(client, cmd):
    """Run a command and return output."""
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode().strip(), stderr.read().decode().strip(), stdout.channel.recv_exit_status()


def check_node_state(node):
    """Check the state of a node."""
    results = {}
    
    try:
        client = get_ssh_client(node)
        
        # Check hostname
        out, err, code = run_command(client, "hostname")
        results["hostname"] = out
        
        # Check architecture
        out, err, code = run_command(client, "uname -m")
        results["arch"] = out
        
        # Check swap
        out, err, code = run_command(client, "free -h | grep -i swap | awk '{print $2}'")
        swap_total = out.strip()
        results["swap_disabled"] = swap_total in ["0B", "0", ""]
        results["swap_value"] = swap_total
        
        # Check cgroups (for RPi) - support both cgroup v1 and v2
        if node["type"] == "worker":
            # Check for cgroup v2 (unified) with memory controller
            out, err, code = run_command(client, "test -f /sys/fs/cgroup/memory.stat && echo 'v2' || echo 'v1'")
            cgroup_version = out.strip()
            
            if cgroup_version == "v2":
                # cgroup v2 - check if memory controller is available
                out, err, code = run_command(client, "cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null")
                results["cgroups_memory"] = "memory" in out or True  # memory files exist means it's working
                results["cgroup_version"] = "v2"
            else:
                # cgroup v1 - check /proc/cgroups
                out, err, code = run_command(client, "cat /proc/cgroups | grep memory | awk '{print $4}'")
                results["cgroups_memory"] = out == "1"
                results["cgroup_version"] = "v1"
        
        # Check k3s status
        out, err, code = run_command(client, "which k3s 2>/dev/null")
        results["k3s_installed"] = code == 0
        
        if node["type"] == "control_plane":
            out, err, code = run_command(client, "systemctl is-active k3s 2>/dev/null")
            results["k3s_running"] = out == "active"
        else:
            out, err, code = run_command(client, "systemctl is-active k3s-agent 2>/dev/null")
            results["k3s_running"] = out == "active"
        
        # Check Python
        out, err, code = run_command(client, "which python3")
        results["python3"] = code == 0
        
        # Check if external storage is mounted (for workers)
        if node["type"] == "worker":
            out, err, code = run_command(client, "df -h /mnt/storage 2>/dev/null | tail -1")
            results["external_storage"] = "/mnt/storage" in out if out else False
            results["storage_info"] = out if out else "Not mounted"
        
        client.close()
        results["reachable"] = True
        
    except Exception as e:
        results["reachable"] = False
        results["error"] = str(e)
    
    return results


def main():
    print("=" * 80)
    print("Cluster Node State Check")
    print("=" * 80)
    print()
    
    all_ready = True
    node_states = []
    
    for node in NODES:
        print(f"Checking {node['name']} ({node['host']})...")
        state = check_node_state(node)
        node_states.append((node, state))
        
        if not state.get("reachable"):
            print(f"  [ERROR] Not reachable: {state.get('error')}")
            all_ready = False
            continue
        
        print(f"  Hostname:      {state.get('hostname')}")
        print(f"  Architecture:  {state.get('arch')}")
        print(f"  Swap disabled: {'Yes' if state.get('swap_disabled') else 'No (' + state.get('swap_value', '?') + ')'}")
        
        if node["type"] == "worker":
            print(f"  cgroups:       {'Enabled' if state.get('cgroups_memory') else 'Not enabled'}")
            if state.get("external_storage"):
                print(f"  Storage:       Mounted")
            else:
                print(f"  Storage:       {state.get('storage_info', 'Not mounted')}")
        
        print(f"  k3s installed: {'Yes' if state.get('k3s_installed') else 'No'}")
        print(f"  k3s running:   {'Yes' if state.get('k3s_running') else 'No'}")
        print()
        
        # Check if node needs bootstrap
        needs_bootstrap = False
        if not state.get("swap_disabled"):
            needs_bootstrap = True
        if node["type"] == "worker" and not state.get("cgroups_memory"):
            needs_bootstrap = True
        
        if needs_bootstrap:
            all_ready = False
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print()
    
    k3s_installed = sum(1 for n, s in node_states if s.get("k3s_installed"))
    k3s_running = sum(1 for n, s in node_states if s.get("k3s_running"))
    swap_ok = sum(1 for n, s in node_states if s.get("swap_disabled"))
    
    print(f"Nodes reachable:    {sum(1 for n, s in node_states if s.get('reachable'))}/{len(NODES)}")
    print(f"Swap disabled:      {swap_ok}/{len(NODES)}")
    print(f"k3s installed:      {k3s_installed}/{len(NODES)}")
    print(f"k3s running:        {k3s_running}/{len(NODES)}")
    print()
    
    # Determine next steps
    if k3s_running == len(NODES):
        print("[SUCCESS] Cluster is fully operational!")
        print()
        print("Next step: Configure kubectl and deploy services")
        print("  scp julia@192.168.12.112:~/.kube/config ~/.kube/config-rpi-cluster")
        print("  export KUBECONFIG=~/.kube/config-rpi-cluster")
        print("  kubectl get nodes")
        return 0
    elif k3s_installed > 0 and k3s_running < len(NODES):
        print("[WARNING] k3s is installed but not fully running")
        print()
        print("Check k3s logs:")
        print("  ssh julia@192.168.12.112 'sudo journalctl -u k3s -f'")
        return 1
    elif swap_ok < len(NODES):
        print("[ACTION REQUIRED] Some nodes need bootstrap (swap not disabled)")
        print()
        print("Run bootstrap on nodes that need it:")
        for node, state in node_states:
            if not state.get("swap_disabled"):
                print(f"  - {node['name']}: needs bootstrap")
        return 1
    else:
        print("[ACTION REQUIRED] Ready for k3s installation")
        print()
        print("Next steps:")
        print("  1. Install k3s on control plane first")
        print("  2. Then install k3s agent on workers")
        return 0


if __name__ == "__main__":
    sys.exit(main())
