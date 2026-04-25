# Extending the Framework

This guide covers how to extend the RPi Kubernetes cluster framework with custom services, integrations, and plugins.

## Caching, vector search, and agent memory (Redis 8 Stack)

The framework ships a shared Redis 8 Stack deployment used by the
management API, the [Document Store portal](document-store.md),
LangGraph agents, and the pipelines package.  See
[redis-stack.md](redis-stack.md) for full details; the short version:

```python
from pipelines.redis_cache import cache_aside, SemanticCache
from pipelines.redis_vectors import ensure_index, upsert_chunks, vector_search
from pipelines.agent_memory import get_checkpointer, get_store
from pipelines.redis_om_models import DocumentRecord, ensure_migrated

# Cache-aside for any function (ttl in seconds, namespace controls invalidation)
@cache_aside(ttl=60, namespace="my_module")
def expensive(x: int) -> dict: ...

# Vector store
ensure_index("idx:my_chunks", vector_dims=384)
upsert_chunks("idx:my_chunks", records=[...])
hits = vector_search("idx:my_chunks", query_vector=[...], top_k=5)

# LLM semantic cache (RedisVL)
sc = SemanticCache(name="my_llm_cache", distance_threshold=0.15)
hit = sc.check("What is X?")
if not hit: sc.store("What is X?", "...response...")

# LangGraph agent memory
checkpointer = get_checkpointer()
store = get_store(vector_dims=1536)

# Redis OM models for typed Python objects
ensure_migrated()
doc = DocumentRecord(title="Notes", collection="manuals", source="upload")
doc.save()
```

All of the above are wrapped in OpenTelemetry spans (visible in Jaeger
under `redis.*`) and increment Prometheus counters
(`rpi_redis_ops_total`, `rpi_redis_op_seconds`).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Management Layer                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │Control Panel│  │  FastAPI    │  │  Python SDK │  │  OTEL      │  │
│  │ (Next.js)   │◄►│  Backend    │◄►│ (streaming) │  │ Collector  │  │
│  │             │  │ /kafka      │  │ AvroProducer│  │ (Telemetry)│  │
│  │             │  │ /flink      │  │ FlinkClient │  │            │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │   MinIO     │ │ PostgreSQL  │ │   MLFlow    │ │ JupyterHub  │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Prometheus  │ │   Grafana   │ │    Dask     │ │     Ray     │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Kafka       │ │ Kafka       │ │ Apicurio    │ │ VictoriaM.  │   │
│  │ (Strimzi)   │ │ Connect/    │ │ Registry    │ │             │   │
│  │             │ │ Bridge/MM2  │ │             │ │             │   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └─────────────┘   │
│         │               │               │                            │
│  ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐                    │
│  │ Flink       │ │ Flink       │ │ Flink       │                    │
│  │ Operator    │ │ Session     │ │ TA-Lib Jobs │                    │
│  │             │ │ (PyFlink)   │ │ (Java)      │                    │
│  └─────────────┘ └─────────────┘ └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Adding Custom Services

### Method 1: Kubernetes Manifests

Create a new service directory under `kubernetes/base-services/`:

```
kubernetes/base-services/my-service/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml
└── configmap.yaml
```

Example `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-namespace

resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml

commonLabels:
  app.kubernetes.io/name: my-service
  app.kubernetes.io/part-of: rpi-k8s-platform
```

Add to root kustomization:

```yaml
# kubernetes/kustomization.yaml
resources:
  - base-services/my-service/
```

### Method 2: Helm Charts

For complex services, use Helm:

```bash
# Create values file
cat > kubernetes/base-services/my-service/values.yaml << EOF
replicaCount: 2
image:
  repository: my-registry/my-service
  tag: latest
resources:
  requests:
    cpu: 100m
    memory: 128Mi
EOF

# Install
helm install my-service my-chart/my-service \
  --namespace my-namespace \
  --create-namespace \
  -f kubernetes/base-services/my-service/values.yaml
```

## Extending the Management API

### Adding a New Service Module

Create a new service in `management/backend/src/services/`:

```python
# management/backend/src/services/my_service.py
"""Custom service integration."""

import logging
from typing import Any, Optional
from ..config import Settings

logger = logging.getLogger(__name__)


class MyService:
    """Service for custom operations."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    async def get_status(self) -> dict[str, Any]:
        """Get service status."""
        # Implementation here
        return {"status": "healthy"}

    async def perform_action(self, params: dict) -> dict[str, Any]:
        """Perform a custom action."""
        # Implementation here
        return {"result": "success"}
```

### Adding API Endpoints

