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
import {
  scheduleCurriculum,
  getCurriculumSubjects,
  type CurriculumCard,
  type SchedulerResult,
} from '@/tongyun/curriculum'

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
const curriculumPlan = ref<SchedulerResult | null>(null)
const activeSubject = ref<ActiveSubject>('english')

const dateText = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const date = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${date} 周${days[now.getDay()]}`
})

const countText = computed(() => {
  if (curriculumPlan.value) {
    return `到期复习 ${curriculumPlan.value.dueTotal} · 新卡 ${curriculumPlan.value.newItems.length}`
  }
  if (activeSubject.value === 'java' || activeSubject.value === 'ai') {
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
  if (curriculumPlan.value) {
    return curriculumPlan.value.items.length === 0
  }
  if (activeSubject.value === 'java' || activeSubject.value === 'ai') {
    return Boolean(subjectPlan.value) && subjectPlan.value!.items.length === 0
  }
  return Boolean(plan.value) && plan.value!.items.length === 0
})

async function load() {
  loading.value = true
  activeSubject.value = getActiveSubject()
  const now = Date.now()

  const list = await loadWordlist()
  const enStats: Record<string, WordStat> = getStats()
  const optional = getOptionalLevels()
  plan.value = buildSession(list, enStats, optional, now)

  const javaBank = getSubjectBank('java')
  const javaStats = getSubjectStats('java')
  const aiBank = getSubjectBank('ai')
  const aiStats = getSubjectStats('ai')

  if (activeSubject.value === 'java' || activeSubject.value === 'ai') {
    const bank = activeSubject.value === 'java' ? javaBank : aiBank
    const stats = activeSubject.value === 'java' ? javaStats : aiStats
    subjectPlan.value = buildSubjectSession(bank, stats, now)
  }

  // 组装多学科课程表输入
  const reviews: CurriculumCard[] = []
  const newCards: Record<string, CurriculumCard[]> = {
    english: [],
    java: [],
    ai: [],
  }

  for (const [w, st] of Object.entries(enStats)) {
    if (st && st.last > 0 && st.due <= now) {
      reviews.push({ id: `en-${w}`, subject: 'english', due: st.due, isReview: true })
    }
  }
  for (const w of list) {
    if (!enStats[w.word]) {
      newCards.english.push({ id: `en-${w.word}`, subject: 'english', prompt: w.word, isReview: false })
    }
  }

  for (const it of javaBank.items || []) {
    const s = javaStats[it.id]
    if (s && s.last > 0) {
      if (s.due <= now) {
        reviews.push({ id: it.id, subject: 'java', type: it.type, tags: it.tags, due: s.due, isReview: true })
      }
    } else {
      newCards.java.push({ id: it.id, subject: 'java', type: it.type, tags: it.tags, isReview: false })
    }
  }

  for (const it of aiBank.items || []) {
    const s = aiStats[it.id]
    if (s && s.last > 0) {
      if (s.due <= now) {
        reviews.push({ id: it.id, subject: 'ai', type: it.type, tags: it.tags, due: s.due, isReview: true })
      }
    } else {
      newCards.ai.push({ id: it.id, subject: 'ai', type: it.type, tags: it.tags, isReview: false })
    }
  }

  curriculumPlan.value = scheduleCurriculum({
    subjects: getCurriculumSubjects(),
    reviews,
    newCards,
    now,
  })

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
