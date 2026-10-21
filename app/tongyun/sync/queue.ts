// tongyun: 练习同步的离线队列。先落在浏览器，登录后按 client_event_id 上传到 Nitro /api/v1/attempts。
// 目标表是 tongyun_learn.words_attempts / words_card_state，不另建库。

export const SYNC_QUEUE_KEY = 'tongyun-sync-queue-v1'
export const SYNC_ACKED_KEY = 'tongyun-sync-acked-v1'
export const SYNC_PARKED_KEY = 'tongyun-sync-parked-v1'

export const VALID_INTERVALS = [1, 3, 7, 14, 30] as const
export type IntervalDays = (typeof VALID_INTERVALS)[number]

export interface SyncAttempt {
  client_event_id: string
  word: string
  point_id?: string | null
  level?: string | null
  mode: string
  correct: boolean
  duration_ms: number
  answer_text?: string | null
  answered_at: string
  interval_days: IntervalDays
  next_review_on: string
  wordlist_ver?: string | null
}

const MAX_PENDING = 5000
const MAX_ACKED = 8000
const MAX_PARKED = 200

function storage(): Storage | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage
  } catch {
    return null
  }
}

function readList<T>(key: string): T[] {
  const box = storage()
  if (!box) return []
  try {
    const raw = box.getItem(key)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeList(key: string, value: unknown[]) {
  const box = storage()
  if (!box) return
  try {
    box.setItem(key, JSON.stringify(value))
  } catch {
    // 配额满时保留内存中的这次调用失败，下次作答再写
  }
}

export function isSyncAttempt(raw: unknown): raw is SyncAttempt {
  if (!raw || typeof raw !== 'object') return false
  const row = raw as SyncAttempt
  return (
    typeof row.client_event_id === 'string' &&
    row.client_event_id.length > 0 &&
    row.client_event_id.length <= 36 &&
    typeof row.word === 'string' &&
    row.word.length > 0 &&
    typeof row.mode === 'string' &&
    typeof row.correct === 'boolean' &&
    typeof row.duration_ms === 'number' &&
    typeof row.answered_at === 'string' &&
    VALID_INTERVALS.includes(row.interval_days) &&
    typeof row.next_review_on === 'string'
  )
}

export function listPending(): SyncAttempt[] {
  return readList<unknown>(SYNC_QUEUE_KEY).filter(isSyncAttempt)
}

export function ackedIds(): Set<string> {
  const ids = readList<unknown>(SYNC_ACKED_KEY).filter((id): id is string => typeof id === 'string' && id.length > 0)
  return new Set(ids)
}

export function enqueueAttempts(events: SyncAttempt[]): number {
  const pending = listPending()
  const seen = new Set(pending.map(item => item.client_event_id))
  const acked = ackedIds()
  let added = 0
  for (const event of events) {
    if (!isSyncAttempt(event)) continue
    if (seen.has(event.client_event_id) || acked.has(event.client_event_id)) continue
    pending.push(event)
    seen.add(event.client_event_id)
    added += 1
  }
  const trimmed = pending.length > MAX_PENDING ? pending.slice(pending.length - MAX_PENDING) : pending
  writeList(SYNC_QUEUE_KEY, trimmed)
  return added
}

export function ackAttempts(ids: string[]) {
  if (!ids.length) return
  const done = new Set(ids)
  const pending = listPending().filter(item => !done.has(item.client_event_id))
  writeList(SYNC_QUEUE_KEY, pending)
  const acked = readList<unknown>(SYNC_ACKED_KEY).filter((id): id is string => typeof id === 'string')
  for (const id of ids) {
    if (id && !acked.includes(id)) acked.push(id)
  }
  const trimmed = acked.length > MAX_ACKED ? acked.slice(acked.length - MAX_ACKED) : acked
  writeList(SYNC_ACKED_KEY, trimmed)
}

/** 服务端判为无效的事件移出待传队列，避免每次重试都卡在同一条。 */
export function parkAttempts(events: SyncAttempt[]) {
  if (!events.length) return
  const ids = new Set(events.map(item => item.client_event_id))
  writeList(
    SYNC_QUEUE_KEY,
    listPending().filter(item => !ids.has(item.client_event_id))
  )
  const parked = readList<unknown>(SYNC_PARKED_KEY).filter(isSyncAttempt)
  parked.push(...events.filter(isSyncAttempt))
  writeList(SYNC_PARKED_KEY, parked.slice(-MAX_PARKED))
}
