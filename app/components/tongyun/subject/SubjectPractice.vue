<script setup lang="ts">
// tongyun: 学科练习：出题 → 交卡（敲字 / 选择 / 自评）→ 讲解 → 1/3/7/14/30 间隔
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import SelfGradePanel from '@/components/tongyun/SelfGradePanel.vue'
import {
  INTERVALS,
  applySelfAssessment,
  buildSubjectSession,
  getKnowledgePoint,
  getSubject,
  getSubjectStats,
  gradeCard,
  isCodeQuestion,
  isSelfQuestion,
  loadBank,
  recordSubjectResult,
  saveSubjectStat,
  type ActiveSubject,
  type Card,
  type GradeResult,
  type QuestionBank,
  type SelfAssessment,
  type SubjectItemStat,
} from '@/tongyun/subject'

const props = defineProps<{
  subject: string
}>()

const emit = defineEmits<{
  (e: 'exit'): void
  (e: 'switch-subject', subject: ActiveSubject): void
}>()

const ready = ref(false)
const loading = ref(true)
const bank = ref<QuestionBank>({ subject: '', version: '', points: [], items: [] })
const items = ref<Card[]>([])
const index = ref(0)
const statsMap = ref<Record<string, SubjectItemStat>>({})

const typed = ref('')
const chosen = ref('')
const selfGrade = ref<SelfAssessment | null>(null)
const answered = ref(false)
const gradeResult = ref<GradeResult | null>(null)
const lastSavedStat = ref<SubjectItemStat | null>(null)
const inputRef = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)

const correctCount = ref(0)
const totalAnswered = ref(0)

const current = computed(() => items.value[index.value] || null)
const total = computed(() => items.value.length)
const finished = computed(() => ready.value && !loading.value && (total.value === 0 || index.value >= total.value))
const point = computed(() => (current.value ? getKnowledgePoint(bank.value, current.value.point_id) : undefined))
const isCode = computed(() => (current.value ? isCodeQuestion(current.value) : false))
const isChoice = computed(() => current.value?.type === 'choice')
const isSelf = computed(() => (current.value ? isSelfQuestion(current.value.type) : false))
const isCorrect = computed(() => gradeResult.value === 'correct' || gradeResult.value === 'self')

const subjectTitle = computed(() => {
  try {
    return getSubject(props.subject).title
  } catch {
    const s = (bank.value.subject || props.subject || '').toLowerCase()
    if (s === 'ai') return 'AI'
    if (s === 'java') return 'Java'
    return props.subject || '学科'
  }
})

const typeLabel = computed(() => {
  if (!current.value) return ''
  const t = current.value.type
  if (t === 'code') return '编码题'
  if (t === 'concept') return '概念题'
  if (t === 'choice') return '选择题'
  if (t === 'oral') return '口述题'
  if (t === 'project') return '项目题'
  return '术语题'
})

const intervalHint = computed(() => {
  if (!lastSavedStat.value || !gradeResult.value) return ''
  if (gradeResult.value === 'wrong') return '答错已重置：1 天后复习'
  if (gradeResult.value === 'self') {
    const days = INTERVALS[lastSavedStat.value.box] ?? 1
    return `自评已记：下次约 ${days} 天后`
  }
  return `下次复习：${INTERVALS[lastSavedStat.value.box]} 天后`
})

function focusInput() {
  nextTick(() => {
    inputRef.value?.focus()
  })
}

function openCard() {
  typed.value = ''
  chosen.value = ''
  selfGrade.value = null
  answered.value = false
  gradeResult.value = null
  lastSavedStat.value = null
  if (!isChoice.value && !isSelf.value) focusInput()
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
    if (items.value.length) openCard()
  } finally {
    loading.value = false
  }
}

function persistAuto(item: Card, correct: boolean, now = Date.now()) {
  const saved = recordSubjectResult(props.subject, item.id, correct, now)
  lastSavedStat.value = saved
  statsMap.value[item.id] = saved
  return saved
}

function persistSelf(item: Card, assessment: SelfAssessment, now = Date.now()) {
  const prev = statsMap.value[item.id]
  const scheduled = applySelfAssessment(assessment, {
    box: prev?.box ?? 0,
    intervals: INTERVALS,
    now,
  })
  const saved: SubjectItemStat = {
    right: (prev?.right ?? 0) + (assessment === 'self_ok' ? 1 : 0),
    wrong: (prev?.wrong ?? 0) + (assessment === 'self_fail' ? 1 : 0),
    last: now,
    box: scheduled.box,
    due: scheduled.due,
    first: prev?.first || now,
  }
  saveSubjectStat(props.subject, item.id, saved)
  lastSavedStat.value = saved
  statsMap.value[item.id] = saved
  return saved
}

