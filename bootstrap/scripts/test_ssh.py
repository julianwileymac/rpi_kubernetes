#!/usr/bin/env python3
"""Test SSH connectivity to cluster nodes using paramiko."""

import os
import sys

try:
    import paramiko
except ImportError:
    print("Installing paramiko...")
    os.system("pip install paramiko --quiet")
    import paramiko

# Cluster configuration from inventory
NODES = [
    {"name": "k8s-control", "host": "192.168.12.112", "user": "julia", "type": "control_plane"},
    {"name": "rpi1", "host": "192.168.12.48", "user": "julian", "type": "worker"},
    {"name": "rpi2", "host": "192.168.12.88", "user": "julian", "type": "worker"},
    {"name": "rpi3", "host": "192.168.12.170", "user": "julian", "type": "worker"},
    {"name": "rpi4", "host": "192.168.12.235", "user": "julian", "type": "worker"},
]

SSH_KEY = os.path.expanduser("~/.ssh/id_ed")
PASSPHRASE = "WeLoveCookies0116"


def test_node(node):
    """Test SSH connection to a node."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Try to load private key with passphrase (try RSA first, then Ed25519)
        key = None
        for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]:
            try:
                key = key_class.from_private_key_file(SSH_KEY, password=PASSPHRASE)
                break
            except paramiko.ssh_exception.SSHException:
                continue
        
        if key is None:
            return False, None, "Could not load SSH key"
        
        # Connect
        client.connect(
            hostname=node["host"],
            username=node["user"],
            pkey=key,
            timeout=10
        )
        
        # Test command
        stdin, stdout, stderr = client.exec_command("uname -a")
        output = stdout.read().decode().strip()
        
        # Get additional info
        stdin, stdout, stderr = client.exec_command("hostname")
        hostname = stdout.read().decode().strip()
        
        client.close()
        return True, hostname, output
        
    except paramiko.ssh_exception.AuthenticationException as e:
        return False, None, f"Authentication failed: {e}"
    except paramiko.ssh_exception.SSHException as e:
        return False, None, f"SSH error: {e}"
    except Exception as e:
        return False, None, f"Error: {e}"


def main():
    print("=" * 70)
    print("SSH Connectivity Test for Kubernetes Cluster")
    print("=" * 70)
    print()
    
    results = []
    
    for node in NODES:
        print(f"Testing {node['name']} ({node['host']})...", end=" ")
        success, hostname, info = test_node(node)
        
        if success:
            print(f"[OK] - {hostname}")
            results.append((node, True, info))
        else:
            print(f"[FAILED] - {info}")
            results.append((node, False, info))
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    success_count = sum(1 for _, success, _ in results if success)
    print(f"Connected: {success_count}/{len(NODES)} nodes")
    print()
    
    if success_count == len(NODES):
        print("[SUCCESS] All nodes are accessible via SSH!")
        print()
        print("System information:")
        for node, success, info in results:
            if success:
                print(f"  {node['name']}: {info}")
        return 0
    else:
        print("[WARNING] Some nodes failed to connect:")
        for node, success, info in results:
            if not success:
                print(f"  {node['name']}: {info}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
