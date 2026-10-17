// tongyun: 阿学定制的英语词表（L1–L5）+ 本地复习记录。完全不依赖学习服务。
// 许可：en-ngsl.json 为 NGSL/NAWL 派生（CC BY-SA 4.0），en-tongyun.json 为自编，分文件存放。
import { withAppBaseURL } from '@/core/utils/base-url'

export interface WordEntry {
  word: string
  phonetic: string
  meaning: string
  example: string
  example_zh?: string
  tag: string
  level: number
  point_id?: string
  source: string
}

export const LEVELS: { level: number; title: string }[] = [
  { level: 1, title: 'L1 基础通用' },
  { level: 2, title: 'L2 技术文档' },
  { level: 3, title: 'L3 AI / Agent' },
  { level: 4, title: 'L4 面试口语' },
  { level: 5, title: 'L5 README / PR' },
]

export const WORDLIST_FILES = ['/wordlists/en-ngsl.json', '/wordlists/en-tongyun.json']
export const NGSL_ATTRIBUTION =
  'L1 词条取自 NGSL / NAWL 1.2（Browne, Culligan & Phillips），CC BY-SA 4.0，已筛选修改；其余词表与例句为橦云自编。'

let cache: WordEntry[] | null = null

export async function loadWordlist(): Promise<WordEntry[]> {
  if (cache) return cache
  const all: WordEntry[] = []
  for (const file of WORDLIST_FILES) {
    try {
      const res = await fetch(withAppBaseURL(file))
      if (!res.ok) continue
      const data = await res.json()
      if (Array.isArray(data?.words)) all.push(...data.words)
    } catch {}
  }
  all.sort((a, b) => a.level - b.level)
  if (all.length) cache = all
  return all
}

// ---- 本地记录（localStorage） ----
export interface WordStat {
  right: number
  wrong: number
  last: number
  /** 0–5：答对 +1，答错清零 */
  stability: number
}

const STATS_KEY = 'tongyun-en-stats-v1'
const PROGRESS_KEY = 'tongyun-en-progress-v1'
const LEVEL_KEY = 'tongyun-en-level-v1'

function readJson<T>(key: string, fallback: T): T {
  try {
    if (typeof localStorage === 'undefined') return fallback
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

export function getStats(): Record<string, WordStat> {
  return readJson(STATS_KEY, {})
}

export function recordResult(word: string, correct: boolean, now = Date.now()): WordStat {
  const stats = getStats()
  const cur = stats[word] || { right: 0, wrong: 0, last: 0, stability: 0 }
  const next: WordStat = correct
    ? { ...cur, right: cur.right + 1, last: now, stability: Math.min(5, cur.stability + 1) }
    : { ...cur, wrong: cur.wrong + 1, last: now, stability: 0 }
  stats[word] = next
  writeJson(STATS_KEY, stats)
  return next
}

/** 每级一个游标：已学到第几个词。线性推进，不跳级。 */
export function getProgress(): Record<string, number> {
  return readJson(PROGRESS_KEY, {})
}

export function advanceProgress(level: number, word: string, list: WordEntry[]) {
  const levelWords = list.filter(w => w.level === level)
  const idx = levelWords.findIndex(w => w.word === word)
  const prog = getProgress()
  const cur = prog[level] || 0
  if (idx === cur) {
    prog[level] = cur + 1
    writeJson(PROGRESS_KEY, prog)
  }
}

export function getLevel(): number {
  const v = Number(readJson(LEVEL_KEY, 1))
  return v >= 1 && v <= 5 ? v : 1
}

export function setLevel(level: number) {
  writeJson(LEVEL_KEY, level)
}

export const NEW_PER_ROUND = 10
export const REVIEW_PER_ROUND = 3

/** 本轮：先复习本级已学且不稳的词，再按顺序接下一批新词。 */
export function pickRound(list: WordEntry[], level: number, stats = getStats(), progress = getProgress()) {
  const levelWords = list.filter(w => w.level === level)
  const cursor = Math.min(progress[level] || 0, levelWords.length)
  const learned = levelWords.slice(0, cursor)
  const review = learned
    .filter(w => stats[w.word] && stats[w.word].stability < 2)
    .sort((a, b) => stats[a.word].stability - stats[b.word].stability || stats[a.word].last - stats[b.word].last)
    .slice(0, REVIEW_PER_ROUND)
  const fresh = levelWords.slice(cursor, cursor + NEW_PER_ROUND)
  // 本级学完：整级按稳定度从低到高复习
  if (!fresh.length && !review.length) {
    return levelWords
      .slice()
      .sort((a, b) => (stats[a.word]?.stability ?? 0) - (stats[b.word]?.stability ?? 0))
      .slice(0, NEW_PER_ROUND)
  }
  return [...review, ...fresh]
}
