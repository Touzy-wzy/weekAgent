import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      redirect: '/chat',
      children: [
        {
          path: 'chat',
          name: 'chat',
          component: () => import('@/pages/ChatPage.vue'),
        },
        {
          path: 'chat/:sessionId',
          name: 'chat-session',
          component: () => import('@/pages/ChatPage.vue'),
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/pages/KnowledgePage.vue'),
        },
      ],
    },
  ],
})

export default router
