<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { withAppBaseURL } from '@/core/utils/base-url'
import { gradePrefsOf, gradeTyped } from '@/tongyun/english/grade'
import { getEnglishPrefs } from '@/tongyun/english/prefs'
import { recordAnswer, type AnswerMode } from '@/tongyun/english/records'
import { hintText, randomHint, type HintMask } from '@/tongyun/english/hint'
import { typeableSentence } from '@/tongyun/english/local-queue'
import { buildMeaningChoices, buildSession, buildWordChoices, handleChoiceTransition, resolveChoice, resolveSpell, type StudyItem } from '@/tongyun/english/study'
import {
  getOptionalLevels,
  getStats,
  loadWordlist,
  relearnStat,
  saveStat,
  splitPhonetics,
  teachStat,
  toneOf,
  type WordEntry,
} from '@/tongyun/english/wordlist'
import SubjectPractice from '@/components/tongyun/subject/SubjectPractice.vue'
import { getActiveSubject, setActiveSubject, type ActiveSubject } from '@/tongyun/subject'
import {
  formatEndScreenSummary,
  getWeekTrainedDaysCount,
  recordTrainingDay,
} from '@/tongyun/curriculum'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '学习 · 橦云学习',
})

const router = useRouter()
const route = useRoute()
const markSrc = withAppBaseURL('/yunya-mark.svg')

const activeSubject = ref<ActiveSubject>('english')

function syncSubjectFromUrl() {
  const querySub = ((route.query.subject as string) || '').toLowerCase()
  if (querySub === 'java' || querySub === 'ai' || querySub === 'english') {
    activeSubject.value = querySub as ActiveSubject
    setActiveSubject(querySub as ActiveSubject)
  } else {
    activeSubject.value = getActiveSubject()
  }
}

function setSubject(sub: ActiveSubject) {
  activeSubject.value = sub
  setActiveSubject(sub)
  router.replace({ query: { ...route.query, subject: sub } })
}

const ready = ref(false)
const loading = ref(true)
const list = ref<WordEntry[]>([])
const items = ref<StudyItem[]>([])
const index = ref(0)
const prefs = ref(getEnglishPrefs())
const gradePrefs = computed(() => gradePrefsOf(prefs.value))

const wordInput = ref<HTMLInputElement | null>(null)
const sentenceInput = ref<HTMLTextAreaElement | null>(null)
const spellInput = ref<HTMLInputElement | null>(null)

// 当前卡片状态
const typed = ref('')
const chosen = ref('')
const choiceResult = ref<'idle' | 'correct' | 'wrong'>('idle')
const wrongCount = ref(0)
const hintMask = ref<HintMask | null>(null)
const hintShown = ref(false)
const answered = ref(false)
const feedback = ref('')
const options = ref<string[]>([])
const teachWord = ref('')
const teachSentence = ref('')

const sessionDueTotal = ref(0)
const sessionReviewedTotal = ref(0)
const weekDays = ref(1)

const endScreenText = computed(() =>
  formatEndScreenSummary(sessionDueTotal.value, sessionReviewedTotal.value, weekDays.value)
)

const item = computed(() => items.value[index.value] || null)
const total = computed(() => items.value.length)
const finished = computed(() => ready.value && !loading.value && index.value >= total.value)
const mode = computed<AnswerMode>(() => item.value?.mode || 'teach')
const entry = computed(() => item.value?.word || null)
const meaning = computed(() => entry.value?.meaning || '')
const answer = computed(() => entry.value?.word || '')
const exampleText = computed(() => (entry.value ? typeableSentence(entry.value.example) : ''))
const tone = computed(() => (entry.value ? toneOf(entry.value) : ''))
const hintDisplay = computed(() => (entry.value && hintMask.value ? hintText(entry.value.word, hintMask.value) : ''))
const spellMode = computed(() => (mode.value === 'spell' || mode.value === 'hint_spell'))
const modeLabel = computed(() => {
  if (mode.value === 'teach') return item.value?.reason === 'relearn' ? '重教' : '新词·先教'
  if (mode.value === 'choice') return '第 1 次复习·选'
  return '拼写'
})
const canTeach = computed(
  () => teachWord.value.trim().length > 0 && (!exampleText.value || teachSentence.value.trim().length > 0)
)
const hintsHint = computed(() => (hintMask.value ? `提示：${hintDisplay.value}（${hintMask.value.letters} 个字母）` : ''))

