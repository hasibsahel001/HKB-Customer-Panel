export interface ActionCustomer {
  username: string | null
  identity: string | null
  ip: string
  tid: string
}

export interface FirmwareInfo {
  supported: boolean
  model: string | null
  current: string | null
  upgrade: string | null
  pending: boolean
}

export type UpdateState = 'up_to_date' | 'available' | 'major_change' | 'error' | 'unknown'

export interface UpdateCheck {
  channel: string | null
  installed: string | null
  latest: string | null
  status: string | null
  state: UpdateState
  channel_changed_from: string | null
  firmware: FirmwareInfo
}

export interface JobStep {
  at: string
  text: string
}

export interface UpdateJob {
  id: string
  state: 'running' | 'done' | 'failed'
  mode: 'now' | 'later'
  firmware: boolean
  message: string | null
  steps: JobStep[]
  result: { check?: UpdateCheck; firmware_auto?: boolean }
}

export interface UsageSample {
  elapsed_ms: number
  up_bps: number | null
  down_bps: number | null
}

export interface UsageResult {
  interface: string
  seconds: number
  samples: UsageSample[]
}

export interface NatEnterResult {
  pppoe_ip: string
  ap_ip: string
  port: number
  rule_added: boolean
}

export interface VpnEnterResult {
  pppoe_ip: string
  ap_ip: string
}

export interface DnsInfo {
  servers: string[]
  dynamic_servers: string[]
  allow_remote_requests: boolean
}