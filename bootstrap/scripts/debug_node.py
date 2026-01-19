#!/usr/bin/env python3
"""Debug a node's state."""

import os
import sys

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import paramiko
except ImportError:
    os.system("pip install paramiko --quiet")
    import paramiko

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"


def get_ssh_client(host, user):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    key = None
    for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
        try:
            key = key_class.from_private_key_file(SSH_KEY, password=PASSPHRASE)
            break
        except:
            continue
    
    client.connect(hostname=host, username=user, pkey=key, timeout=10)
    return client


def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip(), stderr.read().decode('utf-8', errors='replace').strip()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.12.48"
    user = sys.argv[2] if len(sys.argv) > 2 else "julian"
    
    print(f"Debugging {user}@{host}...")
    client = get_ssh_client(host, user)
    
    print("\n=== Swap Status ===")
    out, err = run(client, "free -h")
    print(out)
    
    print("\n=== Swap Services ===")
    out, err = run(client, "systemctl list-units --type=swap --all")
    print(out or "No swap units")
    
    out, err = run(client, "systemctl is-enabled dphys-swapfile 2>/dev/null || echo 'not installed'")
    print(f"dphys-swapfile: {out}")
    
    print("\n=== /etc/fstab (swap entries) ===")
    out, err = run(client, "grep -i swap /etc/fstab || echo 'No swap in fstab'")
    print(out)
    
    print("\n=== Cmdline (cgroups) ===")
    out, err = run(client, "cat /boot/firmware/cmdline.txt 2>/dev/null || cat /boot/cmdline.txt")
    print(out)
    
    print("\n=== cgroups status ===")
    out, err = run(client, "cat /proc/cgroups | grep memory")
    print(out or "memory cgroup not in /proc/cgroups")
    
    print("\n=== Sudo access ===")
    out, err = run(client, "sudo -n whoami 2>&1")
    print(f"sudo -n whoami: {out} {err}")
    
    client.close()


if __name__ == "__main__":
    main()
