// 全局类型定义

export interface Session {
  session_id: string
  title: string
  created_at?: string
  updated_at?: string
  message_count?: number
}

export type Role = 'user' | 'assistant'

// 工具调用追踪
export interface ToolCall {
  name: string
  status: 'running' | 'done' | 'error'
  args?: any
  result?: any
  duration?: number
}

export interface Message {
  role: Role
  content: string
  timestamp?: string
  toolCalls?: ToolCall[]
}

export interface FileInfo {
  name: string
  size: number
  ext: string
}

// SSE 流式事件
export interface SSEEvent {
  type: string
  data: any
  timestamp?: string
}

export interface PageItem {
  id: string
  title: string
  type?: string
  children?: PageItem[]
}

export interface PageContent {
  id: string
  title: string
  content: string
  html?: string
}
