<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { buildSession, type SessionPlan } from '@/tongyun/english/study'
import {
  LEVELS,
  NGSL_ATTRIBUTION,
  getOptionalLevels,
  getStats,
  loadWordlist,
  orderedLevels,
  setOptionalLevel,
  type WordEntry,
  type WordStat,
} from '@/tongyun/english/wordlist'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '今日 · 橦云学习',
})

const router = useRouter()
const ready = ref(false)
const loading = ref(true)
const plan = ref<SessionPlan | null>(null)
const levels = ref<{ level: number; title: string; optional?: boolean; done: number; total: number }[]>([])
const optional = ref<number[]>([])

const dateText = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const date = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${date} 周${days[now.getDay()]}`
})

const countText = computed(() => {
  const p = plan.value
  if (!p) return ''
  const parts = [`到期复习 ${p.dueTotal}`, `新词 ${p.newTotal}`]
  return parts.join(' · ')
})

const empty = computed(() => Boolean(plan.value) && plan.value!.items.length === 0)

async function load() {
  loading.value = true
  const list = await loadWordlist()
  const stats: Record<string, WordStat> = getStats()
  optional.value = getOptionalLevels()
  plan.value = buildSession(list, stats, optional.value)
  levels.value = orderedLevels(optional.value).map(n => {
    const meta = LEVELS.find(l => l.level === n)
    const words: WordEntry[] = list.filter(w => w.level === n)
    const done = words.filter(w => stats[w.word]?.taught).length
    return { level: n, title: meta?.title || `L${n}`, optional: meta?.optional, done, total: words.length }
  })
  loading.value = false
}

function toggleOptional(n: number) {
  const on = !optional.value.includes(n)
  setOptionalLevel(n, on)
  load()
}

onMounted(() => {
  ready.value = true
  load()
})
</script>

<template>
  <section class="today">
    <p class="eyebrow">橦云学习</p>
    <h1>今日</h1>
    <p class="date">{{ dateText }}</p>

    <div v-if="!ready || loading" class="yy-card panel skeleton" />

    <div v-else class="yy-card panel">
      <template v-if="empty">
        <p class="lead">今天的词都学完了，明天再来。</p>
      </template>
      <template v-else>
        <p class="unit">{{ countText }}</p>
        <p class="meta">先复习到期的，再学新词；随时可以停下。</p>
      </template>
      <button
        type="button"
        class="yy-btn"
        data-testid="start-learn"
        :disabled="empty"
        @click="router.push('/practice')"
      >
        开始学
      </button>
    </div>

    <details class="levels" data-testid="level-progress">
      <summary>级别进度</summary>
      <ul>
        <li v-for="l in levels" :key="l.level" :data-testid="`level-${l.level}`">
          <span class="lv-title">{{ l.title }}</span>
          <span class="lv-count">{{ l.done }}/{{ l.total }}</span>
          <label v-if="l.optional" class="lv-opt">
            <input
              type="checkbox"
              :checked="optional.includes(l.level)"
              :data-testid="`level-optional-${l.level}`"
              @change="toggleOptional(l.level)"
            />
            可选
          </label>
        </li>
      </ul>
    </details>

    <p class="credit">{{ NGSL_ATTRIBUTION }}</p>
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
.meta {
  margin: 0;
  font-size: 16px;
  line-height: 1.6;
}

.unit {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
}

.levels {
  margin-top: 20px;
  font-size: 13px;
  color: var(--yy-ink-soft);
}

.levels summary {
  cursor: pointer;
  min-height: 32px;
}

.levels ul {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.levels li {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lv-title {
  flex: 1;
}

.lv-count {
  color: var(--yy-matcha-deep);
}

.lv-opt {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.credit {
  margin-top: 18px;
  font-size: 12px;
  color: var(--yy-ink-soft);
  line-height: 1.6;
}
</style>
