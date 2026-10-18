<!-- tongyun: AI 错词复习卷 -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { BasePage, BaseButton } from '@/base'
import { useBaseStore } from '@/core/stores/base.ts'
import {
  aiQuiz,
  gradeQuizAnswer,
  isLearnConfigured,
  pickWrongWordsForQuiz,
  LearnError,
  type QuizQuestion,
  type QuizWordItem,
} from '@/tongyun/learn-client'

useSeoMeta({
  title: 'AI 错词复习卷',
})

definePageMeta({
  // client-only: 读 IndexedDB 错词本 + 调学习服务
})

const router = useRouter()
const base = useBaseStore()

type Phase = 'pick' | 'loading' | 'quiz' | 'done'

const phase = ref<Phase>('pick')
const selected = ref<Set<string>>(new Set())
const loading = ref(false)
const errorMsg = ref('')
const notConfigured = ref(false)

const questions = ref<QuizQuestion[]>([])
const qIndex = ref(0)
const userInput = ref('')
const choicePicked = ref<string | null>(null)
const answered = ref(false)
const lastCorrect = ref(false)
const correctCount = ref(0)

let abortController: AbortController | null = null
// tongyun: 追踪组件挂载状态，防止异步请求返回时更新已卸载组件
let isMounted = false

const wrongWords = computed(() => base.wrong?.words || [])

const candidates = computed(() => pickWrongWordsForQuiz(wrongWords.value, 20))

const current = computed(() => questions.value[qIndex.value] || null)

const progressText = computed(() => {
  if (!questions.value.length) return ''
  return `${qIndex.value + 1} / ${questions.value.length}`
})

// tongyun: 错词本数据从 IndexedDB 异步载入时，默认全选候选词
watch(
  candidates,
  next => {
    if (selected.value.size === 0 && next.length > 0) {
      selected.value = new Set(next.map(w => w.word.toLowerCase()))
    }
  },
  { immediate: true }
)

onMounted(() => {
  isMounted = true
  const all = candidates.value
  if (selected.value.size === 0 && all.length > 0) {
    selected.value = new Set(all.map(w => w.word.toLowerCase()))
  }
})

onUnmounted(() => {
  isMounted = false
  if (abortController) {
    abortController.abort()
    abortController = null
  }
})

