<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  filename: string
  url?: string
  size?: number
}>()

const ext = computed(() => {
  const m = props.filename.match(/\.(\w+)$/)
  return m ? m[1].toLowerCase() : ''
})
const isExcel = computed(() => ['xlsx', 'xls', 'csv'].includes(ext.value))
const isDoc = computed(() => ['doc', 'docx', 'pdf', 'txt', 'md'].includes(ext.value))

function fmtSize(b?: number) {
  if (!b) return ''
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <a :href="url" :download="filename" class="chip" target="_blank">
    <span class="icon" :class="{ excel: isExcel, doc: isDoc }">
      <svg v-if="isExcel" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="m8 13 4 4M12 13l-4 4" />
      </svg>
      <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M8 13h8M8 17h8M8 9h2" />
      </svg>
    </span>
    <span class="info">
      <span class="name">{{ filename }}</span>
      <span v-if="size" class="size">{{ fmtSize(size) }}</span>
    </span>
    <span class="dl">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <path d="M7 10l5 5 5-5M12 15V3" />
      </svg>
    </span>
  </a>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  text-decoration: none;
  transition: all var(--dur) var(--ease);
  max-width: 320px;
}
.chip:hover {
  border-color: var(--brand-300);
  background: var(--brand-50);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  background: var(--bg-sunken);
}
.icon.excel {
  color: #16a34a;
  background: var(--success-soft);
}
.icon.doc {
  color: var(--brand-500);
  background: var(--brand-50);
}
.info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.name {
  font-size: 12.5px;
  color: var(--text-primary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}
.size {
  font-size: 11px;
  color: var(--text-quaternary);
}
.dl {
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: color var(--dur) var(--ease);
}
.chip:hover .dl {
  color: var(--brand-500);
}
</style>
