// tongyun: 学习同步客户端。登录打 Nitro /api/v1/auth/login（会话 cookie），
// 练习队列打 /api/v1/attempts，写入现有 words_attempts / words_card_state。不迁 TiDB。

import { importEnglishHistory } from './history'
import { ackAttempts, listPending, parkAttempts, type SyncAttempt } from './queue'

export const SYNC_API_PREFIX = '/api/v1'

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
  needsLogin: boolean
  offline: boolean
  status?: number
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
    const res = await fetcher(`${SYNC_API_PREFIX}/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ username: name, password }),
    })
    if (res.ok) {
      const data = await res.json().catch(() => ({}))
      const usernameBack = data?.user?.username || name
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
  if (!fetcher) return
  try {
    await fetcher(`${SYNC_API_PREFIX}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
  } catch {
    // 本地队列还在，下次登录再传
  }
}

export async function currentSyncUser(fetchImpl?: SyncFetch): Promise<string | null> {
  const fetcher = resolveFetch(fetchImpl)
  if (!fetcher) return null
  try {
    const res = await fetcher(`${SYNC_API_PREFIX}/auth/me`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
    if (!res.ok) return null
    const data = await res.json()
    const name = data?.user?.username || data?.user?.user_id
    return typeof name === 'string' && name ? name : null
  } catch {
    return null
  }
}

export async function flushSyncQueue(fetchImpl?: SyncFetch): Promise<FlushResult> {
  importEnglishHistory()
  const fetcher = resolveFetch(fetchImpl)
  const empty = (): FlushResult => ({
    ok: true,
    accepted: 0,
    duplicate: 0,
    rejected: 0,
    pending: listPending().length,
    needsLogin: false,
    offline: false,
  })
  const snapshot = listPending()
  if (!snapshot.length) return empty()
  if (!fetcher) {
    return { ...empty(), ok: false, offline: true, pending: snapshot.length }
  }

  let accepted = 0
  let duplicate = 0
  let rejected = 0
  for (let offset = 0; offset < snapshot.length; offset += 200) {
    const batch = snapshot.slice(offset, offset + 200)
    let res: Response
    try {
      res = await fetcher(`${SYNC_API_PREFIX}/attempts`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ events: batch }),
      })
    } catch {
      return { ok: false, accepted, duplicate, rejected, pending: listPending().length, needsLogin: false, offline: true }
    }
    if (res.status === 401 || res.status === 403) {
      return { ok: false, accepted, duplicate, rejected, pending: listPending().length, needsLogin: true, offline: false, status: res.status }
    }
    if (!res.ok) {
      return {
        ok: false,
        accepted,
        duplicate,
        rejected,
        pending: listPending().length,
        needsLogin: false,
        offline: false,
        status: res.status,
      }
    }
    const data = await res.json().catch(() => ({}))
    const rejectedRows: Array<{ client_event_id?: string }> = Array.isArray(data?.rejected) ? data.rejected : []
    const rejectedIds = new Set(rejectedRows.map(row => row.client_event_id).filter((id): id is string => !!id))
    const parked = batch.filter(item => rejectedIds.has(item.client_event_id))
    const done = batch.filter(item => !rejectedIds.has(item.client_event_id)).map(item => item.client_event_id)
    ackAttempts(done)
    parkAttempts(parked)
    accepted += Number(data?.accepted) || 0
    duplicate += Number(data?.duplicate) || 0
    rejected += rejectedRows.length
  }
  return { ok: true, accepted, duplicate, rejected, pending: listPending().length, needsLogin: false, offline: false }
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
