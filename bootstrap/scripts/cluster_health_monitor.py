#!/usr/bin/env python3
"""
=============================================================================
Cluster Health Monitor Daemon
=============================================================================
A long-running daemon that monitors the health of all cluster nodes and
provides automatic recovery capabilities.

Features:
- Periodic health checks for all nodes
- IP change detection (via mDNS re-resolution)
- k3s service health monitoring
- Automatic notification of failures
- Integration with systemd journal logging
- REST API for status queries (optional)

Usage:
    python cluster_health_monitor.py --daemon
    python cluster_health_monitor.py --check-once
    python cluster_health_monitor.py --status

This daemon is managed by k3s-cluster-health-monitor.service

Author: RPi Kubernetes Project
=============================================================================
"""

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Import our discovery module
try:
    from discover_cluster import MDNSDiscovery, discover_cluster
    from cluster_registry import ClusterRegistry, NodeStatus, RegisteredNode
    DISCOVERY_AVAILABLE = True
except ImportError:
    DISCOVERY_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_CHECK_INTERVAL = 60  # seconds
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "cluster-config.yaml"
DEFAULT_REGISTRY_PATH = Path.home() / ".rpi-cluster" / "registry.json"
LOG_FILE = Path("/var/log/k3s-health-monitor.log")
PID_FILE = Path("/var/run/k3s-health-monitor.pid")

# Ports to check
SSH_PORT = 22
K3S_API_PORT = 6443
KUBELET_PORT = 10250

# Thresholds
MAX_CONSECUTIVE_FAILURES = 3
IP_RECHECK_INTERVAL = 300  # Re-resolve mDNS every 5 minutes


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(log_level: str = "INFO", log_file: Optional[Path] = None):
    """Configure logging for the daemon."""
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file and log_file.parent.exists():
        try:
            handlers.append(logging.FileHandler(log_file))
        except PermissionError:
            pass
    
    # Try to use systemd journal if available
    try:
        from systemd.journal import JournalHandler
        handlers.append(JournalHandler(SYSLOG_IDENTIFIER="k3s-health-monitor"))
    except ImportError:
        pass
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    return logging.getLogger("health-monitor")


# =============================================================================
# Data Classes
# =============================================================================

class NodeHealthStatus(Enum):
    """Health status for a node."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


@dataclass
class NodeHealthReport:
    """Health report for a single node."""
    hostname: str
    ip: str
    status: str = "unknown"
    ssh_reachable: bool = False
    k3s_healthy: bool = False
    latency_ms: float = 0.0
    last_check: str = field(default_factory=lambda: datetime.now().isoformat())
    consecutive_failures: int = 0
    ip_changed: bool = False
    previous_ip: str = ""
    error_message: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClusterHealthReport:
    """Health report for the entire cluster."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    overall_status: str = "unknown"
    control_plane: Optional[NodeHealthReport] = None
    workers: list = field(default_factory=list)
    healthy_count: int = 0
    unhealthy_count: int = 0
    unreachable_count: int = 0
    ip_changes_detected: int = 0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "control_plane": self.control_plane.to_dict() if self.control_plane else None,
            "workers": [w.to_dict() for w in self.workers],
            "healthy_count": self.healthy_count,
            "unhealthy_count": self.unhealthy_count,
            "unreachable_count": self.unreachable_count,
            "ip_changes_detected": self.ip_changes_detected
        }


# =============================================================================
# Health Checker
# =============================================================================

