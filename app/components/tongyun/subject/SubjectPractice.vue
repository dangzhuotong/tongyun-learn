<script setup lang="ts">
// tongyun: Java / AI 学科敲字练习组件：出题 → 敲答案 → 讲解 → 复用 1/3/7/14/30 天复习
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  DAY,
  INTERVALS,
  buildSubjectSession,
  getKnowledgePoint,
  getSubjectStats,
  gradeAnswer,
  isCodeQuestion,
  loadBank,
  recordSubjectResult,
  type Card,
  type QuestionBank,
  type SubjectItemStat,
} from '@/tongyun/subject'

const props = defineProps<{
  subject: string
}>()

const emit = defineEmits<{
  (e: 'exit'): void
  (e: 'switch-subject', subject: 'english' | 'java' | 'ai'): void
}>()

const ready = ref(false)
const loading = ref(true)
const bank = ref<QuestionBank>({ subject: '', version: '', points: [], items: [] })
const items = ref<Card[]>([])
const index = ref(0)
const statsMap = ref<Record<string, SubjectItemStat>>({})

// 当前题目状态
const typed = ref('')
const answered = ref(false)
const isCorrect = ref(false)
const lastSavedStat = ref<SubjectItemStat | null>(null)
const inputRef = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)

// 统计
const correctCount = ref(0)
const totalAnswered = ref(0)

const current = computed(() => items.value[index.value] || null)
const total = computed(() => items.value.length)
const finished = computed(() => ready.value && !loading.value && (total.value === 0 || index.value >= total.value))
const point = computed(() => (current.value ? getKnowledgePoint(bank.value, current.value.point_id) : undefined))
const isCode = computed(() => (current.value ? isCodeQuestion(current.value) : false))

const subjectTitle = computed(() => {
  const s = (bank.value.subject || props.subject || '').toLowerCase()
  if (s === 'ai') return 'AI'
  if (s === 'java') return 'Java'
  return props.subject || '学科'
})
const typeLabel = computed(() => {
  if (!current.value) return ''
  if (current.value.type === 'code') return '编码题'
  if (current.value.type === 'concept') return '概念题'
  return '术语题'
})

function focusInput() {
  nextTick(() => {
    inputRef.value?.focus()
  })
}

function openCard() {
  typed.value = ''
  answered.value = false
  isCorrect.value = false
  lastSavedStat.value = null
  focusInput()
}

async function load() {
  loading.value = true
  ready.value = false
  try {
    bank.value = await loadBank(props.subject)
    statsMap.value = getSubjectStats(props.subject)
    const session = buildSubjectSession(bank.value, statsMap.value, Date.now())
    items.value = session.items
    index.value = 0
    correctCount.value = 0
    totalAnswered.value = 0
    ready.value = true
    if (items.value.length) {
      openCard()
    }
  } finally {
    loading.value = false
  }
}

function submit() {
  if (answered.value || !current.value) return
  const t = typed.value.trim()
  if (!t) return

  const item = current.value
  const correct = gradeAnswer(typed.value, item)
  isCorrect.value = correct
  answered.value = true
  totalAnswered.value += 1
  if (correct) correctCount.value += 1

  const saved = recordSubjectResult(props.subject, item.id, correct, Date.now())
  lastSavedStat.value = saved
  statsMap.value[item.id] = saved
}

function next() {
  if (!answered.value) return
  index.value += 1
  if (index.value < items.value.length) {
    openCard()
  }
}

function onInputKey(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    if (isCode.value && event.shiftKey) {
      // Shift+Enter 允许换行
      return
    }
    event.preventDefault()
    if (answered.value) {
      next()
    } else {
      submit()
    }
  }
}

function onWindowKey(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (!answered.value || finished.value) return
  if (event.key === ' ' || event.key === 'Enter') {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      if (event.key === ' ') return // 输入框内空格不跳题
    }
    event.preventDefault()
    next()
  }
}

watch(
  () => props.subject,
  () => {
    load()
  }
)

onMounted(() => {
  window.addEventListener('keydown', onWindowKey)
  load()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onWindowKey)
})
</script>

