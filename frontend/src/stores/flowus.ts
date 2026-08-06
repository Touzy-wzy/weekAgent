import { defineStore } from 'pinia'
import { ref } from 'vue'
import { flowusApi } from '@/api/flowus'
import type { PageItem } from '@/types'

export const useFlowusStore = defineStore('flowus', () => {
  const pages = ref<PageItem[]>([])
  const currentPageId = ref<string | null>(null)
  const currentContent = ref<{ title: string; content: string; html: string } | null>(null)
  const loading = ref(false)
  const loadingContent = ref(false)

  async function loadPages() {
    loading.value = true
    try {
      pages.value = await flowusApi.listPages()
    } catch (e) {
      console.error('加载页面树失败', e)
      pages.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadPage(pageId: string) {
    currentPageId.value = pageId
    loadingContent.value = true
    try {
      const data = await flowusApi.getPage(pageId)
      currentContent.value = { title: data.title, content: data.content, html: data.html }
    } catch (e) {
      console.error('加载页面内容失败', e)
      currentContent.value = null
    } finally {
      loadingContent.value = false
    }
  }

  async function refresh() {
    await flowusApi.refresh()
    await loadPages()
  }

  function reset() {
    pages.value = []
    currentPageId.value = null
    currentContent.value = null
  }

  return {
    pages,
    currentPageId,
    currentContent,
    loading,
    loadingContent,
    loadPages,
    loadPage,
    refresh,
    reset,
  }
})
