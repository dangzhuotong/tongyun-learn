<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { withAppBaseURL } from '@/core/utils/base-url'
import { getLearnConfig } from '@/tongyun/learn-client'
import { freshAttempt, isResolved, submitAttempt, type AttemptState } from '@/tongyun/english/attempt'
import { buildTypeEvent, expectedOf, fetchToday, postTypeEvent } from '@/tongyun/english/client'
import { gradePrefsOf, gradeTyped, markLetters } from '@/tongyun/english/grade'
import { getEnglishPrefs, type EnglishPrefs } from '@/tongyun/english/prefs'
import type { PracticeStep, TodayQueue, TypeEventBody } from '@/tongyun/english/types'
import { buildLocalQueue } from '@/tongyun/english/local-queue'
import { splitPhonetics, advanceProgress, getLevel, loadWordlist, recordResult } from '@/tongyun/english/wordlist'

definePageMeta({
  layout: 'yunya',
})

useSeoMeta({
  title: '橦云学习',
})

const router = useRouter()
const markSrc = withAppBaseURL('/yunya-mark.svg')
const ready = ref(false)
const hasToken = ref(false)
const loading = ref(false)
const error = ref('')
const queue = ref<TodayQueue | null>(null)
// tongyun: 本地词书模式下敲击只本地判分，不上报学习服务
const localMode = ref(false)
const index = ref(0)
const attempt = ref<AttemptState>(freshAttempt())
const prefs = ref<EnglishPrefs>(getEnglishPrefs())
const busy = ref(false)
const saveError = ref('')
const pending = ref<TypeEventBody | null>(null)
const elapsedMs = ref(0)
const wordInput = ref<HTMLInputElement | null>(null)
const sentenceInput = ref<HTMLTextAreaElement | null>(null)

let cardStarted = 0
let sessionStarted = 0
let timer = 0
let alive = true
let confirming = false

const step = computed(() => queue.value?.items[index.value] || null)
const total = computed(() => queue.value?.items.length ?? 0)
const finished = computed(() => Boolean(queue.value) && index.value >= total.value && total.value > 0)
const gradePrefs = computed(() => gradePrefsOf(prefs.value))
const expected = computed(() => (step.value ? expectedOf(step.value) : ''))
const matched = computed(() =>
  step.value ? gradeTyped(attempt.value.typed, expected.value, step.value.stage, gradePrefs.value) : false
)
const letters = computed(() => (step.value?.stage === 'A' ? markLetters(step.value.word, attempt.value.typed, gradePrefs.value) : []))
const resolved = computed(() => isResolved(attempt.value))
const locked = computed(() => resolved.value || busy.value)

const sentencePos = computed(() => {
  const items = queue.value?.items || []
  let n = 0
  let k = 0
  items.forEach((item, i) => {
    if (item.stage !== 'B') return
    n += 1
    if (i === index.value) k = n
  })
  return { k, n }
})

const progressPct = computed(() => {
  if (!total.value) return 0
  return Math.round(((index.value + (finished.value ? 0 : 1)) / total.value) * 100)
})

const unitTitle = computed(() => step.value?.unitTitle || queue.value?.unitTitle || '英语')

const hint = computed(() => {
  if (saveError.value) return saveError.value
  if (busy.value) return '正在记下…'
  if (attempt.value.hint) return attempt.value.hint
  if (step.value?.stage === 'B') return '请完成整个句子'
  if (matched.value) return '敲完按空格'
  return '敲完按空格'
})

const clock = computed(() => {
  const seconds = Math.max(0, Math.floor(elapsedMs.value / 1000))
  const minutes = Math.floor(seconds / 60)
  if (minutes <= 0) return `${seconds}秒`
  return `${minutes}分钟`
})

function resetCard() {
  attempt.value = freshAttempt()
  pending.value = null
  saveError.value = ''
  cardStarted = Date.now()
}

async function load() {
  loading.value = true
  error.value = ''
  // tongyun: 没令牌不请求；today 404/报错/空时静默回退本地词书
  const res = hasToken.value ? await fetchToday() : null
  if (!alive) return
  if (res && res.ok && res.data && res.data.items.length) {
    queue.value = res.data
    localMode.value = false
  } else {
    queue.value = await buildLocalQueue()
    if (!alive) return
    localMode.value = true
  }
  loading.value = false
  index.value = 0
  resetCard()
  sessionStarted = Date.now()
  openCard()
}