<template>
  <div class="subject-practice">
    <div v-if="!ready || loading" class="yy-card wait" data-testid="subject-loading">正在准备题目…</div>

    <div v-else-if="finished" class="yy-card wait done" data-testid="subject-done">
      <p class="done-title">这一轮学完了</p>
      <p class="summary-line">
        共完成 {{ totalAnswered }} 题 · 答对 {{ correctCount }} 题（正确率 {{ totalAnswered ? Math.round((correctCount / totalAnswered) * 100) : 0 }}%）
      </p>
      <p class="hint">复习间隔（1/3/7/14/30 天）已保存在当前浏览器。</p>
      <div class="actions">
        <button type="button" class="yy-btn" data-testid="restart" @click="load">再学一轮</button>
        <button type="button" class="yy-btn ghost" data-testid="exit-to-today" @click="emit('exit')">回到今日</button>
      </div>
    </div>

    <template v-else-if="current">
      <header class="top">
        <button type="button" class="back" data-testid="subject-back" @click="emit('exit')">
          <span aria-hidden="true">←</span>
          返回
        </button>
        <div class="progress">
          <div class="frac">{{ index + 1 }} / {{ total }}</div>
          <div class="bar" aria-hidden="true">
            <span :style="{ width: ((index + 1) / total) * 100 + '%' }" />
          </div>
        </div>
        <div class="unit">
          <span>{{ subjectTitle }} · 敲字练习</span>
        </div>
      </header>

      <div class="stage" data-testid="subject-card">
        <div class="chips">
          <span class="chip subject-tag">{{ subjectTitle }}</span>
          <span v-if="point" class="chip point-tag">{{ point.title }}</span>
          <span class="chip type-tag">{{ typeLabel }}</span>
          <span class="chip level-tag">L{{ current.level }}</span>
          <span v-for="tag in current.tags || []" :key="tag" class="chip">{{ tag }}</span>
        </div>

        <!-- 出题 -->
        <h1 class="prompt" data-testid="subject-prompt">{{ current.prompt }}</h1>

        <!-- 敲答案 -->
        <div class="typing-box">
          <label class="typebox" :class="{ ok: answered && isCorrect, bad: answered && !isCorrect }">
            <template v-if="isCode">
              <textarea
                ref="inputRef"
                v-model="typed"
                rows="2"
                class="code-input"
                data-testid="subject-input"
                :readonly="answered"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                :placeholder="answered ? '' : '敲入代码，按回车交卡（Shift+Enter 换行）'"
                aria-label="敲入代码答案"
                @keydown="onInputKey"
              />
            </template>
            <template v-else>
              <input
                ref="inputRef"
                v-model="typed"
                class="text-input"
                data-testid="subject-input"
                :readonly="answered"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                :placeholder="answered ? '' : '敲入答案，按回车交卡'"
                aria-label="敲入答案"
                @keydown="onInputKey"
              />
            </template>
          </label>

          <div v-if="!answered" class="action-bar">
            <span class="hint-tip">
              {{ isCode ? 'code 题忽略空格，直接敲核心逻辑' : '支持标准术语及别名' }}
            </span>
            <button
              type="button"
              class="yy-btn"
              data-testid="subject-submit"
              :disabled="!typed.trim()"
              @click="submit"
            >
              交卡
            </button>
          </div>
        </div>

        <!-- 讲解 -->
        <div v-if="answered" class="explain-card" data-testid="subject-explain-card">
          <div class="result-banner" :class="{ correct: isCorrect, wrong: !isCorrect }">
            <span class="result-icon">{{ isCorrect ? '✓' : '✕' }}</span>
            <span class="result-text" data-testid="subject-result">{{ isCorrect ? '回答正确！' : '回答有误' }}</span>
            <span v-if="lastSavedStat" class="interval-badge" data-testid="subject-interval">
              {{ isCorrect ? `下次复习：${INTERVALS[lastSavedStat.box]} 天后` : '答错已重置：1 天后复习' }}
            </span>
          </div>

          <div class="answer-row">
            <span class="label">标准答案：</span>
            <code class="ans-code" data-testid="subject-answer">{{ current.answer }}</code>
          </div>

          <div v-if="!isCorrect" class="typed-row">
            <span class="label">你的输入：</span>
            <span class="user-typed" data-testid="subject-user-typed">{{ typed }}</span>
          </div>

          <div class="explain-body">
            <p class="explain-title">讲解：</p>
            <p class="explain-text" data-testid="subject-explain">{{ current.explain }}</p>
          </div>

          <div class="continue-bar">
            <button type="button" class="yy-btn" data-testid="subject-continue" @click="next">
              下一题 (Enter)
            </button>
          </div>
        </div>
      </div>

      <footer class="foot">
        <span class="time">随时可点返回停下 · 复习进度实时保存</span>
      </footer>
    </template>
  </div>
</template>