function speak(text: string) {
  if (!text || typeof speechSynthesis === 'undefined') return
  try {
    speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    utter.lang = 'en-US'
    speechSynthesis.speak(utter)
  } catch {}
}

function focusSpell() {
  nextTick(() => spellInput.value?.focus())
}

function focusWord() {
  nextTick(() => wordInput.value?.focus())
}

function openCard() {
  const current = item.value
  if (!current) return
  typed.value = ''
  chosen.value = ''
  choiceResult.value = 'idle'
  wrongCount.value = 0
  hintMask.value = null
  hintShown.value = false
  answered.value = false
  feedback.value = ''
  options.value = []
  teachWord.value = ''
  teachSentence.value = ''
  const w = current.word
  if (current.mode === 'teach') {
    focusWord()
    speak(w.word)
    return
  }
  if (current.mode === 'choice') {
    if (current.variant === 'audio2zh') {
      options.value = buildMeaningChoices(w, list.value)
      speak(w.word)
    } else {
      options.value = buildWordChoices(w, list.value)
    }
    return
  }
  if (current.mode === 'hint_spell') {
    hintMask.value = randomHint(w.word)
    hintShown.value = true
  }
  focusSpell()
}

function next() {
  index.value += 1
  if (index.value < items.value.length) {
    openCard()
  } else {
    recordTrainingDay()
    weekDays.value = getWeekTrainedDaysCount()
  }
}

async function load() {
  loading.value = true
  list.value = await loadWordlist()
  const plan = buildSession(list.value, getStats(), getOptionalLevels())
  items.value = plan.items
  sessionDueTotal.value = plan.dueTotal
  sessionReviewedTotal.value = 0
  weekDays.value = getWeekTrainedDaysCount()
  index.value = 0
  loading.value = false
  ready.value = true
  if (items.value.length) openCard()
}

async function restart() {
  await load()
}

// ---- 教学 ----
function finishTeach() {
  const w = entry.value
  if (!w || !canTeach.value) return
  const now = Date.now()
  const stats = getStats()
  const stat = stats[w.word] ? relearnStat(stats[w.word]!, now) : teachStat(w.word, now)
  saveStat(w.word, stat)
  recordAnswer(w.word, 'teach', true, now)
  next()
}

function onTeachKey(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  event.preventDefault()
  if (mode.value === 'teach' && document.activeElement === wordInput.value && exampleText.value) {
    sentenceInput.value?.focus()
    return
  }
  finishTeach()
}

// ---- 选择 ----
function choose(option: string) {
  if (choiceResult.value !== 'idle' || !entry.value) return
  const w = entry.value
  const correctOption = item.value?.variant === 'audio2zh' ? w.meaning : w.word
  chosen.value = option
  const correct = option === correctOption
  choiceResult.value = correct ? 'correct' : 'wrong'
  sessionReviewedTotal.value += 1
  const now = Date.now()
  recordAnswer(w.word, 'choice', correct, now)
  if (!correct) {
    const prev = getStats()[w.word] || teachStat(w.word, now)
    const { stat } = resolveChoice(prev, false, now)
    saveStat(w.word, stat)
  }
}

function continueChoice() {
  if (choiceResult.value === 'idle') return
  const w = entry.value
  if (w && choiceResult.value === 'wrong') {
    handleChoiceTransition(items.value, index.value, w, false)
  }
  next()
}