class HealthChecker:
    """Performs health checks on cluster nodes."""
    
    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        timeout: float = 5.0
    ):
        self.config_path = config_path
        self.timeout = timeout
        self.logger = logging.getLogger("health-checker")
        self._node_state: dict[str, NodeHealthReport] = {}
        self._mdns = MDNSDiscovery() if DISCOVERY_AVAILABLE else None
    
    def load_config(self) -> dict:
        """Load cluster configuration."""
        if not self.config_path.exists():
            self.logger.warning(f"Config not found: {self.config_path}")
            return {}
        
        if not YAML_AVAILABLE:
            self.logger.error("PyYAML not available")
            return {}
        
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def check_port(self, ip: str, port: int) -> tuple[bool, float]:
        """Check if a port is open and return latency."""
        start_time = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            latency = (time.time() - start_time) * 1000
            return (result == 0, latency)
        except Exception as e:
            self.logger.debug(f"Port check failed for {ip}:{port}: {e}")
            return (False, 0.0)
    
    def resolve_hostname(self, hostname: str) -> Optional[str]:
        """Resolve hostname via mDNS."""
        if self._mdns:
            return self._mdns.resolve_hostname(hostname)
        
        # Fallback to standard resolution
        try:
            return socket.gethostbyname(f"{hostname}.local")
        except socket.gaierror:
            return None
    
    def check_node(
        self,
        hostname: str,
        ip: str,
        role: str = "worker"
    ) -> NodeHealthReport:
        """Perform health check on a single node."""
        report = NodeHealthReport(
            hostname=hostname,
            ip=ip
        )
        
        # Check for IP changes via mDNS
        current_ip = self.resolve_hostname(hostname)
        if current_ip and current_ip != ip:
            report.ip_changed = True
            report.previous_ip = ip
            report.ip = current_ip
            self.logger.warning(f"IP change detected for {hostname}: {ip} -> {current_ip}")
        
        # Check SSH
        ssh_ok, latency = self.check_port(report.ip, SSH_PORT)
        report.ssh_reachable = ssh_ok
        report.latency_ms = latency
        
        # Check k3s port
        k3s_port = K3S_API_PORT if role == "control_plane" else KUBELET_PORT
        k3s_ok, _ = self.check_port(report.ip, k3s_port)
        report.k3s_healthy = k3s_ok
        
        # Determine status
        if ssh_ok and k3s_ok:
            report.status = NodeHealthStatus.HEALTHY.value
            report.consecutive_failures = 0
        elif ssh_ok:
            report.status = NodeHealthStatus.DEGRADED.value
            report.error_message = "k3s not responding"
        else:
            report.status = NodeHealthStatus.UNREACHABLE.value
            report.error_message = "SSH not reachable"
            
            # Track consecutive failures
            prev_state = self._node_state.get(hostname)
            if prev_state:
                report.consecutive_failures = prev_state.consecutive_failures + 1
        
        # Update state
        self._node_state[hostname] = report
        
        return report
    
    def check_cluster(self) -> ClusterHealthReport:
        """Perform health check on the entire cluster."""
        report = ClusterHealthReport()
        config = self.load_config()
        
        if not config:
            report.overall_status = "error"
            return report
        
        # Check control plane
        cp_config = config.get("control_plane", {})
        if cp_config:
            cp_report = self.check_node(
                hostname=cp_config.get("hostname", "k8s-control"),
                ip=cp_config.get("ip", ""),
                role="control_plane"
            )
            report.control_plane = cp_report
            
            if cp_report.ip_changed:
                report.ip_changes_detected += 1
        
        # Check workers
        workers_config = config.get("workers", [])
        for worker in workers_config:
            worker_report = self.check_node(
                hostname=worker.get("name", ""),
                ip=worker.get("ip", ""),
                role="worker"
            )
            report.workers.append(worker_report)
            
            if worker_report.ip_changed:
                report.ip_changes_detected += 1
        
        # Calculate counts
        all_reports = report.workers.copy()
        if report.control_plane:
            all_reports.append(report.control_plane)
        
        for r in all_reports:
            if r.status == NodeHealthStatus.HEALTHY.value:
                report.healthy_count += 1
            elif r.status == NodeHealthStatus.UNREACHABLE.value:
                report.unreachable_count += 1
            else:
                report.unhealthy_count += 1
        
        # Determine overall status
        if report.unreachable_count == 0 and report.unhealthy_count == 0:
            report.overall_status = "healthy"
        elif report.control_plane and report.control_plane.status != NodeHealthStatus.HEALTHY.value:
            report.overall_status = "critical"
        elif report.unreachable_count > 0:
            report.overall_status = "degraded"
        else:
            report.overall_status = "warning"
        
        return report


# =============================================================================
# Health Monitor Daemon
# =============================================================================

