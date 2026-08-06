<script setup lang="ts">
import { ref } from 'vue'
import type { ToolCall } from '@/types'

defineProps<{ calls: ToolCall[] }>()

function statusIcon(s: ToolCall['status']) {
  if (s === 'running') return '⏳'
  if (s === 'done') return '✓'
  return '✕'
}
function statusLabel(s: ToolCall['status']) {
  if (s === 'running') return '执行中'
  if (s === 'done') return '完成'
  return '失败'
}
</script>

<template>
  <div v-if="calls.length" class="trace">
    <div
      v-for="(c, i) in calls"
      :key="i"
      class="call"
      :class="c.status"
    >
      <span class="icon">{{ statusIcon(c.status) }}</span>
      <span class="name">{{ c.name }}</span>
      <span class="status">{{ statusLabel(c.status) }}</span>
      <span v-if="c.duration" class="dur">{{ c.duration.toFixed(1) }}s</span>
    </div>
  </div>
</template>

<style scoped>
.trace {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.call {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 11.5px;
  font-family: var(--font-mono);
  background: var(--bg-sunken);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}
.call.running {
  background: var(--brand-50);
  color: var(--brand-600);
  border-color: var(--brand-200);
}
.call.running .icon {
  animation: pulse-glow 1.2s ease-in-out infinite;
}
.call.done {
  background: var(--success-soft);
  color: var(--success);
  border-color: transparent;
}
.call.error {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: transparent;
}
.icon {
  font-size: 11px;
}
.name {
  font-weight: 500;
}
.status {
  opacity: 0.7;
}
.dur {
  opacity: 0.5;
  font-size: 10.5px;
}
</style>
