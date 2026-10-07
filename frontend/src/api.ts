export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) throw new Error(await res.text() || res.statusText)
  if (res.status === 204) return undefined as T
  return res.json()
}

/** 把 api() 抛出的错误（FastAPI {"detail": ...} 文本）转成可读信息。 */
export function errText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e)
  try {
    const j = JSON.parse(raw)
    return typeof j.detail === 'string' ? j.detail : raw
  } catch {
    return raw
  }
}
