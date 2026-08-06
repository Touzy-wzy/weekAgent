<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import ChatView from '@/components/chat/ChatView.vue'

const store = useChatStore()
const route = useRoute()

onMounted(async () => {
  await store.loadSessions()
  const sid = route.params.sessionId as string | undefined
  if (sid) {
    await store.selectSession(sid)
  }
})

watch(
  () => route.params.sessionId,
  async (sid) => {
    if (sid && sid !== store.currentSessionId) {
      await store.selectSession(sid as string)
    }
  },
)
</script>

<template>
  <ChatView />
</template>