class HealthMonitorDaemon:
    """Long-running daemon for cluster health monitoring."""
    
    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        callbacks: dict = None
    ):
        self.config_path = config_path
        self.check_interval = check_interval
        self.logger = logging.getLogger("health-daemon")
        self.checker = HealthChecker(config_path)
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_report: Optional[ClusterHealthReport] = None
        self._callbacks = callbacks or {}
        
        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        self.logger.info(f"Received signal {signum}, stopping daemon...")
        self.stop()
    
    def _write_pid(self):
        """Write PID file."""
        try:
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except PermissionError:
            self.logger.warning("Cannot write PID file (no permission)")
    
    def _remove_pid(self):
        """Remove PID file."""
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception:
            pass
    
    def _run_callbacks(self, event: str, *args):
        """Run callbacks for an event."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                self.logger.error(f"Callback error for {event}: {e}")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        last_ip_check = 0
        
        while self._running:
            try:
                # Run health check
                report = self.checker.check_cluster()
                self._last_report = report
                
                # Log status
                self.logger.info(
                    f"Health check complete: {report.overall_status} "
                    f"(healthy={report.healthy_count}, unhealthy={report.unhealthy_count}, "
                    f"unreachable={report.unreachable_count})"
                )
                
                # Trigger callbacks
                self._run_callbacks("health_check", report)
                
                # Check for critical conditions
                if report.overall_status == "critical":
                    self.logger.critical("CRITICAL: Control plane is unhealthy!")
                    self._run_callbacks("critical", report)
                
                # Check for IP changes
                if report.ip_changes_detected > 0:
                    self.logger.warning(f"Detected {report.ip_changes_detected} IP change(s)")
                    self._run_callbacks("ip_changed", report)
                    
                    # Update config file with new IPs
                    self._update_config_ips(report)
                
                # Check for nodes with consecutive failures
                for node in report.workers + ([report.control_plane] if report.control_plane else []):
                    if node.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        self.logger.error(
                            f"Node {node.hostname} has failed {node.consecutive_failures} "
                            "consecutive health checks"
                        )
                        self._run_callbacks("node_failed", node)
                
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
            
            # Sleep until next check
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)
    
    def _update_config_ips(self, report: ClusterHealthReport):
        """Update cluster-config.yaml with new IPs."""
        if not YAML_AVAILABLE:
            return
        
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            
            updated = False
            
            # Update control plane IP
            if report.control_plane and report.control_plane.ip_changed:
                config["control_plane"]["ip"] = report.control_plane.ip
                updated = True
            
            # Update worker IPs
            for worker_report in report.workers:
                if worker_report.ip_changed:
                    for w in config.get("workers", []):
                        if w.get("name") == worker_report.hostname:
                            w["ip"] = worker_report.ip
                            updated = True
                            break
            
            if updated:
                with open(self.config_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                self.logger.info("Updated cluster-config.yaml with new IPs")
                
        except Exception as e:
            self.logger.error(f"Failed to update config: {e}")
    
    def start(self, daemon: bool = False):
        """Start the monitor daemon."""
        if self._running:
            self.logger.warning("Daemon already running")
            return
        
        self.logger.info("Starting health monitor daemon...")
        self._running = True
        
        if daemon:
            self._write_pid()
        
        self._thread = threading.Thread(target=self._monitor_loop, daemon=False)
        self._thread.start()
        
        if daemon:
            # Block main thread
            self._thread.join()
    
    def stop(self):
        """Stop the monitor daemon."""
        self.logger.info("Stopping health monitor daemon...")
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=10)
        
        self._remove_pid()
    
    def get_status(self) -> Optional[ClusterHealthReport]:
        """Get the last health report."""
        return self._last_report
    
    def check_once(self) -> ClusterHealthReport:
        """Run a single health check."""
        return self.checker.check_cluster()


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Cluster Health Monitor Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run as daemon"
    )
    
    parser.add_argument(
        "--check-once", "-c",
        action="store_true",
        help="Run a single health check and exit"
    )
    
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Check if daemon is running and show last status"
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to cluster-config.yaml (default: {DEFAULT_CONFIG_PATH})"
    )
    
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=DEFAULT_CHECK_INTERVAL,
        help=f"Check interval in seconds (default: {DEFAULT_CHECK_INTERVAL})"
    )
    
    parser.add_argument(
        "--output", "-o",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output (same as --log-level DEBUG)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else args.log_level
    logger = setup_logging(log_level)
    
    # Check status
    if args.status:
        if PID_FILE.exists():
            pid = PID_FILE.read_text().strip()
            print(f"Daemon is running (PID: {pid})")
        else:
            print("Daemon is not running")
        return 0
    
    # Run single check
    if args.check_once:
        checker = HealthChecker(args.config)
        report = checker.check_cluster()
        
        if args.output == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print("\n" + "=" * 60)
            print("Cluster Health Report")
            print("=" * 60)
            print(f"Timestamp:    {report.timestamp}")
            print(f"Status:       {report.overall_status.upper()}")
            print()
            
            if report.control_plane:
                cp = report.control_plane
                status_icon = "OK" if cp.status == "healthy" else "!!"
                print(f"Control Plane: {cp.hostname}")
                print(f"  IP:     {cp.ip}")
                print(f"  Status: [{status_icon}] {cp.status}")
                print(f"  SSH:    {'OK' if cp.ssh_reachable else 'FAIL'}")
                print(f"  k3s:    {'OK' if cp.k3s_healthy else 'FAIL'}")
                if cp.ip_changed:
                    print(f"  *** IP CHANGED from {cp.previous_ip}")
            
            print()
            print(f"Workers ({len(report.workers)}):")
            for w in report.workers:
                status_icon = "OK" if w.status == "healthy" else "!!"
                print(f"  {w.hostname}: [{status_icon}] {w.ip} - {w.status}")
                if w.ip_changed:
                    print(f"    *** IP CHANGED from {w.previous_ip}")
            
            print()
            print(f"Summary: {report.healthy_count} healthy, "
                  f"{report.unhealthy_count} unhealthy, "
                  f"{report.unreachable_count} unreachable")
            print("=" * 60)
        
        # Exit code based on status
        if report.overall_status == "healthy":
            return 0
        elif report.overall_status == "critical":
            return 2
        else:
            return 1
    
    # Run as daemon
    if args.daemon:
        daemon = HealthMonitorDaemon(
            config_path=args.config,
            check_interval=args.interval
        )
        daemon.start(daemon=True)
        return 0
    
    # Default: run single check
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
