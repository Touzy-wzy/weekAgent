import { request } from './client'
import type { PageItem } from '@/types'

export const flowusApi = {
  listPages: (project?: string) =>
    request<PageItem[]>(`/api/pages${project ? `?project=${encodeURIComponent(project)}` : ''}`),
  getPage: (pageId: string) =>
    request<{ id: string; title: string; content: string; html: string }>(
      `/api/page/${pageId}`,
    ),
  search: (q: string) =>
    request<{ query: string; results: any[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  refresh: (project?: string) =>
    request<{ status: string; cleared: number }>(
      `/api/refresh${project ? `?project=${encodeURIComponent(project)}` : ''}`,
      { method: 'POST' },
    ),
}
