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
  redis_connected?: boolean
  redis_modules_missing?: string[]
}

export interface DocumentSummary {
  id: string
  title: string
  collection: string
  tags: string[]
  source: string
  source_uri: string
  mime_type: string
  size_bytes: number
  chunk_count: number
  created_at: number
  updated_at: number
  owner: string
  description: string
  checksum: string
}

export interface DocumentSearchHit {
  id: string
  title: string
  text: string
  score: number
  collection: string
  doc_id: string
  tags: string[]
}

export interface AnnotationModel {
  id: string
  doc_id: string
  author: string
  body: string
  tags: string[]
  anchor: string
  created_at: number
  updated_at: number
}

export interface ArtifactListEntry {
  bucket: string
  key: string
  size: number
  last_modified: number | null
  is_json: boolean
}

export interface RedisHealth {
  enabled: boolean
  ping: boolean
  modules: Record<string, string>
  missing_modules: string[]
  error?: string
}

export interface RedisIndexInfo {
  name: string
  info: Record<string, unknown>
}

export interface DocumentSearchPayload {
  query: string
  mode: 'hybrid' | 'semantic' | 'keyword'
  top_k?: number
  collection?: string | null
  tags?: string[]
}

export interface ArtifactIngestPayload {
  bucket: string
  key: string
  title?: string | null
  tags?: string[]
  collection?: string | null
  owner?: string
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

export const documentsApi = {
  async list(params: {
    query?: string
    collection?: string
    tag?: string[]
    limit?: number
    offset?: number
  } = {}): Promise<DocumentSummary[]> {
    const response = await apiClient.get<DocumentSummary[]>('/documents', {
      params,
    })
    return response.data
  },
  async get(id: string): Promise<DocumentSummary> {
    const response = await apiClient.get<DocumentSummary>(`/documents/${id}`)
    return response.data
  },
  async upload(file: File, fields: {
    title?: string
    tags?: string
    collection?: string
    owner?: string
    description?: string
    source?: string
  } = {}): Promise<DocumentSummary> {
    const form = new FormData()
    form.append('file', file)
    Object.entries(fields).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        form.append(key, value)
      }
    })
    const response = await apiClient.post<DocumentSummary>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },
  async remove(id: string): Promise<{ deleted: number; id: string }> {
    const response = await apiClient.delete<{ deleted: number; id: string }>(
      `/documents/${id}`,
    )
    return response.data
  },
  async search(payload: DocumentSearchPayload): Promise<DocumentSearchHit[]> {
    const response = await apiClient.post<DocumentSearchHit[]>(
      '/documents/search',
      payload,
    )
    return response.data
  },
  async listAnnotations(docId: string): Promise<AnnotationModel[]> {
    const response = await apiClient.get<AnnotationModel[]>(
      `/documents/${docId}/annotations`,
    )
    return response.data
  },
  async addAnnotation(docId: string, payload: {
    body: string
    author?: string
    tags?: string[]
    anchor?: string
  }): Promise<AnnotationModel> {
    const response = await apiClient.post<AnnotationModel>(
      `/documents/${docId}/annotations`,
      payload,
    )
    return response.data
  },
  async deleteAnnotation(docId: string, annId: string): Promise<{ deleted: number }> {
    const response = await apiClient.delete<{ deleted: number }>(
      `/documents/${docId}/annotations/${annId}`,
    )
    return response.data
  },
  async listArtifactBuckets(): Promise<string[]> {
    const response = await apiClient.get<string[]>('/documents/artifacts/buckets')
    return response.data
  },
  async browseArtifacts(bucket: string, prefix = '', maxKeys = 200): Promise<ArtifactListEntry[]> {
    const response = await apiClient.get<ArtifactListEntry[]>(
      '/documents/artifacts/browse',
      { params: { bucket, prefix, max_keys: maxKeys } },
    )
    return response.data
  },
  async ingestArtifact(payload: ArtifactIngestPayload): Promise<DocumentSummary> {
    const response = await apiClient.post<DocumentSummary>(
      '/documents/artifacts/ingest',
      payload,
    )
    return response.data
  },
}