Create a new router in `management/backend/src/api/`:

```python
# management/backend/src/api/my_service.py
"""Custom service API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from ..config import Settings, get_settings
from ..services.my_service import MyService

router = APIRouter()


def get_my_service(settings: Settings = Depends(get_settings)) -> MyService:
    return MyService(settings)


@router.get("/status")
async def get_status(service: MyService = Depends(get_my_service)):
    """Get service status."""
    return await service.get_status()


@router.post("/action")
async def perform_action(
    params: dict,
    service: MyService = Depends(get_my_service),
):
    """Perform a custom action."""
    return await service.perform_action(params)
```

Register the router in `management/backend/src/api/__init__.py`:

```python
from .my_service import router as my_service_router

api_router.include_router(
    my_service_router,
    prefix="/my-service",
    tags=["my-service"],
)
```

## Adding Frontend Components

### Creating a New Dashboard Page

Create a new page in `management/frontend/src/app/`:

```typescript
// management/frontend/src/app/my-service/page.tsx
'use client'

import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { api } from '@/lib/api'

export default function MyServicePage() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-service-status'],
    queryFn: () => api.get('/my-service/status').then(res => res.data),
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="My Service" />
        <main className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div>Loading...</div>
          ) : (
            <div className="card p-6">
              <h2 className="text-lg font-semibold">Status</h2>
              <pre>{JSON.stringify(data, null, 2)}</pre>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
```

Add to navigation in `Sidebar.tsx`:

```typescript
const navigation = [
  // ... existing items
  { name: 'My Service', href: '/my-service', icon: MyIcon },
]
```

## Adding OpenTelemetry Instrumentation

### Instrument Custom Code

```python
from management.backend.src.telemetry import traced, SpanContext

# Using decorator
@traced("my_operation", attributes={"service": "my-service"})
async def my_operation():
    # Your code here
    pass

# Using context manager
async def another_operation():
    with SpanContext("sub_operation") as span:
        span.set_attribute("key", "value")
        # Your code here
```

### Add Custom Metrics

```python
from prometheus_client import Counter, Histogram

# Define metrics
REQUEST_COUNT = Counter(
    'my_service_requests_total',
    'Total requests to my service',
    ['method', 'status']
)

REQUEST_DURATION = Histogram(
    'my_service_request_duration_seconds',
    'Request duration in seconds',
    ['method']
)

# Use in code
@REQUEST_DURATION.labels(method='get_status').time()
async def get_status():
    REQUEST_COUNT.labels(method='get_status', status='success').inc()
    # ...
```

## Creating Custom Resource Definitions (CRDs)

For advanced use cases, create Kubernetes CRDs:

```yaml
# kubernetes/crds/my-resource.yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: myresources.rpi-k8s.io
spec:
  group: rpi-k8s.io
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                replicas:
                  type: integer
                config:
                  type: object
  scope: Namespaced
  names:
    plural: myresources
    singular: myresource
    kind: MyResource
    shortNames:
      - mr
```

## Kafka + Flink Control Plane

The management backend exposes `/kafka` and `/flink` routers (see
[`management-api.md`](./management-api.md)) for declarative control of
Strimzi CRDs and Flink jobs:

```bash
# List every KafkaTopic CR
curl http://control.local/api/kafka/topics

# Activate a suspended FlinkSessionJob
curl -XPOST http://control.local/api/flink/sessionjobs/indicators-momentum/activate

# Scale a running job
curl -XPOST http://control.local/api/flink/sessionjobs/indicator-compute/scale?parallelism=4
```

The [Python SDK](../management/sdk/) wraps these endpoints plus direct
Kafka IO:

```python
from rpi_k8s_sdk import configure_tracing
from rpi_k8s_sdk.kafka import AvroProducer
from rpi_k8s_sdk.flink import ManagementFlinkClient

configure_tracing("my-pipeline")
with AvroProducer(bootstrap="...", username="producer-market", password=...) as p:
    p.produce(topic="market.trade.v1", schema="market_trade_v1", record={...}, key="AAPL")

ManagementFlinkClient("http://control.local/api").activate("indicators-momentum")
```

See [`docs/kafka-clients.md`](./kafka-clients.md) for the Python + Java client
templates under [`templates/`](../templates/) and the bundled samples under
[`samples/market-data-producers/`](../samples/market-data-producers/).

## Integration with agentic_assistants

The cluster is designed to integrate with the `agentic_assistants` framework:

### Shared MLFlow Backend

```python
# In your agentic_assistants config
from agentic_assistants import AgenticConfig

config = AgenticConfig(
    mlflow_enabled=True,
    mlflow_tracking_uri="http://mlflow.ml-platform.svc.cluster.local:5000",
)
```

