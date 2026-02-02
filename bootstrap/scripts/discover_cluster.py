#!/usr/bin/env python3
"""
=============================================================================
Cluster Discovery Service
=============================================================================
Discovers Raspberry Pi Kubernetes cluster nodes using mDNS (Avahi) as the
primary method with network scanning as a fallback.

Features:
- mDNS resolution via hostname.local
- Network scan fallback for environments without mDNS
- Node caching to reduce discovery time
- Auto-update of cluster-config.yaml with discovered IPs
- Service discovery for k3s API endpoints

Usage:
    python discover_cluster.py --verbose
    python discover_cluster.py --update-config
    python discover_cluster.py --method mdns --hostnames rpi1,rpi2,rpi3,rpi4
    python discover_cluster.py --method scan --network 192.168.12.0/24

Author: RPi Kubernetes Project
=============================================================================
"""

import argparse
import ipaddress
import json
import logging
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Optional imports for enhanced functionality
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_HOSTNAMES = ["rpi1", "rpi2", "rpi3", "rpi4"]
DEFAULT_CONTROL_PLANE = "k8s-control"
MDNS_DOMAIN = ".local"
DEFAULT_NETWORK = "192.168.12.0/24"
CACHE_FILE = Path.home() / ".rpi-cluster" / "node-cache.json"
CACHE_TTL = 3600  # seconds
SSH_PORT = 22
K3S_API_PORT = 6443
KUBELET_PORT = 10250
SCAN_TIMEOUT = 2  # seconds
MAX_WORKERS = 20

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DiscoveredNode:
    """Represents a discovered cluster node."""
    hostname: str
    ip: str
    role: str = "worker"  # control_plane or worker
    arch: str = "arm64"
    ssh_available: bool = False
    k3s_available: bool = False
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    services: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveredNode":
        return cls(**data)


@dataclass
class DiscoveryResult:
    """Result of cluster discovery."""
    control_plane: Optional[DiscoveredNode] = None
    workers: list = field(default_factory=list)
    method_used: str = "unknown"
    discovery_time: float = 0.0
    errors: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "control_plane": self.control_plane.to_dict() if self.control_plane else None,
            "workers": [w.to_dict() for w in self.workers],
            "method_used": self.method_used,
            "discovery_time": self.discovery_time,
            "errors": self.errors
        }
    
    def all_nodes(self) -> list:
        """Return all nodes including control plane."""
        nodes = []
        if self.control_plane:
            nodes.append(self.control_plane)
        nodes.extend(self.workers)
        return nodes


# =============================================================================
# mDNS Discovery
# =============================================================================

