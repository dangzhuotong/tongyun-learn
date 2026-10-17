<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getLearnConfig } from '@/tongyun/learn-client'
import { fetchToday } from '@/tongyun/english/client'
import type { TodayQueue } from '@/tongyun/english/types'
import { buildLocalQueue } from '@/tongyun/english/local-queue'
import { LEVELS, NGSL_ATTRIBUTION, dueCount, getLevel, getProgress, loadWordlist, setLevel } from '@/tongyun/english/wordlist'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '今日 · 橦云学习',
})

const router = useRouter()
const ready = ref(false)
const hasToken = ref(false)
const loading = ref(false)
const error = ref('')
const queue = ref<TodayQueue | null>(null)
// tongyun: 按 L1–L5 分级选词
const level = ref(1)
const levelStats = ref<{ level: number; title: string; optional?: boolean; done: number; total: number; due: number }[]>([])
const localMode = ref(false)

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
  const items = queue.value?.items ?? []
  const n = localMode.value ? items.filter(i => i.stage === 'A').length : items.length
  if (!n) return '今天没有要练的词'
  return localMode.value ? `本轮 ${n} 个词：看中文拼英文，再敲例句` : `今天 ${n} 项`
})

async function load() {
  loading.value = true
  error.value = ''
  // tongyun: 没令牌就不请求学习服务；today 404/报错时静默回退本地词书，不弹报错
  const res = hasToken.value ? await fetchToday() : null
  if (res && res.ok && res.data && res.data.items.length) {
    queue.value = res.data
    localMode.value = false
  } else {
    await refreshLevels()
    queue.value = await buildLocalQueue(level.value)
    localMode.value = true
  }
  loading.value = false
}

async function refreshLevels() {
  const list = await loadWordlist()
  const prog = getProgress()
  levelStats.value = LEVELS.map(l => {
    const total = list.filter(w => w.level === l.level).length
    return { ...l, total, done: Math.min(prog[l.level] || 0, total), due: dueCount(list, l.level) }
  })
}

async function pickLevel(n: number) {
  level.value = n
  setLevel(n)
  queue.value = await buildLocalQueue(n)
}

onMounted(() => {
  ready.value = true
  hasToken.value = Boolean(getLearnConfig().token)
  level.value = getLevel()
  load()
})
</script>

<template>
  <section class="today">
    <p class="eyebrow">橦云学习</p>
    <h1>今日</h1>
    <p class="date">{{ dateText }}</p>

    <div v-if="!ready" class="yy-card panel skeleton" />

    <div v-else class="yy-card panel">
      <p v-if="loading" class="lead">正在准备今天的词…</p>
      <template v-else-if="error">
        <p class="lead">{{ error }}</p>
        <div class="actions">
          <button type="button" class="yy-btn ghost" @click="load">重试</button>
        </div>
      </template>
      <template v-else-if="queue">
        <div v-if="localMode" class="levels" data-testid="level-picker">
          <button
            v-for="l in levelStats"
            :key="l.level"
            type="button"
            class="lv"
            :class="{ on: l.level === level }"
            :data-testid="`level-${l.level}`"
            @click="pickLevel(l.level)"
          >
            <strong>{{ l.title }}</strong>
            <span>{{ l.done }}/{{ l.total }}<template v-if="l.due"> · 待复习 {{ l.due }}</template><template v-if="l.optional"> · 可选</template></span>
          </button>
        </div>
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
    <p v-if="localMode" class="credit">{{ NGSL_ATTRIBUTION }}</p>
  </section>
</template>

<style scoped lang="scss">
.levels { display: flex; flex-wrap: wrap; gap: 8px; }
.lv { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 12px; border-radius: 12px; border: 1px solid var(--yy-line, #e5ddd0); background: transparent; cursor: pointer; font-size: 13px; color: inherit; }
.lv span { color: var(--yy-ink-soft); font-size: 12px; }
.lv.on { border-color: var(--yy-matcha, #a4c48c); background: rgba(164, 196, 140, 0.15); }
.credit { margin-top: 18px; font-size: 12px; color: var(--yy-ink-soft); line-height: 1.6; }

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