export const redisApi = {
  async health(): Promise<RedisHealth> {
    const response = await apiClient.get<RedisHealth>('/redis/health')
    return response.data
  },
  async stats(sections?: string[]): Promise<{ info: Record<string, unknown>; cache: Record<string, number> }> {
    const params: Record<string, string | string[]> = {}
    if (sections?.length) params.sections = sections
    const response = await apiClient.get('/redis/stats', { params })
    return response.data
  },
  async indexes(): Promise<RedisIndexInfo[]> {
    const response = await apiClient.get<RedisIndexInfo[]>('/redis/indexes')
    return response.data
  },
  async invalidate(namespace: string): Promise<{ namespace: string; deleted: number }> {
    const response = await apiClient.delete<{ namespace: string; deleted: number }>(
      `/redis/cache/${encodeURIComponent(namespace)}`,
    )
    return response.data
  },
}


// ===========================================================================
// Alpha Vantage
// ===========================================================================

export interface AlphaVantageHealth {
  enabled: boolean
  credentials_loaded: boolean
  base_url: string
  rpm_limit: number
  daily_limit: number
  cache_backend: string
  client_version?: string | null
  client_available: boolean
  message?: string | null
}

export interface AlphaVantageUsage {
  rpm_limit: number
  daily_limit: number
  requests_this_minute: number
  requests_today: number
  tokens_available: number
  next_refill_seconds: number
  daily_reset_utc: string
}

export interface SymbolSearchMatch {
  symbol: string
  name?: string
  type?: string
  region?: string
  market_open?: string
  market_close?: string
  timezone?: string
  currency?: string
  match_score?: number
}

export interface OhlcvBar {
  timestamp: string
  open?: number
  high?: number
  low?: number
  close?: number
  adjusted_close?: number
  volume?: number
  dividend_amount?: number
  split_coefficient?: number
}

export interface TimeSeriesPayload {
  function: string
  symbol: string
  interval?: string | null
  output_size?: string | null
  entitlement?: string | null
  metadata?: Record<string, unknown> | null
  bars: OhlcvBar[]
}

export interface GlobalQuote {
  symbol: string
  open?: number
  high?: number
  low?: number
  price?: number
  volume?: number
  latest_trading_day?: string
  previous_close?: number
  change?: number
  change_percent?: string
}

export interface NewsArticle {
  title?: string
  url?: string
  time_published?: string
  authors?: string[]
  summary?: string
  banner_image?: string
  source?: string
  source_domain?: string
  category_within_source?: string
  overall_sentiment_score?: number
  overall_sentiment_label?: string
  topics?: { topic?: string; relevance_score?: number }[]
  ticker_sentiment?: {
    ticker?: string
    relevance_score?: number
    ticker_sentiment_score?: number
    ticker_sentiment_label?: string
  }[]
}

export interface NewsSentimentPayload {
  items?: string
  feed: NewsArticle[]
}

export interface TopMover {
  ticker?: string
  price?: string
  change_amount?: string
  change_percentage?: string
  volume?: string
}

export interface TopMoversPayload {
  last_updated?: string
  top_gainers: TopMover[]
  top_losers: TopMover[]
  most_actively_traded: TopMover[]
}

export interface FundamentalsEarnings {
  symbol?: string
  annual_earnings: Array<Record<string, unknown>>
  quarterly_earnings: Array<Record<string, unknown>>
}

export interface MarketStatusPayload {
  endpoint?: string
  markets: Array<{
    market_type?: string
    region?: string
    primary_exchanges?: string
    local_open?: string
    local_close?: string
    current_status?: string
    notes?: string
  }>
}

export interface AvBulkLoadRequest {
  category: string
  symbols: string[]
  date_range?: { start?: string; end?: string } | null
  extra_params?: Record<string, unknown>
  target_bucket?: string
}

export interface AvBulkLoadResponse {
  workflow_name: string
  namespace: string
  category: string
  status: string
  submitted_at: string
  symbols: string[]
  parameters: Record<string, unknown>
}

export interface AvWorkflowEntry {
  name: string
  namespace: string
  phase: string
  started_at?: string | null
  finished_at?: string | null
  category?: string | null
}

