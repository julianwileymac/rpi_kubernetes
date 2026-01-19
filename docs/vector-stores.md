# Vector Stores Guide

This guide covers the vector database options available in the cluster: ChromaDB (for development) and Milvus (for production).

## Overview

The cluster provides two vector database options:

- **ChromaDB** - Lightweight, embedded vector database for rapid development
- **Milvus** - Production-grade, scalable vector database for large-scale deployments

## ChromaDB - Development Vector Store

### Use Cases

- Rapid prototyping in JupyterHub notebooks
- Small-scale RAG applications
- Development and testing
- Learning and experimentation

### Access

- **Internal**: `chromadb.data-services:8000`
- **External**: `http://chromadb.local:8000`

### Python Client Example

```python
import chromadb
from chromadb.config import Settings

# Connect to ChromaDB
client = chromadb.Client(Settings(
    chroma_api_impl="rest",
    chroma_server_host="chromadb.data-services",
    chroma_server_http_port=8000
))

# Create a collection
collection = client.create_collection(
    name="my_documents",
    metadata={"description": "Document embeddings"}
)

# Add documents
collection.add(
    documents=["Document 1 text", "Document 2 text"],
    ids=["doc1", "doc2"],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]]  # Your embeddings
)

# Query
results = collection.query(
    query_embeddings=[[0.15, 0.25, ...]],
    n_results=5
)
```

### LangChain Integration

```python
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings()

vector_store = Chroma(
    client=client,
    collection_name="my_documents",
    embedding_function=embeddings
)

# Add documents
vector_store.add_texts(["Document 1", "Document 2"])

# Similarity search
docs = vector_store.similarity_search("query text", k=5)
```

### Limitations

- Best for datasets < 10 million vectors
- Single-node deployment
- Limited scalability
- Not optimized for high-throughput production workloads

## Milvus - Production Vector Store

### Use Cases

- Production RAG systems
- Large-scale semantic search
- Recommendation systems
- Similarity search at scale (billions of vectors)

### Access

- **Internal**: `milvus.data-services:19530`
- **External**: `http://milvus.local:19530`

### Python Client Example

```python
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType

# Connect to Milvus
connections.connect(
    alias="default",
    host="milvus.data-services",
    port="19530"
)

# Define schema
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=1000),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)
]
schema = CollectionSchema(fields, "Document collection")

# Create collection
collection = Collection("documents", schema)

# Create index
index_params = {
    "metric_type": "L2",
    "index_type": "HNSW",
    "params": {"M": 16, "efConstruction": 200}
}
collection.create_index(
    field_name="embedding",
    index_params=index_params
)

# Load collection
collection.load()

# Insert data
data = [
    ["Document 1", "Document 2"],
    [[0.1] * 768, [0.2] * 768]  # Embeddings
]
collection.insert(data)
collection.flush()

# Search
search_params = {"metric_type": "L2", "params": {"ef": 64}}
results = collection.search(
    data=[[0.15] * 768],  # Query embedding
    anns_field="embedding",
    param=search_params,
    limit=10,
    output_fields=["text"]
)
```

### LangChain Integration

```python
from langchain.vectorstores import Milvus
from langchain.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings()

vector_store = Milvus(
    embedding_function=embeddings,
    connection_args={
        "host": "milvus.data-services",
        "port": "19530"
    },
    collection_name="documents"
)

# Add documents
vector_store.add_texts(["Document 1", "Document 2"])

# Similarity search
docs = vector_store.similarity_search("query text", k=5)
```

### Advanced Features

#### Index Types

Milvus supports multiple index types:

- **HNSW** - High performance, high memory usage
- **IVF_FLAT** - Balanced performance and memory
- **IVF_PQ** - Memory-efficient, good for large datasets

```python
# HNSW index
index_params = {
    "metric_type": "L2",
    "index_type": "HNSW",
    "params": {"M": 16, "efConstruction": 200}
}

# IVF_FLAT index
index_params = {
    "metric_type": "L2",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 1024}
}
```

#### Partitioning

For very large collections:

```python
# Create partition
collection.create_partition("partition_2024")

# Insert into partition
collection.insert(
    data,
    partition_name="partition_2024"
)
```

## Choosing Between ChromaDB and Milvus

### Use ChromaDB When:

- ✅ Prototyping in JupyterHub
- ✅ Small datasets (< 1M vectors)
- ✅ Quick iteration and experimentation
- ✅ Simple setup required
- ✅ Development/testing environments

### Use Milvus When:

- ✅ Production deployments
- ✅ Large datasets (> 10M vectors)
- ✅ High query throughput required
- ✅ Need advanced indexing options
- ✅ Multi-tenant applications

## Migration Path

1. **Start with ChromaDB**: Develop and test your application
2. **Validate Performance**: Ensure your use case works
3. **Migrate to Milvus**: When ready for production

**Migration Script Example**:

```python
# Export from ChromaDB
chroma_collection = chroma_client.get_collection("my_documents")
chroma_data = chroma_collection.get()

# Import to Milvus
milvus_collection = Collection("my_documents")
milvus_collection.insert([
    chroma_data["ids"],
    chroma_data["embeddings"]
])
```

## Storage Configuration

### ChromaDB

- **Storage**: 20GB PVC
- **Location**: `/chroma/chroma` in container
- **Persistence**: Enabled

### Milvus

- **Vector Storage**: 50GB PVC
- **Object Storage**: MinIO (`milvus-bucket`)
- **Metadata**: Embedded etcd (10GB PVC)

## Monitoring

Both vector stores expose metrics that can be monitored in Prometheus/Grafana:

- Query latency
- Query throughput
- Storage usage
- Index build time

## Best Practices

1. **Choose Appropriate Index**: Balance query speed vs. memory
2. **Batch Operations**: Insert/search in batches for better performance
3. **Monitor Resource Usage**: Watch CPU/memory for both stores
4. **Regular Backups**: Backup vector data regularly
5. **Test with Production Data**: Validate performance with real data volumes

## Troubleshooting

### ChromaDB Connection Issues

```bash
# Check ChromaDB pod
kubectl get pods -n data-services -l app=chromadb

# Check logs
kubectl logs -n data-services -l app=chromadb
```

### Milvus Connection Issues

```bash
# Check Milvus pods
kubectl get pods -n data-services -l app.kubernetes.io/name=milvus

# Check MinIO bucket
kubectl run -it --rm minio-client --image=minio/mc --restart=Never -- \
  sh -c "mc alias set minio http://minio.data-services:9000 minioadmin minioadmin123 && \
         mc ls minio/milvus-bucket"
```

## Additional Resources

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Milvus Documentation](https://milvus.io/docs)
- [LangChain Vector Stores](https://python.langchain.com/docs/modules/data_connection/vectorstores/)
- [Vector Database Comparison](https://www.pinecone.io/learn/vector-database/)
