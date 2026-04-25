"""Cluster management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings
from ..models.cluster import ClusterInfo, NodeInfo, PodInfo, ServiceInfo
from ..services import KubernetesService, RedisService
from .redis_admin import get_redis_service

router = APIRouter()


def get_k8s_service(settings: Settings = Depends(get_settings)) -> KubernetesService:
    """Get Kubernetes service instance."""
    return KubernetesService(settings)


@router.get("", response_model=ClusterInfo)
async def get_cluster_info(
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> ClusterInfo:
    """Get overall cluster information (cached 30s via Redis)."""
    try:
        data = await redis.cached_call(
            namespace="cluster",
            identifier="info",
            fetch=lambda: _fetch_cluster_info(k8s),
            ttl=30,
        )
        if isinstance(data, ClusterInfo):
            return data
        return ClusterInfo(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_cluster_info(k8s: KubernetesService) -> dict:
    info = await k8s.get_cluster_info()
    return info.model_dump() if hasattr(info, "model_dump") else info.dict()


@router.get("/nodes", response_model=list[NodeInfo])
async def list_nodes(
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> list[NodeInfo]:
    """List all cluster nodes (cached 30s via Redis)."""
    try:
        rows = await redis.cached_call(
            namespace="cluster",
            identifier="nodes",
            fetch=lambda: _fetch_nodes(k8s),
            ttl=30,
        )
        return [NodeInfo(**row) if isinstance(row, dict) else row for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_nodes(k8s: KubernetesService) -> list[dict]:
    nodes = await k8s.list_nodes()
    return [
        n.model_dump() if hasattr(n, "model_dump") else n.dict()
        for n in nodes
    ]


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
