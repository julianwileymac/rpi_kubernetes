# MLOps Workflows Guide

This guide covers Argo Workflows and BentoML for ML pipeline orchestration and model serving.

## Overview

The cluster provides two key MLOps tools:

- **Argo Workflows** - Kubernetes-native workflow engine for ML pipelines
- **BentoML / Yatai** - Model serving and deployment platform

## Argo Workflows

### Use Cases

- ML training pipelines
- Data preprocessing workflows
- Model evaluation and validation
- Distributed training coordination
- CI/CD for ML models

### Access

- **Internal**: `http://argo-workflows-server.mlops:2746`
- **External**: `http://argo.local:2746`

### Basic Workflow Example

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-pipeline-
  namespace: mlops
spec:
  entrypoint: train-model
  templates:
    - name: train-model
      dag:
        tasks:
          - name: prepare-data
            template: data-prep
          - name: train
            dependencies: [prepare-data]
            template: train-job
          - name: evaluate
            dependencies: [train]
            template: evaluate-job
    
    - name: data-prep
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Preparing data...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
    
    - name: train-job
      container:
        image: rayproject/ray:2.9.0
        command: [python, -c]
        args: ["print('Training model...')"]
        resources:
          requests:
            memory: 2Gi
            cpu: 1000m
    
    - name: evaluate-job
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Evaluating model...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
```

### Integration with Ray

Launch distributed Ray jobs from Argo Workflows:

```yaml
- name: ray-training
  container:
    image: rayproject/ray:2.9.0
    command: [ray, submit]
    args:
      - --address=ray-head.ml-platform:10001
      - --working-dir=/workspace
      - train_distributed.py
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
```

### Integration with MLFlow

Log experiments and register models:

```yaml
- name: train-and-log
  container:
    image: python:3.11
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
    command: [python, -c]
    args:
      - |
        import mlflow
        import mlflow.sklearn
        
        with mlflow.start_run():
            # Train model
            model = train_model()
            
            # Log parameters and metrics
            mlflow.log_param("epochs", 10)
            mlflow.log_metric("accuracy", 0.95)
            
            # Register model
            mlflow.sklearn.log_model(model, "model")
```

### Artifact Management

Workflows store artifacts in MinIO:

```yaml
- name: save-artifact
  container:
    image: python:3.11
    command: [python, -c]
    args: ["print('Saving artifact...')"]
  outputs:
    artifacts:
      - name: model
        path: /workspace/model.pkl
        s3:
          endpoint: minio.data-services:9000
          bucket: argo-workflows
          key: models/{{workflow.name}}/model.pkl
          accessKeySecret:
            name: argo-workflows-minio
            key: accesskey
          secretKeySecret:
            name: argo-workflows-minio
            key: secretkey
```

### Workflow Templates

Create reusable workflow templates:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: ml-training-template
  namespace: mlops
spec:
  entrypoint: train
  templates:
    - name: train
      dag:
        tasks:
          - name: train
            template: train-job
    # ... templates ...
```

## BentoML / Yatai

### Use Cases

- Model serving as REST APIs
- Model versioning and management
- A/B testing different model versions
- Production model deployment
- Integration with MLFlow model registry

### Access

- **Internal**: `http://yatai.ml-platform:3000`
- **External**: `http://yatai.local:3000`

### Creating a Bento Service

#### 1. Define Service

```python
# service.py
import bentoml
from bentoml.io import JSON, NumpyNdarray
import numpy as np

@bentoml.service(
    resources={"cpu": "1", "memory": "2Gi"},
    traffic={"timeout": 60}
)
class MyMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data: dict):
        # Your inference logic
        result = model.predict(input_data["features"])
        return {"prediction": result.tolist()}
    
    @bentoml.api(input=NumpyNdarray(), output=NumpyNdarray())
    def predict_batch(self, input_array: np.ndarray):
        # Batch prediction
        return model.predict(input_array)
```

#### 2. Build Bento

```python
# build_bento.py
import bentoml

# Build the service
svc = MyMLService()

# Save as Bento
bentoml.build("my-ml-service:latest")
```

#### 3. Deploy to Kubernetes

