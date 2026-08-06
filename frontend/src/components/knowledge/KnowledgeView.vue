<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFlowusStore } from '@/stores/flowus'
import type { PageItem } from '@/types'
import PageTree from './PageTree.vue'
import PageContent from './PageContent.vue'

const store = useFlowusStore()
const { pages, currentPageId, currentContent, loading, loadingContent } = storeToRefs(store)

const refreshing = ref(false)

function findPage(list: PageItem[], id: string): PageItem | undefined {
  for (const p of list) {
    if (p.id === id) return p
    if (p.children?.length) {
      const found = findPage(p.children, id)
      if (found) return found
    }
  }
  return undefined
}

const selectedTitle = computed(() => {
  if (currentContent.value?.title) return currentContent.value.title
  if (currentPageId.value) {
    return findPage(pages.value, currentPageId.value)?.title ?? ''
  }
  return ''
})

function handleSelect(id: string) {
  store.loadPage(id)
}

async function handleRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await store.refresh()
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  store.loadPages()
})
</script>

<template>
  <div class="knowledge-view">
    <header class="kv-header">
      <div class="header-left">
        <div class="title-mark">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
        </div>
        <h1 class="header-title">知识库</h1>
      </div>
      <button
        class="refresh-btn"
        :class="{ spinning: refreshing }"
        :disabled="refreshing"
        @click="handleRefresh"
      >
        <svg
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        <span>{{ refreshing ? '同步中' : '刷新' }}</span>
      </button>
    </header>

    <div class="kv-body">
      <aside class="kv-tree">
        <div v-if="loading && !pages.length" class="tree-skeleton">
          <div class="ts-line" style="width: 80%"></div>
          <div class="ts-line" style="width: 65%"></div>
          <div class="ts-line" style="width: 90%"></div>
          <div class="ts-line" style="width: 70%"></div>
          <div class="ts-line" style="width: 55%"></div>
        </div>
        <div v-else-if="!pages.length" class="tree-empty">
          <svg
            viewBox="0 0 24 24"
            width="28"
            height="28"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <p>暂无页面</p>
        </div>
        <PageTree
          v-else
          :pages="pages"
          :current-id="currentPageId ?? undefined"
          @select="handleSelect"
        />
      </aside>

      <section class="kv-content">
        <PageContent
          v-if="currentPageId"
          :title="selectedTitle"
          :html="currentContent?.html ?? ''"
          :loading="loadingContent"
        />
        <div v-else class="content-empty">
          <div class="orb orb-1"></div>
          <div class="orb orb-2"></div>
          <div class="empty-card">
            <div class="empty-icon">
              <svg
                viewBox="0 0 24 24"
                width="32"
                height="32"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="8" y1="13" x2="16" y2="13" />
                <line x1="8" y1="17" x2="14" y2="17" />
              </svg>
            </div>
            <p class="empty-title">选择左侧页面查看内容</p>
            <p class="empty-desc">从页面树中点选一个文档，即可在此阅读其内容</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.knowledge-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-subtle);
}

/* 顶部 */
.kv-header {
  flex: 0 0 auto;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
  z-index: 3;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.title-mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: var(--accent-gradient);
  box-shadow: 0 4px 12px var(--glow-brand);
}
.header-title {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}
.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
  transition: all var(--dur) var(--ease);
}
.refresh-btn:hover:not(:disabled) {
  color: var(--brand-600);
  border-color: var(--brand-300);
  background: var(--brand-50);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.refresh-btn:active:not(:disabled) {
  transform: translateY(0);
}
.refresh-btn:disabled {
  cursor: progress;
  opacity: 0.7;
}
.refresh-btn.spinning svg {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 主体两栏 */
.kv-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

/* 左侧树 */
.kv-tree {
  flex: 0 0 280px;
  width: 280px;
  min-height: 0;
  overflow-y: auto;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border-subtle);
  padding: 14px 12px;
}
.tree-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 6px;
}
.ts-line {
  height: 22px;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    var(--bg-sunken) 0%,
    var(--border-subtle) 50%,
    var(--bg-sunken) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}
.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-quaternary);
}
.tree-empty p {
  font-size: 12.5px;
  color: var(--text-tertiary);
}

/* 右侧内容 */
.kv-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  background: var(--bg-elevated);
}

/* 空状态 */
.content-empty {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 24px;
}
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.45;
  pointer-events: none;
}
.orb-1 {
  width: 300px;
  height: 300px;
  background: var(--brand-200);
  top: 12%;
  left: 18%;
  animation: float-slow 12s ease-in-out infinite;
}
.orb-2 {
  width: 260px;
  height: 260px;
  background: #d9ccff;
  bottom: 12%;
  right: 18%;
  animation: float-slow 14s ease-in-out infinite reverse;
}
.empty-card {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 360px;
}
.empty-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 18px;
  border-radius: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--brand-500);
  background: var(--accent-gradient-soft);
  border: 1px solid var(--brand-100);
}
.empty-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.empty-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.6;
}

/* 左侧树滚动条（细） */
.kv-tree::-webkit-scrollbar {
  width: 8px;
}
.kv-tree::-webkit-scrollbar-track {
  background: transparent;
}
.kv-tree::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-full);
}
.kv-tree::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}
</style>
