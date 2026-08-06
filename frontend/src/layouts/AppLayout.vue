<script setup lang="ts">
import TopBar from '@/components/TopBar.vue'
import SideNav from '@/components/SideNav.vue'
</script>

<template>
  <div class="app-layout">
    <TopBar />
    <div class="app-body">
      <SideNav />
      <main class="app-main">
        <RouterView v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
}
.app-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.app-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-subtle);
}
</style>
