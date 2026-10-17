<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getLearnConfig } from '@/tongyun/learn-client'
import { failCopy, fetchToday } from '@/tongyun/english/client'
import type { TodayQueue } from '@/tongyun/english/types'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '今日 · 云芽英语',
})

const router = useRouter()
const ready = ref(false)
const hasToken = ref(false)
const loading = ref(false)
const error = ref('')
const queue = ref<TodayQueue | null>(null)

const dateText = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const date = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${date} 周${days[now.getDay()]}`
})

const progressPct = computed(() => {
  const value = queue.value?.unitProgress
  if (value === null || value === undefined) return 0
  return Math.round(value * 100)
})

const countText = computed(() => {
  const n = queue.value?.items.length ?? 0
  if (!n) return '教练今天没有排练习'
  return `${n} 项，按今日队列`
})

async function load() {
  loading.value = true
  error.value = ''
  const res = await fetchToday()
  loading.value = false
  if (!res.ok) {
    error.value = res.message || failCopy(res.kind)
    queue.value = null
    return
  }
  queue.value = res.data || null
}

onMounted(() => {
  ready.value = true
  hasToken.value = Boolean(getLearnConfig().token)
  if (hasToken.value) load()
})
</script>

<template>
  <section class="today">
    <p class="eyebrow">云芽英语</p>
    <h1>今日</h1>
    <p class="date">{{ dateText }}</p>

    <div v-if="!ready" class="yy-card panel skeleton" />

    <div v-else-if="!hasToken" class="yy-card panel">
      <p class="lead">先填写学习服务地址和令牌。填好之后，今天敲什么由教练的队列决定。</p>
      <button type="button" class="yy-btn" @click="router.push('/settings')">去设置</button>
    </div>

    <div v-else class="yy-card panel">
      <p v-if="loading" class="lead">正在取今日队列…</p>
      <template v-else-if="error">
        <p class="lead">{{ error }}</p>
        <div class="actions">
          <button type="button" class="yy-btn ghost" @click="load">重试</button>
          <button type="button" class="yy-btn" @click="router.push('/settings')">去设置</button>
        </div>
      </template>
      <template v-else-if="queue">
        <p class="unit">{{ queue.unitTitle || '英语' }}</p>
        <div class="bar" aria-hidden="true">
          <span :style="{ width: progressPct + '%' }" />
        </div>
        <p v-if="queue.unitProgress !== null" class="meta">单元进度 {{ progressPct }}%</p>
        <p v-if="queue.suggestion" class="suggest">{{ queue.suggestion }}</p>
        <p class="meta">{{ countText }}</p>
        <button type="button" class="yy-btn" data-testid="start-practice" :disabled="!queue.items.length" @click="router.push('/practice')">
          开始练习
        </button>
      </template>
    </div>
  </section>
</template>

<style scoped lang="scss">
.today {
  padding-top: 28px;
}

.eyebrow {
  margin: 0;
  color: var(--yy-matcha);
  letter-spacing: 0.14em;
  font-size: 13px;
}

h1 {
  margin: 8px 0 0;
  font-size: 40px;
  font-weight: 650;
  letter-spacing: 0.04em;
}

.date,
.meta {
  color: var(--yy-ink-soft);
}

.date {
  margin: 6px 0 22px;
}

.panel {
  padding: 28px 28px 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
}

.skeleton {
  min-height: 180px;
}

.lead,
.suggest {
  margin: 0;
  font-size: 18px;
  line-height: 1.6;
}

.unit {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
}

.suggest {
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--yy-matcha-soft);
  color: var(--yy-matcha-deep);
}

.bar {
  width: min(420px, 100%);
  height: 8px;
  border-radius: 999px;
  background: var(--yy-bg-deep);
  overflow: hidden;
}

.bar span {
  display: block;
  height: 100%;
  background: var(--yy-matcha);
}

.meta {
  margin: 0;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
