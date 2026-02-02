#!/usr/bin/env python3
"""
=============================================================================
Cluster Node Registry
=============================================================================
Manages a persistent registry of cluster nodes with caching, health tracking,
and automatic IP updates for dynamic environments.

This module provides:
- Persistent node storage with JSON backend
- Health status tracking for each node
- IP address history and change detection
- Integration with discover_cluster.py
- Event hooks for node state changes

Usage:
    from cluster_registry import ClusterRegistry
    
    registry = ClusterRegistry()
    registry.update_from_discovery(discovery_result)
    
    # Get current control plane IP
    cp = registry.get_control_plane()
    print(f"Control plane: {cp.ip}")
    
    # Get all healthy workers
    workers = registry.get_healthy_workers()

Author: RPi Kubernetes Project
=============================================================================
"""

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_REGISTRY_PATH = Path.home() / ".rpi-cluster" / "registry.json"
HEALTH_CHECK_INTERVAL = 60  # seconds
HEALTH_CHECK_TIMEOUT = 5  # seconds
IP_HISTORY_LIMIT = 10


# =============================================================================
# Enums
# =============================================================================

class NodeStatus(Enum):
    """Node health status."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


class NodeRole(Enum):
    """Node role in the cluster."""
    CONTROL_PLANE = "control_plane"
    WORKER = "worker"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class NodeHealth:
    """Health information for a node."""
    status: str = "unknown"
    last_check: str = ""
    ssh_reachable: bool = False
    k3s_healthy: bool = False
    latency_ms: float = 0.0
    error_message: str = ""
    consecutive_failures: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "NodeHealth":
        return cls(**data)


@dataclass
class RegisteredNode:
    """A node in the cluster registry."""
    hostname: str
    ip: str
    role: str = "worker"
    arch: str = "arm64"
    user: str = "julian"
    storage_device: str = "/dev/sda"
    
    # Tracking fields
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    ip_history: list = field(default_factory=list)
    health: NodeHealth = field(default_factory=NodeHealth)
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data["health"] = self.health.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "RegisteredNode":
        health_data = data.pop("health", {})
        node = cls(**data)
        if health_data:
            node.health = NodeHealth.from_dict(health_data)
        return node
    
    def update_ip(self, new_ip: str):
        """Update the IP address and track history."""
        if new_ip != self.ip:
            # Add old IP to history
            if self.ip and self.ip not in self.ip_history:
                self.ip_history.append({
                    "ip": self.ip,
                    "changed_at": datetime.now().isoformat()
                })
                # Trim history
                if len(self.ip_history) > IP_HISTORY_LIMIT:
                    self.ip_history = self.ip_history[-IP_HISTORY_LIMIT:]
            
            self.ip = new_ip
            logger.info(f"Node {self.hostname} IP changed to {new_ip}")
        
        self.last_seen = datetime.now().isoformat()
    
    def is_healthy(self) -> bool:
        """Check if node is considered healthy."""
        return self.health.status == NodeStatus.HEALTHY.value


# =============================================================================
# Cluster Registry
# =============================================================================

class ClusterRegistry:
    """
    Persistent registry of cluster nodes.
    
    Provides:
    - Node storage and retrieval
    - Health status tracking
    - IP change detection
    - Event callbacks
    """
    
    def __init__(
        self,
        registry_path: Path = DEFAULT_REGISTRY_PATH,
        auto_save: bool = True
    ):
        self.registry_path = registry_path
        self.auto_save = auto_save
        self._nodes: dict[str, RegisteredNode] = {}
        self._lock = threading.RLock()
        self._callbacks: dict[str, list[Callable]] = {
            "node_added": [],
            "node_removed": [],
            "node_updated": [],
            "ip_changed": [],
            "health_changed": [],
        }
        
        # Load existing registry
        self.load()
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def load(self) -> bool:
        """Load registry from disk."""
        if not self.registry_path.exists():
            logger.debug(f"Registry file not found: {self.registry_path}")
            return False
        
        try:
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self._nodes = {}
                for hostname, node_data in data.get("nodes", {}).items():
                    self._nodes[hostname] = RegisteredNode.from_dict(node_data)
            
            logger.info(f"Loaded {len(self._nodes)} nodes from registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            return False
    
    def save(self) -> bool:
        """Save registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with self._lock:
                data = {
                    "version": "1.0",
                    "updated_at": datetime.now().isoformat(),
                    "nodes": {
                        hostname: node.to_dict()
                        for hostname, node in self._nodes.items()
                    }
                }
            
            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self._nodes)} nodes to registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
            return False
    
    # =========================================================================
    # Node Management
    # =========================================================================
    
    def add_node(self, node: RegisteredNode) -> bool:
        """Add or update a node in the registry."""
        with self._lock:
            is_new = node.hostname not in self._nodes
            
            if is_new:
                self._nodes[node.hostname] = node
                self._trigger("node_added", node)
                logger.info(f"Added node: {node.hostname} ({node.ip})")
            else:
                existing = self._nodes[node.hostname]
                old_ip = existing.ip
                
                # Update fields
                existing.update_ip(node.ip)
                existing.arch = node.arch
                existing.user = node.user
                
                if old_ip != node.ip:
                    self._trigger("ip_changed", existing, old_ip, node.ip)
                
                self._trigger("node_updated", existing)
            
            if self.auto_save:
                self.save()
            
            return is_new
    
    def remove_node(self, hostname: str) -> bool:
        """Remove a node from the registry."""
        with self._lock:
            if hostname in self._nodes:
                node = self._nodes.pop(hostname)
                self._trigger("node_removed", node)
                logger.info(f"Removed node: {hostname}")
                
                if self.auto_save:
                    self.save()
                
                return True
            return False
    
    def get_node(self, hostname: str) -> Optional[RegisteredNode]:
        """Get a node by hostname."""
        with self._lock:
            return self._nodes.get(hostname)
    
    def get_all_nodes(self) -> list[RegisteredNode]:
        """Get all registered nodes."""
        with self._lock:
            return list(self._nodes.values())
    
    def get_control_plane(self) -> Optional[RegisteredNode]:
        """Get the control plane node."""
        with self._lock:
            for node in self._nodes.values():
                if node.role == NodeRole.CONTROL_PLANE.value:
                    return node
            return None
    
    def get_workers(self) -> list[RegisteredNode]:
        """Get all worker nodes."""
        with self._lock:
            return [
                node for node in self._nodes.values()
                if node.role == NodeRole.WORKER.value
            ]
    
    def get_healthy_workers(self) -> list[RegisteredNode]:
        """Get all healthy worker nodes."""
        return [w for w in self.get_workers() if w.is_healthy()]
    
    # =========================================================================
    # Discovery Integration
    # =========================================================================
    
    def update_from_discovery(self, result) -> dict:
        """
        Update registry from a discovery result.
        
        Args:
            result: DiscoveryResult from discover_cluster.py
        
        Returns:
            Summary of changes
        """
        summary = {
            "added": [],
            "updated": [],
            "ip_changes": []
        }
        
        # Process control plane
        if result.control_plane:
            cp = result.control_plane
            node = RegisteredNode(
                hostname=cp.hostname,
                ip=cp.ip,
                role=NodeRole.CONTROL_PLANE.value,
                arch=cp.arch,
                user="julia" if cp.arch == "amd64" else "julian"
            )
            
            is_new = self.add_node(node)
            if is_new:
                summary["added"].append(cp.hostname)
            else:
                summary["updated"].append(cp.hostname)
        
        # Process workers
        for worker in result.workers:
            node = RegisteredNode(
                hostname=worker.hostname,
                ip=worker.ip,
                role=NodeRole.WORKER.value,
                arch=worker.arch,
                user="julian"
            )
            
            # Check for IP change
            existing = self.get_node(worker.hostname)
            if existing and existing.ip != worker.ip:
                summary["ip_changes"].append({
                    "hostname": worker.hostname,
                    "old_ip": existing.ip,
                    "new_ip": worker.ip
                })
            
            is_new = self.add_node(node)
            if is_new:
                summary["added"].append(worker.hostname)
            else:
                summary["updated"].append(worker.hostname)
        
        return summary
    
    # =========================================================================
    # Health Checking
    # =========================================================================
    
    def check_node_health(self, hostname: str) -> NodeHealth:
        """Check health of a specific node."""
        node = self.get_node(hostname)
        if not node:
            return NodeHealth(status=NodeStatus.UNKNOWN.value)
        
        health = NodeHealth()
        start_time = time.time()
        
        try:
            # Check SSH connectivity
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(HEALTH_CHECK_TIMEOUT)
            result = sock.connect_ex((node.ip, 22))
            sock.close()
            
            health.ssh_reachable = (result == 0)
            health.latency_ms = (time.time() - start_time) * 1000
            
            if health.ssh_reachable:
                # Check k3s port
                k3s_port = 6443 if node.role == NodeRole.CONTROL_PLANE.value else 10250
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(HEALTH_CHECK_TIMEOUT)
                result = sock.connect_ex((node.ip, k3s_port))
                sock.close()
                health.k3s_healthy = (result == 0)
            
            # Determine overall status
            if health.ssh_reachable and health.k3s_healthy:
                health.status = NodeStatus.HEALTHY.value
                health.consecutive_failures = 0
            elif health.ssh_reachable:
                health.status = NodeStatus.UNHEALTHY.value
                health.error_message = "k3s port not responding"
            else:
                health.status = NodeStatus.UNREACHABLE.value
                health.error_message = "SSH not reachable"
                health.consecutive_failures = node.health.consecutive_failures + 1
                
        except Exception as e:
            health.status = NodeStatus.UNREACHABLE.value
            health.error_message = str(e)
            health.consecutive_failures = node.health.consecutive_failures + 1
        
        health.last_check = datetime.now().isoformat()
        
        # Update node health
        with self._lock:
            old_status = node.health.status
            node.health = health
            
            if old_status != health.status:
                self._trigger("health_changed", node, old_status, health.status)
            
            if self.auto_save:
                self.save()
        
        return health
    
    def check_all_health(self) -> dict[str, NodeHealth]:
        """Check health of all nodes."""
        results = {}
        for hostname in list(self._nodes.keys()):
            results[hostname] = self.check_node_health(hostname)
        return results
    
    # =========================================================================
    # Event Callbacks
    # =========================================================================
    
    def on(self, event: str, callback: Callable):
        """Register a callback for an event."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def off(self, event: str, callback: Callable):
        """Unregister a callback."""
        if event in self._callbacks and callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
    
    def _trigger(self, event: str, *args):
        """Trigger callbacks for an event."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")
    
    # =========================================================================
    # Export
    # =========================================================================
    
    def export_ansible_inventory(self) -> dict:
        """Export registry as Ansible inventory format."""
        inventory = {
            "all": {
                "vars": {
                    "ansible_user": "julian",
                    "ansible_python_interpreter": "/usr/bin/python3"
                },
                "children": {
                    "control_plane": {"hosts": {}},
                    "workers": {"hosts": {}}
                }
            }
        }
        
        for node in self.get_all_nodes():
            host_vars = {
                "ansible_host": node.ip,
                "node_ip": node.ip,
                "node_arch": node.arch
            }
            
            if node.role == NodeRole.CONTROL_PLANE.value:
                host_vars["ansible_user"] = node.user
                inventory["all"]["children"]["control_plane"]["hosts"][node.hostname] = host_vars
            else:
                inventory["all"]["children"]["workers"]["hosts"][node.hostname] = host_vars
        
        return inventory
    
    def export_hosts_file(self) -> str:
        """Export registry as /etc/hosts format."""
        lines = ["# Cluster nodes - generated by cluster_registry.py"]
        for node in self.get_all_nodes():
            lines.append(f"{node.ip}\t{node.hostname}\t{node.hostname}.local")
        return "\n".join(lines)
    
    def to_cluster_config(self) -> dict:
        """Export registry as cluster-config.yaml format."""
        config = {
            "cluster": {
                "name": "rpi-k8s-cluster",
                "domain": "local"
            }
        }
        
        cp = self.get_control_plane()
        if cp:
            config["control_plane"] = {
                "hostname": cp.hostname,
                "ip": cp.ip,
                "user": cp.user,
                "arch": cp.arch
            }
        
        workers = self.get_workers()
        if workers:
            config["workers"] = [
                {
                    "name": w.hostname,
                    "ip": w.ip,
                    "user": w.user,
                    "arch": w.arch,
                    "storage_device": w.storage_device
                }
                for w in workers
            ]
        
        return config


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Cluster Node Registry")
    parser.add_argument("--list", "-l", action="store_true", help="List all nodes")
    parser.add_argument("--health", action="store_true", help="Check health of all nodes")
    parser.add_argument("--export", choices=["ansible", "hosts", "config"], help="Export format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    registry = ClusterRegistry()
    
    if args.list:
        print("\nRegistered Nodes:")
        print("-" * 60)
        for node in registry.get_all_nodes():
            status = node.health.status
            print(f"  {node.hostname:15} {node.ip:15} {node.role:15} {status}")
        print()
    
    if args.health:
        print("\nNode Health Check:")
        print("-" * 60)
        results = registry.check_all_health()
        for hostname, health in results.items():
            print(f"  {hostname:15} {health.status:12} {health.latency_ms:.1f}ms")
        print()
    
    if args.export:
        if args.export == "ansible":
            import yaml
            print(yaml.dump(registry.export_ansible_inventory(), default_flow_style=False))
        elif args.export == "hosts":
            print(registry.export_hosts_file())
        elif args.export == "config":
            import yaml
            print(yaml.dump(registry.to_cluster_config(), default_flow_style=False))


if __name__ == "__main__":
    main()
