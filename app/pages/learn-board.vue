<!-- tongyun: 学习看板（只读） -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { BasePage } from '@/base'
import { getLearnConfig } from '@/tongyun/learn-client'
import type { Subject, NextResp, ReviewDueResp, Blocker } from '@/tongyun/learn-board-api'
import {
  fetchSubjects,
  fetchNext,
  fetchReviewDue,
  fetchOpenBlockers,
  fetchProgress,
  fetchMap,
} from '@/tongyun/learn-board-api'
import LbBlock from '@/components/tongyun/learn-board/LbBlock.vue'
import LbToday from '@/components/tongyun/learn-board/LbToday.vue'
import LbReview from '@/components/tongyun/learn-board/LbReview.vue'
import LbBlockers from '@/components/tongyun/learn-board/LbBlockers.vue'
import LbSubjects from '@/components/tongyun/learn-board/LbSubjects.vue'
import LbMap from '@/components/tongyun/learn-board/LbMap.vue'
import LbMapStatus from '@/components/tongyun/learn-board/LbMapStatus.vue'
import {
  JAVA_SUBJECT_ID,
  boardSubjectLabel,
  resolveBoardSubjects,
  summarizeMap,
  mapStatusLine,
  type MapStatusSummary,
} from '@/tongyun/learn-board-glance'
import { applyRecommendationsToMap } from '@/tongyun/learn-board-recommend'

useSeoMeta({
  title: '学习看板',
})

const router = useRouter()
const mapRef = ref<InstanceType<typeof LbMap> | null>(null)

const isMounted = ref(false)
const hasToken = ref(false)
const refreshing = ref(false)

const todayDateText = computed(() => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const date = String(now.getDate()).padStart(2, '0')
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const dayName = days[now.getDay()]
  return `${year}-${month}-${date} 周${dayName}`
})

// 各区块状态
type BlockState = 'loading' | 'ok' | 'bad_token' | 'unreachable' | 'soon'

const todayState = ref<BlockState>('loading')
const todayData = ref<NextResp>({
  recheck: [],
  next: [],
  new_point_quota: { global_left: 0, by_subject_left: {} },
})

const reviewState = ref<BlockState>('loading')
const reviewData = ref<ReviewDueResp>({
  review: [],
  new: [],
  counts: { due_total: 0 },
})

const blockersState = ref<BlockState>('loading')
const blockersData = ref<Blocker[]>([])
const blockersSoonText = ref('卡点记录即将接入')

const subjectsState = ref<BlockState>('loading')
const subjectsData = ref<Subject[]>([])
const retention = ref<Record<string, number | null | undefined>>({})
const retentionLoaded = ref<Record<string, boolean>>({})

const javaMapState = ref<BlockState>('loading')
const englishMapState = ref<BlockState>('loading')
const javaSummary = ref<MapStatusSummary | null>(null)
const englishSummary = ref<MapStatusSummary | null>(null)
const javaSubjectId = ref(JAVA_SUBJECT_ID)
const javaSubjectTitle = ref('Java')
const englishSubjectId = ref('')
const englishSubjectTitle = ref('英语')
const javaMissingText = ref('')
const englishMissingText = ref('')

const subjectTitles = computed(() => {
  const titles: Record<string, string> = {}
  const resolved = resolveBoardSubjects(subjectsData.value)
  for (const s of subjectsData.value) {
    if (resolved.java?.id === s.id) titles[s.id] = 'Java'
    else if (resolved.english?.id === s.id) titles[s.id] = '英语'
    else titles[s.id] = boardSubjectLabel(s)
  }
  titles[JAVA_SUBJECT_ID] = titles[JAVA_SUBJECT_ID] || 'Java'
  return titles
})

const todayHeadline = computed(() => {
  const recheck = todayData.value.recheck?.[0]
  if (recheck?.title) return `待复查 ${recheck.title}`
  const next = todayData.value.next?.[0]
  if (next?.title) {
    const sub = next.subject_id ? subjectTitles.value[next.subject_id] : ''
    return sub ? `${next.title}（${sub}）` : next.title
  }
  if (todayState.value === 'ok') return '今天没有要学的新点'
  return ''
})

const javaHeadline = computed(() => (javaSummary.value ? mapStatusLine(javaSummary.value) : ''))

function markMapPair(state: BlockState) {
  javaMapState.value = state
  englishMapState.value = state
}

