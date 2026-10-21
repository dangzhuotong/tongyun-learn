// tongyun: 学习同步客户端。登录打 Nitro /api/v1/auth/login（会话 cookie），
// 练习队列打 /api/v1/attempts，写入现有 words_attempts / words_card_state。不迁 TiDB。

import { withAppBaseURL } from '@/core/utils/base-url'
import { importEnglishHistory } from './history'
import {
  ackAttempts,
  ANONYMOUS_OWNER,
  clearActiveUser,
  detachForeign,
  getActiveUser,
  listPending,
  normalizeOwner,
  parkAttempts,
  setActiveUser,
  syncBacklog,
  unclaimedCount,
  type SyncAttempt,
} from './queue'

/** Nitro 挂在站点 base 下。/learn/ 时是 /learn/api/v1，避免打到会 302 的根路径。 */
export function syncApiPrefix(baseURL?: string): string {
  return withAppBaseURL('/api/v1', baseURL).replace(/\/$/, '')
}

export type SyncFetch = (input: string, init?: RequestInit) => Promise<Response>

export interface LoginOk {
  ok: true
  username: string
}

export interface LoginFail {
  ok: false
  status: number
  message: string
  offline: boolean
}

export type LoginResult = LoginOk | LoginFail

export interface FlushResult {
  ok: boolean
  accepted: number
  duplicate: number
  rejected: number
  pending: number
  parked: number
  full: boolean
  unclaimed: number
  needsLogin: boolean
  offline: boolean
  status?: number
}

export function wireAttempt(event: SyncAttempt): Omit<SyncAttempt, 'owner'> {
  const { owner: _owner, ...rest } = event
  return rest
}

function resolveFetch(fetchImpl?: SyncFetch): SyncFetch | null {
  if (fetchImpl) return fetchImpl
  if (typeof globalThis.fetch === 'function') return globalThis.fetch.bind(globalThis)
  return null
}

async function readMessage(res: Response): Promise<string> {
  try {
    const data = await res.json()
    return data?.message || data?.statusMessage || ''
  } catch {
    return ''
  }
}

export async function loginSync(username: string, password: string, fetchImpl?: SyncFetch): Promise<LoginResult> {
  const name = username.trim()
  if (!name || !password) {
    return { ok: false, status: 400, message: '请填写账号和密码', offline: false }
  }
  const fetcher = resolveFetch(fetchImpl)
  if (!fetcher) return { ok: false, status: 0, message: '连不上同步服务，练习先留在这台浏览器', offline: true }
  try {
    const res = await fetcher(`${syncApiPrefix()}/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ username: name, password }),
    })
    if (res.ok) {
      const data = await res.json().catch(() => ({}))
      const usernameBack = data?.user?.username || data?.user?.user_id || name
      setActiveUser(String(usernameBack))
      return { ok: true, username: String(usernameBack) }
    }
    if (res.status === 401 || res.status === 403) {
      return { ok: false, status: res.status, message: '账号或密码不对', offline: false }
    }
    if (res.status === 429) {
      return { ok: false, status: 429, message: '试得太勤，等一会儿再登', offline: false }
    }
    const message = await readMessage(res)
    return { ok: false, status: res.status, message: message || '同步服务暂时不可用', offline: false }
  } catch {
    return { ok: false, status: 0, message: '连不上同步服务，练习先留在这台浏览器', offline: true }
  }
}

export async function logoutSync(fetchImpl?: SyncFetch): Promise<void> {
  const fetcher = resolveFetch(fetchImpl)
  if (fetcher) {
    try {
      await fetcher(`${syncApiPrefix()}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
    } catch {
      // 网络失败也清掉本机的当前账号，队列按原账号冻结，不会跟着下一次登录走
    }
  }
  clearActiveUser()
}

