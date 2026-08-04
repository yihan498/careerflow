import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'http://localhost:54321'
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'local-development'
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    storage: window.sessionStorage,
  },
})

export const sessionId = (() => {
  const existing = sessionStorage.getItem('careerflow-session-id')
  if (existing) return existing
  const value = crypto.randomUUID()
  sessionStorage.setItem('careerflow-session-id', value)
  return value
})()

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  if (data.session?.access_token) headers.set('Authorization', `Bearer ${data.session.access_token}`)
  if (import.meta.env.VITE_DEV_AUTH_BYPASS === 'true') headers.set('X-Dev-User', '00000000-0000-0000-0000-000000000001')
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers, signal: init.signal || AbortSignal.timeout(300_000) })
  const contentType = response.headers.get('content-type') || ''
  const body = response.status === 204 ? null : contentType.includes('application/json')
    ? await response.json()
    : { error: { message: (await response.text()).slice(0, 500) || `请求失败（${response.status}）` } }
  if (!response.ok) throw new Error(body?.error?.message || `请求失败（${response.status}）`)
  return body?.data as T
}

export function idempotencyKey(type: string): string {
  return `${type}-${crypto.randomUUID()}`
}
