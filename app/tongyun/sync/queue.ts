// tongyun: 练习同步的离线队列。按账号分开存放，登录后只上传当前账号的事件。
// 目标表是 tongyun_learn.words_attempts / words_card_state，不另建库。

export const SYNC_QUEUE_KEY = 'tongyun-sync-queue-v1'
export const SYNC_ACKED_KEY = 'tongyun-sync-acked-v1'
export const SYNC_PARKED_KEY = 'tongyun-sync-parked-v1'
export const ACTIVE_USER_KEY = 'tongyun-sync-active-user-v1'
export const ANONYMOUS_OWNER = 'anonymous'
export const MAX_PENDING = 5000

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
  /** 入队时的账号。anonymous 表示还没认领，不能上传。 */
  owner?: string
}

export interface EnqueueResult {
  added: number
  duplicate: number
  skipped: number
  full: boolean
}

const MAX_ACKED = 8000

function storage(): Storage | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage
  } catch {
    return null
  }
}

export function normalizeOwner(owner: string | null | undefined): string {
  const text = (owner || '').trim()
  if (!text) return ANONYMOUS_OWNER
  const safe = text.replace(/[^a-zA-Z0-9._@-]/g, '_').slice(0, 64)
  return safe || ANONYMOUS_OWNER
}

function scopedKey(base: string, owner: string): string {
  return `${base}:${normalizeOwner(owner)}`
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
    // 配额满时这次写入失败，队列里已有的记录不动
  }
}

function removeKey(key: string) {
  try {
    storage()?.removeItem(key)
  } catch {
    // 清不掉就留着，下次迁移再试
  }
}

