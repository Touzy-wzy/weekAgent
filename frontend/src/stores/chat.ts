import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { chatApi } from '@/api/chat'
import { useSSE } from '@/composables/useSSE'
import type { Session, Message, ToolCall, FileInfo } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const files = ref<FileInfo[]>([])
  const streaming = ref(false)
  const waitingFirstByte = ref(false) // SSE 已连接但尚未收到首个事件（思考中）
  const streamingBuffer = ref('')
  const toolCalls = ref<ToolCall[]>([])
  const loading = ref(false)

  const { stream: sseStream, abort: sseAbort } = useSSE()

  const currentSession = computed(
    () => sessions.value.find((s) => s.session_id === currentSessionId.value) || null,
  )
  const hasMessages = computed(() => messages.value.length > 0)

  async function loadSessions() {
    try {
      sessions.value = await chatApi.listSessions()
    } catch (e) {
      console.error('加载会话列表失败', e)
    }
  }

  async function createSession(): Promise<string> {
    const s = await chatApi.createSession()
    sessions.value.unshift(s)
    await selectSession(s.session_id)
    return s.session_id
  }

  async function selectSession(id: string) {
    // 切换会话前，标记旧流为"已放弃"（不中断 fetch，让流自然结束）
    if (streaming.value) {
      sseAbort()
    }
    currentSessionId.value = id
    streamingBuffer.value = ''
    toolCalls.value = []
    // 注意：不重置 streaming/waitingFirstByte，让旧流的 onClose 回调负责清理
    // 重置这些状态会触发 Vue 响应式更新，导致 webview 中止 pending fetch → ERR_ABORTED
    loading.value = true
    try {
      const data = await chatApi.getMessages(id)
      messages.value = data.messages || []
      sessions.value = sessions.value.map((s) =>
        s.session_id === id ? { ...s, ...(data.meta || {}) } : s,
      )
      await loadFiles(id)
    } catch (e) {
      console.error('加载会话消息失败', e)
      messages.value = []
    } finally {
      loading.value = false
    }
  }

  async function deleteSession(id: string) {
    await chatApi.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.session_id !== id)
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      messages.value = []
      files.value = []
    }
  }

  async function loadFiles(id: string) {
    try {
      const data = await chatApi.listFiles(id)
      files.value = data.files || []
    } catch {
      files.value = []
    }
  }

  async function uploadFile(file: File) {
    if (!currentSessionId.value) {
      const id = await createSession()
      const info = await chatApi.upload(id, file)
      await loadFiles(id)
      return info
    }
    const info = await chatApi.upload(currentSessionId.value, file)
    await loadFiles(currentSessionId.value)
    return info
  }

  // 发送消息（SSE 流式）
  async function sendMessage(text: string) {
    if (!text.trim() || streaming.value) return

    // 无会话则自动建
    if (!currentSessionId.value) {
      await createSession()
    }
    const sid = currentSessionId.value!

    // 先插入 user 消息
    messages.value.push({ role: 'user', content: text })
    // 准备 assistant 占位
    messages.value.push({ role: 'assistant', content: '' })
    const assistantIdx = messages.value.length - 1

    streaming.value = true
    waitingFirstByte.value = true // 进入"思考中"，等待首个 SSE 事件
    streamingBuffer.value = ''
    toolCalls.value = []

    await sseStream(`/api/agent/sessions/${sid}/chat/stream`, text, {
      onEvent: (ev) => handleSSEEvent(ev, assistantIdx),
      onError: (err) => {
        streaming.value = false
        waitingFirstByte.value = false
        messages.value[assistantIdx].content =
          (streamingBuffer.value || '') + `\n\n> ⚠️ 出错：${err.message}`
      },
      onClose: () => {
        streaming.value = false
        waitingFirstByte.value = false
        // 延迟刷新会话列表，避免与 SSE 流收尾并发导致浏览器中止连接
        setTimeout(() => loadSessions(), 100)
      },
    })
  }

  function handleSSEEvent(ev: any, assistantIdx: number) {
    const t = ev.type
    const d = ev.data || {}
    // 仅在收到实质性事件时结束"思考中"
    // agent_start / step_start 等生命周期信号不结束，避免 LLM 思考期间"思考中"瞬间消失
    if (
      waitingFirstByte.value &&
      (t === 'llm_chunk' ||
        t === 'tool_call_finish' ||
        t === 'agent_finish' ||
        t === 'error')
    ) {
      waitingFirstByte.value = false
    }
    if (t === 'llm_chunk') {
      // data: { chunk: "文本片段", step: N }
      const chunk = typeof d === 'string' ? d : d.chunk || d.delta || d.content || ''
      streamingBuffer.value += chunk
      messages.value[assistantIdx].content = streamingBuffer.value
    } else if (t === 'tool_call_finish') {
      // data: { tool_name, tool_call_id, result, step }
      // 注意：hello_agents 的 react_agent arun_stream 不发送 tool_call_start，
      // 工具调用仅在完成时以 tool_call_finish 事件出现，故直接置为 done。
      const name = d.tool_name || d.name || d.tool || 'tool'
      toolCalls.value.push({
        name,
        status: d.result && String(d.result).startsWith('❌') ? 'error' : 'done',
        result: d.result,
      })
      messages.value[assistantIdx].toolCalls = [...toolCalls.value]
    } else if (t === 'agent_finish') {
      // data: { result, total_steps }
      const result = d.result || d.answer || streamingBuffer.value
      if (result) messages.value[assistantIdx].content = result
      streaming.value = false
      waitingFirstByte.value = false
      // fetch stream 不会自动重连，无需主动 abort；后端发送完毕后流自然结束
    } else if (t === 'error') {
      streaming.value = false
      waitingFirstByte.value = false
      messages.value[assistantIdx].content =
        (streamingBuffer.value || '') + `\n\n> ⚠️ ${d.error || '执行出错'}`
    }
    // agent_start / step_start / step_finish 仅作生命周期信号，不影响 UI
  }

  function stopStreaming() {
    sseAbort()
    streaming.value = false
    waitingFirstByte.value = false
  }

  function reset() {
    currentSessionId.value = null
    messages.value = []
    files.value = []
    streamingBuffer.value = ''
    toolCalls.value = []
    streaming.value = false
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    messages,
    files,
    streaming,
    waitingFirstByte,
    streamingBuffer,
    toolCalls,
    loading,
    hasMessages,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
    loadFiles,
    uploadFile,
    sendMessage,
    stopStreaming,
    reset,
  }
})
