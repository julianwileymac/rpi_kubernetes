#!/usr/bin/env python3
"""Fix bootstrap issues on cluster nodes."""

import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

# Cluster configuration
CONTROL_PLANE = {"name": "k8s-control", "host": "192.168.12.112", "user": "julia", "type": "control_plane"}
WORKERS = [
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian", "type": "worker"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian", "type": "worker"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian", "type": "worker"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian", "type": "worker"},
]

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"


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


def run(client, cmd, sudo=False, timeout=120):
    if sudo:
        cmd = f"sudo {cmd}"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err, exit_code


def fix_rpi_worker(node):
    """Fix Raspberry Pi worker node."""
    print(f"\n{'='*60}")
    print(f"Fixing {node['name']} ({node['host']})")
    print(f"{'='*60}")
    
    try:
        client = get_ssh_client(node)
        
        # Step 1: Disable zram swap
        print("  Disabling zram swap...", end=" ", flush=True)
        
        # Stop all swap
        run(client, "swapoff -a", sudo=True)
        
        # Disable zram service
        run(client, "systemctl stop zramswap 2>/dev/null || true", sudo=True)
        run(client, "systemctl disable zramswap 2>/dev/null || true", sudo=True)
        
        # Disable swap via systemd
        out, err, code = run(client, "systemctl list-units --type=swap --all --no-legend | awk '{print $1}'", sudo=False)
        if out:
            for unit in out.split('\n'):
                unit = unit.strip()
                if unit and '.swap' in unit:
                    run(client, f"systemctl stop {unit} 2>/dev/null || true", sudo=True)
                    run(client, f"systemctl mask {unit} 2>/dev/null || true", sudo=True)
        
        # Disable rpi-swap-file 
        run(client, "systemctl stop rpi-swap-file 2>/dev/null || true", sudo=True)
        run(client, "systemctl disable rpi-swap-file 2>/dev/null || true", sudo=True)
        
        # Remove zram config
        run(client, "rm -f /etc/systemd/zram-generator.conf 2>/dev/null || true", sudo=True)
        
        print("[OK]")
        
        # Step 2: Fix cgroups in cmdline.txt
        print("  Enabling cgroups in cmdline.txt...", end=" ", flush=True)
        
        # Find cmdline file
        out, err, code = run(client, "test -f /boot/firmware/cmdline.txt && echo 'firmware' || echo 'boot'")
        if out == "firmware":
            cmdline_file = "/boot/firmware/cmdline.txt"
        else:
            cmdline_file = "/boot/cmdline.txt"
        
        # Read current cmdline
        out, err, code = run(client, f"cat {cmdline_file}")
        current_cmdline = out.strip()
        
        # Check if cgroup params already present
        if "cgroup_memory=1" in current_cmdline and "cgroup_enable=memory" in current_cmdline:
            print("[ALREADY SET]")
        else:
            # Backup
            run(client, f"cp {cmdline_file} {cmdline_file}.bak", sudo=True)
            
            # Remove any existing partial cgroup params and add fresh ones
            new_cmdline = current_cmdline
            for param in ["cgroup_memory=1", "cgroup_enable=memory"]:
                new_cmdline = new_cmdline.replace(f" {param}", "").replace(param, "")
            
            # Add cgroup params at the end (must be on single line)
            new_cmdline = new_cmdline.strip() + " cgroup_memory=1 cgroup_enable=memory"
            
            # Write new cmdline
            run(client, f"echo '{new_cmdline}' > {cmdline_file}", sudo=True)
            print("[OK]")
            
            # Verify
            out, err, code = run(client, f"cat {cmdline_file}")
            if "cgroup_memory=1" in out:
                print(f"    -> cmdline updated successfully")
            else:
                print(f"    -> WARNING: cmdline may not have been updated")
        
        # Step 3: Set up kernel modules
        print("  Setting up kernel modules...", end=" ", flush=True)
        run(client, "modprobe br_netfilter 2>/dev/null || true", sudo=True)
        run(client, "modprobe overlay 2>/dev/null || true", sudo=True)
        run(client, """cat > /etc/modules-load.d/k8s.conf << 'EOF'
br_netfilter
overlay
EOF""", sudo=True)
        print("[OK]")
        
        # Step 4: Set up sysctl
        print("  Configuring sysctl...", end=" ", flush=True)
        run(client, """cat > /etc/sysctl.d/k8s.conf << 'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF""", sudo=True)
        run(client, "sysctl --system > /dev/null 2>&1", sudo=True)
        print("[OK]")
        
        # Check current swap status
        out, err, code = run(client, "free -h | grep Swap | awk '{print $2}'")
        print(f"    -> Current swap total: {out}")
        
        client.close()
        print(f"\n[SUCCESS] {node['name']} configured!")
        print(f"[NOTE] Reboot required for cgroups to take effect")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


