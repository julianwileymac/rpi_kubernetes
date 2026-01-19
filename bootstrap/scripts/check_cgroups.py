#!/usr/bin/env python3
"""Check cgroups support on a node."""

import os
import sys

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
    
    client.connect(hostname=host, username=user, pkey=key, timeout=30)
    return client


def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.12.48"
    user = sys.argv[2] if len(sys.argv) > 2 else "julian"
    
    print(f"Checking cgroups on {user}@{host}...")
    client = get_ssh_client(host, user)
    
    print("\n=== /proc/cgroups (all) ===")
    out = run(client, "cat /proc/cgroups")
    print(out)
    
    print("\n=== Kernel config (cgroup) ===")
    out = run(client, "zcat /proc/config.gz 2>/dev/null | grep -i cgroup || grep -i cgroup /boot/config-$(uname -r) 2>/dev/null | head -20")
    print(out or "Could not read kernel config")
    
    print("\n=== Current cmdline ===")
    out = run(client, "cat /proc/cmdline")
    print(out)
    
    print("\n=== Cgroup mounts ===")
    out = run(client, "mount | grep cgroup")
    print(out or "No cgroup mounts")
    
    print("\n=== Cgroup v2 check ===")
    out = run(client, "ls -la /sys/fs/cgroup/")
    print(out)
    
    print("\n=== Kernel version ===")
    out = run(client, "uname -r")
    print(out)
    
    client.close()


if __name__ == "__main__":
    main()
