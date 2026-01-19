#!/usr/bin/env python3
"""Fix cgroups on Raspberry Pi nodes using proper sudo."""

import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

WORKERS = [
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian"},
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


def run(client, cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err, exit_code


def fix_cgroups(node):
    """Fix cgroups on a node."""
    print(f"\nFixing cgroups on {node['name']} ({node['host']})...")
    
    try:
        client = get_ssh_client(node)
        
        # Find cmdline file
        out, err, code = run(client, "test -f /boot/firmware/cmdline.txt && echo '/boot/firmware/cmdline.txt' || echo '/boot/cmdline.txt'")
        cmdline_file = out.strip()
        print(f"  cmdline file: {cmdline_file}")
        
        # Read current cmdline
        out, err, code = run(client, f"cat {cmdline_file}")
        current = out.strip()
        print(f"  Current: {current[:80]}...")
        
        # Check if already has cgroups
        if "cgroup_memory=1" in current and "cgroup_enable=memory" in current:
            print("  [ALREADY SET] cgroups params present")
            client.close()
            return True
        
        # Backup
        print("  Creating backup...")
        run(client, f"sudo cp {cmdline_file} {cmdline_file}.bak")
        
        # Build new cmdline - add cgroup params
        new_cmdline = current
        # Remove any partial cgroup params
        for param in ["cgroup_memory=1", "cgroup_enable=memory"]:
            new_cmdline = new_cmdline.replace(f" {param}", "")
        # Add fresh params
        new_cmdline = new_cmdline.strip() + " cgroup_memory=1 cgroup_enable=memory"
        
        print(f"  New: {new_cmdline[:80]}...")
        
        # Write using tee (works with sudo and redirect)
        write_cmd = f"echo '{new_cmdline}' | sudo tee {cmdline_file} > /dev/null"
        out, err, code = run(client, write_cmd)
        
        if code != 0:
            print(f"  [ERROR] Write failed: {err}")
            client.close()
            return False
        
        # Verify
        out, err, code = run(client, f"cat {cmdline_file}")
        if "cgroup_memory=1" in out and "cgroup_enable=memory" in out:
            print("  [SUCCESS] cmdline updated!")
        else:
            print(f"  [WARNING] Verification failed")
            print(f"  Content: {out}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def reboot_node(node):
    """Reboot a node."""
    try:
        client = get_ssh_client(node)
        print(f"  Rebooting {node['name']}...", end=" ", flush=True)
        run(client, "sudo reboot")
        print("[OK]")
    except:
        print("[OK]")  # Connection closed is expected


def wait_for_nodes(nodes, timeout=120):
    """Wait for nodes to come back."""
    print(f"\nWaiting for nodes (timeout: {timeout}s)...")
    time.sleep(15)
    
    pending = list(nodes)
    start = time.time()
    
    while pending and (time.time() - start) < timeout:
        for node in list(pending):
            try:
                client = get_ssh_client(node)
                client.close()
                print(f"  {node['name']} is online")
                pending.remove(node)
            except:
                pass
        if pending:
            time.sleep(5)
    
    return len(pending) == 0


def verify_cgroups(node):
    """Verify cgroups are enabled after reboot."""
    try:
        client = get_ssh_client(node)
        out, err, code = run(client, "cat /proc/cgroups | grep memory")
        client.close()
        
        if "memory" in out:
            # Check if enabled (4th column should be 1)
            parts = out.split()
            if len(parts) >= 4 and parts[3] == "1":
                return True, "enabled"
            else:
                return False, f"disabled ({out})"
        return False, "not found"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("Fix cgroups on Raspberry Pi Workers")
    print("=" * 60)
    
    # Fix cgroups on all workers
    for worker in WORKERS:
        fix_cgroups(worker)
    
    # Reboot
    print("\n" + "=" * 60)
    print("Rebooting workers...")
    print("=" * 60)
    
    for worker in WORKERS:
        reboot_node(worker)
    
    # Wait
    if wait_for_nodes(WORKERS):
        print("\n[SUCCESS] All workers back online!")
    else:
        print("\n[WARNING] Some workers may still be rebooting")
    
    # Verify
    print("\n" + "=" * 60)
    print("Verifying cgroups...")
    print("=" * 60)
    
    time.sleep(5)  # Extra wait for services to start
    
    all_good = True
    for worker in WORKERS:
        ok, status = verify_cgroups(worker)
        if ok:
            print(f"  {worker['name']}: [OK] {status}")
        else:
            print(f"  {worker['name']}: [FAILED] {status}")
            all_good = False
    
    if all_good:
        print("\n[SUCCESS] All workers have cgroups enabled!")
    else:
        print("\n[WARNING] Some workers may need manual intervention")
    
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