class MDNSDiscovery:
    """Discover nodes using mDNS/Avahi resolution."""
    
    def __init__(self, domain: str = MDNS_DOMAIN):
        self.domain = domain
    
    def resolve_hostname(self, hostname: str) -> Optional[str]:
        """Resolve a hostname via mDNS."""
        fqdn = f"{hostname}{self.domain}"
        
        try:
            # Try socket resolution first (works if libnss-mdns is configured)
            ip = socket.gethostbyname(fqdn)
            logger.debug(f"Resolved {fqdn} to {ip} via socket")
            return ip
        except socket.gaierror:
            pass
        
        # Try avahi-resolve command
        try:
            result = subprocess.run(
                ["avahi-resolve", "-n", fqdn],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    ip = parts[1]
                    logger.debug(f"Resolved {fqdn} to {ip} via avahi-resolve")
                    return ip
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Try DNS resolution with .local suffix (some routers support this)
        try:
            result = subprocess.run(
                ["nslookup", fqdn],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Address:' in line and not '127.' in line and not '#' in line:
                        ip = line.split('Address:')[1].strip()
                        if ip and not ip.startswith('192.168.') is False:
                            logger.debug(f"Resolved {fqdn} to {ip} via nslookup")
                            return ip
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        logger.debug(f"Failed to resolve {fqdn}")
        return None
    
    def discover_nodes(
        self,
        hostnames: list,
        control_plane_hostname: str = DEFAULT_CONTROL_PLANE
    ) -> DiscoveryResult:
        """Discover nodes by resolving their mDNS hostnames."""
        start_time = time.time()
        result = DiscoveryResult(method_used="mdns")
        
        # Resolve control plane
        logger.info(f"Resolving control plane: {control_plane_hostname}")
        cp_ip = self.resolve_hostname(control_plane_hostname)
        if cp_ip:
            result.control_plane = DiscoveredNode(
                hostname=control_plane_hostname,
                ip=cp_ip,
                role="control_plane",
                arch="amd64",
                ssh_available=self._check_port(cp_ip, SSH_PORT),
                k3s_available=self._check_port(cp_ip, K3S_API_PORT)
            )
            logger.info(f"  Found: {control_plane_hostname} -> {cp_ip}")
        else:
            result.errors.append(f"Failed to resolve control plane: {control_plane_hostname}")
            logger.warning(f"  Not found: {control_plane_hostname}")
        
        # Resolve workers
        logger.info(f"Resolving {len(hostnames)} worker nodes...")
        for hostname in hostnames:
            ip = self.resolve_hostname(hostname)
            if ip:
                node = DiscoveredNode(
                    hostname=hostname,
                    ip=ip,
                    role="worker",
                    arch="arm64",
                    ssh_available=self._check_port(ip, SSH_PORT),
                    k3s_available=self._check_port(ip, KUBELET_PORT)
                )
                result.workers.append(node)
                logger.info(f"  Found: {hostname} -> {ip}")
            else:
                result.errors.append(f"Failed to resolve: {hostname}")
                logger.warning(f"  Not found: {hostname}")
        
        result.discovery_time = time.time() - start_time
        return result
    
    def _check_port(self, ip: str, port: int, timeout: float = SCAN_TIMEOUT) -> bool:
        """Check if a port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False


# =============================================================================
# Network Scan Discovery
# =============================================================================

class NetworkScanDiscovery:
    """Discover nodes by scanning the network."""
    
    def __init__(self, network: str = DEFAULT_NETWORK):
        self.network = ipaddress.ip_network(network, strict=False)
    
    def scan_host(self, ip: str) -> Optional[dict]:
        """Scan a single host for SSH and try to get hostname."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SCAN_TIMEOUT)
            result = sock.connect_ex((ip, SSH_PORT))
            sock.close()
            
            if result == 0:
                hostname = self._get_hostname(ip)
                return {"ip": ip, "hostname": hostname, "ssh": True}
        except Exception:
            pass
        return None
    
    def _get_hostname(self, ip: str) -> Optional[str]:
        """Try to get hostname for an IP."""
        # Try reverse DNS
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            # Strip domain if present
            hostname = hostname.split('.')[0]
            return hostname
        except socket.herror:
            pass
        
        # Try SSH banner (hostname often in banner)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((ip, SSH_PORT))
            banner = sock.recv(256).decode('utf-8', errors='ignore')
            sock.close()
            # Some SSH banners include hostname
            # Format: SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1
        except Exception:
            pass
        
        return None
    
    def discover_nodes(
        self,
        hostname_pattern: str = "rpi",
        control_plane_pattern: str = "k8s-control"
    ) -> DiscoveryResult:
        """Discover nodes by scanning the network."""
        start_time = time.time()
        result = DiscoveryResult(method_used="network_scan")
        
        # Generate list of IPs to scan
        ips = [str(ip) for ip in self.network.hosts()]
        logger.info(f"Scanning {len(ips)} IP addresses in {self.network}...")
        
        found_hosts = []
        
        # Parallel scanning
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self.scan_host, ip): ip for ip in ips}
            
            for future in as_completed(futures):
                host_info = future.result()
                if host_info:
                    found_hosts.append(host_info)
                    logger.debug(f"Found SSH at {host_info['ip']}")
        
        # Categorize discovered hosts
        for host in found_hosts:
            hostname = host.get("hostname")
            ip = host["ip"]
            
            if hostname:
                # Check if it matches control plane pattern
                if control_plane_pattern in hostname.lower():
                    result.control_plane = DiscoveredNode(
                        hostname=hostname,
                        ip=ip,
                        role="control_plane",
                        arch="amd64",
                        ssh_available=True,
                        k3s_available=self._check_port(ip, K3S_API_PORT)
                    )
                    logger.info(f"Found control plane: {hostname} ({ip})")
                
                # Check if it matches worker pattern
                elif hostname_pattern in hostname.lower():
                    node = DiscoveredNode(
                        hostname=hostname,
                        ip=ip,
                        role="worker",
                        arch="arm64",
                        ssh_available=True,
                        k3s_available=self._check_port(ip, KUBELET_PORT)
                    )
                    result.workers.append(node)
                    logger.info(f"Found worker: {hostname} ({ip})")
        
        # Sort workers by hostname
        result.workers.sort(key=lambda x: x.hostname)
        
        result.discovery_time = time.time() - start_time
        return result
    
    def _check_port(self, ip: str, port: int) -> bool:
        """Check if a port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SCAN_TIMEOUT)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False


# =============================================================================
# Zeroconf Service Discovery (Optional Enhanced Discovery)
# =============================================================================

if ZEROCONF_AVAILABLE:
    class K3SServiceListener(ServiceListener):
        """Listener for k3s mDNS service advertisements."""
        
        def __init__(self):
            self.services = {}
        
        def add_service(self, zeroconf: Zeroconf, service_type: str, name: str):
            info = zeroconf.get_service_info(service_type, name)
            if info:
                self.services[name] = {
                    "addresses": [socket.inet_ntoa(addr) for addr in info.addresses],
                    "port": info.port,
                    "properties": {k.decode(): v.decode() if isinstance(v, bytes) else v 
                                   for k, v in info.properties.items()}
                }
        
        def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str):
            if name in self.services:
                del self.services[name]
        
        def update_service(self, zeroconf: Zeroconf, service_type: str, name: str):
            self.add_service(zeroconf, service_type, name)
    
    
    def discover_k3s_services(timeout: float = 5.0) -> dict:
        """Discover k3s services via Zeroconf."""
        zeroconf = Zeroconf()
        listener = K3SServiceListener()
        
        # Browse for k3s services
        ServiceBrowser(zeroconf, "_k3s._tcp.local.", listener)
        ServiceBrowser(zeroconf, "_k3s-agent._tcp.local.", listener)
        
        time.sleep(timeout)
        zeroconf.close()
        
        return listener.services


# =============================================================================
# Cache Management
# =============================================================================

class NodeCache:
    """Cache for discovered nodes."""
    
    def __init__(self, cache_file: Path = CACHE_FILE, ttl: int = CACHE_TTL):
        self.cache_file = cache_file
        self.ttl = ttl
    
    def load(self) -> Optional[DiscoveryResult]:
        """Load cached discovery result if valid."""
        if not self.cache_file.exists():
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            # Check TTL
            cache_time = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
            age = (datetime.now() - cache_time).total_seconds()
            
            if age > self.ttl:
                logger.debug(f"Cache expired (age: {age}s, ttl: {self.ttl}s)")
                return None
            
            # Reconstruct result
            result = DiscoveryResult(
                method_used=data.get("method_used", "cache"),
                discovery_time=data.get("discovery_time", 0)
            )
            
            if data.get("control_plane"):
                result.control_plane = DiscoveredNode.from_dict(data["control_plane"])
            
            for worker_data in data.get("workers", []):
                result.workers.append(DiscoveredNode.from_dict(worker_data))
            
            logger.info(f"Loaded {len(result.all_nodes())} nodes from cache")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None
    
    def save(self, result: DiscoveryResult):
        """Save discovery result to cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = result.to_dict()
        data["cached_at"] = datetime.now().isoformat()
        
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(result.all_nodes())} nodes to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def clear(self):
        """Clear the cache."""
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.info("Cache cleared")


