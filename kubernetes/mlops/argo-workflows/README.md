# Argo Workflows - ML Pipeline Orchestration

Argo Workflows is a Kubernetes-native workflow engine for orchestrating parallel jobs on Kubernetes, perfect for ML training pipelines and data processing workflows.

## Installation

```bash
# Add Argo Helm repository
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Create MinIO bucket for artifacts
kubectl run -it --rm minio-client --image=minio/mc --restart=Never -- \
  sh -c "mc alias set minio http://minio.data-services:9000 minioadmin minioadmin123 && \
         mc mb --ignore-existing minio/argo-workflows && \
         mc anonymous set download minio/argo-workflows"

# Install Argo Workflows
helm install argo-workflows argo/argo-workflows \
  --namespace mlops \
  --create-namespace \
  -f values.yaml

# Create MinIO secret
kubectl apply -f secret.yaml
```

## Access

After installation, Argo Workflows UI is accessible at:
- **Internal**: `http://argo-workflows-server.mlops:2746`
- **External**: `http://argo.local` (via Ingress)

## Example Workflow: ML Training Pipeline

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-training-
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
        args: ["print('Training model with Ray...')"]
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

## Integration with Ray

Argo Workflows can launch Ray jobs for distributed ML training:

```yaml
- name: ray-training
  container:
    image: rayproject/ray:2.9.0
    command: [ray, submit]
    args:
      - --address=ray-head.ml-platform:10001
      - train_script.py
```

## Integration with MLFlow

Workflows can log experiments to MLFlow:

```yaml
- name: log-to-mlflow
  container:
    image: python:3.11
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
    command: [python, -c]
    args:
      - |
        import mlflow
        mlflow.log_param("epochs", 10)
        mlflow.log_metric("accuracy", 0.95)
```

## Artifact Storage

Workflows store artifacts in MinIO. Access artifacts via the Argo UI or MinIO console.

## Monitoring

Argo Workflows exposes Prometheus metrics. Create a ServiceMonitor to scrape metrics:

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
