<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import { chatApi } from '@/api/chat'

const store = useChatStore()

function fmtTime(t?: string) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function newSession() {
  await store.createSession()
}

async function del(id: string, e: Event) {
  e.stopPropagation()
  if (!confirm('删除该会话？此操作不可撤销。')) return
  await store.deleteSession(id)
}
</script>

<template>
  <aside class="session-list">
    <div class="head">
      <button class="new-btn" @click="newSession">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新对话
      </button>
    </div>
    <div class="list">
      <div
        v-for="s in store.sessions"
        :key="s.session_id"
        class="item"
        :class="{ active: s.session_id === store.currentSessionId }"
        @click="store.selectSession(s.session_id)"
      >
        <div class="info">
          <div class="title">{{ s.title || '新对话' }}</div>
          <div class="meta">
            <span v-if="s.message_count">{{ s.message_count }} 条</span>
            <span>{{ fmtTime(s.updated_at) }}</span>
          </div>
        </div>
        <button class="del" @click="del(s.session_id, $event)" title="删除">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M3 6h18M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
      </div>
      <div v-if="!store.sessions.length" class="empty">暂无会话</div>
    </div>
  </aside>
</template>

<style scoped>
.session-list {
  width: 260px;
  min-width: 260px;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
}
.head {
  padding: 14px 14px 10px;
}
.new-btn {
  width: 100%;
  height: 38px;
  border-radius: var(--radius-md);
  background: var(--accent-gradient);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all var(--dur) var(--ease);
  box-shadow: 0 4px 12px var(--glow-brand);
}
.new-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px var(--glow-brand);
}
.list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--dur) var(--ease);
  position: relative;
}
.item:hover {
  background: var(--bg-subtle);
}
.item.active {
  background: var(--brand-50);
}
.item.active .title {
  color: var(--brand-700);
  font-weight: 600;
}
.info {
  flex: 1;
  min-width: 0;
}
.title {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}
.meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-quaternary);
}
.del {
  opacity: 0;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-quaternary);
  transition: all var(--dur) var(--ease);
}
.item:hover .del {
  opacity: 1;
}
.del:hover {
  background: var(--danger-soft);
  color: var(--danger);
}
.empty {
  padding: 40px 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-quaternary);
}
</style>