### Using Cluster Resources from JupyterHub

```python
# In a JupyterHub notebook
import mlflow
import os

# MLFlow is pre-configured via environment variables
mlflow.set_tracking_uri(os.environ['MLFLOW_TRACKING_URI'])

# Use MinIO for artifact storage
import boto3
s3 = boto3.client(
    's3',
    endpoint_url=os.environ['S3_ENDPOINT_URL'],
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
)
```

### Connecting Dask/Ray from Notebooks

```python
# Connect to Dask cluster
from dask.distributed import Client
client = Client('tcp://dask-scheduler.ml-platform.svc.cluster.local:8786')

# Connect to Ray cluster
import ray
ray.init(address='ray://ray-head.ml-platform.svc.cluster.local:10001')
```

## Webhook Integration

The management API supports webhooks for deployment events:

### Configure Webhooks

```python
# management/backend/src/config.py
class WebhookSettings(BaseSettings):
    enabled: bool = True
    endpoints: list[str] = []
    secret: str = ""
```

### Webhook Payload

```json
{
  "event": "deployment.created",
  "timestamp": "2024-01-10T12:00:00Z",
  "deployment": {
    "name": "my-app",
    "namespace": "default",
    "replicas": 3,
    "image": "my-registry/my-app:v1.0.0"
  }
}
```

## Plugin Architecture

Create plugins by extending the base classes:

```python
# management/backend/src/plugins/base.py
from abc import ABC, abstractmethod

class Plugin(ABC):
    """Base class for management plugins."""

    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the plugin."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the plugin."""
        pass


class DeploymentPlugin(Plugin):
    """Plugin for custom deployment types."""

    @abstractmethod
    async def deploy(self, config: dict) -> dict:
        """Deploy using this plugin."""
        pass

    @abstractmethod
    async def status(self, name: str) -> dict:
        """Get deployment status."""
        pass
```

## Adding a new Alpha Vantage endpoint

The AV integration follows a layered design: add the endpoint to the client
library once, then everything above it reuses the typed response.

1. **Client library**: add a method (and an async twin) to the matching
   `integrations/alphavantage/src/alphavantage_client/endpoints/*.py`.
   Parse the AV response into the appropriate Pydantic model from
   `models/`. Add a default TTL to `_cache.default_ttl` if the data is
   immutable.
2. **Re-export**: if the response is a new model, add it to
   `alphavantage_client/models/__init__.py` and bump the reference in
   `management/backend/src/models/alphavantage.py`.
3. **Backend**: add a `service.xxx(...)` method in
   `management/backend/src/services/alphavantage_service.py` and a route in
   `management/backend/src/api/alphavantage.py`. Follow the existing
   `ValueError -> HTTPException(400)` and `Exception -> HTTPException(500)`
   patterns.
4. **Frontend**: extend `alphaVantageApi` in
   `management/frontend/src/lib/api.ts` with a typed TS wrapper; add the UI
   under `management/frontend/src/app/alphavantage/...`.
5. **Streaming (optional)**: if the endpoint should be polled, add a stream
   coroutine in `templates/alphavantage-producer/src/alphavantage_producer/streams.py`
   and register it in `STREAMS`. Add a matching Avro schema under
   `flink-jobs/jobs/schemas/alphavantage/` and a new KafkaTopic.
6. **Batch (optional)**: extend `pipelines/alphavantage_io.py::_LOADERS`
   with a new category + loader function, then author a WorkflowTemplate
   at `kubernetes/mlops/pipelines/alphavantage/` that delegates to
   `av-bulk` with the right `category` + `extra_params`.

The rate limiter, retry policy, and cache apply automatically to every new
endpoint as long as it routes through `client._sync_request` /
`client._async_request`.

## Best Practices

1. **Use Namespaces**: Organize resources in appropriate namespaces
2. **Label Everything**: Use consistent labels for filtering and selection
3. **Resource Limits**: Always set resource requests and limits
4. **Health Checks**: Implement readiness and liveness probes
5. **Secrets Management**: Use Kubernetes secrets, never hardcode credentials
6. **Observability**: Add metrics, logs, and traces to all services
7. **Documentation**: Document all custom additions

## Testing Extensions

```bash
# Run backend tests
cd management/backend
pytest tests/

# Run frontend tests
cd management/frontend
npm test

# Test Kubernetes manifests
kubectl apply -k kubernetes/ --dry-run=client

# Validate Helm charts
helm lint kubernetes/base-services/my-service/
```
