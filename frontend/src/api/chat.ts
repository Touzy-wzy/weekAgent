import { request, uploadFile, fileUrl } from './client'
import type { Session, Message, FileInfo } from '@/types'

export const chatApi = {
  listSessions: () => request<Session[]>('/api/agent/sessions'),
  createSession: () =>
    request<Session>('/api/agent/sessions', { method: 'POST' }),
  deleteSession: (id: string) =>
    request<{ deleted: boolean }>(`/api/agent/sessions/${id}`, {
      method: 'DELETE',
    }),
  getMessages: (id: string) =>
    request<{ session_id: string; meta: Session; messages: Message[] }>(
      `/api/agent/sessions/${id}/messages`,
    ),
  upload: (id: string, file: File) =>
    uploadFile(`/api/agent/sessions/${id}/upload`, file),
  listFiles: (id: string) =>
    request<{ session_id: string; files: FileInfo[] }>(
      `/api/agent/sessions/${id}/files`,
    ),
  fileDownloadUrl: (sessionId: string, filename: string) =>
    fileUrl(`/api/agent/sessions/${sessionId}/files/${encodeURIComponent(filename)}`),
}
