<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <nav class="side-nav">
    <RouterLink to="/chat" class="nav-item" active-class="active">
      <span class="icon">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </span>
      <span class="label">对话</span>
    </RouterLink>
    <RouterLink to="/knowledge" class="nav-item" active-class="active">
      <span class="icon">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
      </span>
      <span class="label">知识库</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.side-nav {
  width: 80px;
  min-width: 80px;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
  gap: 8px;
}
.nav-item {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: var(--text-tertiary);
  transition: all var(--dur) var(--ease);
  position: relative;
}
.nav-item:hover {
  background: var(--bg-subtle);
  color: var(--text-secondary);
}
.nav-item.active {
  color: var(--brand-600);
  background: var(--brand-50);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 24px;
  background: var(--accent-gradient);
  border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
}
.icon {
  display: flex;
  align-items: center;
  justify-content: center;
}
.label {
  font-size: 11px;
  font-weight: 500;
}
</style>
