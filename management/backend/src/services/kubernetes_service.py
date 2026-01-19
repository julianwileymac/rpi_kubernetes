"""
Kubernetes cluster management service.

Provides operations for querying cluster state, nodes, pods, and services.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from ..config import Settings
from ..models.cluster import (
    ClusterInfo,
    NodeInfo,
    NodeMetrics,
    NodeStatus,
    PodInfo,
    PodPhase,
    ServiceInfo,
)

logger = logging.getLogger(__name__)


class KubernetesService:
    """Service for Kubernetes cluster operations."""

    def __init__(self, settings: Settings):
        """Initialize the Kubernetes service."""
        self.settings = settings
        self._core_api: Optional[client.CoreV1Api] = None
        self._apps_api: Optional[client.AppsV1Api] = None
        self._version_api: Optional[client.VersionApi] = None
        self._custom_api: Optional[client.CustomObjectsApi] = None
        self._initialized = False
        self._last_error: Optional[str] = None

    def _initialize(self) -> None:
        """Initialize Kubernetes client with robust auto-detection and diagnostics."""
        if self._initialized:
            return

        errors: list[str] = []

        def try_load(desc: str, loader) -> bool:
            nonlocal errors
            try:
                loader()
                # Probe API to confirm connectivity
                version_api = client.VersionApi()
                version_api.get_code()
                logger.info("Kubernetes client initialized via %s", desc)
                self._core_api = client.CoreV1Api()
                self._apps_api = client.AppsV1Api()
                self._version_api = version_api
                self._custom_api = client.CustomObjectsApi()
                self._initialized = True
                self._last_error = None
                return True
            except Exception as e:  # noqa: BLE001
                msg = f"{desc}: {e}"
                logger.debug("Kube init attempt failed: %s", msg, exc_info=True)
                errors.append(msg)
                return False

        # 1) Explicit kubeconfig path + context
        if self.settings.kubernetes.kubeconfig_path:
            if try_load(
                f"kubeconfig={self.settings.kubernetes.kubeconfig_path}, context={self.settings.kubernetes.context or 'default'}",
                lambda: config.load_kube_config(
                    config_file=self.settings.kubernetes.kubeconfig_path,
                    context=self.settings.kubernetes.context,
                ),
            ):
                return

        # 2) Auto-discovery paths/contexts
        if self.settings.kubernetes.auto_discover:
            # Candidate kubeconfig paths
            env_kubeconfig = os.getenv("KUBECONFIG", "")
            candidates = []
            if env_kubeconfig:
                candidates.extend(env_kubeconfig.split(os.pathsep))
            candidates.extend(self.settings.kubernetes.extra_kubeconfig_paths or [])
            # Default kubeconfig
            candidates.append(os.path.expanduser("~/.kube/config"))

            # Remove duplicates while preserving order
            seen = set()
            unique_candidates = []
            for path in candidates:
                if path and path not in seen:
                    seen.add(path)
                    unique_candidates.append(path)

            # Try preferred contexts first on each kubeconfig
            preferred_contexts = self.settings.kubernetes.context_preference or []
            for kubeconfig_path in unique_candidates:
                if preferred_contexts:
                    try:
                        contexts, active = config.list_kube_config_contexts(
                            config_file=kubeconfig_path
                        )
                    except Exception:  # noqa: BLE001
                        contexts, active = [], None
                    names = [c["name"] for c in contexts] if contexts else []
                    for ctx in preferred_contexts:
                        if ctx in names and try_load(
                            f"kubeconfig={kubeconfig_path}, context={ctx}",
                            lambda c=ctx, p=kubeconfig_path: config.load_kube_config(
                                config_file=p, context=c
                            ),
                        ):
                            return
                # Fallback to default context on this kubeconfig
                if try_load(
                    f"kubeconfig={kubeconfig_path}",
                    lambda p=kubeconfig_path: config.load_kube_config(
                        config_file=p
                    ),
                ):
                    return

        # 3) In-cluster config
        if try_load("in-cluster", config.load_incluster_config):
            return

        # 4) Default kubeconfig with default context
        if try_load("default kubeconfig", config.load_kube_config):
            return

        # If all fail, surface diagnostics
        self._last_error = "; ".join(errors) if errors else "Unknown initialization error"
        logger.error("Failed to initialize Kubernetes client. Attempts: %s", self._last_error)
        raise RuntimeError(f"Kubernetes client initialization failed: {self._last_error}")

    def get_connection_diagnostics(self) -> dict:
        """Return diagnostics about the last connection attempt."""
        return {
            "initialized": self._initialized,
            "last_error": self._last_error,
            "kubeconfig_path": self.settings.kubernetes.kubeconfig_path,
            "context": self.settings.kubernetes.context,
            "auto_discover": self.settings.kubernetes.auto_discover,
            "extra_kubeconfig_paths": self.settings.kubernetes.extra_kubeconfig_paths,
            "context_preference": self.settings.kubernetes.context_preference,
        }

    @property
    def core_api(self) -> client.CoreV1Api:
        """Get CoreV1Api instance."""
        self._initialize()
        assert self._core_api is not None
        return self._core_api

    @property
    def apps_api(self) -> client.AppsV1Api:
        """Get AppsV1Api instance."""
        self._initialize()
        assert self._apps_api is not None
        return self._apps_api

    async def get_cluster_info(self) -> ClusterInfo:
        """Get overall cluster information."""
        self._initialize()

        # Get Kubernetes version
        version_info = self._version_api.get_code()
        k8s_version = version_info.git_version

        # Get nodes
        nodes = await self.list_nodes()
        ready_nodes = sum(1 for n in nodes if n.status == NodeStatus.READY)

        # Calculate total resources
        total_cpu = 0
        total_memory = 0
        for node in nodes:
            if node.metrics:
                # Parse CPU (e.g., "4" or "4000m")
                cpu_str = node.metrics.cpu_capacity
                if cpu_str.endswith("m"):
                    total_cpu += int(cpu_str[:-1]) / 1000
                else:
                    total_cpu += int(cpu_str)

                # Parse memory (e.g., "8Gi" or "8192Mi")
                mem_str = node.metrics.memory_capacity
                if mem_str.endswith("Gi"):
                    total_memory += int(mem_str[:-2])
                elif mem_str.endswith("Mi"):
                    total_memory += int(mem_str[:-2]) / 1024
                elif mem_str.endswith("Ki"):
                    total_memory += int(mem_str[:-2]) / (1024 * 1024)

        # Get pods
        pods = self.core_api.list_pod_for_all_namespaces()
        total_pods = len(pods.items)
        running_pods = sum(1 for p in pods.items if p.status.phase == "Running")

        # Get namespaces
        namespaces = self.core_api.list_namespace()
        namespace_names = [ns.metadata.name for ns in namespaces.items]

        return ClusterInfo(
            name=self.settings.cluster_name,
            version=k8s_version,
            node_count=len(nodes),
            ready_nodes=ready_nodes,
            total_pods=total_pods,
            running_pods=running_pods,
            total_cpu=f"{total_cpu:.0f}",
            total_memory=f"{total_memory:.1f}Gi",
            namespaces=namespace_names,
            nodes=nodes,
        )

    async def list_nodes(self) -> list[NodeInfo]:
        """List all cluster nodes with details."""
        nodes = self.core_api.list_node()
        result = []

        for node in nodes.items:
            # Determine status
            status = NodeStatus.UNKNOWN
            conditions = {}
            for condition in node.status.conditions or []:
                conditions[condition.type] = condition.status
                if condition.type == "Ready":
                    status = (
                        NodeStatus.READY
                        if condition.status == "True"
                        else NodeStatus.NOT_READY
                    )

            # Get roles from labels
            roles = []
            for label, value in (node.metadata.labels or {}).items():
                if label.startswith("node-role.kubernetes.io/") and value:
                    roles.append(label.split("/")[1])
            if not roles:
                roles = ["worker"]

            # Get taints
            taints = []
            for taint in node.spec.taints or []:
                taints.append(f"{taint.key}={taint.value}:{taint.effect}")

            # Get IP address
            ip_address = ""
            for addr in node.status.addresses or []:
                if addr.type == "InternalIP":
                    ip_address = addr.address
                    break

            # Get metrics
            capacity = node.status.capacity or {}
            allocatable = node.status.allocatable or {}

            # Count pods on this node
            pods = self.core_api.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node.metadata.name}"
            )
            pods_running = len([p for p in pods.items if p.status.phase == "Running"])

            metrics = NodeMetrics(
                cpu_capacity=capacity.get("cpu", "0"),
                cpu_allocatable=allocatable.get("cpu", "0"),
                memory_capacity=capacity.get("memory", "0"),
                memory_allocatable=allocatable.get("memory", "0"),
                pods_capacity=int(capacity.get("pods", "110")),
                pods_running=pods_running,
            )

            node_info = NodeInfo(
                name=node.metadata.name,
                status=status,
                roles=roles,
                ip_address=ip_address,
                architecture=node.status.node_info.architecture,
                os_image=node.status.node_info.os_image,
                kernel_version=node.status.node_info.kernel_version,
                container_runtime=node.status.node_info.container_runtime_version,
                kubelet_version=node.status.node_info.kubelet_version,
                created_at=node.metadata.creation_timestamp,
                labels=node.metadata.labels or {},
                taints=taints,
                conditions=conditions,
                metrics=metrics,
            )
            result.append(node_info)

        return result

    async def get_node(self, name: str) -> Optional[NodeInfo]:
        """Get a specific node by name."""
        nodes = await self.list_nodes()
        for node in nodes:
            if node.name == name:
                return node
        return None

    async def list_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> list[PodInfo]:
        """List pods in the cluster."""
        if namespace:
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
            )
        else:
            pods = self.core_api.list_pod_for_all_namespaces(
                label_selector=label_selector,
            )

        result = []
        for pod in pods.items:
            # Calculate total restarts
            restarts = 0
            containers = []
            for cs in pod.status.container_statuses or []:
                restarts += cs.restart_count
                containers.append(cs.name)

            # Map phase
            phase_map = {
                "Pending": PodPhase.PENDING,
                "Running": PodPhase.RUNNING,
                "Succeeded": PodPhase.SUCCEEDED,
                "Failed": PodPhase.FAILED,
            }
            phase = phase_map.get(pod.status.phase, PodPhase.UNKNOWN)

            pod_info = PodInfo(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                phase=phase,
                node_name=pod.spec.node_name,
                ip_address=pod.status.pod_ip,
                containers=containers,
                restarts=restarts,
                created_at=pod.metadata.creation_timestamp,
                labels=pod.metadata.labels or {},
            )
            result.append(pod_info)

        return result

    async def get_pod_logs(
        self,
        name: str,
        namespace: str,
        container: Optional[str] = None,
        tail_lines: int = 100,
    ) -> str:
        """Get logs from a pod."""
        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
            )
            return logs
        except ApiException as e:
            logger.error(f"Failed to get logs for pod {name}: {e}")
            raise

    async def list_services(
        self,
        namespace: Optional[str] = None,
    ) -> list[ServiceInfo]:
        """List services in the cluster."""
        if namespace:
            services = self.core_api.list_namespaced_service(namespace=namespace)
        else:
            services = self.core_api.list_service_for_all_namespaces()

        result = []
        for svc in services.items:
            # Get external IP if LoadBalancer
            external_ip = None
            if svc.status.load_balancer and svc.status.load_balancer.ingress:
                ingress = svc.status.load_balancer.ingress[0]
                external_ip = ingress.ip or ingress.hostname

            # Parse ports
            ports = []
            for port in svc.spec.ports or []:
                ports.append({
                    "name": port.name,
                    "port": port.port,
                    "target_port": str(port.target_port),
                    "protocol": port.protocol,
                    "node_port": port.node_port,
                })

            service_info = ServiceInfo(
                name=svc.metadata.name,
                namespace=svc.metadata.namespace,
                type=svc.spec.type,
                cluster_ip=svc.spec.cluster_ip,
                external_ip=external_ip,
                ports=ports,
                selector=svc.spec.selector or {},
                created_at=svc.metadata.creation_timestamp,
            )
            result.append(service_info)

        return result

    async def get_namespaces(self) -> list[str]:
        """Get list of namespace names."""
        namespaces = self.core_api.list_namespace()
        return [ns.metadata.name for ns in namespaces.items]
