import { API_BASE_URL } from '../config/api'

export class ApiUnavailableError extends Error {
  constructor(message = 'The Aura API is unavailable.') {
    super(message)
    this.name = 'ApiUnavailableError'
  }
}
export class ApiHttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiHttpError'
  }
}
export class ApiResponseError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiResponseError'
  }
}
type ApiRequestOptions = Omit<RequestInit, 'headers'> & { headers?: HeadersInit; onText?: (text: string) => void }
type AuthTokenProvider = () => string | null | Promise<string | null>
let authTokenProvider: AuthTokenProvider = () => null
let unauthorizedHandler: (token: string) => void = () => {}
export function setApiUnauthorizedHandler(handler: (token: string) => void): void {
  unauthorizedHandler = handler
}

/** The host application supplies its auth token; credentials remain centralized here. */
export function setApiAuthTokenProvider(provider: AuthTokenProvider): void {
  authTokenProvider = provider
}
export async function requestApi<T>(
  path: string,
  options: ApiRequestOptions,
  decode: (value: unknown) => T,
): Promise<T> {
  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  const headers = new Headers(options.headers)
  const token = await authTokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    const { onText: _onText, ...init } = options
    options.signal?.throwIfAborted()
    response = await fetch(url, { ...init, headers })
  } catch (error) {
    if (options.signal?.aborted) throw error
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiUnavailableError(`Could not reach the Aura API at ${API_BASE_URL}.`)
  }
  if (!response.ok) {
    if (response.status === 401 && token && !/^\/?auth\/(login|register)$/.test(path)) {
      unauthorizedHandler(token)
    }
    throw new ApiHttpError(response.status, await readErrorMessage(response))
  }
  let body: unknown
  try {
    body = options.onText && response.headers.get('Content-Type')?.includes('text/event-stream')
      ? await readAnswerStream(response, options.onText, options.signal)
      : await response.json()
    options.signal?.throwIfAborted()
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiResponseError(`The Aura API returned invalid JSON (HTTP ${response.status}).`)
  }
  return decode(body)
}

/** Additive SSE contract: delta {text}, result {full JSON response}. No fabricated citations. */
export async function readAnswerStream(response: Response, onText: (text: string) => void, signal?: AbortSignal | null): Promise<unknown> {
  if (!response.body) throw new ApiResponseError('No answer was received.')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', text = '', result: unknown, ended = false
  const aborted = () => { void reader.cancel().catch(() => {}) }
  signal?.addEventListener('abort', aborted, { once: true })
  function event(block: string) {
    const lines = block.split('\n'), kind = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (!data || ended) return
    const row = requireRecord(JSON.parse(data), 'stream event')
    if (kind === 'delta') {
      if (typeof row.text !== 'string' || text.length + row.text.length > 120000) throw new ApiResponseError('Invalid answer stream.')
      text += row.text; signal?.throwIfAborted(); onText(text)
    } else if (kind === 'result') { result = row; ended = true }
    else if (kind === 'error') throw new ApiResponseError('Aura could not finish this answer. Your received text is kept.')
  }
  try {
    while (!ended) {
      signal?.throwIfAborted()
      const { value, done } = await reader.read()
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n')
      if (buffer.length > 2000000) throw new ApiResponseError('Invalid answer stream.')
      let separator: number
      while ((separator = buffer.indexOf('\n\n')) >= 0) { const block = buffer.slice(0, separator); buffer = buffer.slice(separator + 2); event(block) }
      if (done) { if (buffer.trim()) event(buffer); break }
    }
    signal?.throwIfAborted()
    if (!ended) throw new ApiResponseError('Aura could not finish this answer. Your received text is kept.')
    return result
  } finally { signal?.removeEventListener('abort', aborted); await reader.cancel().catch(() => {}); reader.releaseLock() }
}
export function requireRecord(value: unknown, resource: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiResponseError(`The Aura API returned an invalid ${resource} response.`)
  }
  return value as Record<string, unknown>
}
async function readErrorMessage(response: Response): Promise<string> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return `Aura API request failed (HTTP ${response.status}).`
  }
  if (typeof body !== 'object' || body === null) return `Aura API request failed (HTTP ${response.status}).`
  const detail = (body as Record<string, unknown>).detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null && typeof (detail as Record<string,unknown>).message === 'string') return String((detail as Record<string,unknown>).message)
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => {
      if (typeof item !== 'object' || item === null) return []
      const message = (item as Record<string, unknown>).msg
      return typeof message === 'string' ? [message] : []
    })
    if (messages.length) return messages.join(' ')
  }
  return `Aura API request failed (HTTP ${response.status}).`
}

/** Binary previews use the same account token and 401 handling as JSON requests. */
export async function requestApiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  const headers = new Headers()
  const token = await authTokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try { response = await fetch(url, { method: 'GET', headers, signal }) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiUnavailableError(`Could not reach the Aura API at ${API_BASE_URL}.`)
  }
  if (!response.ok) {
    if (response.status === 401 && token) unauthorizedHandler(token)
    throw new ApiHttpError(response.status, await readErrorMessage(response))
  }
  return response.blob()
}

