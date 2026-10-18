// tongyun: 阿学英语学习流（本地，不依赖学习服务）。
// 新词先教 → 次日第 1 次复习（选择 + 带提示拼写）→ 第 2 次起纯拼写；
// 拼错一次给随机提示，再错重教、该词从第 1 步重来。间隔 1/3/7/14/30。
import type { AnswerMode } from './records'
import {
  DAY,
  INTERVALS,
  countIntroducedToday,
  getOptionalLevels,
  getStats,
  orderedLevels,
  remainingNewBudget,
  type WordEntry,
  type WordStat,
} from './wordlist'

export type { AnswerMode }
export type StudyReason = 'new' | 'review' | 'relearn'
export type ChoiceVariant = 'zh2en' | 'audio2zh'

export interface StudyItem {
  id: string
  word: WordEntry
  mode: AnswerMode
  reason: StudyReason
  /** 该词第几次复习：0 = 首次（次日），1 = 第二次，依此类推 */
  reviewIndex: number
  /** choice 卡片的两种变体之一 */
  variant?: ChoiceVariant
}

export interface SessionPlan {
  items: StudyItem[]
  dueTotal: number
  newTotal: number
}

/** 从词表里挑出当前该教的新词：按级别顺序、跳过已教过的，最多 budget 个。 */
export function pickNewWords(
  list: WordEntry[],
  stats: Record<string, WordStat>,
  optional: number[],
  budget: number
): WordEntry[] {
  if (budget <= 0) return []
  const picked: WordEntry[] = []
  for (const level of orderedLevels(optional)) {
    const lvl = list.filter(w => w.level === level)
    for (const w of lvl) {
      if (picked.length >= budget) return picked
      if (!stats[w.word]) picked.push(w)
    }
  }
  return picked
}

function dueEntries(
  list: WordEntry[],
  stats: Record<string, WordStat>,
  now: number
): { word: WordEntry; stat: WordStat }[] {
  const byWord = new Map(list.map(w => [w.word, w]))
  const out: { word: WordEntry; stat: WordStat }[] = []
  for (const [word, stat] of Object.entries(stats)) {
    const entry = byWord.get(word)
    if (!entry) continue
    if (stat.due <= now) out.push({ word: entry, stat })
  }
  out.sort((a, b) => a.stat.due - b.stat.due)
  return out
}

/**
 * 组装本轮队列：先排到期复习（到期早的在前），再按每日额度补新词。
 * 队列不设上限，随时可停。
 */
export function buildSession(
  list: WordEntry[],
  stats: Record<string, WordStat> = getStats(),
  optional: number[] = getOptionalLevels(),
  now = Date.now(),
  rng: () => number = Math.random
): SessionPlan {
  const items: StudyItem[] = []
  let dueTotal = 0

  for (const { word, stat } of dueEntries(list, stats, now)) {
    if (!stat.taught) {
      items.push({ id: `teach-${word.word}`, word, mode: 'teach', reason: 'relearn', reviewIndex: 0 })
      continue
    }
    dueTotal += 1
    if (stat.box <= 0) {
      items.push({
        id: `choice-${word.word}`,
        word,
        mode: 'choice',
        reason: 'review',
        reviewIndex: 0,
        variant: rng() < 0.5 ? 'zh2en' : 'audio2zh',
      })
      items.push({ id: `hint-${word.word}`, word, mode: 'hint_spell', reason: 'review', reviewIndex: 0 })
    } else {
      items.push({ id: `spell-${word.word}`, word, mode: 'spell', reason: 'review', reviewIndex: stat.box })
    }
  }

  const introduced = countIntroducedToday(stats, now)
  const budget = remainingNewBudget(dueTotal, introduced)
  const fresh = pickNewWords(list, stats, optional, budget)
  for (const word of fresh) {
    items.push({ id: `teach-${word.word}`, word, mode: 'teach', reason: 'new', reviewIndex: 0 })
  }

  return { items, dueTotal, newTotal: fresh.length }
}

// ---- 选择卡片的选项 ----

function shuffle<T>(arr: T[], rng: () => number): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[out[i], out[j]] = [out[j]!, out[i]!]
  }
  return out
}

function pickOptions(target: WordEntry, source: WordEntry[], field: (w: WordEntry) => string, rng: () => number): string[] {
  const used = new Set([field(target)])
  const options: string[] = []
  const pool = source.slice()
  while (options.length < 3 && pool.length) {
    const i = Math.floor(rng() * pool.length)
    const w = pool.splice(i, 1)[0]!
    const value = field(w)
    if (!value || used.has(value)) continue
    used.add(value)
    options.push(value)
  }
  return shuffle([field(target), ...options], rng)
}

/** 看中文选英文：正确答案 + 3 个同级别干扰项，不足时用其他级别补。 */
export function buildWordChoices(target: WordEntry, pool: WordEntry[], rng: () => number = Math.random): string[] {
  const same = pool.filter(w => w.word !== target.word && w.level === target.level)
  const rest = pool.filter(w => w.word !== target.word && w.level !== target.level)
  const source = same.length >= 3 ? same : [...same, ...rest]
  return pickOptions(target, source, w => w.word, rng)
}

/** 听音选中文：正确答案 + 3 个同级别干扰项。 */
export function buildMeaningChoices(target: WordEntry, pool: WordEntry[], rng: () => number = Math.random): string[] {
  const same = pool.filter(w => w.word !== target.word && w.level === target.level && w.meaning)
  const rest = pool.filter(w => w.word !== target.word && w.level !== target.level && w.meaning)
  const source = same.length >= 3 ? same : [...same, ...rest]
  return pickOptions(target, source, w => w.meaning, rng)
}

// ---- 复盘结果 ----

export interface SpellResolution {
  stat: WordStat
  action: 'advance' | 'hint' | 'reteach'
}

/**
 * 拼写（spell / hint_spell）的结果处理。
 * - 答对：升到下一档，间隔按 1/3/7/14/30。
 * - 第一次错：给提示重来（不改排课）。
 * - 再错（wrongCount >= 1 表示这是第 2 次错）：重教，词从第 1 步重来。
 */
export function resolveSpell(prev: WordStat, correct: boolean, wrongCount: number, now = Date.now()): SpellResolution {
  if (correct) {
    const box = prev.last ? Math.min(INTERVALS.length - 1, prev.box + 1) : 0
    return {
      stat: {
        ...prev,
        right: prev.right + 1,
        last: now,
        box,
        due: now + INTERVALS[box]! * DAY,
        first: prev.first || now,
        taught: true,
      },
      action: 'advance',
    }
  }
  if (wrongCount < 1) return { stat: prev, action: 'hint' }
  return {
    stat: { ...prev, wrong: prev.wrong + 1, last: now, box: 0, due: now, first: prev.first || now, taught: false },
    action: 'reteach',
  }
}