function focusField() {
  return nextTick(() => {
    const el = step.value?.stage === 'B' ? sentenceInput.value : wordInput.value
    el?.focus()
  })
}

function openCard() {
  focusField()
  // tongyun: 主动回忆卡先不读音，免得泄露答案
  if (step.value?.stage === 'A' && step.value.word && !step.value.recall) speak(step.value)
}

function onWordInput(event: Event) {
  if (locked.value || !step.value) return
  const raw = (event.target as HTMLInputElement).value
  const allowSpace = step.value.word.includes(' ')
  attempt.value = {
    ...attempt.value,
    typed: raw.replace(allowSpace ? /[^A-Za-z'’ \-]/g : /[^A-Za-z'’-]/g, ''),
  }
}

function onSentenceInput(event: Event) {
  if (locked.value) return
  attempt.value = { ...attempt.value, typed: (event.target as HTMLTextAreaElement).value }
}

async function confirm() {
  if (!step.value || busy.value || confirming) return
  confirming = true
  try {
    if (resolved.value) {
      await advance()
      return
    }
    const next = submitAttempt(attempt.value, expected.value, step.value.stage, gradePrefs.value)
    if (next === attempt.value) return
    attempt.value = next
    // tongyun: 主动回忆卡交卡后停在揭示页（音标/例句），再按空格进入敲句
    if (step.value.stage === 'A' && step.value.recall) {
      if (isResolved(next)) speak(step.value)
      return
    }
    if (next.phase === 'done' && step.value.stage === 'A') await advance()
  } finally {
    confirming = false
  }
}

function onWordKey(event: KeyboardEvent) {
  if (event.repeat) return
  if (event.key !== ' ' && event.key !== 'Enter') return
  if (event.key === ' ' && step.value?.word.includes(' ')) return
  event.preventDefault()
  confirm()
}

function onSentenceKey(event: KeyboardEvent) {
  if (event.repeat) return
  if (event.key === 'Enter' || (resolved.value && event.key === ' ')) {
    event.preventDefault()
    confirm()
  }
}

function onWindowKey(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (!step.value || finished.value) return
  if (resolved.value && (event.key === ' ' || event.key === 'Enter')) {
    event.preventDefault()
    confirm()
  }
}

async function advance() {
  if (!step.value || busy.value) return
  if (!isResolved(attempt.value)) return
  busy.value = true
  saveError.value = ''
  try {
    if (localMode.value) {
      // tongyun: 本地记录对错次数/稳定度；敲完词算学过，游标线性前进
      const cur = step.value
      if (cur.stage === 'A') {
        recordResult(cur.word, attempt.value.correct && !attempt.value.usedCorrection)
        const lv = getLevel()
        if (cur.unitTitle.startsWith(`L${lv}`)) advanceProgress(lv, cur.word, await loadWordlist())
      }
      index.value += 1
      if (index.value < (queue.value?.items.length || 0)) {
        resetCard()
        openCard()
      }
      return
    }
    if (!pending.value) {
      const built = buildTypeEvent(step.value, attempt.value, Date.now() - cardStarted)
      if (!built) {
        saveError.value = '这一项没有 card_id，记不进去。'
        return
      }
      pending.value = built
    }
    const res = await postTypeEvent(pending.value)
    if (!alive) return
    if (!res.ok) {
      saveError.value = res.message || '没记上，再按一次空格。'
      return
    }
    pending.value = null
    index.value += 1
    if (index.value < (queue.value?.items.length || 0)) {
      resetCard()
      openCard()
    }
  } finally {
    if (alive) busy.value = false
  }
}

let audio: HTMLAudioElement | null = null