# =============================================================================
# Configuration Update
# =============================================================================

def update_cluster_config(result: DiscoveryResult, config_file: Path) -> bool:
    """Update cluster-config.yaml with discovered IPs."""
    if not YAML_AVAILABLE:
        logger.error("PyYAML not available. Cannot update config file.")
        return False
    
    if not config_file.exists():
        logger.error(f"Config file not found: {config_file}")
        return False
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Update control plane
        if result.control_plane:
            config["control_plane"]["ip"] = result.control_plane.ip
            config["control_plane"]["hostname"] = result.control_plane.hostname
        
        # Update workers
        workers = []
        for node in result.workers:
            worker = {
                "name": node.hostname,
                "ip": node.ip,
                "user": "julian",
                "arch": node.arch,
                "storage_device": "/dev/sda"
            }
            workers.append(worker)
        
        if workers:
            config["workers"] = workers
        
        # Write back
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Updated {config_file} with discovered IPs")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return False


# =============================================================================
# Main Discovery Function
# =============================================================================

def discover_cluster(
    method: str = "auto",
    hostnames: list = None,
    control_plane_hostname: str = DEFAULT_CONTROL_PLANE,
    network: str = DEFAULT_NETWORK,
    use_cache: bool = True,
    cache_ttl: int = CACHE_TTL
) -> DiscoveryResult:
    """
    Discover cluster nodes using the specified method.
    
    Args:
        method: Discovery method - "mdns", "scan", or "auto" (tries mdns first)
        hostnames: List of worker hostnames to resolve (for mdns method)
        control_plane_hostname: Hostname of the control plane
        network: Network range for scanning (for scan method)
        use_cache: Whether to use/update cache
        cache_ttl: Cache time-to-live in seconds
    
    Returns:
        DiscoveryResult with discovered nodes
    """
    if hostnames is None:
        hostnames = DEFAULT_HOSTNAMES
    
    cache = NodeCache(ttl=cache_ttl)
    
    # Try cache first
    if use_cache:
        cached_result = cache.load()
        if cached_result:
            return cached_result
    
    result = None
    
    # Auto method: try mDNS first, fall back to network scan
    if method == "auto":
        logger.info("Using auto discovery (mDNS -> network scan)")
        
        # Try mDNS
        mdns = MDNSDiscovery()
        result = mdns.discover_nodes(hostnames, control_plane_hostname)
        
        # Check if we found enough nodes
        if not result.control_plane or len(result.workers) < len(hostnames):
            logger.info("mDNS discovery incomplete, trying network scan...")
            
            # Try network scan for missing nodes
            scanner = NetworkScanDiscovery(network)
            scan_result = scanner.discover_nodes()
            
            # Merge results
            if not result.control_plane and scan_result.control_plane:
                result.control_plane = scan_result.control_plane
            
            found_hostnames = {w.hostname for w in result.workers}
            for worker in scan_result.workers:
                if worker.hostname not in found_hostnames:
                    result.workers.append(worker)
            
            result.method_used = "auto (mdns + scan)"
    
    elif method == "mdns":
        logger.info("Using mDNS discovery")
        mdns = MDNSDiscovery()
        result = mdns.discover_nodes(hostnames, control_plane_hostname)
    
    elif method == "scan":
        logger.info("Using network scan discovery")
        scanner = NetworkScanDiscovery(network)
        result = scanner.discover_nodes()
    
    else:
        raise ValueError(f"Unknown discovery method: {method}")
    
    # Save to cache
    if use_cache and result:
        cache.save(result)
    
    return result


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Discover Raspberry Pi Kubernetes cluster nodes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --verbose
  %(prog)s --method mdns --hostnames rpi1,rpi2,rpi3,rpi4
  %(prog)s --method scan --network 192.168.12.0/24
  %(prog)s --update-config --config cluster-config.yaml
  %(prog)s --output json
  %(prog)s --clear-cache
        """
    )
    
    parser.add_argument(
        "--method", "-m",
        choices=["auto", "mdns", "scan"],
        default="auto",
        help="Discovery method (default: auto)"
    )
    
    parser.add_argument(
        "--hostnames", "-H",
        type=lambda s: s.split(','),
        default=DEFAULT_HOSTNAMES,
        help=f"Comma-separated list of worker hostnames (default: {','.join(DEFAULT_HOSTNAMES)})"
    )
    
    parser.add_argument(
        "--control-plane", "-c",
        default=DEFAULT_CONTROL_PLANE,
        help=f"Control plane hostname (default: {DEFAULT_CONTROL_PLANE})"
    )
    
    parser.add_argument(
        "--network", "-n",
        default=DEFAULT_NETWORK,
        help=f"Network range for scanning (default: {DEFAULT_NETWORK})"
    )
    
    parser.add_argument(
        "--output", "-o",
        choices=["table", "json", "yaml", "hosts"],
        default="table",
        help="Output format (default: table)"
    )
    
    parser.add_argument(
        "--update-config", "-u",
        action="store_true",
        help="Update cluster-config.yaml with discovered IPs"
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent.parent.parent / "cluster-config.yaml",
        help="Path to cluster-config.yaml"
    )
    
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache usage"
    )
    
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the discovery cache"
    )
    
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=CACHE_TTL,
        help=f"Cache TTL in seconds (default: {CACHE_TTL})"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Clear cache if requested
    if args.clear_cache:
        cache = NodeCache()
        cache.clear()
        print("Cache cleared")
        return 0
    
    # Run discovery
    try:
        result = discover_cluster(
            method=args.method,
            hostnames=args.hostnames,
            control_plane_hostname=args.control_plane,
            network=args.network,
            use_cache=not args.no_cache,
            cache_ttl=args.cache_ttl
        )
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return 1
    
    # Update config if requested
    if args.update_config:
        if not update_cluster_config(result, args.config):
            return 1
    
    # Output results
    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2))
    
    elif args.output == "yaml":
        if YAML_AVAILABLE:
            print(yaml.dump(result.to_dict(), default_flow_style=False))
        else:
            print("PyYAML not available")
            return 1
    
    elif args.output == "hosts":
        # Output in hosts file format
        for node in result.all_nodes():
            print(f"{node.ip}\t{node.hostname}\t{node.hostname}.local")
    
    else:  # table format
        print("\n" + "=" * 70)
        print("Cluster Discovery Results")
        print("=" * 70)
        print(f"Method: {result.method_used}")
        print(f"Time: {result.discovery_time:.2f}s")
        print()
        
        # Control plane
        print("Control Plane:")
        if result.control_plane:
            cp = result.control_plane
            status = "OK" if cp.ssh_available else "SSH N/A"
            k3s_status = "k3s OK" if cp.k3s_available else "k3s N/A"
            print(f"  {cp.hostname:15} {cp.ip:15} {status:10} {k3s_status}")
        else:
            print("  Not found")
        print()
        
        # Workers
        print(f"Workers ({len(result.workers)}):")
        if result.workers:
            for worker in result.workers:
                status = "OK" if worker.ssh_available else "SSH N/A"
                k3s_status = "k3s OK" if worker.k3s_available else "k3s N/A"
                print(f"  {worker.hostname:15} {worker.ip:15} {status:10} {k3s_status}")
        else:
            print("  None found")
        print()
        
        # Errors
        if result.errors:
            print("Errors:")
            for error in result.errors:
                print(f"  - {error}")
            print()
        
        print("=" * 70)
    
    # Return non-zero if discovery was incomplete
    expected_workers = len(args.hostnames)
    found_workers = len(result.workers)
    
    if not result.control_plane:
        logger.warning("Control plane not found")
        return 1
    
    if found_workers < expected_workers:
        logger.warning(f"Only found {found_workers}/{expected_workers} workers")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
