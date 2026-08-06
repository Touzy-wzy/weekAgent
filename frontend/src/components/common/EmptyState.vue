<script setup lang="ts">
defineProps<{
  title?: string
  desc?: string
}>()

const suggestions = [
  '帮我生成本周周报',
  '查一下知识库里有哪些文档',
  '总结一下我上传的文件',
]
</script>

<template>
  <div class="empty-state">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="content">
      <div class="logo-mark">
        <span>GG</span>
      </div>
      <h2>{{ title || '你好，我是 GGBond' }}</h2>
      <p>{{ desc || '有什么可以帮你的？试着对我说点什么吧。' }}</p>
      <div class="suggestions">
        <button
          v-for="s in suggestions"
          :key="s"
          class="suggestion"
          @click="$emit('pick', s)"
        >
          {{ s }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
  pointer-events: none;
}
.orb-1 {
  width: 320px;
  height: 320px;
  background: var(--brand-200);
  top: 10%;
  left: 15%;
  animation: float-slow 12s ease-in-out infinite;
}
.orb-2 {
  width: 280px;
  height: 280px;
  background: #d9ccff;
  bottom: 10%;
  right: 15%;
  animation: float-slow 14s ease-in-out infinite reverse;
}
.content {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 480px;
  padding: 0 24px;
}
.logo-mark {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  border-radius: 20px;
  background: var(--accent-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 22px;
  font-family: var(--font-display);
  box-shadow: 0 12px 32px var(--glow-brand);
}
h2 {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}
p {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-bottom: 24px;
}
.suggestions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
.suggestion {
  padding: 10px 18px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  font-size: 13px;
  color: var(--text-secondary);
  transition: all var(--dur) var(--ease);
  box-shadow: var(--shadow-xs);
}
.suggestion:hover {
  border-color: var(--brand-300);
  color: var(--brand-600);
  background: var(--brand-50);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
</style>