function speak(current: PracticeStep) {
  const text = current.stage === 'B' ? current.sentence : current.word
  if (!text) return
  const url = current.audioUrl || `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(current.word || text)}&type=2`
  if (audio) audio.pause()
  const el = new Audio(url)
  audio = el
  el.play().catch(() => {
    if (typeof speechSynthesis === 'undefined') return
    const utter = new SpeechSynthesisUtterance(text)
    utter.lang = 'en-US'
    speechSynthesis.cancel()
    speechSynthesis.speak(utter)
  })
}

onMounted(() => {
  alive = true
  ready.value = true
  prefs.value = getEnglishPrefs()
  hasToken.value = Boolean(getLearnConfig().token)
  sessionStarted = Date.now()
  timer = window.setInterval(() => {
    elapsedMs.value = Date.now() - sessionStarted
  }, 500)
  window.addEventListener('keydown', onWindowKey)
  load()
})

onUnmounted(() => {
  alive = false
  window.clearInterval(timer)
  window.removeEventListener('keydown', onWindowKey)
  if (audio) audio.pause()
})
</script>

<template>
  <section class="screen">
    <div v-if="!ready || loading" class="yy-card wait">正在准备今天的词…</div>

    <div v-else-if="error" class="yy-card wait">
      <p>{{ error }}</p>
      <div class="actions">
        <button type="button" class="yy-btn ghost" @click="load">重试</button>
      </div>
    </div>

    <div v-else-if="queue && !queue.items.length" class="yy-card wait">
      <p>今天的队列是空的。</p>
      <button type="button" class="yy-btn" @click="router.push('/')">回到今日</button>
    </div>

    <div v-else-if="finished" class="yy-card wait done">
      <p class="done-title">这一轮敲完了</p>
      <p v-if="localMode">这一轮练完了，对错已记在这台浏览器。</p>
      <p v-else>这一轮敲完了，记录已保存。</p>
      <button v-if="localMode" type="button" class="yy-btn" @click="load">再来一轮</button>
      <div class="actions">
        <button type="button" class="yy-btn ghost" @click="router.push('/coach')">看教练</button>
        <button type="button" class="yy-btn" @click="router.push('/')">回到今日</button>
      </div>
    </div>

    <template v-else-if="step">
      <header class="top">
        <button type="button" class="back" @click="router.push('/')">
          <span aria-hidden="true">←</span>
          返回
        </button>
        <div v-if="step.stage === 'A'" class="progress">
          <div class="frac">{{ index + 1 }} / {{ total }}</div>
          <div class="bar" aria-hidden="true"><span :style="{ width: progressPct + '%' }" /></div>
        </div>
        <div v-else class="sentence-label">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="currentColor"
              d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v16.2a2.8 2.8 0 0 0-2.2-.7H7.2A2.2 2.2 0 0 0 5 19.7V4.5Zm2.2 14h9.6c.4 0 .8.1 1.2.2V4H7.5A.5.5 0 0 0 7 4.5v12.6c.4-.1.8-.1 1.2-.1.3 0 .7 0 1 .1Z"
            />
          </svg>
          <span>{{ unitTitle }} · 例句 {{ sentencePos.k }}/{{ sentencePos.n }}</span>
        </div>
        <div v-if="step.stage === 'A'" class="unit">
          <img :src="markSrc" alt="" />
          <span>{{ unitTitle }}</span>
        </div>
        <div v-else class="progress side">
          <div class="frac quiet">进度 {{ index + 1 }}/{{ total }}</div>
          <div class="bar" aria-hidden="true"><span :style="{ width: progressPct + '%' }" /></div>
        </div>
      </header>

      <div v-if="step.stage === 'A' && step.recall" class="word-stage recall" data-testid="recall-card">
        <div class="chips">
          <span v-if="step.tag" class="chip" data-testid="recall-tag">{{ step.tag }}</span>
          <span v-if="step.tone" class="chip tone" data-testid="recall-tone">{{ step.tone }}</span>
        </div>
        <h1 class="recall-meaning" data-testid="recall-meaning" @click="focusField">{{ step.meaning }}</h1>
        <p class="recall-ask">用英文怎么说？</p>
        <label class="typebox" :class="{ bad: attempt.failures > 0 && !matched, ok: resolved && matched }">
          <input
            ref="wordInput"
            data-testid="word-input"
            :value="attempt.typed"
            :readonly="locked"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
            :placeholder="attempt.typed ? '' : '拼出英文，按回车交卡'"
            aria-label="拼出这个英文"
            @input="onWordInput"
            @keydown="onWordKey"
          />
        </label>
        <p class="hint" data-testid="practice-hint">{{ resolved ? (attempt.correct ? '答对了。按空格继续敲例句' : '记下了，答案在下面。按空格继续敲例句') : attempt.hint || '拼完按回车交卡' }}</p>
        <div v-if="resolved" class="reveal" data-testid="recall-reveal">
          <p class="reveal-word">{{ step.word }}</p>
          <p v-if="step.phonetic" class="phonetic" data-testid="recall-phonetic">
            <span v-for="(ph, i) in splitPhonetics(step.phonetic)" :key="i" class="ph">{{ ph }}</span>
            <button type="button" class="speaker" aria-label="播放发音" @click="speak(step)">🔊</button>
          </p>
          <p v-if="step.phoneticNote" class="ph-note" data-testid="recall-phonetic-note">{{ step.phoneticNote }}</p>
          <ul v-if="step.examples.length" class="examples">
            <li v-for="(example, i) in step.examples" :key="i">
              <p class="en" style="white-space: pre-line">{{ example.en }}</p>
              <p v-if="example.zh" class="zh">{{ example.zh }}</p>
            </li>
          </ul>
        </div>
      </div>

      <div v-else-if="step.stage === 'A'" class="word-stage">
        <h1 class="word" @click="focusField">
          <span v-for="(mark, i) in letters" :key="i" :class="mark">{{ [...step.word][i] }}</span>
        </h1>
        <p v-if="prefs.showPhonetic && step.phonetic" class="phonetic">
          {{ step.phonetic }}
          <button type="button" class="speaker" aria-label="播放发音" @click="speak(step)">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="currentColor"
                d="M4 9v6h4l5 4V5L8 9H4zm11.5 3a3.5 3.5 0 0 0-1.8-3.06v6.12A3.5 3.5 0 0 0 15.5 12zM13.7 5.1v1.7a6 6 0 0 1 0 10.4v1.7a7.8 7.8 0 0 0 0-13.8z"
              />
            </svg>
          </button>
        </p>
        <p v-else-if="step.word" class="phonetic solo">
          <button type="button" class="speaker" aria-label="播放发音" @click="speak(step)">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="currentColor"
                d="M4 9v6h4l5 4V5L8 9H4zm11.5 3a3.5 3.5 0 0 0-1.8-3.06v6.12A3.5 3.5 0 0 0 15.5 12z"
              />
            </svg>
          </button>
        </p>
        <p v-if="prefs.showChinese && step.meaning" class="meaning">{{ step.meaning }}</p>
        <label class="typebox" :class="{ bad: attempt.failures > 0 && !matched, ok: matched }">
          <input
            ref="wordInput"
            data-testid="word-input"
            :value="attempt.typed"
            :readonly="locked"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
            :placeholder="matched || !attempt.typed ? '敲完按空格' : ''"
            aria-label="手敲这个词"
            @input="onWordInput"
            @keydown="onWordKey"
          />
        </label>
        <p class="hint" data-testid="practice-hint">{{ hint }}</p>
        <ul v-if="step.examples.length" class="examples">
          <li v-for="(example, i) in step.examples" :key="i">
            <p class="en">{{ example.en }}</p>
            <p v-if="prefs.showChinese && example.zh" class="zh">{{ example.zh }}</p>
          </li>
        </ul>
      </div>

      <div v-else class="sentence-stage">
        <article class="yy-card sentence-card">
          <p class="kicker">中文提示</p>
          <h1 class="prompt">{{ step.promptZh || '听完后敲出整句' }}</h1>
          <p v-if="step.word" class="listen">
            <button type="button" @click="speak(step)">听英文</button>
          </p>
          <div class="divider" />
          <p class="kicker">输入英文例句</p>
          <label class="sentence-box" :class="{ ok: matched, bad: attempt.failures > 0 && !matched }">
            <textarea
              ref="sentenceInput"
              data-testid="sentence-input"
              rows="2"
              :value="attempt.typed"
              :readonly="locked"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              aria-label="手敲英文例句"
              @input="onSentenceInput"
              @keydown="onSentenceKey"
            />
            <span v-if="matched" class="check" aria-hidden="true">✓</span>
          </label>
          <p class="hint inline" data-testid="practice-hint">
            <span v-if="matched" class="mini-check">✓</span>
            {{ hint }}
          </p>
          <p v-if="resolved && !matched" class="answer">{{ expected }}</p>
          <button type="button" class="yy-btn continue" data-testid="continue" :disabled="busy" @click="confirm">
            继续
          </button>
        </article>
      </div>

      <footer class="foot">
        <span class="time">时间 {{ clock }}</span>
        <div v-if="total <= 12" class="dots" aria-hidden="true">
          <i v-for="n in total" :key="n" :class="{ on: n - 1 < index, now: n - 1 === index }" />
        </div>
      </footer>

      <svg class="cloud" viewBox="0 0 200 80" aria-hidden="true">
        <path
          fill="#e7d8c4"
          d="M46 62c-18 0-30-12-30-26 0-12 9-22 21-23 5-14 18-23 34-23 12 0 22 6 28 15 6-10 16-16 28-16 18 0 32 14 32 30 10 3 18 12 18 23 0 14-12 20-26 20H46z"
        />
      </svg>
      <svg class="leaf" viewBox="0 0 80 140" aria-hidden="true">
        <path fill="#d5e3cc" d="M42 128c0-48-28-62-18-104 26 18 48 34 36 86-6 16-12 22-18 18z" />
        <path fill="none" stroke="#b7cba8" stroke-width="2" d="M40 126c4-36 8-62 16-92" />
      </svg>
    </template>
  </section>