function finishAnswer(result: GradeResult, assessment?: SelfAssessment) {
  gradeResult.value = result
  answered.value = true
  totalAnswered.value += 1
  if (result === 'correct') correctCount.value += 1
  if (result === 'self' && assessment && assessment !== 'self_fail') correctCount.value += 1
}

/** 敲字题交卡 */
function submitTyped() {
  if (answered.value || !current.value || isChoice.value || isSelf.value) return
  const t = typed.value.trim()
  if (!t) return
  const item = current.value
  const result = gradeCard(item, typed.value)
  if (result === 'self') {
    // 不应出现在敲字路径
    return
  }
  finishAnswer(result)
  persistAuto(item, result === 'correct')
}

/** 选择题点选项即交卡 */
function submitChoice(option: string) {
  if (answered.value || !current.value || !isChoice.value) return
  chosen.value = option
  typed.value = option
  const item = current.value
  const result = gradeCard(item, option)
  finishAnswer(result === 'self' ? 'wrong' : result)
  persistAuto(item, result === 'correct')
}

/** oral / project：选完自评三档才落库 */
function onSelfAssess(assessment: SelfAssessment) {
  if (answered.value || !current.value || !isSelf.value) return
  selfGrade.value = assessment
  const item = current.value
  persistSelf(item, assessment)
  finishAnswer('self', assessment)
}

function submit() {
  if (isChoice.value || isSelf.value) return
  submitTyped()
}

function next() {
  if (!answered.value) return
  index.value += 1
  if (index.value < items.value.length) openCard()
}

function onInputKey(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    if (isCode.value && event.shiftKey) return
    event.preventDefault()
    if (answered.value) next()
    else submitTyped()
  }
}

function onWindowKey(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (!answered.value || finished.value) return
  if (event.key === ' ' || event.key === 'Enter') {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      if (event.key === ' ') return
    }
    event.preventDefault()
    next()
  }
}

watch(() => props.subject, () => { load() })

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
          <span>{{ subjectTitle }} · 练习</span>
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

        <h1 class="prompt" data-testid="subject-prompt">{{ current.prompt }}</h1>

        <!-- choice：选项交卡 -->
        <div v-if="isChoice" class="choice-box" data-testid="subject-choice">
          <button
            v-for="(opt, i) in current.options || []"
            :key="i"
            type="button"
            class="yy-btn choice-btn"
            :class="{ on: chosen === opt, ok: answered && opt === current.answer, bad: answered && chosen === opt && opt !== current.answer }"
            :data-testid="`subject-choice-${i}`"
            :disabled="answered"
            @click="submitChoice(opt)"
          >
            {{ opt }}
          </button>
        </div>

        <!-- oral / project：自评面板 -->
        <div v-else-if="isSelf" class="self-box" data-testid="subject-self">
          <SelfGradePanel
            :card="current"
            :model-value="selfGrade"
            @update:model-value="onSelfAssess"
          />
        </div>

        <!-- 敲字 -->
        <div v-else class="typing-box">
          <label class="typebox" :class="{ ok: answered && gradeResult === 'correct', bad: answered && gradeResult === 'wrong' }">
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
              @click="submitTyped"
            >
              交卡
            </button>
          </div>
        </div>

        <!-- 讲解（自评也出讲解 + 间隔） -->
        <div v-if="answered" class="explain-card" data-testid="subject-explain-card">
          <div
            class="result-banner"
            :class="{
              correct: gradeResult === 'correct' || gradeResult === 'self',
              wrong: gradeResult === 'wrong',
            }"
          >
            <span class="result-icon">{{ gradeResult === 'wrong' ? '✕' : '✓' }}</span>
            <span class="result-text" data-testid="subject-result">
              <template v-if="gradeResult === 'self'">自评已记录</template>
              <template v-else-if="gradeResult === 'correct'">回答正确！</template>
              <template v-else>回答有误</template>
            </span>
            <span v-if="lastSavedStat" class="interval-badge" data-testid="subject-interval">
              {{ intervalHint }}
            </span>
          </div>

          <div v-if="!isSelf" class="answer-row">
            <span class="label">标准答案：</span>
            <code class="ans-code" data-testid="subject-answer">{{ current.answer }}</code>
          </div>

          <div v-if="gradeResult === 'wrong'" class="typed-row">
            <span class="label">你的输入：</span>
            <span class="user-typed" data-testid="subject-user-typed">{{ typed || chosen }}</span>
          </div>

          <div v-if="current.explain" class="explain-body">
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

.choice-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 16px 0;
}

.choice-btn.on {
  outline: 2px solid var(--yy-matcha-deep, #6b8f4e);
}

.choice-btn.ok {
  background: color-mix(in srgb, var(--yy-matcha, #a4c48c) 35%, transparent);
}

.choice-btn.bad {
  background: color-mix(in srgb, #e07070 25%, transparent);
}

.self-box {
  margin: 16px 0;
}

</style>
