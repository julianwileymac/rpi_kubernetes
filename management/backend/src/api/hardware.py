"""Hardware monitoring API endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models.hardware import ClusterHardwareOverview, HardwareMetrics, NodeHardwareInfo
from ..services import HardwareService, KubernetesService

router = APIRouter()


def get_hardware_service(
    settings: Settings = Depends(get_settings),
) -> HardwareService:
    """Get hardware service instance."""
    return HardwareService(settings)


def get_k8s_service(settings: Settings = Depends(get_settings)) -> KubernetesService:
    """Get Kubernetes service instance."""
    return KubernetesService(settings)


@router.get("", response_model=ClusterHardwareOverview)
async def get_cluster_hardware(
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> ClusterHardwareOverview:
    """Get hardware overview for all cluster nodes."""
    try:
        # Get node IPs from Kubernetes
        nodes = await k8s.list_nodes()
        node_ips = {node.name: node.ip_address for node in nodes}

        return await hardware.get_cluster_hardware_overview(node_ips)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{node_name}", response_model=NodeHardwareInfo)
async def get_node_hardware(
    node_name: str,
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> NodeHardwareInfo:
    """Get hardware information for a specific node."""
    try:
        # Get node IP from Kubernetes
        node = await k8s.get_node(node_name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_name} not found")

        return await hardware.get_node_hardware_info(node.ip_address, node_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{node_name}/metrics", response_model=HardwareMetrics)
async def get_node_metrics(
    node_name: str,
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> HardwareMetrics:
    """Get current hardware metrics for a specific node."""
    try:
        # Get node IP from Kubernetes
        node = await k8s.get_node(node_name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_name} not found")

        metrics = await hardware.get_node_metrics(node.ip_address)
        if not metrics:
            raise HTTPException(
                status_code=503,
                detail=f"Unable to collect metrics from {node_name}",
            )
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