</template>

<style scoped lang="scss">
.recall .chips { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-bottom: 10px; }
.recall .chip { font-size: 12px; padding: 3px 10px; border-radius: 999px; background: rgba(164, 196, 140, 0.2); color: var(--yy-matcha-deep, #5d7a48); }
.recall .chip.tone { background: rgba(253, 200, 156, 0.35); color: #9a5b2a; }
.recall-meaning { font-size: 30px; font-weight: 650; text-align: center; margin: 6px 0; line-height: 1.4; }
.recall-ask { text-align: center; color: var(--yy-ink-soft); margin: 0 0 12px; }
.reveal { margin-top: 14px; text-align: center; }
.reveal .ph { margin: 0 6px; }
.ph-note { font-size: 12px; color: var(--yy-ink-soft); margin: 2px 0 8px; }
.reveal-word { font-size: 34px; font-weight: 700; margin: 0; letter-spacing: 0.02em; }

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

.wait p,
.done-title {
  margin: 0;
  font-size: 18px;
  line-height: 1.6;
}

.done-title {
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
.unit,
.sentence-label {
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

.sentence-label {
  justify-self: start;
  color: #8c6b45;
  font-weight: 650;
}

.sentence-label svg {
  width: 22px;
  height: 22px;
}

.progress {
  min-width: 180px;
  text-align: center;
}

.progress.side {
  justify-self: end;
  min-width: 160px;
}

.frac {
  color: var(--yy-matcha);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.frac.quiet {
  color: var(--yy-ink-soft);
  font-weight: 600;
  letter-spacing: 0;
  font-size: 14px;
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

.word-stage,
.sentence-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 16px 12px;
  position: relative;
  z-index: 1;
}

.word {
  margin: 8px 0 0;
  font-family: 'Iowan Old Style', Palatino, 'Palatino Linotype', 'Songti SC', Georgia, serif;
  font-size: clamp(64px, 9vw, 112px);
  font-weight: 560;
  line-height: 1.05;
  letter-spacing: -0.03em;
  color: var(--yy-matcha);
  cursor: text;
}

.word span.bad {
  color: var(--yy-danger);
}

.word span.next {
  box-shadow: inset 0 -3px 0 var(--yy-matcha);
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

.meaning {
  color: var(--yy-matcha);
  font-size: 18px;
}

.speaker,
.listen button {
  border: 0;
  background: transparent;
  color: var(--yy-matcha);
  cursor: pointer;
  padding: 4px;
}

.speaker svg {
  width: 18px;
  height: 18px;
  display: block;
}

.typebox {
  margin-top: 28px;
  width: min(440px, 100%);
  background: var(--yy-card-warm);
  border-radius: 16px;
  border: 1px solid transparent;
}

.typebox.bad {
  background: var(--yy-danger-soft);
}

.typebox.ok {
  background: var(--yy-matcha-soft);
}

.typebox input {
  width: 100%;
  box-sizing: border-box;
  min-height: 64px;
  border: 0;
  background: transparent;
  text-align: center;
  font-size: 20px;
  color: var(--yy-ink);
  outline: none;
}

.typebox input::placeholder {
  color: #b3a89a;
}

.hint {
  min-height: 1.4em;
  margin: 12px 0 0;
  color: var(--yy-ink-soft);
  font-size: 14px;
}

.examples {
  list-style: none;
  margin: 28px 0 0;
  padding: 0;
  width: min(640px, 100%);
}

.examples li {
  padding: 12px 0 12px 18px;
  border-top: 1px solid rgba(228, 217, 200, 0.9);
  position: relative;
}

.examples li::before {
  content: '';
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #8eae78;
  position: absolute;
  left: 0;
  top: 18px;
}

.examples .en,
.examples .zh {
  margin: 0;
}

.examples .en {
  color: #4e463e;
}

.examples .zh {
  margin-top: 4px;
  color: var(--yy-ink-soft);
  font-size: 14px;
}

.sentence-card {
  width: min(760px, 100%);
  padding: 28px 32px 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.kicker {
  margin: 0;
  color: #a89478;
  font-size: 14px;
}

.prompt {
  margin: 12px 0 0;
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 650;
  letter-spacing: 0.04em;
}

.listen {
  margin: 8px 0 0;
}

.divider {
  width: 100%;
  height: 1px;
  margin: 22px 0 16px;
  background: var(--yy-line);
}

.sentence-box {
  width: 100%;
  margin-top: 12px;
  background: var(--yy-card-warm);
  border-radius: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px 8px 18px;
  box-sizing: border-box;
}

.sentence-box.ok {
  background: #f4f7f1;
}

.sentence-box.bad {
  background: var(--yy-danger-soft);
}

.sentence-box textarea {
  flex: 1;
  border: 0;
  resize: none;
  background: transparent;
  min-height: 72px;
  font-size: 26px;
  font-weight: 650;
  color: #2c261f;
  outline: none;
  text-align: left;
  line-height: 1.45;
}

.check,
.mini-check {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--yy-matcha);
  color: white;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.mini-check {
  width: 18px;
  height: 18px;
  font-size: 12px;
  margin-right: 6px;
}

.hint.inline {
  display: inline-flex;
  align-items: center;
  color: var(--yy-matcha-deep);
}

.answer {
  margin: 4px 0 0;
  color: var(--yy-ink-soft);
}

.continue {
  margin-top: 18px;
  min-width: 148px;
  background: #f3ebdd;
  color: #8d7b68;
}

.continue:hover:not(:disabled) {
  background: #e7dccb;
}

.continue:disabled {
  opacity: 0.7;
}

.foot {
  margin-top: auto;
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 8px 8px;
  color: var(--yy-matcha-deep);
}

.time {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.dots {
  display: flex;
  gap: 8px;
}

.dots i {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #ddd4c6;
  display: block;
}

.dots i.on,
.dots i.now {
  background: #7ea37a;
}

.dots i.now {
  background: var(--yy-matcha-deep);
  transform: scale(1.12);
}

.cloud,
.leaf {
  position: absolute;
  pointer-events: none;
  z-index: 0;
}

.cloud {
  width: 220px;
  left: -20px;
  bottom: 36px;
  opacity: 0.85;
}

.leaf {
  width: 90px;
  right: 12px;
  bottom: 28px;
  opacity: 0.9;
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
  .unit,
  .sentence-label,
  .progress.side {
    justify-self: center;
  }

  .sentence-card {
    padding: 22px 16px;
  }

  .sentence-box textarea {
    font-size: 20px;
  }

  .cloud,
  .leaf {
    display: none;
  }
}
</style>
