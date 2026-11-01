export class ApiError extends Error {
  status: number
  code: string
  reasons: string[]

  constructor(status: number, code: string, message: string, reasons: string[] = []) {
    super(message)
    this.status = status
    this.code = code
    this.reasons = reasons
  }
}

export const REASON_TEXT: Record<string, string> = {
  timeout: 'The router did not answer in time',
  port_closed: 'The API port is closed',
  auth_rejected: 'The router rejected the login',
  unreachable: 'The address is not reachable',
  protocol_error: 'The device sent an unexpected reply',
}

let csrfToken = ''
let unauthorizedHandler: (() => void) | null = null

export function setCsrfToken(token: string): void {
  csrfToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

interface Options {
  method?: string
  body?: unknown
  signal?: AbortSignal
}

function parseError(status: number, payload: any): ApiError {
  const detail = payload?.detail
  if (Array.isArray(detail)) {
    return new ApiError(status, 'invalid_input', 'The request contains invalid values')
  }
  if (detail && typeof detail === 'object') {
    const reasons = Array.isArray(detail.reasons) ? detail.reasons.map(String) : []
    return new ApiError(
      status,
      String(detail.code ?? 'error'),
      String(detail.message ?? 'The request failed'),
      reasons,
    )
  }
  if (typeof detail === 'string') return new ApiError(status, 'error', detail)
  return new ApiError(status, 'error', `The request failed (${status})`)
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: 'same-origin',
      signal: options.signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      throw new ApiError(0, 'timeout', 'The request took too long')
    }
    throw new ApiError(0, 'network', 'Cannot reach the server')
  }

  let payload: any = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    if (response.status === 401 && unauthorizedHandler) unauthorizedHandler()
    throw parseError(response.status, payload)
  }
  return payload as T
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError(0, 'unknown', 'Something went wrong')
}