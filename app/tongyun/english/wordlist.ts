// tongyun: 阿学定制英语词表 v1.0（L1–L6，L6 可选）+ 本地间隔复习。完全不依赖学习服务。
// 许可：en-ngsl.json 为 NGSL 1.2 派生（CC BY-SA 4.0，文件头保留出处），en-tongyun.json 为自编，分文件存放。
import { withAppBaseURL } from '@/core/utils/base-url'

/** 语体。与词表顶层 register_values 一致，只有这五种。 */
export const REGISTER_VALUES = ['technical', 'neutral', 'informal', 'slang', 'formal'] as const
export type WordRegister = (typeof REGISTER_VALUES)[number]

export interface WordEntry {
  word: string
  phonetic: string
  /** 可选：音标备注 */
  phonetic_note?: string
  meaning: string
  /** 语体，取值为 REGISTER_VALUES */
  register?: WordRegister
  example: string
  example_zh?: string
  tag: string
  level: number
  point_id?: string
  source: string
  /** 展示用语气；有则优先于 register */
  tone?: string
}

export const LEVELS: { level: number; title: string; optional?: boolean }[] = [
  { level: 1, title: 'L1 AI 核心术语' },
  { level: 2, title: 'L2 X/社区用语' },
  { level: 3, title: 'L3 技术文档词汇' },
  { level: 4, title: 'L4 通用基础词（NGSL 1.2 筛选）' },
  { level: 5, title: 'L5 推文/README/PR 写作' },
  { level: 6, title: 'L6 面试表达', optional: true },
]

export const TAG_LABEL: Record<string, string> = {
  ai: 'AI', community: 'X 社区', java: 'Java', spring: 'Spring', db: '数据库', web: 'Web', cloud: '部署',
  general: '通用', tweet: '发推', readme: 'README', issue: 'issue', pr: 'PR', interview: '面试', work: '工作',
}

/** phonetic 可用逗号写多种读法，拆开展示 */
export function splitPhonetics(p: string): string[] {
  return (p || '').split(/[,，]/).map(x => x.trim()).filter(Boolean)
}

export const WORDLIST_FILES = ['/wordlists/en-ngsl.json', '/wordlists/en-tongyun.json']
export const NGSL_ATTRIBUTION =
  'L4 词条派生自 New General Service List (NGSL) 1.2，Browne, C., Culligan, B. & Phillips, J.，CC BY-SA 4.0（https://www.newgeneralservicelist.com/ ，https://creativecommons.org/licenses/by-sa/4.0/）。已筛选并加注，本词表按 CC BY-SA 4.0 共享。其余词表与例句为橦云自编。'

const PENDING_POINT_ID = '待定'
const COMMUNITY_POINT_ID = 'en.x-community'

/** L2/L5 里 point_id 仍为「待定」的条目挂到社区知识点。 */
export function normalizeEntry(raw: WordEntry): WordEntry {
  if ((raw.level === 2 || raw.level === 5) && raw.point_id === PENDING_POINT_ID) {
    return { ...raw, point_id: COMMUNITY_POINT_ID }
  }
  return raw
}

export function entriesFromWordlist(data: { words?: WordEntry[] } | null | undefined): WordEntry[] {
  if (!data || !Array.isArray(data.words)) return []
  return data.words.map(normalizeEntry)
}

/** 语气标注：词表字段优先；没有就按释义/标签推断（俚语、缩写、回复用语） */
export function toneOf(w: Pick<WordEntry, 'meaning' | 'tag' | 'tone' | 'register'>): string {
  const explicit = (w.tone || w.register || '').trim()
  if (explicit) return explicit
  const m = w.meaning || ''
  if (/俚/.test(m)) return '俚语 · 随意口吻，正式场合别用'
  if (w.tag === 'community' && /^abbr/i.test(m)) return '网络缩写 · 随意口吻，正式文档别用'
  if (w.tag === 'community' && /回复用语/.test(m)) return '回复用语 · 口语'
  if (w.tag === 'community') return '社区说法 · 偏口语'
  return ''
}

let cache: WordEntry[] | null = null

export async function loadWordlist(): Promise<WordEntry[]> {
  if (cache) return cache
  const all: WordEntry[] = []
  for (const file of WORDLIST_FILES) {
    try {
      const res = await fetch(withAppBaseURL(file))
      if (!res.ok) continue
      const data = await res.json()
      all.push(...entriesFromWordlist(data))
    } catch {}
  }
  all.sort((a, b) => a.level - b.level)
  if (all.length) cache = all
  return all
}