export async function currentSyncUser(fetchImpl?: SyncFetch): Promise<string | null> {
  const fetcher = resolveFetch(fetchImpl)
  if (!fetcher) return null
  try {
    const res = await fetcher(`${syncApiPrefix()}/auth/me`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
    if (res.status === 401 || res.status === 403) {
      clearActiveUser()
      return null
    }
    if (!res.ok) return getActiveUser()
    const data = await res.json().catch(() => null)
    if (!data || typeof data !== 'object') return getActiveUser()
    const name = data?.user?.username || data?.user?.user_id
    if (typeof name !== 'string' || !name) {
      clearActiveUser()
      return null
    }
    setActiveUser(name)
    return name
  } catch {
    return getActiveUser()
  }
}

interface SessionLook {
  username: string | null
  offline: boolean
}

async function readSession(fetchImpl?: SyncFetch): Promise<SessionLook> {
  const fetcher = resolveFetch(fetchImpl)
  if (!fetcher) return { username: null, offline: true }
  try {
    const res = await fetcher(`${syncApiPrefix()}/auth/me`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
    if (res.status === 401 || res.status === 403) {
      clearActiveUser()
      return { username: null, offline: false }
    }
    if (!res.ok) return { username: null, offline: true }
    const data = await res.json().catch(() => null)
    if (!data || typeof data !== 'object') return { username: null, offline: true }
    const name = data?.user?.username || data?.user?.user_id
    if (typeof name !== 'string' || !name) {
      clearActiveUser()
      return { username: null, offline: false }
    }
    return { username: name, offline: false }
  } catch {
    return { username: null, offline: true }
  }
}

function flushState(partial: Partial<FlushResult> & Pick<FlushResult, 'ok' | 'needsLogin' | 'offline'>): FlushResult {
  const owner = getActiveUser()
  const backlog = syncBacklog(owner || ANONYMOUS_OWNER)
  return {
    accepted: 0,
    duplicate: 0,
    rejected: 0,
    pending: backlog.pending,
    parked: backlog.parked,
    full: backlog.full,
    unclaimed: unclaimedCount(),
    status: partial.status,
    ...partial,
  }
}

function accountedBatch(
  data: unknown,
  batchLength: number
): { ok: true; accepted: number; duplicate: number; rejected: Array<{ client_event_id?: string }> } | { ok: false } {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return { ok: false }
  const body = data as { accepted?: unknown; duplicate?: unknown; rejected?: unknown }
  if (typeof body.accepted !== 'number' || typeof body.duplicate !== 'number' || !Array.isArray(body.rejected)) {
    return { ok: false }
  }
  const rejected = body.rejected as Array<{ client_event_id?: string }>
  if (rejected.some(row => !row || typeof row.client_event_id !== 'string' || !row.client_event_id)) return { ok: false }
  if (body.accepted + body.duplicate + rejected.length !== batchLength) return { ok: false }
  return { ok: true, accepted: body.accepted, duplicate: body.duplicate, rejected }
}

export async function flushSyncQueue(fetchImpl?: SyncFetch): Promise<FlushResult> {
  importEnglishHistory()
  const session = await readSession(fetchImpl)
  if (session.offline) return flushState({ ok: false, needsLogin: false, offline: true })
  if (!session.username) return flushState({ ok: false, needsLogin: true, offline: false })

  const me = normalizeOwner(session.username)
  setActiveUser(me)
  detachForeign(me)
  const snapshot = listPending(me).filter(item => normalizeOwner(item.owner || me) === me)
  if (!snapshot.length) return flushState({ ok: true, needsLogin: false, offline: false })

  const fetcher = resolveFetch(fetchImpl)
  if (!fetcher) return flushState({ ok: false, needsLogin: false, offline: true })

  let accepted = 0
  let duplicate = 0
  let rejected = 0
  for (let offset = 0; offset < snapshot.length; offset += 200) {
    const batch = snapshot.slice(offset, offset + 200)
    let res: Response
    try {
      res = await fetcher(`${syncApiPrefix()}/attempts`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ events: batch.map(wireAttempt) }),
      })
    } catch {
      return flushState({ ok: false, accepted, duplicate, rejected, needsLogin: false, offline: true })
    }
    if (res.status === 401 || res.status === 403) {
      return flushState({ ok: false, accepted, duplicate, rejected, needsLogin: true, offline: false, status: res.status })
    }
    if (!res.ok) {
      return flushState({
        ok: false,
        accepted,
        duplicate,
        rejected,
        needsLogin: false,
        offline: false,
        status: res.status,
      })
    }
    const accounted = accountedBatch(await res.json().catch(() => null), batch.length)
    if (!accounted.ok) {
      return flushState({ ok: false, accepted, duplicate, rejected, needsLogin: false, offline: false, status: res.status })
    }
    const rejectedIds = new Set(accounted.rejected.map(row => row.client_event_id).filter((id): id is string => !!id))
    const parked = batch.filter(item => rejectedIds.has(item.client_event_id))
    const done = batch.filter(item => !rejectedIds.has(item.client_event_id)).map(item => item.client_event_id)
    ackAttempts(done, me)
    parkAttempts(parked, me)
    accepted += accounted.accepted
    duplicate += accounted.duplicate
    rejected += accounted.rejected.length
  }
  return flushState({ ok: true, accepted, duplicate, rejected, needsLogin: false, offline: false })
}

let flushing = false

/** 浏览器里补历史并上传。未登录或离线时队列留着。 */
export function bootSync() {
  if (typeof window === 'undefined') return
  const run = () => {
    if (flushing) return
    flushing = true
    void flushSyncQueue().finally(() => {
      flushing = false
    })
  }
  window.addEventListener('online', run)
  run()
}

export type { SyncAttempt }
