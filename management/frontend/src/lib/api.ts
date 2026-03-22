import axios from 'axios'

const isServer = typeof window === 'undefined'
const API_BASE_URL = isServer
  ? (process.env.API_URL || 'http://management-api.management.svc.cluster.local:8080') + '/api'
  : '/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

export interface NodeMetrics {
  cpu_capacity: string
  cpu_allocatable: string
  cpu_usage?: string
  cpu_usage_percent?: number
  memory_capacity: string
  memory_allocatable: string
  memory_usage?: string
  memory_usage_percent?: number
  pods_capacity: number
  pods_running: number
}

export interface NodeInfo {
  name: string
  status: string
  roles: string[]
  ip_address: string
  architecture: string
  os_image: string
  kernel_version: string
  container_runtime: string
  kubelet_version: string
  created_at: string
  labels: Record<string, string>
  taints: string[]
  conditions: Record<string, string>
  metrics?: NodeMetrics
}

export interface ServiceInfo {
  name: string
  namespace: string
  type: string
  cluster_ip?: string
  external_ip?: string
  ports: Array<{
    name?: string
    port: number
    target_port: string
    protocol: string
    node_port?: number
  }>
  selector: Record<string, string>
  created_at: string
}

export interface ClusterInfo {
  name: string
  version: string
  node_count: number
  ready_nodes: number
  total_pods: number
  running_pods: number
  total_cpu: string
  total_memory: string
  namespaces: string[]
  nodes: NodeInfo[]
}

export interface HardwareMetrics {
  cpu_temperature?: number
  cpu_frequency?: number
  cpu_usage_percent: number
  load_average_1m: number
  load_average_5m: number
  load_average_15m: number
  memory_total_mb: number
  memory_used_mb: number
  memory_available_mb: number
  memory_usage_percent: number
  disk_total_gb: number
  disk_used_gb: number
  disk_available_gb: number
  disk_usage_percent: number
  network_rx_bytes: number
  network_tx_bytes: number
  throttle_status: string[]
  gpu_temperature?: number
  voltage?: number
}

export interface NodeHardwareInfo {
  node_name: string
  ip_address: string
  hardware_type: string
  model?: string
  serial?: string
  cpu_model?: string
  cpu_cores: number
  architecture: string
  uptime_seconds: number
  last_boot: string
  metrics?: HardwareMetrics
  online: boolean
  last_seen: string
}

export interface ClusterHardwareOverview {
  total_nodes: number
  online_nodes: number
  total_cpu_cores: number
  total_memory_gb: number
  total_storage_gb: number
  average_cpu_usage: number
  average_memory_usage: number
  average_temperature?: number
  nodes: NodeHardwareInfo[]
}

export interface HealthStatus {
  status: string
  version: string
  kubernetes_connected: boolean
  mlflow_connected: boolean
  minio_connected?: boolean
}

export const clusterApi = {
  async getClusterInfo(): Promise<ClusterInfo> {
    const response = await apiClient.get<ClusterInfo>('/cluster')
    return response.data
  },
  async getNodes(): Promise<NodeInfo[]> {
    const response = await apiClient.get<NodeInfo[]>('/cluster/nodes')
    return response.data
  },
  async getServices(): Promise<ServiceInfo[]> {
    const response = await apiClient.get<ServiceInfo[]>('/cluster/services')
    return response.data
  },
}

export const hardwareApi = {
  async getOverview(): Promise<ClusterHardwareOverview> {
    const response = await apiClient.get<ClusterHardwareOverview>('/hardware')
    return response.data
  },
}

export const healthApi = {
  async getStatus(): Promise<HealthStatus> {
    const response = await apiClient.get<HealthStatus>('/health')
    return response.data
  },
}