function toggleWord(word: string) {
  const key = word.toLowerCase()
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

function selectAll() {
  selected.value = new Set(candidates.value.map(w => w.word.toLowerCase()))
}

function clearAll() {
  selected.value = new Set()
}

function goSetting() {
  router.push('/setting?index=0')
}

function resetQuizState() {
  qIndex.value = 0
  userInput.value = ''
  choicePicked.value = null
  answered.value = false
  lastCorrect.value = false
  correctCount.value = 0
}

async function generate() {
  // tongyun: 请求进行中阻止重复点击导致重复提交
  if (loading.value) return
  errorMsg.value = ''
  notConfigured.value = false

  if (!isLearnConfigured()) {
    notConfigured.value = true
    errorMsg.value = 'AI 功能暂不可用'
    return
  }

  const picked: QuizWordItem[] = candidates.value.filter(w =>
    selected.value.has(w.word.toLowerCase())
  )
  if (!picked.length) {
    errorMsg.value = '请至少勾选 1 个错词'
    return
  }

  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  phase.value = 'loading'

  try {
    const res = await aiQuiz(picked, { signal: abortController.signal })
    // tongyun: 组件卸载后停止更新状态
    if (!isMounted) return
    const qs = res?.content?.questions || []
    if (!qs.length) {
      errorMsg.value = '服务没有返回题目，请稍后再试'
      phase.value = 'pick'
      return
    }
    questions.value = qs
    resetQuizState()
    phase.value = 'quiz'
  } catch (err: any) {
    // tongyun: 主动取消或组件卸载后不更新状态
    if (!isMounted || err?.name === 'AbortError') return
    // tongyun: 401/403 鉴权失败与未配置一样引导去设置页填令牌
    if (
      err instanceof LearnError &&
      (err.code === 'not_configured' ||
        err.code === 'unauthorized' ||
        err.code === 'forbidden' ||
        err.status === 401 ||
        err.status === 403)
    ) {
      notConfigured.value = true
    }
    errorMsg.value = err instanceof LearnError ? err.message : '生成复习卷失败'
    phase.value = 'pick'
  } finally {
    // tongyun: 组件若仍挂载才重置 loading
    if (isMounted) {
      loading.value = false
      abortController = null
    }
  }
}

function submitAnswer(choice?: string) {
  const q = current.value
  if (!q || answered.value) return

  let ok = false
  if (q.type === 'choice') {
    const pick = choice ?? choicePicked.value
    if (!pick) return
    choicePicked.value = pick
    // tongyun: 单选大小写/前后空白容错比较
    ok = pick.trim().toLowerCase() === q.answer.trim().toLowerCase()
  } else {
    // tongyun: 填空空输入时不提交，防止误按回车直接判错
    if (!userInput.value.trim()) return
    ok = gradeQuizAnswer(userInput.value, q.answer)
  }

  lastCorrect.value = ok
  if (ok) correctCount.value += 1
  answered.value = true
}

function nextQuestion() {
  if (qIndex.value + 1 >= questions.value.length) {
    phase.value = 'done'
    return
  }
  qIndex.value += 1
  userInput.value = ''
  choicePicked.value = null
  answered.value = false
  lastCorrect.value = false
}

function again() {
  questions.value = []
  resetQuizState()
  errorMsg.value = ''
  phase.value = 'pick'
}
</script>

<template>
  <BasePage>
    <div class="aq-container">
      <div class="aq-header">
        <div class="aq-header-info">
          <h1 class="aq-title">AI 错词复习卷</h1>
          <p class="aq-subtitle">从错词本出题 · cloze / 选择 / 英译中 · 本地判分</p>
        </div>
        <button type="button" class="aq-link-btn" @click="router.push('/words')">回单词</button>
      </div>

      <!-- 选词 -->
      <div v-if="phase === 'pick' || phase === 'loading'" class="aq-card">
        <template v-if="!candidates.length">
          <p class="aq-muted">错词本还是空的。先去练习，打错的词会自动进来。</p>
          <BaseButton type="primary" class="mt-3" @click="router.push('/words')">去练习</BaseButton>
        </template>
        <template v-else>
          <div class="aq-toolbar">
            <span class="aq-muted">最多 20 个 · 已选 {{ selected.size }}</span>
            <div class="aq-toolbar-actions">
              <button type="button" class="aq-text-btn" :disabled="loading" @click="selectAll">全选</button>
              <button type="button" class="aq-text-btn" :disabled="loading" @click="clearAll">清空</button>
            </div>
          </div>
          <ul class="aq-word-list">
            <li v-for="w in candidates" :key="w.word">
              <label class="aq-word-item">
                <input
                  type="checkbox"
                  :disabled="loading"
                  :checked="selected.has(w.word.toLowerCase())"
                  @change="toggleWord(w.word)"
                />
                <span class="aq-word">{{ w.word }}</span>
                <span v-if="w.cn" class="aq-cn">{{ w.cn }}</span>
              </label>
            </li>
          </ul>
          <p v-if="errorMsg" class="aq-error">{{ errorMsg }}</p>
          <p v-if="notConfigured" class="aq-muted">
            AI 功能暂不可用
          </p>
          <BaseButton
            type="primary"
            class="mt-3"
            :loading="loading"
            :disabled="loading || selected.size === 0"
            @click="generate"
          >
            {{ loading ? '生成中…' : '生成复习卷' }}
          </BaseButton>
        </template>
      </div>

      <!-- 答题 -->
      <div v-else-if="phase === 'quiz' && current" class="aq-card">
        <div class="aq-progress">{{ progressText }} · {{ current.type }}</div>
        <p class="aq-stem">{{ current.stem }}</p>
        <p class="aq-muted">目标词：{{ current.word }}</p>

        <div v-if="current.type === 'choice'" class="aq-options">
          <button
            v-for="opt in current.options"
            :key="opt"
            type="button"
            class="aq-option"
            :class="{
              picked: choicePicked === opt,
              correct: answered && opt.trim().toLowerCase() === current.answer.trim().toLowerCase(),
              wrong: answered && choicePicked === opt && opt.trim().toLowerCase() !== current.answer.trim().toLowerCase(),
            }"
            :disabled="answered"
            @click="submitAnswer(opt)"
          >
            {{ opt }}
          </button>
        </div>
        <div v-else class="aq-input-row">
          <input
            v-model="userInput"
            class="aq-input"
            type="text"
            :placeholder="current.type === 'en2zh' ? '输入中文释义' : '填入英文单词'"
            :disabled="answered"
            @keydown.enter.prevent="submitAnswer()"
          />
          <BaseButton
            v-if="!answered"
            type="primary"
            :disabled="!userInput.trim()"
            @click="submitAnswer()"
          >
            提交
          </BaseButton>
        </div>

        <div v-if="answered" class="aq-feedback" :class="lastCorrect ? 'ok' : 'bad'">
          <p class="aq-feedback-title">{{ lastCorrect ? '答对了' : '不对' }}</p>
          <p v-if="!lastCorrect" class="aq-muted">答案：{{ current.answer }}</p>
          <p class="aq-explain">{{ current.explain }}</p>
          <BaseButton type="primary" class="mt-3" @click="nextQuestion">
            {{ qIndex + 1 >= questions.length ? '看结果' : '下一题' }}
          </BaseButton>
        </div>
      </div>

      <!-- 结果 -->
      <div v-else-if="phase === 'done'" class="aq-card aq-center">
        <p class="aq-title">本卷结束</p>
        <p class="aq-score">{{ correctCount }} / {{ questions.length }}</p>
        <div class="aq-done-actions">
          <BaseButton type="primary" @click="again">再来一组</BaseButton>
          <BaseButton type="info" @click="router.push('/words')">回单词</BaseButton>
        </div>
      </div>
    </div>
  </BasePage>
