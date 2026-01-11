"""Cluster management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings
from ..models.cluster import ClusterInfo, NodeInfo, PodInfo, ServiceInfo
from ..services import KubernetesService

router = APIRouter()


def get_k8s_service(settings: Settings = Depends(get_settings)) -> KubernetesService:
    """Get Kubernetes service instance."""
    return KubernetesService(settings)


@router.get("", response_model=ClusterInfo)
async def get_cluster_info(
    k8s: KubernetesService = Depends(get_k8s_service),
) -> ClusterInfo:
    """Get overall cluster information."""
    try:
        return await k8s.get_cluster_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes", response_model=list[NodeInfo])
async def list_nodes(
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[NodeInfo]:
    """List all cluster nodes."""
    try:
        return await k8s.list_nodes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/{name}", response_model=NodeInfo)
async def get_node(
    name: str,
    k8s: KubernetesService = Depends(get_k8s_service),
) -> NodeInfo:
    """Get a specific node by name."""
    try:
        node = await k8s.get_node(name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {name} not found")
        return node
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pods", response_model=list[PodInfo])
async def list_pods(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    label_selector: Optional[str] = Query(None, description="Label selector"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[PodInfo]:
    """List pods in the cluster."""
    try:
        return await k8s.list_pods(namespace=namespace, label_selector=label_selector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pods/{namespace}/{name}/logs")
async def get_pod_logs(
    namespace: str,
    name: str,
    container: Optional[str] = Query(None, description="Container name"),
    tail_lines: int = Query(100, ge=1, le=10000, description="Number of lines"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> dict:
    """Get logs from a pod."""
    try:
        logs = await k8s.get_pod_logs(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
        )
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=list[ServiceInfo])
async def list_services(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[ServiceInfo]:
    """List services in the cluster."""
    try:
        return await k8s.list_services(namespace=namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespaces", response_model=list[str])
async def list_namespaces(
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[str]:
    """List all namespaces."""
    try:
        return await k8s.get_namespaces()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