export interface AvStreamToggle {
  deployment: string
  namespace: string
  desired_replicas: number
  previous_replicas: number
  ready: boolean
  message: string
}

export const alphaVantageApi = {
  async health(): Promise<AlphaVantageHealth> {
    const response = await apiClient.get<AlphaVantageHealth>('/alphavantage/health')
    return response.data
  },
  async usage(): Promise<AlphaVantageUsage> {
    const response = await apiClient.get<AlphaVantageUsage>('/alphavantage/usage')
    return response.data
  },
  async searchSymbols(keywords: string): Promise<SymbolSearchMatch[]> {
    const response = await apiClient.get<SymbolSearchMatch[]>('/alphavantage/search', {
      params: { keywords },
    })
    return response.data
  },
  async marketStatus(): Promise<MarketStatusPayload> {
    const response = await apiClient.get<MarketStatusPayload>('/alphavantage/market-status')
    return response.data
  },
  async timeseries(
    fn: string,
    params: Record<string, string | number | boolean | undefined | null>,
  ): Promise<TimeSeriesPayload | GlobalQuote | unknown> {
    const response = await apiClient.get(`/alphavantage/timeseries/${fn}`, { params })
    return response.data
  },
  async globalQuote(symbol: string): Promise<GlobalQuote> {
    const response = await apiClient.get<GlobalQuote>('/alphavantage/timeseries/global_quote', {
      params: { symbol },
    })
    return response.data
  },
  async fundamentals(
    kind: string,
    params: Record<string, string | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/fundamentals/${kind}`, { params })
    return response.data
  },
  async technicals(
    indicator: string,
    params: Record<string, string | number | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/technicals/${indicator}`, { params })
    return response.data
  },
  async intelligence(
    kind: string,
    params: Record<string, string | number | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/intelligence/${kind}`, { params })
    return response.data
  },
  async topMovers(): Promise<TopMoversPayload> {
    const response = await apiClient.get<TopMoversPayload>('/alphavantage/intelligence/top-movers')
    return response.data
  },
  async news(params: {
    tickers?: string
    topics?: string
    time_from?: string
    time_to?: string
    sort?: string
    limit?: number
  }): Promise<NewsSentimentPayload> {
    const response = await apiClient.get<NewsSentimentPayload>(
      '/alphavantage/intelligence/news',
      { params },
    )
    return response.data
  },
  async forex(
    kind: string,
    params: Record<string, string | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/forex/${kind}`, { params })
    return response.data
  },
  async crypto(
    kind: string,
    params: Record<string, string | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/crypto/${kind}`, { params })
    return response.data
  },
  async options(
    kind: string,
    params: Record<string, string | undefined | null>,
  ): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/options/${kind}`, { params })
    return response.data
  },
  async commodity(commodity: string, interval = 'monthly'): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/commodities/${commodity}`, {
      params: { interval },
    })
    return response.data
  },
  async economic(indicator: string, params: Record<string, string> = {}): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/economics/${indicator}`, {
      params,
    })
    return response.data
  },
  async indices(name: string, interval?: string): Promise<unknown> {
    const response = await apiClient.get(`/alphavantage/indices/${name}`, {
      params: interval ? { interval } : {},
    })
    return response.data
  },
  async indicesCatalog(): Promise<unknown[]> {
    const response = await apiClient.get<unknown[]>('/alphavantage/indices/catalog')
    return response.data
  },
  async bulkLoad(payload: AvBulkLoadRequest): Promise<AvBulkLoadResponse> {
    const response = await apiClient.post<AvBulkLoadResponse>(
      '/alphavantage/bulk-load',
      payload,
    )
    return response.data
  },
  async listWorkflows(limit = 25): Promise<AvWorkflowEntry[]> {
    const response = await apiClient.get<AvWorkflowEntry[]>('/alphavantage/workflows', {
      params: { limit },
    })
    return response.data
  },
  async toggleStream(enable: boolean, replicas = 1): Promise<AvStreamToggle> {
    const response = await apiClient.post<AvStreamToggle>('/alphavantage/stream', {
      enable,
      replicas,
    })
    return response.data
  },
}
