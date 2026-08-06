<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import MessageBubble from './MessageBubble.vue'
import ChatInput from './ChatInput.vue'
import SessionList from './SessionList.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const store = useChatStore()
const scrollRef = ref<HTMLDivElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(
  () => store.messages.length,
  () => scrollToBottom(),
)
watch(
  () => store.messages[store.messages.length - 1]?.content,
  () => scrollToBottom(),
)

function onPickSuggestion(s: string) {
  store.sendMessage(s)
}
</script>

<template>
  <div class="chat-view">
    <SessionList class="session-pane" />
    <div class="chat-main">
      <div v-if="store.hasMessages || store.streaming" ref="scrollRef" class="messages">
        <div class="messages-inner">
          <MessageBubble
            v-for="(m, i) in store.messages"
            :key="i"
            :message="m"
            :streaming="store.streaming && i === store.messages.length - 1"
            :waiting="store.waitingFirstByte && i === store.messages.length - 1"
            :session-id="store.currentSessionId"
          />
        </div>
      </div>
      <EmptyState v-else @pick="onPickSuggestion" />
      <ChatInput />
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  min-height: 0;
}
.session-pane {
  flex-shrink: 0;
}
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}
.messages-inner {
  max-width: var(--chat-max);
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
