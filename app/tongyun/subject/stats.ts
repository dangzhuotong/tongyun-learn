// tongyun: 学科敲字练习 1/3/7/14/30 间隔复习与本地进度持久化
import type { SubjectItemStat } from './types'

export const DAY = 24 * 3600 * 1000
export const INTERVALS = [1, 3, 7, 14, 30]

export const ZERO_STAT: SubjectItemStat = {
  right: 0,
  wrong: 0,
  last: 0,
  box: 0,
  due: 0,
  first: 0,
}

function num(v: unknown, d = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : d
}

export function normalizeSubjectStat(raw: any): SubjectItemStat {
  const r = raw && typeof raw === 'object' ? raw : {}
  const last = num(r.last)
  let box = num(r.box, 0)
  box = Math.min(INTERVALS.length - 1, Math.max(0, Math.floor(box)))
  const due = r.due !== undefined ? num(r.due) : last ? last + INTERVALS[box] * DAY : 0
  const first = num(r.first) || last
  return {
    right: num(r.right),
    wrong: num(r.wrong),
    last,
    box,
    due,
    first,
  }
}

/**
 * 推进或重置 1/3/7/14/30 间隔：
 * - 答对：已有作答记录时进下一档（box + 1），首次答对入第 0 档（1 天）；最高停在 30 天档。
 * - 答错：重置回第 0 档（1 天）。
 */
export function nextSubjectStat(
  cur: SubjectItemStat | undefined,
  correct: boolean,
  now = Date.now()
): SubjectItemStat {
  const prev = cur || ZERO_STAT
  if (!correct) {
    return {
      ...prev,
      wrong: prev.wrong + 1,
      last: now,
      box: 0,
      due: now + INTERVALS[0] * DAY,
      first: prev.first || now,
    }
  }

  const box = prev.last ? Math.min(INTERVALS.length - 1, prev.box + 1) : 0
  return {
    ...prev,
    right: prev.right + 1,
    last: now,
    box,
    due: now + INTERVALS[box] * DAY,
    first: prev.first || now,
  }
}

function storageKey(subject: string): string {
  return `tongyun-subject-stats-v1:${(subject || 'java').toLowerCase()}`
}

export function getSubjectStats(subject: string): Record<string, SubjectItemStat> {
  try {
    if (typeof localStorage === 'undefined') return {}
    const raw = localStorage.getItem(storageKey(subject))
    const obj = raw ? JSON.parse(raw) : null
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return {}
    const out: Record<string, SubjectItemStat> = {}
    for (const [k, v] of Object.entries(obj)) {
      out[k] = normalizeSubjectStat(v)
    }
    return out
  } catch {
    return {}
  }
}

export function saveSubjectStat(
  subject: string,
  itemId: string,
  stat: SubjectItemStat
): SubjectItemStat {
  try {
    if (typeof localStorage === 'undefined') return stat
    const all = getSubjectStats(subject)
    all[itemId] = stat
    localStorage.setItem(storageKey(subject), JSON.stringify(all))
  } catch {}
  return stat
}

export function recordSubjectResult(
  subject: string,
  itemId: string,
  correct: boolean,
  now = Date.now()
): SubjectItemStat {
  const all = getSubjectStats(subject)
  const next = nextSubjectStat(all[itemId], correct, now)
  all[itemId] = next
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(storageKey(subject), JSON.stringify(all))
    }
  } catch {}
  return next
}