// ---- 拼写 ----
function spellAnswerMode(): AnswerMode {
  if (mode.value === 'hint_spell') return 'hint_spell'
  return hintShown.value ? 'hint_spell' : 'spell'
}

function submitSpell() {
  const w = entry.value
  if (!w || answered.value || !typed.value.trim()) return
  const now = Date.now()
  const correct = gradeTyped(typed.value, w.word, 'A', gradePrefs.value)
  if (correct) {
    recordAnswer(w.word, spellAnswerMode(), true, now)
    const prev = getStats()[w.word] || teachStat(w.word, now)
    const { stat } = resolveSpell(prev, true, 0, now)
    saveStat(w.word, stat)
    sessionReviewedTotal.value += 1
    answered.value = true
    feedback.value = '答对了'
    return
  }
  recordAnswer(w.word, spellAnswerMode(), false, now)
  wrongCount.value += 1
  if (wrongCount.value < 2) {
    typed.value = ''
    hintMask.value = randomHint(w.word)
    hintShown.value = true
    feedback.value = mode.value === 'spell' && wrongCount.value === 1
      ? '第一次错，给个提示，再试一次'
      : '还是不对，提示更新了，再试一次'
    focusSpell()
    return
  }
  const prev = getStats()[w.word] || teachStat(w.word, now)
  const { stat } = resolveSpell(prev, false, 1, now)
  saveStat(w.word, stat)
  sessionReviewedTotal.value += 1
  const reteach: StudyItem = { id: `teach-${w.word}`, word: w, mode: 'teach', reason: 'relearn', reviewIndex: 0 }
  items.value.splice(index.value + 1, 0, reteach)
  feedback.value = '再错一次了，重新教一遍'
  next()
}

function continueSpell() {
  if (answered.value) next()
}

function onSpellKey(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  event.preventDefault()
  if (answered.value) continueSpell()
  else submitSpell()
}

function onWindowKey(event: KeyboardEvent) {
  if (activeSubject.value !== 'english') return
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (!item.value || finished.value) return
  if (event.key !== ' ' && event.key !== 'Enter') return
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
  if (mode.value === 'choice' && choiceResult.value !== 'idle') {
    event.preventDefault()
    continueChoice()
    return
  }
  if (spellMode.value && answered.value) {
    event.preventDefault()
    continueSpell()
  }
}

watch(
  () => route.query.subject,
  () => {
    syncSubjectFromUrl()
    if (activeSubject.value === 'english') {
      load()
    }
  }
)

onMounted(() => {
  syncSubjectFromUrl()
  prefs.value = getEnglishPrefs()
  ready.value = true
  window.addEventListener('keydown', onWindowKey)
  if (activeSubject.value === 'english') {
    load()
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onWindowKey)
  if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel()
})
</script>

