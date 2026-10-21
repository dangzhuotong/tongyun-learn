// tongyun: 把一次练习收成 words_attempts 那一行。字段长度与间隔档跟服务端校验对齐。

import { VALID_INTERVALS, type IntervalDays, type SyncAttempt } from './queue'

export function shanghaiDay(ts: number): string {
  const shifted = new Date(ts + 8 * 60 * 60 * 1000)
  const year = shifted.getUTCFullYear()
  const month = String(shifted.getUTCMonth() + 1).padStart(2, '0')
  const day = String(shifted.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function addCalendarDays(day: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  if (!match) return shanghaiDay(Date.now())
  const stamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days)
  const next = new Date(stamp)
  const year = next.getUTCFullYear()
  const month = String(next.getUTCMonth() + 1).padStart(2, '0')
  const date = String(next.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${date}`
}

export function snapInterval(days: number | null | undefined): IntervalDays {
  if (VALID_INTERVALS.includes(days as IntervalDays)) return days as IntervalDays
  let best: IntervalDays = 1
  let dist = Number.POSITIVE_INFINITY
  const value = typeof days === 'number' && Number.isFinite(days) ? days : 1
  for (const option of VALID_INTERVALS) {
    const gap = Math.abs(option - value)
    if (gap < dist) {
      dist = gap
      best = option
    }
  }
  return best
}

/** 稳定的 36 位 id，同一条历史重复导入时服务端按唯一键当重复。 */
export function stableEventId(key: string): string {
  const seeds = [0x811c9dc5, 0x01000193, 0x9e3779b9, 0x85ebca6b]
  const hex = seeds
    .map(seed => {
      let hash = seed
      for (let i = 0; i < key.length; i += 1) {
        hash ^= key.charCodeAt(i)
        hash = Math.imul(hash, 0x01000193)
      }
      return (hash >>> 0).toString(16).padStart(8, '0')
    })
    .join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`
}

export function newEventId(): string {
  const cryptoObj = globalThis.crypto
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') return cryptoObj.randomUUID()
  return stableEventId(`new:${Date.now()}:${Math.random()}`)
}

function clip(value: string | null | undefined, max: number): string | null {
  if (value === null || value === undefined) return null
  const text = String(value).trim()
  if (!text) return null
  return text.slice(0, max)
}

export interface CaptureInput {
  word: string
  mode: string
  correct: boolean
  answeredAt?: number
  durationMs?: number
  answerText?: string | null
  pointId?: string | null
  level?: string | number | null
  intervalDays?: number | null
  dueAt?: number | null
  nextReviewOn?: string | null
  wordlistVer?: string | null
  eventId?: string | null
}

export function buildSyncAttempt(input: CaptureInput): SyncAttempt | null {
  const word = clip(input.word, 128)
  if (!word) return null
  const answeredAt = typeof input.answeredAt === 'number' && Number.isFinite(input.answeredAt) ? input.answeredAt : Date.now()
  const interval = snapInterval(input.intervalDays)
  const explicitDay = input.nextReviewOn && /^\d{4}-\d{2}-\d{2}$/.test(input.nextReviewOn) ? input.nextReviewOn : ''
  const nextReview =
    explicitDay ||
    (typeof input.dueAt === 'number' && input.dueAt > 0
      ? shanghaiDay(input.dueAt)
      : addCalendarDays(shanghaiDay(answeredAt), interval))
  const levelValue = input.level === null || input.level === undefined ? null : clip(String(input.level), 8)
  const id = clip(input.eventId, 36) || newEventId()
  return {
    client_event_id: id,
    word,
    point_id: clip(input.pointId, 64),
    level: levelValue,
    mode: clip(input.mode, 16) || 'recall',
    correct: Boolean(input.correct),
    duration_ms: Math.max(0, Math.round(input.durationMs || 0)),
    answer_text: clip(input.answerText, 512),
    answered_at: new Date(answeredAt).toISOString(),
    interval_days: interval,
    next_review_on: nextReview,
    wordlist_ver: clip(input.wordlistVer, 16),
  }
}
