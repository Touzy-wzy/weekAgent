// HTTP 客户端封装

const BASE = import.meta.env.VITE_API_BASE || ''

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail)
    this.name = 'ApiError'
  }
}

export async function request<T>(
  url: string,
  opts: RequestInit = {},
): Promise<T> {
  const res = await fetch(BASE + url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...opts.headers,
    },
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return (await res.text()) as unknown as T
}

export async function uploadFile(
  url: string,
  file: File,
  extra?: Record<string, string>,
): Promise<any> {
  const fd = new FormData()
  fd.append('file', file)
  if (extra) {
    for (const k of Object.keys(extra)) fd.append(k, extra[k])
  }
  const res = await fetch(BASE + url, { method: 'POST', body: fd })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

export function fileUrl(path: string): string {
  return BASE + path
}
