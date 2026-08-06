<script setup lang="ts">
import type { PageItem } from '@/types'

defineProps<{
  pages: PageItem[]
  currentId?: string
}>()

defineEmits<{
  (e: 'select', id: string): void
}>()

function isFolder(page: PageItem): boolean {
  return page.type === 'folder' || !!(page.children && page.children.length > 0)
}
</script>

<template>
  <ul class="page-tree">
    <li v-for="page in pages" :key="page.id" class="tree-node">
      <button
        class="node-label"
        :class="{ active: page.id === currentId }"
        @click="$emit('select', page.id)"
      >
        <span class="node-icon" :class="{ folder: isFolder(page) }">
          <svg
            v-if="isFolder(page)"
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <svg
            v-else
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="14" y2="17" />
          </svg>
        </span>
        <span class="node-title">{{ page.title }}</span>
      </button>
      <PageTree
        v-if="page.children && page.children.length"
        :pages="page.children"
        :current-id="currentId"
        @select="$emit('select', $event)"
      />
    </li>
  </ul>
</template>

<style scoped>
.page-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}
.page-tree .page-tree {
  padding-left: 14px;
  margin-top: 2px;
}
.tree-node {
  margin: 0;
}
.node-label {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13.5px;
  line-height: 1.5;
  text-align: left;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.node-label:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}
.node-label.active {
  background: var(--brand-50);
  color: var(--brand-600);
  font-weight: 600;
}
.node-icon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  transition: color var(--dur) var(--ease);
}
.node-icon.folder {
  color: var(--brand-500);
}
.node-label.active .node-icon {
  color: var(--brand-600);
}
.node-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
