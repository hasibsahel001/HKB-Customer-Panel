export interface Me {
  id: number
  username: string
  role: string
  is_active: boolean
  theme: string
  created_at: string
  permissions: string[]
  csrf_token: string
}

export interface UserItem {
  id: number
  username: string
  role: string
  is_active: boolean
  theme: string
  created_at: string
}

export interface SessionItem {
  id: number
  created_at: string
  last_seen_at: string
  expires_at: string
  ip: string | null
  user_agent: string | null
  current: boolean
}

export interface AuditItem {
  id: number
  created_at: string
  user_id: number | null
  username: string | null
  action: string
  target: string | null
  ip: string | null
  success: boolean
  details: string | null
}

export interface SectionResult<T> {
  ok: boolean
  data: T | null
  error: string | null
  error_type?: string | null
  error_detail?: string | null
  fetched_at: string
  elapsed_ms?: number
}

export interface IdentityData {
  identity: string | null
}

export interface ResourceData {
  model: string | null
  version: string | null
  uptime: string | null
  cpu_load: number | null
  ram_used_percent: number | null
  architecture: string | null
}

export interface TemperatureData {
  temperature_c: number
}

export interface Chain {
  chain: number
  tx_dbm: number | null
  rx_dbm: number | null
}

export interface Registration {
  interface: string | null
  mac_address: string | null
  radio_name: string | null
  signal_dbm: number | null
  snr_db: number | null
  noise_floor_dbm: number | null
  chains: Chain[]
  tx_ccq: number | null
  rx_ccq: number | null
  tx_rate: string | null
  rx_rate: string | null
  uptime: string | null
}

export interface PingSummary {
  sent: number | null
  received: number | null
  loss_percent: number | null
  min_ms: number | null
  avg_ms: number | null
  max_ms: number | null
  reachable: boolean | null
}

export interface WirelessAnalysis {
  signal: string
  ccq: string
  overall: string
  ccq_tx?: string
  ccq_rx?: string
  chains?: { chain: number; level: string }[]
}

export interface WirelessData {
  interface: string | null
  running: boolean | null
  disabled: boolean | null
  ssid: string | null
  frequency: number | string | null
  band: string | null
  channel_width: string | null
  registration_count: number
  registration: Registration | null
  ccq_used: number | null
  ccq_source: string | null
  analysis: WirelessAnalysis
  debug_registration_keys?: string[]
}

export interface ExpectedAddress {
  address: string
  configured: boolean
}

export interface Ether1Data {
  name: string
  running: boolean | null
  disabled: boolean | null
  rx_bytes_total: number | null
  tx_bytes_total: number | null
  link_downs: number | null
  last_link_up_time: string | null
  link_rate: string | null
  full_duplex: boolean | null
  link_status: string | null
  addresses?: string[] | null
  expected_addresses?: ExpectedAddress[]
}

export type QueueScope = 'own' | 'shared' | 'none' | 'unknown'

export interface DeviceItem {
  ip: string
  mac_address: string
  interface: string
  hostname: string | null
  lease_status: string | null
  queue_scope: QueueScope
  queue_names: string[]
  queue_limit_upload_bps: number | null
  queue_limit_download_bps: number | null
  queue_ambiguous: boolean
  source?: 'arp' | 'dhcp'
}

export interface TotalTraffic {
  interface: string
  method: string
  upload_bps: number | null
  download_bps: number | null
}

export interface DevicesData {
  fetched_at?: string
  interfaces: string[]
  count: number
  total_traffic: TotalTraffic | null
  devices: DeviceItem[]
}

export interface QueueItem {
  name: string | null
  target: string | null
  parent: string | null
  disabled: boolean | null
  max_limit_upload_bps: number | null
  max_limit_download_bps: number | null
  current_upload_bps: number | null
  current_download_bps: number | null
  very_low_limit: boolean
  matched_ips: string[]
}

export interface QueuesData {
  total_count: number
  matched_count: number
  unmatched_count: number
  skipped_rows: number
  skipped_reasons?: string[]
  queues: QueueItem[]
}

export interface RouterQueue {
  id: string
  name: string
  targets: string[]
  max_up_bps: number | null
  max_down_bps: number | null
  max_up: string
  max_down: string
  disabled: boolean
  parent: string | null
  comment: string | null
  matches_customer: boolean
}

export interface PppoeData {
  name: string | null
  username: string | null
  client_count: number
  running: boolean | null
  disabled: boolean | null
  underlying_interface: string | null
  service_name: string | null
  status: string | null
  uptime: string | null
  local_address: string | null
  remote_address: string | null
  matches_panel_ip: boolean | null
}

export interface PingEntry {
  host: string
  summary: PingSummary | null
  reachable: boolean | null
  status: string
  error: string | null
}

export interface PingData {
  layers: {
    router_connected: boolean
    pppoe_running: boolean | null
    gateway_reachable: boolean | null
    internet_reachable: boolean | null
  }
  gateway: PingEntry | null
  targets: PingEntry[]
}

export interface ApPeer {
  ip: string
  reachable: boolean | null
  avg_ms: number | null
  loss_percent: number | null
  mac: string | null
  vendor: string | null
}

export interface ApProbe {
  peers: ApPeer[]
  found: string[]
}

export interface Finding {
  code: string
  title: string
  severity: string
  evidence: Record<string, unknown>
  threshold: Record<string, unknown> | null
  probable_causes: string[]
  suggested_action: string
  detected_at: string
}

export interface Diagnostics {
  overall: string
  count: number
  generated_at?: string
  findings: Finding[]
  error?: string
}

export interface Sections {
  identity?: SectionResult<IdentityData>
  resource?: SectionResult<ResourceData>
  temperature?: SectionResult<TemperatureData>
  wireless?: SectionResult<WirelessData>
  ether1?: SectionResult<Ether1Data>
  devices?: SectionResult<DevicesData>
  queues?: SectionResult<QueuesData>
  pppoe?: SectionResult<PppoeData>
}

export interface Timings {
  connect: number
  total: number
  sections: Record<string, number>
}

export interface Report {
  ip: string
  technical_id: string
  connected_with_account: number
  api_port: number
  connect_attempts?: number
  fetched_at: string
  timings_ms?: Timings
  sections: Sections
  diagnostics: Diagnostics
}

export interface LiveResult {
  fetched_at: string
  ping: SectionResult<PingData>
  ap_probe?: SectionResult<ApProbe>
  diagnostics: { findings: Finding[] }
  timings_ms?: { total: number }
}

export interface RecentItem {
  username: string | null
  ip: string
  tid: string
  identity: string | null
  overall: string | null
  checked_at: string
}