<template>
  <div class="practice-container">
    <div class="subject-bar" data-testid="subject-switcher">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeSubject === 'english' }"
        data-testid="subject-tab-english"
        @click="setSubject('english')"
      >
        英语
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeSubject === 'java' }"
        data-testid="subject-tab-java"
        @click="setSubject('java')"
      >
        Java
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeSubject === 'ai' }"
        data-testid="subject-tab-ai"
        @click="setSubject('ai')"
      >
        AI
      </button>
    </div>

    <SubjectPractice
      v-if="activeSubject === 'java' || activeSubject === 'ai'"
      :subject="activeSubject"
      @exit="router.push('/')"
      @switch-subject="setSubject"
    />

    <section v-else class="screen">
    <div v-if="!ready || loading" class="yy-card wait">正在准备今天的词…</div>

    <div v-else-if="!items.length" class="yy-card wait">
      <p>今天的词都学完了，明天再来。</p>
      <button type="button" class="yy-btn" @click="router.push('/')">回到今日</button>
    </div>

    <div v-else-if="finished" class="yy-card wait done" data-testid="practice-end-screen">
      <p class="done-title">这一轮学完了</p>
      <p class="end-summary" data-testid="end-summary">{{ endScreenText }}</p>
      <p>对错和进度已记在这台浏览器。</p>
      <div class="actions">
        <button type="button" class="yy-btn" data-testid="restart" @click="restart">再学一轮</button>
        <button type="button" class="yy-btn ghost" @click="router.push('/')">回到今日</button>
      </div>
    </div>

    <template v-else-if="item">
      <header class="top">
        <button type="button" class="back" @click="router.push('/')">
          <span aria-hidden="true">←</span>
          返回
        </button>
        <div class="progress">
          <div class="frac">{{ index + 1 }} / {{ total }}</div>
          <div class="bar" aria-hidden="true"><span :style="{ width: ((index + 1) / total) * 100 + '%' }" /></div>
        </div>
        <div class="unit">
          <img :src="markSrc" alt="" />
          <span>{{ modeLabel }}</span>
        </div>
      </header>

      <!-- 新词先教 -->
      <div v-if="mode === 'teach'" class="stage teach" data-testid="teach-card">
        <div class="chips">
          <span v-if="entry?.tag" class="chip">{{ entry.tag }}</span>
          <span v-if="tone" class="chip tone" data-testid="teach-register">{{ tone }}</span>
        </div>
        <h1 class="word">{{ answer }}</h1>
        <p v-if="entry?.phonetic" class="phonetic">
          <span v-for="(ph, i) in splitPhonetics(entry.phonetic)" :key="i" class="ph">{{ ph }}</span>
          <button type="button" class="speaker" aria-label="重播发音" data-testid="replay" @click="speak(answer)">🔊</button>
        </p>
        <p v-if="entry?.phonetic_note" class="ph-note">{{ entry.phonetic_note }}</p>
        <p class="meaning">{{ meaning }}</p>
        <div v-if="entry?.example" class="example">
          <p class="en" style="white-space: pre-line">{{ entry.example }}</p>
          <p v-if="entry?.example_zh" class="zh">{{ entry.example_zh }}</p>
        </div>

        <div class="typing">
          <p class="kicker">照着敲一遍这个词</p>
          <label class="typebox">
            <input
              ref="wordInput"
              data-testid="teach-word-input"
              v-model="teachWord"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              aria-label="照着敲这个词"
              @keydown="onTeachKey"
            />
          </label>
          <template v-if="exampleText">
            <p class="kicker">照着敲一遍例句</p>
            <label class="typebox">
              <textarea
                ref="sentenceInput"
                data-testid="teach-sentence-input"
                v-model="teachSentence"
                rows="2"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                aria-label="照着敲例句"
                @keydown="onTeachKey"
              />
            </label>
          </template>
          <p class="hint">不判对错，照着敲完就行。</p>
          <button type="button" class="yy-btn" data-testid="teach-continue" :disabled="!canTeach" @click="finishTeach">
            继续
          </button>
        </div>
      </div>

      <!-- 第 1 次复习：选择 -->
      <div v-else-if="mode === 'choice'" class="stage choice" data-testid="choice-card">
        <template v-if="item.variant === 'audio2zh'">
          <p class="kicker">听发音，选中文</p>
          <button type="button" class="big-speaker" aria-label="播放发音" @click="speak(answer)">🔊 再听一次</button>
        </template>
        <template v-else>
          <p class="kicker">看中文，选英文</p>
          <h1 class="prompt" data-testid="choice-prompt">{{ meaning }}</h1>
        </template>
        <ul class="options">
          <li v-for="option in options" :key="option">
            <button
              type="button"
              class="option"
              :class="{
                correct: choiceResult !== 'idle' && option === (item.variant === 'audio2zh' ? meaning : answer),
                wrong: choiceResult === 'wrong' && option === chosen,
              }"
              :disabled="choiceResult !== 'idle'"
              @click="choose(option)"
            >
              {{ option }}
            </button>
          </li>
        </ul>
        <p v-if="choiceResult !== 'idle'" class="hint" data-testid="choice-feedback">
          {{ choiceResult === 'correct' ? '答对了。' : `答案是 ${item.variant === 'audio2zh' ? meaning : answer}` }}
        </p>
        <button
          v-if="choiceResult !== 'idle'"
          type="button"
          class="yy-btn"
          data-testid="choice-continue"
          @click="continueChoice"
        >
          继续
        </button>
      </div>

      <!-- 拼写（hint_spell / spell） -->
      <div v-else class="stage spell" data-testid="spell-card">
        <p class="kicker">看中文，拼英文</p>
        <h1 class="prompt" data-testid="spell-prompt">{{ meaning }}</h1>
        <p v-if="hintShown" class="hint-mask" data-testid="spell-hint">{{ hintsHint }}</p>
        <label class="typebox" :class="{ ok: answered }">
          <input
            ref="spellInput"
            data-testid="spell-input"
            v-model="typed"
            :readonly="answered"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
            :placeholder="answered ? '' : '拼出英文，按回车交卡'"
            aria-label="拼出这个英文"
            @keydown="onSpellKey"
          />
        </label>
        <p class="hint" data-testid="spell-feedback">
          <template v-if="answered">答对了：{{ answer }}</template>
          <template v-else>{{ feedback || '敲完按回车' }}</template>
        </p>
        <button v-if="answered" type="button" class="yy-btn" data-testid="spell-continue" @click="continueSpell">
          继续
        </button>
        <button v-else type="button" class="yy-btn ghost" data-testid="spell-submit" :disabled="!typed.trim()" @click="submitSpell">
          交卡
        </button>
      </div>

      <footer class="foot">
        <span class="time">可以随时点返回停下</span>
      </footer>
    </template>
  </section>
  </div>