/** 旧版三个全局 key 没有账号。迁到 anonymous，避免下一个登录的人直接上传。 */
function migrateLegacy() {
  const box = storage()
  if (!box) return
  const pairs: Array<[string, (raw: unknown) => unknown]> = [
    [SYNC_QUEUE_KEY, raw => raw],
    [SYNC_ACKED_KEY, raw => raw],
    [SYNC_PARKED_KEY, raw => raw],
  ]
  for (const [legacy] of pairs) {
    const raw = box.getItem(legacy)
    if (!raw) continue
    const dest = scopedKey(legacy, ANONYMOUS_OWNER)
    let incoming: unknown[] = []
    try {
      const parsed = JSON.parse(raw)
      incoming = Array.isArray(parsed) ? parsed : []
    } catch {
      incoming = []
    }
    const existing = readList<unknown>(dest)
    writeList(dest, [...existing, ...incoming])
    removeKey(legacy)
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

export function getActiveUser(): string | null {
  const box = storage()
  if (!box) return null
  const raw = box.getItem(ACTIVE_USER_KEY)
  if (!raw) return null
  const owner = normalizeOwner(raw)
  return owner === ANONYMOUS_OWNER ? null : owner
}

export function setActiveUser(userId: string) {
  const owner = normalizeOwner(userId)
  const box = storage()
  if (!box) return
  if (owner === ANONYMOUS_OWNER) {
    clearActiveUser()
    return
  }
  try {
    box.setItem(ACTIVE_USER_KEY, owner)
  } catch {
    // 记不住当前账号时，新作答进 anonymous，不会串到别人名下
  }
}

export function clearActiveUser() {
  removeKey(ACTIVE_USER_KEY)
}

export function queueOwner(): string {
  return getActiveUser() || ANONYMOUS_OWNER
}

function stamp(events: SyncAttempt[], owner: string): SyncAttempt[] {
  return events.map(event => ({ ...event, owner: event.owner ? normalizeOwner(event.owner) : owner }))
}

export function listPending(owner: string = queueOwner()): SyncAttempt[] {
  migrateLegacy()
  const bucket = normalizeOwner(owner)
  return stamp(readList<unknown>(scopedKey(SYNC_QUEUE_KEY, bucket)).filter(isSyncAttempt), bucket)
}

export function listParked(owner: string = queueOwner()): SyncAttempt[] {
  migrateLegacy()
  const bucket = normalizeOwner(owner)
  return stamp(readList<unknown>(scopedKey(SYNC_PARKED_KEY, bucket)).filter(isSyncAttempt), bucket)
}

export function ackedIds(owner: string = queueOwner()): Set<string> {
  migrateLegacy()
  const ids = readList<unknown>(scopedKey(SYNC_ACKED_KEY, normalizeOwner(owner))).filter(
    (id): id is string => typeof id === 'string' && id.length > 0
  )
  return new Set(ids)
}

export function syncBacklog(owner: string = queueOwner()): { pending: number; parked: number; full: boolean } {
  const pending = listPending(owner).length
  return { pending, parked: listParked(owner).length, full: pending >= MAX_PENDING }
}

export function unclaimedCount(): number {
  return listPending(ANONYMOUS_OWNER).length + listParked(ANONYMOUS_OWNER).length
}

export function enqueueAttempts(events: SyncAttempt[], owner: string = queueOwner()): EnqueueResult {
  const bucket = normalizeOwner(owner)
  const pending = listPending(bucket)
  const seen = new Set(pending.map(item => item.client_event_id))
  const acked = ackedIds(bucket)
  if (pending.length >= MAX_PENDING) {
    return { added: 0, duplicate: 0, skipped: events.length, full: true }
  }
  let added = 0
  let duplicate = 0
  let skipped = 0
  for (const event of events) {
    if (!isSyncAttempt(event)) {
      skipped += 1
      continue
    }
    if (seen.has(event.client_event_id) || acked.has(event.client_event_id)) {
      duplicate += 1
      continue
    }
    if (pending.length >= MAX_PENDING) {
      skipped += 1
      continue
    }
    pending.push({ ...event, owner: bucket })
    seen.add(event.client_event_id)
    added += 1
  }
  writeList(scopedKey(SYNC_QUEUE_KEY, bucket), pending)
  return { added, duplicate, skipped, full: pending.length >= MAX_PENDING }
}

function rememberAcked(ids: string[], owner: string) {
  if (!ids.length) return
  const acked = readList<unknown>(scopedKey(SYNC_ACKED_KEY, owner)).filter((id): id is string => typeof id === 'string')
  for (const id of ids) {
    if (id && !acked.includes(id)) acked.push(id)
  }
  const trimmed = acked.length > MAX_ACKED ? acked.slice(acked.length - MAX_ACKED) : acked
  writeList(scopedKey(SYNC_ACKED_KEY, owner), trimmed)
}

/** 已经记在某个账号下的事件，不要再从本地历史导成未归属。 */
export function sealFromAnonymous(ids: string[]) {
  rememberAcked(ids, ANONYMOUS_OWNER)
}

export function ackAttempts(ids: string[], owner: string = queueOwner()) {
  if (!ids.length) return
  const bucket = normalizeOwner(owner)
  const done = new Set(ids)
  const pending = listPending(bucket).filter(item => !done.has(item.client_event_id))
  writeList(scopedKey(SYNC_QUEUE_KEY, bucket), pending)
  rememberAcked(ids, bucket)
}

/** 服务端判为无效的事件移出待传队列。不覆盖更早的拒绝记录，设置页可以重新上传。 */
export function parkAttempts(events: SyncAttempt[], owner: string = queueOwner()) {
  if (!events.length) return
  const bucket = normalizeOwner(owner)
  const ids = new Set(events.map(item => item.client_event_id))
  writeList(
    scopedKey(SYNC_QUEUE_KEY, bucket),
    listPending(bucket).filter(item => !ids.has(item.client_event_id))
  )
  const parked = listParked(bucket)
  const seen = new Set(parked.map(item => item.client_event_id))
  for (const event of events) {
    if (!isSyncAttempt(event) || seen.has(event.client_event_id)) continue
    parked.push({ ...event, owner: bucket })
    seen.add(event.client_event_id)
  }
  writeList(scopedKey(SYNC_PARKED_KEY, bucket), parked)
}

/** 把拒绝记录放回待传队列。队列满时留在拒绝列表里，不丢掉。 */
export function requeueParked(owner: string = queueOwner()): { moved: number; parked: number; full: boolean } {
  const bucket = normalizeOwner(owner)
  const parked = listParked(bucket)
  const result = enqueueAttempts(parked, bucket)
  const pendingIds = new Set(listPending(bucket).map(item => item.client_event_id))
  const acked = ackedIds(bucket)
  const remain = parked.filter(item => !pendingIds.has(item.client_event_id) && !acked.has(item.client_event_id))
  writeList(scopedKey(SYNC_PARKED_KEY, bucket), remain)
  return { moved: parked.length - remain.length, parked: remain.length, full: result.full }
}

/**
 * 把未归属记录划给这个账号。已经在该账号队列或已上传的，只从 anonymous 去掉。
 * 队列满时剩下的继续留在 anonymous。
 */
export function claimAnonymous(userId: string): { moved: number; remaining: number } {
  const user = normalizeOwner(userId)
  if (user === ANONYMOUS_OWNER) return { moved: 0, remaining: unclaimedCount() }
  const movedIds: string[] = []
  const keepPending: SyncAttempt[] = []
  const userPending = new Set(listPending(user).map(item => item.client_event_id))
  const userAcked = ackedIds(user)
  for (const event of listPending(ANONYMOUS_OWNER)) {
    if (userPending.has(event.client_event_id) || userAcked.has(event.client_event_id)) {
      movedIds.push(event.client_event_id)
      continue
    }
    const result = enqueueAttempts([{ ...event, owner: user }], user)
    if (result.added || result.duplicate) {
      movedIds.push(event.client_event_id)
      userPending.add(event.client_event_id)
    } else {
      keepPending.push({ ...event, owner: ANONYMOUS_OWNER })
    }
  }
  writeList(scopedKey(SYNC_QUEUE_KEY, ANONYMOUS_OWNER), keepPending)

  const keepParked: SyncAttempt[] = []
  for (const event of listParked(ANONYMOUS_OWNER)) {
    if (userPending.has(event.client_event_id) || userAcked.has(event.client_event_id) || ackedIds(user).has(event.client_event_id)) {
      movedIds.push(event.client_event_id)
      continue
    }
    const result = enqueueAttempts([{ ...event, owner: user }], user)
    if (result.added || result.duplicate) {
      movedIds.push(event.client_event_id)
      userPending.add(event.client_event_id)
    } else {
      keepParked.push({ ...event, owner: ANONYMOUS_OWNER })
    }
  }
  writeList(scopedKey(SYNC_PARKED_KEY, ANONYMOUS_OWNER), keepParked)
  rememberAcked(movedIds, ANONYMOUS_OWNER)
  return { moved: movedIds.length, remaining: unclaimedCount() }
}

/** 当前账号队列里 owner 对不上的事件挪回去，调用方不再上传它们。 */
export function detachForeign(userId: string): number {
  const me = normalizeOwner(userId)
  if (me === ANONYMOUS_OWNER) return 0
  const bucket = listPending(me)
  const keep: SyncAttempt[] = []
  let moved = 0
  for (const event of bucket) {
    const owner = normalizeOwner(event.owner || me)
    if (owner === me) {
      keep.push(event)
      continue
    }
    const result = enqueueAttempts([{ ...event, owner }], owner)
    if (result.added || result.duplicate) moved += 1
    else keep.push(event)
  }
  writeList(scopedKey(SYNC_QUEUE_KEY, me), keep)
  return moved
}
