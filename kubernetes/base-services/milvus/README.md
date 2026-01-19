# Milvus - Production Vector Database

Milvus is a production-grade, open-source vector database designed to handle billions of vectors with high performance.

## Installation

```bash
# Add Milvus Helm repository
helm repo add milvus https://milvus-io.github.io/milvus-helm
helm repo update

# Install Milvus
helm install milvus milvus/milvus \
  --namespace data-services \
  --create-namespace \
  -f values.yaml
```

## Configuration

This deployment uses:
- **Standalone Mode**: Appropriate for the RPi cluster size
- **External MinIO**: Uses existing MinIO instance for object storage
- **Embedded etcd**: For metadata storage
- **50GB PVC**: For vector data persistence
- **ServiceMonitor**: Enabled for Prometheus metrics

## Access

After installation, Milvus is accessible at:
- **Internal**: `milvus.data-services:19530`
- **External**: `http://milvus.local` (via Ingress)

## Python Client Example

```python
from pymilvus import connections, Collection

# Connect to Milvus
connections.connect(
    alias="default",
    host="milvus.data-services",
    port="19530"
)

# Create a collection
from pymilvus import CollectionSchema, FieldSchema, DataType

fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=128)
]
schema = CollectionSchema(fields, "Example collection")
collection = Collection("example_collection", schema)

# Insert vectors
vectors = [[random.random() for _ in range(128)] for _ in range(1000)]
collection.insert([list(range(1000)), vectors])
collection.flush()

# Search
search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
results = collection.search(
    data=[vectors[0]],
    anns_field="embedding",
    param=search_params,
    limit=10
)
```

## Integration with LangChain

```python
from langchain.vectorstores import Milvus
from langchain.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings()
vector_store = Milvus(
    embedding_function=embeddings,
    connection_args={
        "host": "milvus.data-services",
        "port": "19530"
    }
)
```

## Monitoring

Milvus exposes Prometheus metrics and is automatically scraped by Prometheus via ServiceMonitor. Metrics are available in Grafana.

## MinIO Bucket Setup

Before using Milvus, ensure the MinIO bucket exists:

```bash
# Using MinIO client
mc alias set minio http://minio.data-services:9000 minioadmin minioadmin123
mc mb minio/milvus-bucket
```
