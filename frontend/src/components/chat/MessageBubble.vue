<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import ToolCallTrace from './ToolCallTrace.vue'
import FileChip from './FileChip.vue'

const props = defineProps<{
  message: Message
  streaming?: boolean
  waiting?: boolean
  sessionId?: string | null
}>()

const html = computed(() => renderMarkdown(props.message.content))
const isUser = computed(() => props.message.role === 'user')
// 思考中：SSE 已连接但尚未收到首个事件
const isWaiting = computed(
  () => props.waiting && !isUser.value && !props.message.content,
)
// 流式输出中：已开始接收内容，正在逐块增长
const isStreamingContent = computed(
  () => props.streaming && !isUser.value && !!props.message.content,
)

// 从 assistant 内容中提取下载链接并渲染为 FileChip
const downloads = computed(() => {
  if (isUser.value) return []
  const result: { filename: string; url: string }[] = []
  const re = /\((\/api\/agent\/sessions\/[^)]+\/files\/([^)]+))\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(props.message.content)) !== null) {
    result.push({ url: m[1], filename: decodeURIComponent(m[2]) })
  }
  return result
})

const toolCalls = computed(() => props.message.toolCalls || [])
</script>

<template>
  <div class="msg" :class="{ user: isUser, assistant: !isUser }">
    <div class="avatar" :class="{ user: isUser }">
      <span v-if="isUser">我</span>
      <span v-else class="gradient-text">GG</span>
    </div>
    <div class="body">
      <ToolCallTrace v-if="toolCalls.length" :calls="toolCalls" />
      <!-- 思考中：SSE 已连接但尚未收到数据 -->
      <div v-if="isWaiting" class="thinking">
        <span class="think-text">思考中</span>
        <span class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>
      </div>
      <!-- 流式输出中或已完成的正文 -->
      <div v-else-if="props.message.content || !props.streaming" class="content" :class="{ md: !isUser, streaming: isStreamingContent }" v-html="html"></div>
      <div v-if="downloads.length" class="downloads">
        <FileChip
          v-for="d in downloads"
          :key="d.url"
          :filename="d.filename"
          :url="d.url"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  gap: 12px;
  animation: slideUp 0.3s var(--ease-out);
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  background: var(--bg-sunken);
  color: var(--text-secondary);
}
.avatar.user {
  background: var(--accent-gradient);
  color: #fff;
}
.body {
  min-width: 0;
  flex: 1;
  padding-top: 4px;
}
.content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.content.md :deep(p) {
  margin: 0 0 8px;
}
.content.md :deep(p:last-child) {
  margin-bottom: 0;
}
.content.md :deep(h1),
.content.md :deep(h2),
.content.md :deep(h3) {
  font-family: var(--font-display);
  font-weight: 600;
  margin: 16px 0 8px;
  color: var(--text-primary);
}
.content.md :deep(h1) { font-size: 18px; }
.content.md :deep(h2) { font-size: 16px; }
.content.md :deep(h3) { font-size: 15px; }
.content.md :deep(ul),
.content.md :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
.content.md :deep(li) {
  margin: 4px 0;
}
.content.md :deep(code) {
  font-family: var(--font-mono);
  font-size: 12.5px;
  background: var(--bg-sunken);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: var(--brand-600);
}
.content.md :deep(pre) {
  background: var(--bg-sunken);
  padding: 12px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: 8px 0;
}
.content.md :deep(pre code) {
  background: none;
  padding: 0;
  color: var(--text-primary);
}
.content.md :deep(blockquote) {
  border-left: 3px solid var(--brand-300);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 8px 0;
}
.content.md :deep(a) {
  color: var(--brand-600);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.content.md :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}
.content.md :deep(th),
.content.md :deep(td) {
  border: 1px solid var(--border-subtle);
  padding: 6px 10px;
  text-align: left;
}
.content.md :deep(th) {
  background: var(--bg-sunken);
  font-weight: 600;
}
/* 思考中状态 */
.thinking {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 26px;
  padding: 0 4px;
}
.think-text {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.dots {
  display: inline-flex;
  gap: 4px;
}
.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand-400);
  animation: pulse-glow 1.2s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
/* 流式输出中：末尾闪烁光标 */
.content.streaming::after {
  content: '▊';
  display: inline-block;
  margin-left: 2px;
  color: var(--brand-500);
  animation: blink 1s steps(2) infinite;
  vertical-align: text-bottom;
  font-size: 12px;
}
.downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
</style>
