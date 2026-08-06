import { ref, type Ref } from 'vue'
import type { SSEEvent } from '@/types'

const BASE = import.meta.env.VITE_API_BASE || ''

interface SSEHandlers {
  onEvent: (event: SSEEvent) => void
  onError?: (err: Error) => void
  onClose?: () => void
}

/**
 * SSE 消费器（基于 fetch + ReadableStream，不使用 AbortController）。
 *
 * 关键设计：不使用 AbortController.abort() 中断请求。
 * 原因：trae-preview webview（IDE 内嵌 Chromium）会把所有被中止的 fetch 请求
 * 记录为 error 级别的 ERR_ABORTED，包括 AbortController.abort()。
 * 标准 Chrome 不会这样，但 trae-preview 的网络层更"诚实"。
 *
 * 替代方案：用 abandoned 标志位实现"放弃"语义。
 * - abort() 只设置 abandoned = true，不中断 fetch
 * - reader 循环检查 abandoned，为 true 时跳过数据处理
 * - 流自然结束后调用 onClose，不触发 ERR_ABORTED
 *
 * 后端配套：POST /api/agent/sessions/{id}/chat/stream?q=<query>
 * - 首字节立即响应（: connected）避免首字节超时
 * - 每 5 秒心跳（: heartbeat）保活
 */
export function useSSE() {
  const active: Ref<boolean> = ref(false)
  // abandoned: 标志位，表示当前流已被放弃（切换会话/用户停止）
  // 不中断 fetch，让流自然结束，避免 ERR_ABORTED
  const abandoned = { value: false }

  async function stream(
    urlPath: string,
    query: string,
    handlers: SSEHandlers,
  ): Promise<void> {
    abandoned.value = false
    active.value = true
    const fullUrl = `${BASE}${urlPath}?q=${encodeURIComponent(query)}`

    try {
      const resp = await fetch(fullUrl, {
        method: 'POST',
        headers: {
          Accept: 'text/event-stream',
        },
      })

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // 已放弃：继续 read() 直到流结束，但不处理数据
        // 这样 fetch 请求自然完成，不触发 ERR_ABORTED
        if (abandoned.value) continue

        buffer += decoder.decode(value, { stream: true })
        // SSE 帧以空行（\n\n）分隔，拆分后保留最后不完整的片段
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''

        for (const frame of frames) {
          const event = parseSSEFrame(frame)
          if (event) handlers.onEvent(event)
        }
      }

      // 处理缓冲区中残留的最后一帧（仅在未放弃时）
      if (!abandoned.value && buffer.trim()) {
        const event = parseSSEFrame(buffer)
        if (event) handlers.onEvent(event)
      }

      // 被放弃的流：也调用 onClose 清理 streaming 状态
      // 但不处理数据，避免旧流数据污染新会话
      handlers.onClose?.()
    } catch (err: unknown) {
      if (!abandoned.value) {
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)))
      }
      // 已放弃的流出错时静默处理
    } finally {
      active.value = false
    }
  }

  function abort() {
    // 不调用 AbortController.abort()，只设置标志位
    // reader 循环会跳过后续数据，流自然结束后 onClose 被调用
    abandoned.value = true
  }

  return { stream, abort, active }
}

/**
 * 解析单个 SSE 帧（由 \n\n 分隔的文本块）。
 * 忽略注释行（: heartbeat / : connected）和 retry 指令。
 */
function parseSSEFrame(frame: string): SSEEvent | null {
  const lines = frame.split('\n')
  let eventType = 'message'
  let dataStr = ''

  for (const line of lines) {
    if (line.startsWith(':')) continue // 注释行，忽略
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataStr += line.slice(5).trim()
    }
    // retry: / id: 等其他字段忽略
  }

  if (!dataStr) return null
  return parseFrame(eventType, dataStr)
}

function parseFrame(eventType: string, rawData: string): SSEEvent | null {
  if (!rawData) return null
  try {
    const payload = JSON.parse(rawData)
    return {
      type: eventType,
      data: payload.data ?? payload,
      timestamp: payload.timestamp,
    }
  } catch {
    return { type: eventType, data: rawData }
  }
}
