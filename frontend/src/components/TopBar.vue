<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => {
  if (route.name === 'knowledge') return '知识库'
  return 'GGBond'
})
</script>

<template>
  <header class="top-bar glass">
    <div class="left">
      <div class="logo">
        <span class="logo-mark">G</span>
        <span class="logo-text gradient-text">GGBond</span>
      </div>
      <span class="divider"></span>
      <span class="page-title">{{ title }}</span>
    </div>
    <div class="right">
      <span class="status-dot" title="在线"></span>
    </div>
  </header>
</template>

<style scoped>
.top-bar {
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-subtle);
  position: relative;
  z-index: 10;
}
.left {
  display: flex;
  align-items: center;
  gap: 14px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
}
.logo-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--accent-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 15px;
  font-family: var(--font-display);
  box-shadow: 0 4px 12px var(--glow-brand);
}
.logo-text {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.02em;
}
.divider {
  width: 1px;
  height: 18px;
  background: var(--border-default);
}
.page-title {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
  animation: pulse-glow 2s ease-in-out infinite;
}
</style>