</template>

<style scoped lang="scss">
.aq-container {
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px 36px;
  word-break: break-word;
}
.aq-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.aq-header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.aq-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-main-text);
}
.aq-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--color-sub-text);
}
.aq-card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-item-border);
  border-radius: 12px;
  padding: 16px;
}
.aq-center {
  text-align: center;
}
.aq-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.aq-toolbar-actions {
  display: flex;
  gap: 12px;
}
.aq-word-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 50vh;
  overflow: auto;
}
.aq-word-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 4px 0;
  cursor: pointer;
}
.aq-word {
  font-weight: 600;
}
.aq-cn {
  color: var(--color-sub-text);
  font-size: 13px;
}
.aq-muted {
  color: var(--color-sub-text);
  font-size: 14px;
  margin: 8px 0;
}
.aq-error {
  color: #c0392b;
  font-size: 14px;
  margin: 8px 0;
}
.aq-text-btn,
.aq-link-btn {
  background: transparent;
  border: none;
  color: var(--color-link);
  cursor: pointer;
  font-size: 14px;
  min-height: 44px;
  padding: 0 4px;
}
.aq-progress {
  font-size: 13px;
  color: var(--color-sub-text);
  margin-bottom: 8px;
}
.aq-stem {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  line-height: 1.5;
}
.aq-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.aq-option {
  min-height: 44px;
  text-align: left;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--color-item-border);
  background: var(--color-second);
  color: var(--color-main-text);
  cursor: pointer;
  &.picked {
    border-color: var(--color-select-bg);
  }
  &.correct {
    background: rgba(46, 204, 113, 0.15);
    border-color: #27ae60;
  }
  &.wrong {
    background: rgba(231, 76, 60, 0.12);
    border-color: #c0392b;
  }
  &:disabled {
    cursor: default;
  }
}
.aq-input-row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}
.aq-input {
  flex: 1;
  min-height: 44px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--color-item-border);
  background: var(--color-second);
  color: var(--color-main-text);
  font-size: 16px;
}
.aq-feedback {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-item-border);
  &.ok .aq-feedback-title {
    color: #27ae60;
  }
  &.bad .aq-feedback-title {
    color: #c0392b;
  }
}
.aq-feedback-title {
  font-weight: 700;
  margin: 0 0 6px;
}
.aq-explain {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.5;
}
.aq-score {
  font-size: 36px;
  font-weight: 700;
  margin: 12px 0 20px;
}
.aq-done-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