async function loadOneMap(subject: Subject | null, slot: 'java' | 'english') {
  const isJava = slot === 'java'
  const setState = (s: BlockState) => {
    if (isJava) javaMapState.value = s
    else englishMapState.value = s
  }
  const setSummary = (s: MapStatusSummary | null) => {
    if (isJava) javaSummary.value = s
    else englishSummary.value = s
  }
  const setMissing = (s: string) => {
    if (isJava) javaMissingText.value = s
    else englishMissingText.value = s
  }

  if (!subject) {
    setSummary(null)
    setMissing(isJava ? '学科列表里没有 Java（java-fde）' : '学科列表里没有英语')
    if (isJava) {
      javaSubjectId.value = JAVA_SUBJECT_ID
      javaSubjectTitle.value = 'Java'
    } else {
      englishSubjectId.value = ''
      englishSubjectTitle.value = '英语'
    }
    setState('ok')
    return
  }

  if (isJava) {
    javaSubjectId.value = subject.id
    javaSubjectTitle.value = 'Java'
  } else {
    englishSubjectId.value = subject.id
    englishSubjectTitle.value = subject.title && subject.title !== '英语' ? subject.title : '英语'
  }
  setMissing('')

  const res = await fetchMap(subject.id)
  if (res.ok && res.data) {
    const recommendedMap = applyRecommendationsToMap(res.data)
    setSummary(summarizeMap(recommendedMap))
    setState('ok')
  } else if (res.kind === 'bad_token' || res.kind === 'no_token') {
    setSummary(null)
    setState('bad_token')
  } else if (res.kind === 'not_found') {
    setSummary(null)
    setMissing(isJava ? '还没有 Java（java-fde）的地图' : '还没有英语地图')
    setState('ok')
  } else {
    setSummary(null)
    setState('unreachable')
  }
}

function goToSetting() {
  router.push('/setting?index=0')
}

// initial=true：首次加载显示「加载中…」；手动刷新时保留旧内容直到新结果回来（避免知识地图被卸载、选中的学科被重置）
async function loadAll(initial = true) {
  if (initial) {
    todayState.value = 'loading'
    reviewState.value = 'loading'
    blockersState.value = 'loading'
    subjectsState.value = 'loading'
    javaMapState.value = 'loading'
    englishMapState.value = 'loading'
    javaMissingText.value = ''
    englishMissingText.value = ''
  }

  const [subjSettled, nextSettled, revSettled, blockSettled] = await Promise.allSettled([
    fetchSubjects(),
    fetchNext(),
    fetchReviewDue(),
    fetchOpenBlockers(),
  ])

  // 1. 今天学什么
  if (nextSettled.status === 'fulfilled') {
    const res = nextSettled.value
    if (res.ok) {
      todayData.value = res.data
      todayState.value = 'ok'
    } else if (res.kind === 'bad_token' || res.kind === 'no_token') {
      todayState.value = 'bad_token'
    } else {
      todayState.value = 'unreachable'
    }
  } else {
    todayState.value = 'unreachable'
  }

  // 2. 待复习
  if (revSettled.status === 'fulfilled') {
    const res = revSettled.value
    if (res.ok) {
      reviewData.value = res.data
      reviewState.value = 'ok'
    } else if (res.kind === 'bad_token' || res.kind === 'no_token') {
      reviewState.value = 'bad_token'
    } else {
      reviewState.value = 'unreachable'
    }
  } else {
    reviewState.value = 'unreachable'
  }

  // 3. 卡在哪
  if (blockSettled.status === 'fulfilled') {
    const res = blockSettled.value
    if (res.ok) {
      blockersData.value = res.data
      blockersState.value = 'ok'
    } else if (res.kind === 'bad_token' || res.kind === 'no_token') {
      blockersState.value = 'bad_token'
    } else if (res.kind === 'not_found') {
      blockersState.value = 'soon'
      blockersSoonText.value = '卡点记录即将接入'
    } else {
      blockersState.value = 'unreachable'
    }
  } else {
    blockersState.value = 'unreachable'
  }

  // 4. 各科统计（与知识地图共用 subjects 基础数据）
  if (subjSettled.status === 'fulfilled') {
    const res = subjSettled.value
    if (res.ok) {
      const resolved = resolveBoardSubjects(res.data)
      subjectsData.value = resolved.ordered
      subjectsState.value = 'ok'
      await Promise.all([loadOneMap(resolved.java, 'java'), loadOneMap(resolved.english, 'english')])

      // 并行拉 progress
      const currentSubjects = resolved.ordered
      const newRet: Record<string, number | null | undefined> = {}
      const newRetLoaded: Record<string, boolean> = {}

      await Promise.allSettled(
        currentSubjects.map(async sub => {
          const progRes = await fetchProgress(sub.id)
          newRetLoaded[sub.id] = true
          newRet[sub.id] = progRes.ok ? progRes.data?.retention_30d : null
        })
      )
      retention.value = newRet
      retentionLoaded.value = newRetLoaded
    } else if (res.kind === 'bad_token' || res.kind === 'no_token') {
      subjectsState.value = 'bad_token'
      markMapPair('bad_token')
    } else {
      subjectsState.value = 'unreachable'
      markMapPair('unreachable')
    }
  } else {
    subjectsState.value = 'unreachable'
    markMapPair('unreachable')
  }
}