<style scoped lang="scss">
.subject-practice {
  position: relative;
  min-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wait {
  margin: 48px auto;
  max-width: 520px;
  padding: 40px;
  text-align: center;
}

.done {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;

  .done-title {
    font-size: 28px;
    font-weight: 650;
    margin: 0;
  }

  .summary-line {
    font-size: 17px;
    color: var(--yy-matcha-deep);
    font-weight: 600;
    margin: 0;
  }

  .hint {
    color: var(--yy-ink-soft);
    font-size: 14px;
    margin: 0;
  }

  .actions {
    display: flex;
    gap: 12px;
    margin-top: 12px;
  }
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 28px;
  max-width: 860px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;

  .back {
    background: none;
    border: none;
    color: var(--yy-ink-soft);
    cursor: pointer;
    font-size: 14px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    border-radius: 6px;

    &:hover {
      background: var(--yy-bg-deep);
    }
  }

  .progress {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    max-width: 320px;

    .frac {
      font-size: 13px;
      color: var(--yy-ink-soft);
      white-space: nowrap;
    }

    .bar {
      flex: 1;
      height: 6px;
      background: var(--yy-bg-deep);
      border-radius: 999px;
      overflow: hidden;

      span {
        display: block;
        height: 100%;
        background: var(--yy-matcha);
        transition: width 0.2s ease;
      }
    }
  }

  .unit {
    font-size: 13px;
    color: var(--yy-ink-soft);
    font-weight: 600;
  }
}

.stage {
  max-width: 860px;
  margin: 0 auto;
  width: 100%;
  padding: 24px 28px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;

  .chip {
    font-size: 12px;
    padding: 2px 10px;
    border-radius: 999px;
    background: var(--yy-bg-deep);
    color: var(--yy-ink-soft);

    &.subject-tag {
      background: var(--yy-matcha-soft);
      color: var(--yy-matcha-deep);
      font-weight: 600;
    }

    &.point-tag {
      background: #fdf5ea;
      color: #9c6c2e;
    }

    &.type-tag {
      background: #f2eefa;
      color: #5c4491;
    }

    &.level-tag {
      background: #eef5fc;
      color: #2b6199;
    }
  }
}

.prompt {
  font-size: 24px;
  font-weight: 650;
  line-height: 1.45;
  margin: 0;
  color: var(--yy-ink);
}

.typing-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.typebox {
  display: block;
  background: var(--yy-card);
  border: 1.5px solid var(--yy-line);
  border-radius: 12px;
  padding: 12px 16px;
  transition: border-color 0.15s, box-shadow 0.15s;

  &:focus-within {
    border-color: var(--yy-matcha);
    box-shadow: 0 0 0 3px var(--yy-matcha-soft);
  }

  &.ok {
    border-color: var(--yy-matcha);
    background: #f4faf6;
  }

  &.bad {
    border-color: var(--yy-danger);
    background: var(--yy-danger-soft);
  }

  .text-input,
  .code-input {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    font-size: 18px;
    color: var(--yy-ink);
    box-sizing: border-box;
  }

  .code-input {
    font-family: 'Fira Code', 'Cascadia Code', Consolas, Monaco, monospace;
    resize: vertical;
    min-height: 52px;
    line-height: 1.5;
  }
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  .hint-tip {
    font-size: 13px;
    color: var(--yy-ink-soft);
  }
}

.explain-card {
  background: var(--yy-card);
  border: 1px solid var(--yy-line);
  border-radius: 14px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: var(--yy-shadow);

  .result-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 17px;
    font-weight: 650;

    &.correct {
      color: var(--yy-matcha-deep);
    }

    &.wrong {
      color: var(--yy-danger);
    }

    .interval-badge {
      margin-left: auto;
      font-size: 13px;
      font-weight: normal;
      background: var(--yy-bg);
      padding: 3px 10px;
      border-radius: 999px;
      color: var(--yy-ink-soft);
    }
  }

  .answer-row,
  .typed-row {
    font-size: 15px;
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;

    .label {
      color: var(--yy-ink-soft);
      font-weight: 600;
    }

    .ans-code {
      font-family: 'Fira Code', Consolas, monospace;
      background: var(--yy-bg-deep);
      padding: 2px 8px;
      border-radius: 6px;
      color: var(--yy-ink);
      font-size: 15px;
    }

    .user-typed {
      color: var(--yy-danger);
    }
  }

  .explain-body {
    background: var(--yy-bg);
    border-radius: 8px;
    padding: 12px 16px;

    .explain-title {
      font-weight: 650;
      font-size: 14px;
      margin: 0 0 6px;
      color: var(--yy-ink);
    }

    .explain-text {
      margin: 0;
      font-size: 14px;
      line-height: 1.6;
      color: var(--yy-ink);
    }
  }

  .continue-bar {
    display: flex;
    justify-content: flex-end;
    margin-top: 4px;
  }
}

.foot {
  margin-top: auto;
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--yy-ink-soft);
}
</style>
