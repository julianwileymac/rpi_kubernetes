"""API routes for the management backend."""

from fastapi import APIRouter

from .cluster import router as cluster_router
from .deployments import router as deployments_router
from .hardware import router as hardware_router
from .mlflow import router as mlflow_router
from .health import router as health_router

# Create main API router
api_router = APIRouter()

# Include all sub-routers
api_router.include_router(health_router, tags=["health"])
api_router.include_router(cluster_router, prefix="/cluster", tags=["cluster"])
api_router.include_router(deployments_router, prefix="/deployments", tags=["deployments"])
api_router.include_router(hardware_router, prefix="/hardware", tags=["hardware"])
api_router.include_router(mlflow_router, prefix="/mlflow", tags=["mlflow"])

__all__ = ["api_router"]
