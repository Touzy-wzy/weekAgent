<script setup lang="ts">
defineProps<{
  title: string
  html: string
  loading: boolean
}>()
</script>

<template>
  <div class="page-content">
    <header class="content-header">
      <h1 v-if="title" class="content-title">{{ title }}</h1>
      <div v-else class="title-skeleton"></div>
    </header>

    <div class="content-body">
      <div v-if="loading" class="skeleton">
        <div class="skeleton-line" style="width: 92%"></div>
        <div class="skeleton-line" style="width: 78%"></div>
        <div class="skeleton-line" style="width: 85%"></div>
        <div class="skeleton-line" style="width: 60%"></div>
        <div class="skeleton-gap"></div>
        <div class="skeleton-line" style="width: 88%"></div>
        <div class="skeleton-line" style="width: 70%"></div>
        <div class="skeleton-line" style="width: 80%"></div>
      </div>
      <article v-else class="rich-text" v-html="html"></article>
    </div>
  </div>
</template>

<style scoped>
.page-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.content-header {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 28px 40px 20px;
  background: var(--bg-overlay);
  backdrop-filter: saturate(180%) blur(12px);
  -webkit-backdrop-filter: saturate(180%) blur(12px);
  border-bottom: 1px solid var(--border-subtle);
}
.content-title {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
  letter-spacing: 0.01em;
}
.title-skeleton {
  height: 30px;
  width: 280px;
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
.content-body {
  flex: 1;
  min-height: 0;
  padding: 28px 40px 64px;
  display: flex;
  justify-content: center;
}
.rich-text {
  width: 100%;
  max-width: 800px;
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--text-secondary);
  word-break: break-word;
}
.skeleton {
  width: 100%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.skeleton-line {
  height: 14px;
  border-radius: var(--radius-xs);
  background: linear-gradient(
    90deg,
    var(--bg-sunken) 0%,
    var(--border-subtle) 50%,
    var(--bg-sunken) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}
.skeleton-gap {
  height: 18px;
}

/* v-html 富文本排版 */
.rich-text :deep(h1) {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 28px 0 14px;
  line-height: 1.35;
}
.rich-text :deep(h2) {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 24px 0 12px;
  line-height: 1.4;
}
.rich-text :deep(h3) {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 20px 0 10px;
}
.rich-text :deep(p) {
  margin: 0 0 14px;
  color: var(--text-secondary);
}
.rich-text :deep(a) {
  color: var(--brand-600);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease);
}
.rich-text :deep(a:hover) {
  color: var(--brand-700);
  text-decoration: underline;
}
.rich-text :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}
.rich-text :deep(ul) {
  list-style: disc;
  padding-left: 22px;
  margin: 0 0 14px;
}
.rich-text :deep(ol) {
  list-style: decimal;
  padding-left: 22px;
  margin: 0 0 14px;
}
.rich-text :deep(li) {
  margin: 0 0 6px;
  color: var(--text-secondary);
}
.rich-text :deep(li:last-child) {
  margin-bottom: 0;
}
.rich-text :deep(blockquote) {
  margin: 0 0 14px;
  padding: 10px 16px;
  border-left: 3px solid var(--brand-300);
  background: var(--brand-50);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--text-tertiary);
  font-style: italic;
}
.rich-text :deep(blockquote p) {
  margin: 0;
  color: var(--text-tertiary);
}
.rich-text :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.9em;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  background: var(--bg-sunken);
  color: var(--brand-600);
  border: 1px solid var(--border-subtle);
}
.rich-text :deep(pre) {
  margin: 0 0 16px;
  padding: 16px 18px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow-x: auto;
  line-height: 1.6;
}
.rich-text :deep(pre code) {
  padding: 0;
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
}
.rich-text :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-md);
  margin: 8px 0 16px;
  box-shadow: var(--shadow-sm);
}
.rich-text :deep(hr) {
  border: none;
  height: 1px;
  background: var(--border-subtle);
  margin: 24px 0;
}
.rich-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 16px;
  font-size: 13.5px;
}
.rich-text :deep(th),
.rich-text :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  text-align: left;
}
.rich-text :deep(th) {
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-weight: 600;
}

/* 滚动条（细） */
.page-content::-webkit-scrollbar,
.rich-text :deep(pre)::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.page-content::-webkit-scrollbar-track,
.rich-text :deep(pre)::-webkit-scrollbar-track {
  background: transparent;
}
.page-content::-webkit-scrollbar-thumb,
.rich-text :deep(pre)::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-full);
}
.page-content::-webkit-scrollbar-thumb:hover,
.rich-text :deep(pre)::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}
</style>