```python
# deploy.py
import bentoml

# Deploy using Yatai
yatai_client = bentoml.YataiClient()

deployment = yatai_client.deployment.create(
    name="my-ml-service",
    bento="my-ml-service:latest",
    namespace="ml-platform",
    replicas=2
)
```

### Integration with MLFlow

Deploy models from MLFlow registry:

```python
import mlflow
import bentoml

# Load model from MLFlow
model = mlflow.sklearn.load_model("models:/my-model/Production")

# Create BentoML service
svc = bentoml.sklearn.save_model("my-model", model)

# Deploy
bentoml.deploy("my-model", platform="yatai")
```

### Integration with Ray

Use Ray for distributed inference:

```python
import ray
from bentoml.io import JSON

@bentoml.service(
    resources={"cpu": "2", "memory": "4Gi"}
)
class RayMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data):
        @ray.remote
        def process_chunk(chunk):
            return model.predict(chunk)
        
        # Distribute processing
        results = ray.get([
            process_chunk.remote(chunk) 
            for chunk in data_chunks
        ])
        return {"predictions": results}
```

### Model Versioning

BentoML tracks model versions automatically:

```python
# List all versions
bentoml.models.list()

# Load specific version
model = bentoml.models.get("my-model:latest")
model = bentoml.models.get("my-model:v1.0.0")

# Tag versions
bentoml.models.tag("my-model:latest", "production")
```

## Complete ML Pipeline Example

### Workflow: Train → Evaluate → Deploy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-pipeline-
  namespace: mlops
spec:
  entrypoint: ml-pipeline
  templates:
    - name: ml-pipeline
      dag:
        tasks:
          - name: train
            template: train-model
          - name: evaluate
            dependencies: [train]
            template: evaluate-model
          - name: deploy
            dependencies: [evaluate]
            template: deploy-model
            when: "{{tasks.evaluate.outputs.result}} == success"
    
    - name: train-model
      container:
        image: python:3.11
        command: [python, train.py]
        env:
          - name: MLFLOW_TRACKING_URI
            value: http://mlflow.ml-platform:5000
        resources:
          requests:
            memory: 4Gi
            cpu: 2000m
    
    - name: evaluate-model
      container:
        image: python:3.11
        command: [python, evaluate.py]
        env:
          - name: MLFLOW_TRACKING_URI
            value: http://mlflow.ml-platform:5000
        resources:
          requests:
            memory: 2Gi
            cpu: 1000m
    
    - name: deploy-model
      container:
        image: bentoml/bentoml:latest
        command: [bentoml, deploy]
        args:
          - --yatai-endpoint=http://yatai.ml-platform:3000
          - my-model:latest
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
```

## Monitoring

### Argo Workflows Metrics

Argo Workflows exposes Prometheus metrics. Create a ServiceMonitor:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: argo-workflows
  namespace: mlops
spec:
  selector:
    matchLabels:
      app: argo-workflows-controller-metrics
  endpoints:
    - port: metrics
      interval: 30s
```

### BentoML Service Metrics

BentoML services expose metrics automatically. Monitor in Grafana:

- Request latency
- Request throughput
- Error rates
- Resource usage

## Best Practices

1. **Use Workflow Templates**: Reusable pipeline definitions
2. **Version Models**: Track all model versions in MLFlow
3. **Test Before Deploy**: Validate models before production
4. **Monitor Resources**: Watch CPU/memory usage
5. **Automate Pipelines**: Trigger workflows on events
6. **Use Artifacts**: Store intermediate results in MinIO

## Troubleshooting

### Workflow Not Starting

```bash
# Check workflow status
kubectl get workflows -n mlops

# Check workflow logs
argo logs <workflow-name> -n mlops

# Check pod events
kubectl describe pod <pod-name> -n mlops
```

### BentoML Deployment Issues

```bash
# Check Yatai logs
kubectl logs -n ml-platform -l app=yatai

# Check deployment status
kubectl get deployments -n ml-platform

# Check service endpoints
kubectl get endpoints -n ml-platform
```

## Additional Resources

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [BentoML Documentation](https://docs.bentoml.com/)
- [MLFlow Documentation](https://mlflow.org/docs/latest/index.html)
- [Ray Documentation](https://docs.ray.io/)