// ---- 间隔复习（localStorage） ----
export const DAY = 24 * 3600 * 1000
export const INTERVALS = [1, 3, 7, 14, 30]

export interface WordStat {
  right: number
  wrong: number
  last: number
  /** 当前所在间隔档 0–4，对应 1/3/7/14/30 天 */
  box: number
  /** 下次到期时间（毫秒） */
  due: number
  /** tongyun: 首次教学时间，用于统计「今天学过几个新词」 */
  first: number
  /** tongyun: 是否已教过；连续两次拼错后置 false，触发重教（从第 1 步重来） */
  taught: boolean
}

export const ZERO_STAT: WordStat = { right: 0, wrong: 0, last: 0, box: 0, due: 0, first: 0, taught: false }

const STATS_KEY = 'tongyun-en-stats-v1'
const PROGRESS_KEY = 'tongyun-en-progress-v1'
const LEVEL_KEY = 'tongyun-en-level-v1'
const OPTIONAL_KEY = 'tongyun-en-optional-v1'

function readJson<T>(key: string, fallback: T): T {
  try {
    if (typeof localStorage === 'undefined') return fallback
    const raw = localStorage.getItem(key)
    const v = raw ? JSON.parse(raw) : null
    if (v === null || v === undefined) return fallback
    if (typeof fallback === 'object' && (typeof v !== 'object' || Array.isArray(v))) return fallback
    return v as T
  } catch {
    return fallback
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

function num(v: unknown, d = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : d
}

/** 兼容旧数据（stability 0–5，无 box/due）和坏数据，不抛错 */
export function normalizeStat(raw: any): WordStat {
  const r = raw && typeof raw === 'object' ? raw : {}
  const last = num(r.last)
  let box = r.box !== undefined ? num(r.box) : Math.max(0, num(r.stability) - 1)
  box = Math.min(INTERVALS.length - 1, Math.max(0, Math.floor(box)))
  const due = r.due !== undefined ? num(r.due) : last ? last + INTERVALS[box] * DAY : 0
  const first = num(r.first) || last
  const taught = r.taught !== undefined ? Boolean(r.taught) : last > 0
  return { right: num(r.right), wrong: num(r.wrong), last, box, due, first, taught }
}

export function getStats(): Record<string, WordStat> {
  const raw = readJson<Record<string, any>>(STATS_KEY, {})
  const out: Record<string, WordStat> = {}
  for (const [k, v] of Object.entries(raw)) out[k] = normalizeStat(v)
  return out
}

/** 答对：进入下一档（首次答对排 1 天后）；答错：重置到第 1 天 */
export function nextStat(cur: WordStat | undefined, correct: boolean, now: number): WordStat {
  const c = cur || ZERO_STAT
  if (!correct) return { ...c, wrong: c.wrong + 1, last: now, box: 0, due: now + INTERVALS[0] * DAY }
  const box = c.last ? Math.min(INTERVALS.length - 1, c.box + 1) : 0
  return { ...c, right: c.right + 1, last: now, box, due: now + INTERVALS[box] * DAY }
}

export function recordResult(word: string, correct: boolean, now = Date.now()): WordStat {
  const stats = getStats()
  const next = nextStat(stats[word], correct, now)
  stats[word] = next
  writeJson(STATS_KEY, stats)
  return next
}

/** tongyun: 直接写回某个词的排课状态（教学 / 复习 / 重教都走这里）。 */
export function saveStat(word: string, stat: WordStat): WordStat {
  const stats = getStats()
  stats[word] = stat
  writeJson(STATS_KEY, stats)
  return stat
}

/** tongyun: 教完一个新词 —— 记为已教，首次复习排到明天（档 0，间隔 1 天）。 */
export function teachStat(word: string, now = Date.now()): WordStat {
  return { right: 0, wrong: 0, last: now, box: 0, due: now + INTERVALS[0] * DAY, first: now, taught: true }
}

/** tongyun: 重教已学过的词 —— 保留历史，档重置到 0，明天再复习。 */
export function relearnStat(prev: WordStat, now = Date.now()): WordStat {
  return {
    right: prev.right,
    wrong: prev.wrong,
    last: now,
    box: 0,
    due: now + INTERVALS[0] * DAY,
    first: prev.first || now,
    taught: true,
  }
}

/** tongyun: 还没教过的词（完全没见过）。 */
export function isNewWord(stat: WordStat | undefined): boolean {
  return !stat
}

export function startOfDay(ts: number): number {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** tongyun: 今天已教过的新词数（按 first 落在今天统计）。 */
export function countIntroducedToday(stats: Record<string, WordStat> = getStats(), now = Date.now()): number {
  const from = startOfDay(now)
  const to = from + DAY
  return Object.values(stats).filter(s => s.first >= from && s.first < to).length
}

// ---- tongyun: 级别顺序与每日新词额度 ----

/** 级别引入顺序：L1→L2→L3→L5→L4，L6 可选。 */
export const LEVEL_ORDER = [1, 2, 3, 5, 4, 6]

/** 按引入顺序展开；L6 等 optional 级别只有显式开启时才出现。 */
export function orderedLevels(optional: number[] = []): number[] {
  const on = new Set(optional)
  return LEVEL_ORDER.filter(n => {
    const meta = LEVELS.find(l => l.level === n)
    if (!meta) return false
    return meta.optional ? on.has(n) : true
  })
}

export function getOptionalLevels(): number[] {
  const v = readJson<number[]>(OPTIONAL_KEY, [])
  return Array.isArray(v) ? v.filter(n => typeof n === 'number') : []
}

export function setOptionalLevel(level: number, on: boolean) {
  const set = new Set(getOptionalLevels())
  if (on) set.add(level)
  else set.delete(level)
  writeJson(OPTIONAL_KEY, [...set].sort((a, b) => a - b))
}

export const NEW_DEFAULT = 8
export const NEW_WHEN_DUE_HIGH = 3
export const NEW_DUE_REDUCE = 40
export const NEW_DUE_STOP = 80

/** 每日新词上限：默认 8；到期 >40 降到 3；>80 不加新词。 */
export function dailyNewBudget(due: number): number {
  if (due > NEW_DUE_STOP) return 0
  if (due > NEW_DUE_REDUCE) return NEW_WHEN_DUE_HIGH
  return NEW_DEFAULT
}

/** 今天还能引入几个新词（扣掉今天已经教过的）。 */
export function remainingNewBudget(due: number, introducedToday: number): number {
  return Math.max(0, dailyNewBudget(due) - Math.max(0, introducedToday))
}

/** 每级一个游标：已学到第几个词。线性推进，不跳级。 */
export function getProgress(): Record<string, number> {
  return readJson(PROGRESS_KEY, {})
}

export function advanceProgress(level: number, word: string, list: WordEntry[]) {
  const levelWords = list.filter(w => w.level === level)
  const idx = levelWords.findIndex(w => w.word === word)
  const prog = getProgress()
  const cur = num(prog[level])
  if (idx === cur) {
    prog[level] = cur + 1
    writeJson(PROGRESS_KEY, prog)
  }
}

export function getLevel(): number {
  const v = Number(readJson(LEVEL_KEY, 1 as any))
  return v >= 1 && v <= LEVELS.length ? v : 1
}

export function setLevel(level: number) {
  writeJson(LEVEL_KEY, level)
}

export const NEW_PER_ROUND = 10
export const REVIEW_PER_ROUND = 5

/** 本轮：先复习本级已学且到期的词（最早到期优先），再按顺序接下一批新词。 */
export function pickRound(
  list: WordEntry[],
  level: number,
  stats: Record<string, WordStat> = getStats(),
  progress: Record<string, number> = getProgress(),
  now = Date.now()
) {
  const levelWords = list.filter(w => w.level === level)
  const cursor = Math.min(num(progress[level]), levelWords.length)
  const due = levelWords
    .slice(0, cursor)
    .filter(w => stats[w.word] && stats[w.word].due <= now)
    .sort((a, b) => stats[a.word].due - stats[b.word].due)
    .slice(0, REVIEW_PER_ROUND)
  const fresh = levelWords.slice(cursor, cursor + NEW_PER_ROUND)
  return [...due, ...fresh]
}

export function dueCount(list: WordEntry[], level: number, stats = getStats(), progress = getProgress(), now = Date.now()) {
  const levelWords = list.filter(w => w.level === level)
  const cursor = Math.min(num(progress[level]), levelWords.length)
  return levelWords.slice(0, cursor).filter(w => stats[w.word] && stats[w.word].due <= now).length
}
