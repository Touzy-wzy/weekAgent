<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

watch(text, () => nextTick(autoResize))

async function send() {
  const t = text.value.trim()
  if (!t || store.streaming) return
  text.value = ''
  await nextTick(autoResize)
  await store.sendMessage(t)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

async function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  uploading.value = true
  try {
    for (const f of Array.from(input.files)) {
      await store.uploadFile(f)
    }
  } catch (err: any) {
    alert('上传失败：' + err.message)
  } finally {
    uploading.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="chat-input">
    <div class="wrap">
      <button class="attach" @click="fileInputRef?.click()" :disabled="uploading" title="上传文件">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
      </button>
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept=".docx,.pdf,.txt,.md,.xlsx"
        @change="onPickFile"
        hidden
      />
      <textarea
        ref="textareaRef"
        v-model="text"
        class="textarea"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        rows="1"
        @keydown="onKeydown"
      ></textarea>
      <button
        v-if="!store.streaming"
        class="send"
        :disabled="!text.trim()"
        @click="send"
        title="发送"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
        </svg>
      </button>
      <button v-else class="stop" @click="store.stopStreaming()" title="停止">
        <span class="stop-icon"></span>
      </button>
    </div>
    <div v-if="store.files.length" class="files">
      <span
        v-for="f in store.files"
        :key="f.name"
        class="file-tag"
      >
        {{ f.name }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  width: 100%;
  max-width: var(--chat-max);
  margin: 0 auto;
  padding: 0 24px 20px;
}
.wrap {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: 8px 8px 8px 14px;
  box-shadow: var(--shadow-md);
  transition: all var(--dur) var(--ease);
}
.wrap:focus-within {
  border-color: var(--brand-400);
  box-shadow: var(--shadow-md), var(--shadow-glow);
}
.attach {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  transition: all var(--dur) var(--ease);
}
.attach:hover:not(:disabled) {
  background: var(--bg-subtle);
  color: var(--brand-500);
}
.attach:disabled {
  opacity: 0.5;
}
.textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  max-height: 200px;
  padding: 8px 0;
}
.textarea::placeholder {
  color: var(--text-quaternary);
}
.send {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--accent-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur) var(--ease);
  box-shadow: 0 4px 12px var(--glow-brand);
}
.send:hover:not(:disabled) {
  transform: scale(1.06);
}
.send:disabled {
  opacity: 0.4;
  box-shadow: none;
}
.stop {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--bg-sunken);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur) var(--ease);
}
.stop:hover {
  background: var(--danger-soft);
  border-color: var(--danger);
}
.stop-icon {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  background: var(--danger);
}
.files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding: 0 4px;
}
.file-tag {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-sunken);
  padding: 3px 8px;
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
}
</style>
