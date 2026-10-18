<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { buildSession, type SessionPlan } from '@/tongyun/english/study'
import {
  getOptionalLevels,
  getStats,
  loadWordlist,
  type WordStat,
} from '@/tongyun/english/wordlist'
import {
  buildSubjectSession,
  getActiveSubject,
  getSubjectBank,
  getSubjectStats,
  type ActiveSubject,
  type SubjectSessionPlan,
} from '@/tongyun/subject'

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
const subjectPlan = ref<SubjectSessionPlan | null>(null)
const activeSubject = ref<ActiveSubject>('english')

const dateText = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const date = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${date} 周${days[now.getDay()]}`
})

const countText = computed(() => {
  if (activeSubject.value !== 'english') {
    const sp = subjectPlan.value
    if (!sp) return ''
    return `到期复习 ${sp.dueTotal} · 新题 ${sp.newTotal}`
  }
  const p = plan.value
  if (!p) return ''
  const parts = [`到期复习 ${p.dueTotal}`, `新词 ${p.newTotal}`]
  return parts.join(' · ')
})

const empty = computed(() => {
  if (activeSubject.value !== 'english') {
    return Boolean(subjectPlan.value) && subjectPlan.value!.items.length === 0
  }
  return Boolean(plan.value) && plan.value!.items.length === 0
})

async function load() {
  loading.value = true
  activeSubject.value = getActiveSubject()
  if (activeSubject.value !== 'english') {
    const bank = getSubjectBank(activeSubject.value)
    const stats = getSubjectStats(activeSubject.value)
    subjectPlan.value = buildSubjectSession(bank, stats, Date.now())
  } else {
    const list = await loadWordlist()
    const stats: Record<string, WordStat> = getStats()
    const optional = getOptionalLevels()
    plan.value = buildSession(list, stats, optional)
  }
  loading.value = false
}

function startPractice() {
  if (activeSubject.value === 'english') {
    router.push('/practice')
  } else {
    router.push(`/practice?subject=${activeSubject.value}`)
  }
}

onMounted(() => {
  ready.value = true
  load()
  window.addEventListener('tongyun-subject-changed', load)
})

onUnmounted(() => {
  window.removeEventListener('tongyun-subject-changed', load)
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
        @click="startPractice"
      >
        开始学
      </button>
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
</style>
