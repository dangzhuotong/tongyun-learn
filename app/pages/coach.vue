<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getLearnConfig } from '@/tongyun/learn-client'
import { failCopy, fetchCoach, postCoach } from '@/tongyun/english/client'
import type { CoachView } from '@/tongyun/english/types'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '橦云学习',
})

const router = useRouter()
const ready = ref(false)
const hasToken = ref(false)
const loading = ref(false)
const error = ref('')
const coach = ref<CoachView | null>(null)
const posting = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  const res = await fetchCoach()
  loading.value = false
  if (!res.ok) {
    error.value = res.message || failCopy(res.kind)
    coach.value = null
    return
  }
  coach.value = res.data || null
}

async function askCoach(thenPractice = false) {
  if (posting.value) return
  posting.value = true
  error.value = ''
  const res = await postCoach()
  posting.value = false
  if (!res.ok) {
    error.value = res.message || failCopy(res.kind)
    return
  }
  coach.value = res.data || coach.value
  if (thenPractice) router.push('/practice')
}

onMounted(() => {
  ready.value = true
  hasToken.value = Boolean(getLearnConfig().token)
  if (hasToken.value) load()
})
</script>

<template>
  <section class="coach">
    <p class="eyebrow">橦云学习</p>
    <h1>教练</h1>
    <p class="sub">薄弱点和这周怎么排，都是服务端写好的。按这份计划去练习，敲的仍是今日队列。</p>

    <div v-if="!ready" class="yy-card panel skeleton" />

    <div v-else-if="!hasToken" class="yy-card panel">
      <p>先填写学习服务令牌，教练报告才会出现。</p>
      <button type="button" class="yy-btn" @click="router.push('/settings')">去设置</button>
    </div>

    <div v-else-if="loading" class="yy-card panel">
      <p>正在读教练报告…</p>
    </div>

    <div v-else-if="error && !coach" class="yy-card panel">
      <p>{{ error }}</p>
      <div class="actions">
        <button type="button" class="yy-btn ghost" @click="load">重试</button>
        <button type="button" class="yy-btn" :disabled="posting" data-testid="ask-coach" @click="askCoach(false)">
          {{ posting ? '正在请教练…' : '请教练排一下' }}
        </button>
        <button type="button" class="yy-btn ghost" @click="router.push('/settings')">去设置</button>
      </div>
    </div>

    <template v-else-if="coach">
      <article class="yy-card panel">
        <h2>一句话</h2>
        <p class="summary">{{ coach.summary || '教练还没有新的分析。先去敲几轮。' }}</p>
      </article>

      <article class="yy-card panel">
        <h2>薄弱点</h2>
        <ul v-if="coach.weak.length" class="list">
          <li v-for="(item, index) in coach.weak" :key="`${item.word}-${index}`">
            <div class="row">
              <strong>{{ item.word }}</strong>
              <span v-if="item.tag" class="tag">{{ item.tag }}</span>
              <span v-if="item.count !== null" class="count">{{ item.count }} 次</span>
            </div>
            <p v-if="item.detail">{{ item.detail }}</p>
          </li>
        </ul>
        <p v-else class="empty">还没有点名的钉子词。</p>
      </article>

      <article class="yy-card panel">
        <h2>本周计划</h2>
        <ol v-if="coach.plan.length" class="plan">
          <li v-for="(item, index) in coach.plan" :key="`${item.title}-${index}`">
            <strong>{{ item.title }}</strong>
            <p v-if="item.note">{{ item.note }}</p>
          </li>
        </ol>
        <p v-else class="empty">计划还空着。今日队列本身就是当下要敲的。</p>
        <p v-if="error" class="empty">{{ error }}</p>
        <button type="button" class="yy-btn" data-testid="follow-plan" :disabled="posting" @click="askCoach(true)">
          {{ posting ? '正在记下计划…' : '按此计划去练习' }}
        </button>
      </article>
    </template>
  </section>
</template>

<style scoped lang="scss">
.coach {
  padding-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
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
}

h2 {
  margin: 0;
  font-size: 16px;
  color: var(--yy-ink-soft);
  font-weight: 600;
}

.sub,
.empty,
.summary,
.list p,
.plan p {
  margin: 0;
  line-height: 1.6;
  color: var(--yy-ink-soft);
}

.summary {
  color: var(--yy-ink);
  font-size: 20px;
}

.panel {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.skeleton {
  min-height: 140px;
}

.actions {
  display: flex;
  gap: 10px;
}

.list,
.plan {
  margin: 0;
  padding: 0;
  width: 100%;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.plan {
  list-style: decimal;
  padding-left: 1.2rem;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.row strong,
.plan strong {
  font-size: 18px;
  color: var(--yy-ink);
}

.tag,
.count {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--yy-matcha-soft);
  color: var(--yy-matcha-deep);
}

.count {
  background: var(--yy-bg-deep);
  color: var(--yy-ink-soft);
}
</style>