def fix_ubuntu_control_plane(node, sudo_password=None):
    """Fix Ubuntu control plane node."""
    print(f"\n{'='*60}")
    print(f"Fixing {node['name']} ({node['host']})")
    print(f"{'='*60}")
    
    try:
        client = get_ssh_client(node)
        
        # Check if passwordless sudo works
        out, err, code = run(client, "sudo -n whoami 2>&1")
        if "root" not in out:
            print(f"  [INFO] sudo requires password")
            print(f"  Please run these commands manually on {node['host']}:")
            print()
            print(f"  ssh {node['user']}@{node['host']}")
            print("  sudo swapoff -a")
            print("  sudo sed -i '/\\bswap\\b/d' /etc/fstab")
            print("  sudo modprobe br_netfilter")
            print("  echo 'br_netfilter' | sudo tee /etc/modules-load.d/k8s.conf")
            print("  sudo sysctl -w net.bridge.bridge-nf-call-iptables=1")
            print("  sudo sysctl -w net.ipv4.ip_forward=1")
            print()
            client.close()
            return False
        
        # Passwordless sudo works
        print("  Disabling swap...", end=" ", flush=True)
        run(client, "swapoff -a", sudo=True)
        run(client, "sed -i '/\\bswap\\b/d' /etc/fstab", sudo=True)
        print("[OK]")
        
        print("  Setting up kernel modules...", end=" ", flush=True)
        run(client, "modprobe br_netfilter", sudo=True)
        run(client, "modprobe overlay", sudo=True)
        run(client, """cat > /etc/modules-load.d/k8s.conf << 'EOF'
br_netfilter
overlay
EOF""", sudo=True)
        print("[OK]")
        
        print("  Configuring sysctl...", end=" ", flush=True)
        run(client, """cat > /etc/sysctl.d/k8s.conf << 'EOF'
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF""", sudo=True)
        run(client, "sysctl --system > /dev/null 2>&1", sudo=True)
        print("[OK]")
        
        client.close()
        print(f"\n[SUCCESS] {node['name']} configured!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


def reboot_nodes(nodes):
    """Reboot multiple nodes."""
    print(f"\n{'='*60}")
    print("Rebooting nodes...")
    print(f"{'='*60}")
    
    for node in nodes:
        try:
            client = get_ssh_client(node)
            print(f"  Rebooting {node['name']}...", end=" ", flush=True)
            run(client, "reboot", sudo=True)
            print("[INITIATED]")
        except:
            print("[OK]")  # Connection closed during reboot is expected
    
    # Wait for nodes to come back
    print("\nWaiting for nodes to come back online (up to 120s)...")
    time.sleep(15)  # Initial wait
    
    timeout = 120
    start = time.time()
    pending = list(nodes)
    
    while pending and (time.time() - start) < timeout:
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
        print(f"[WARNING] Nodes not responding: {[n['name'] for n in pending]}")
        return False
    
    print("[SUCCESS] All nodes are back online!")
    return True


def main():
    print("=" * 70)
    print("Fixing Kubernetes Cluster Nodes")
    print("=" * 70)
    
    # Fix workers first
    for worker in WORKERS:
        fix_rpi_worker(worker)
    
    # Fix control plane
    fix_ubuntu_control_plane(CONTROL_PLANE)
    
    # Reboot workers
    print("\nWorkers need to reboot for cgroups to take effect.")
    response = input("Reboot workers now? [y/N]: ").strip().lower()
    if response == 'y':
        reboot_nodes(WORKERS)
    else:
        print("\nReboot manually when ready:")
        for w in WORKERS:
            print(f"  ssh {w['user']}@{w['host']} 'sudo reboot'")
    
    print("\nDone! Run check_cluster_state.py to verify.")


if __name__ == "__main__":
    main()