</template>

<style scoped lang="scss">
.practice-container {
  display: flex;
  flex-direction: column;
}

.subject-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 20px 4px;

  .tab-btn {
    border: none;
    background: var(--yy-bg-deep);
    color: var(--yy-ink-soft);
    padding: 6px 18px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
      background: var(--yy-card-warm);
      color: var(--yy-ink);
    }

    &.active {
      background: var(--yy-matcha-deep);
      color: #fff;
      font-weight: 650;
    }
  }
}

.screen {
  position: relative;
  min-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wait {
  margin: 48px auto;
  padding: 32px 28px;
  max-width: 520px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16px;
  box-sizing: border-box;
}

.wait p {
  margin: 0;
  font-size: 18px;
  line-height: 1.6;
}

.done-title {
  margin: 0;
  font-size: 28px;
  font-weight: 650;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.top {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 8px 8px 0;
}

.back,
.unit {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--yy-ink-soft);
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 15px;
}

.back {
  justify-self: start;
  min-height: 40px;
  padding: 0 12px 0 4px;
  border-radius: 999px;
}

.back:hover {
  background: rgba(255, 252, 247, 0.7);
}

.unit {
  justify-self: end;
  color: var(--yy-matcha-deep);
}

.unit img {
  width: 22px;
  height: 22px;
  border-radius: 6px;
}

.progress {
  min-width: 180px;
  text-align: center;
}

.frac {
  color: var(--yy-matcha);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.bar {
  margin-top: 6px;
  height: 6px;
  border-radius: 999px;
  background: #e5d9c8;
  overflow: hidden;
}

.bar span {
  display: block;
  height: 100%;
  background: #8eae78;
}

.stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 16px 12px;
  position: relative;
  z-index: 1;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 10px;
}

.chip {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(164, 196, 140, 0.2);
  color: var(--yy-matcha-deep, #5d7a48);
}

.chip.tone {
  background: rgba(253, 200, 156, 0.35);
  color: #9a5b2a;
}

.word {
  margin: 8px 0 0;
  font-family: 'Iowan Old Style', Palatino, 'Palatino Linotype', 'Songti SC', Georgia, serif;
  font-size: clamp(52px, 8vw, 92px);
  font-weight: 560;
  line-height: 1.05;
  letter-spacing: -0.03em;
  color: var(--yy-matcha);
}

.prompt {
  margin: 12px 0 0;
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 650;
  text-align: center;
  letter-spacing: 0.04em;
}

.phonetic,
.meaning {
  margin: 10px 0 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.phonetic {
  color: var(--yy-ink-soft);
  font-size: 18px;
}

.ph {
  margin: 0 4px;
}

.meaning {
  color: var(--yy-matcha);
  font-size: 18px;
}

.ph-note {
  font-size: 12px;
  color: var(--yy-ink-soft);
  margin: 2px 0 0;
}

.speaker,
.big-speaker {
  border: 0;
  background: transparent;
  color: var(--yy-matcha);
  cursor: pointer;
  padding: 4px;
}

.big-speaker {
  font-size: 18px;
  margin-top: 12px;
  padding: 10px 18px;
  border-radius: 999px;
  background: var(--yy-matcha-soft);
}

.example {
  margin-top: 20px;
  width: min(640px, 100%);
  text-align: center;
  padding-top: 14px;
  border-top: 1px solid rgba(228, 217, 200, 0.9);
}

.example .en {
  margin: 0;
  color: #4e463e;
  font-size: 18px;
  line-height: 1.6;
}

.example .zh {
  margin: 6px 0 0;
  color: var(--yy-ink-soft);
  font-size: 14px;
}

.typing {
  margin-top: 26px;
  width: min(520px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.kicker {
  margin: 12px 0 0;
  color: #a89478;
  font-size: 14px;
}

.typebox {
  width: min(440px, 100%);
  background: var(--yy-card-warm);
  border-radius: 16px;
  border: 1px solid transparent;
  padding: 0 12px;
  box-sizing: border-box;
}

.typebox.ok {
  background: var(--yy-matcha-soft);
}

.typebox input,
.typebox textarea {
  width: 100%;
  box-sizing: border-box;
  min-height: 56px;
  border: 0;
  background: transparent;
  text-align: center;
  font-size: 20px;
  color: var(--yy-ink);
  outline: none;
}

.typebox textarea {
  min-height: 84px;
  padding-top: 12px;
  resize: none;
  line-height: 1.5;
}

.typebox input::placeholder {
  color: #b3a89a;
}

.hint {
  min-height: 1.4em;
  margin: 4px 0 0;
  color: var(--yy-ink-soft);
  font-size: 14px;
}

.hint-mask {
  margin: 10px 0 0;
  font-size: 22px;
  letter-spacing: 0.18em;
  color: var(--yy-matcha-deep);
  font-family: 'Iowan Old Style', Palatino, Georgia, serif;
}

.options {
  list-style: none;
  margin: 22px 0 0;
  padding: 0;
  width: min(520px, 100%);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.option {
  width: 100%;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid var(--yy-line);
  background: var(--yy-card);
  color: var(--yy-ink);
  font-size: 18px;
  cursor: pointer;
  text-align: left;
}

.option:hover:not(:disabled) {
  border-color: var(--yy-matcha);
}

.option.correct {
  background: var(--yy-matcha-soft);
  border-color: var(--yy-matcha);
  color: var(--yy-matcha-deep);
}

.option.wrong {
  background: var(--yy-danger-soft);
  border-color: var(--yy-danger);
  color: var(--yy-danger);
}

.option:disabled {
  cursor: default;
}

.foot {
  margin-top: auto;
  position: relative;
  z-index: 1;
  padding: 14px 8px 8px;
  color: var(--yy-matcha-deep);
}

.time {
  font-size: 14px;
}

@media (max-width: 760px) {
  .screen {
    min-height: calc(100vh - 150px);
  }

  .top {
    grid-template-columns: 1fr;
    justify-items: center;
  }

  .back,
  .unit {
    justify-self: center;
  }

  .typebox textarea {
    font-size: 18px;
  }
}
</style>