async function handleRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    mapRef.value?.reload()
    await loadAll(false)
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  isMounted.value = true
  const cfg = getLearnConfig()
  const token = cfg.token?.trim()
  if (!token) {
    hasToken.value = false
    return
  }

  hasToken.value = true
  loadAll()
})
</script>

<template>
  <BasePage>
    <div class="lb-container">
      <!-- 页面头部 -->
      <header class="lb-header">
        <div class="lb-header-info">
          <h1 class="lb-title">学习看板</h1>
          <p class="lb-subtitle">{{ todayDateText }}</p>
          <p v-if="hasToken" class="lb-pair-line">Java（java-fde） · 英语</p>
          <p v-if="hasToken && (todayHeadline || javaHeadline)" class="lb-glance">
            <span v-if="todayHeadline">今天：{{ todayHeadline }}</span>
            <span v-if="javaHeadline">Java 地图：{{ javaHeadline }}</span>
          </p>
        </div>
        <div v-if="hasToken" class="lb-header-actions">
          <button type="button" class="lb-refresh-btn" :disabled="refreshing" @click="handleRefresh">
            {{ refreshing ? '刷新中…' : '刷新' }}
          </button>
        </div>
      </header>

      <!-- 客户端尚未就绪或未挂载时骨架占位 -->
      <div v-if="!isMounted" class="lb-card-placeholder" />

      <!-- 未配置 token 时的提示卡片 -->
      <div v-else-if="!hasToken" class="lb-no-token-card">
        <p class="lb-no-token-text">学习看板暂不可用，先去「练习」背词。</p>
      </div>

      <!-- 正常数据区块。首屏：今天学什么 + Java 地图状态 + 英语 -->
      <div v-else class="lb-sections">
        <div class="lb-first-screen">
          <LbBlock title="今天学什么" :state="todayState" prominent>
            <LbToday :data="todayData" :subject-titles="subjectTitles" />
          </LbBlock>

          <LbBlock title="Java 地图状态" :state="javaMapState" prominent accent="java">
            <LbMapStatus
              :summary="javaSummary"
              :subject-id="javaSubjectId"
              :subject-title="javaSubjectTitle"
              :missing-text="javaMissingText"
            />
          </LbBlock>

          <LbBlock title="英语" :state="englishMapState" prominent>
            <LbMapStatus
              :summary="englishSummary"
              :subject-id="englishSubjectId"
              :subject-title="englishSubjectTitle"
              :missing-text="englishMissingText"
            />
          </LbBlock>
        </div>

        <div class="lb-top-grid">
          <LbBlock title="待复习" :state="reviewState">
            <LbReview :data="reviewData" />
          </LbBlock>
        </div>

        <!-- 3. 卡在哪 -->
        <LbBlock title="卡在哪" :state="blockersState" :soon-text="blockersSoonText">
          <LbBlockers :items="blockersData" />
        </LbBlock>

        <!-- 4. 各科统计 -->
        <LbBlock title="各科统计" :state="subjectsState">
          <LbSubjects :subjects="subjectsData" :retention="retention" :retention-loaded="retentionLoaded" />
        </LbBlock>

        <!-- 5. 知识地图 -->
        <LbBlock title="知识地图" :state="subjectsState">
          <LbMap ref="mapRef" :subjects="subjectsData" />
        </LbBlock>
      </div>
    </div>
  </BasePage>
</template>

<style scoped lang="scss">
.lb-container {
  max-width: 1120px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px 36px 16px;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.lb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
}

.lb-header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lb-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-main-text);
  line-height: 1.3;
}

.lb-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--color-sub-text);
}

.lb-pair-line {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-main-text);
}

.lb-glance {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 8px 0 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--color-main-text);
}

.lb-header-actions {
  display: flex;
  align-items: center;
}

.lb-refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 18px;
  font-size: 15px;
  border-radius: 8px;
  border: 1px solid var(--color-item-border);
  background: var(--color-second);
  color: var(--color-main-text);
  cursor: pointer;
  touch-action: manipulation;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: var(--color-fourth);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.lb-card-placeholder {
  min-height: 120px;
}

.lb-no-token-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 16px;
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  border-radius: 12px;
  text-align: center;
}

.lb-no-token-text {
  margin: 0;
  font-size: 16px;
  color: var(--color-sub-text);
}

.lb-go-setting-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0 24px;
  font-size: 15px;
  font-weight: 500;
  border-radius: 8px;
  background: var(--color-select-bg);
  border: 1px solid var(--color-select-bg);
  color: white;
  cursor: pointer;
  touch-action: manipulation;
  transition: opacity 0.2s;

  &:hover {
    opacity: 0.9;
  }

  &:active {
    opacity: 0.8;
  }
}

.lb-sections {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lb-first-screen {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  align-items: start;

  @media (min-width: 840px) {
    grid-template-columns: 1.15fr 1fr;
  }

  @media (min-width: 1280px) {
    grid-template-columns: 1.2fr 1fr 0.95fr;
  }
}

.lb-top-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}
</style>
