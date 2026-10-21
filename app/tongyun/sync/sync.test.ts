import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { recordAnswer } from '../english/records'
import { saveStat, teachStat } from '../english/wordlist'
import { captureAnswer } from './capture'
import { currentSyncUser, flushSyncQueue, loginSync, logoutSync, syncApiPrefix } from './client'
import { historyEventId, importEnglishHistory } from './history'
import { shanghaiDay, stableEventId } from './event'
import {
  ACTIVE_USER_KEY,
  ANONYMOUS_OWNER,
  ackAttempts,
  claimAnonymous,
  enqueueAttempts,
  getActiveUser,
  listParked,
  listPending,
  MAX_PENDING,
  parkAttempts,
  requeueParked,
  setActiveUser,
  SYNC_ACKED_KEY,
  SYNC_QUEUE_KEY,
  unclaimedCount,
  type SyncAttempt,
} from './queue'

function mockStorage() {
  const store = new Map<string, string>()
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    key: (index: number) => [...store.keys()][index] ?? null,
    get length() {
      return store.size
    },
  }
  ;(globalThis as any).localStorage = storage
  return store
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function attempt(word: string, id = word): SyncAttempt {
  return {
    client_event_id: id,
    word,
    mode: 'spell',
    correct: true,
    duration_ms: 10,
    answered_at: '2026-10-18T01:00:00.000Z',
    interval_days: 1,
    next_review_on: '2026-10-19',
  }
}

function sessionFetch(user: string, onAttempts?: (body: { events: Array<Record<string, unknown>> }) => unknown) {
  const calls: string[] = []
  const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(url)
    if (url.endsWith('/auth/me')) return jsonResponse({ ok: true, user: { user_id: user, username: user } })
    if (!url.endsWith('/attempts')) throw new Error(`unexpected ${url}`)
    const body = JSON.parse(String(init?.body)) as { events: Array<Record<string, unknown>> }
    const result = onAttempts ? onAttempts(body) : { accepted: body.events.length, duplicate: 0, rejected: [] }
    return result instanceof Response ? result : jsonResponse(result)
  })
  return { fetchImpl, calls }
}

describe('sync api prefix', () => {
  it('keeps the Nitro routes under the site base', () => {
    expect(syncApiPrefix('/')).toBe('/api/v1')
    expect(syncApiPrefix('/learn/')).toBe('/learn/api/v1')
  })
})

describe('sync attempt ids and dates', () => {
  it('builds a stable 36-char id', () => {
    const id = stableEventId('en:prompt:teach:1000:1')
    expect(id).toHaveLength(36)
    expect(id).toBe(stableEventId('en:prompt:teach:1000:1'))
    expect(historyEventId({ word: 'prompt', mode: 'teach', ts: 1000, correct: true })).toBe(id)
  })

  it('uses the Asia/Shanghai calendar day', () => {
    expect(shanghaiDay(Date.parse('2026-10-17T16:30:00.000Z'))).toBe('2026-10-18')
    expect(shanghaiDay(Date.parse('2026-10-17T15:30:00.000Z'))).toBe('2026-10-17')
  })
})

describe('settings copy for the sync queue', () => {
  const source = readFileSync(resolve(__dirname, '../../pages/settings.vue'), 'utf-8')

  it('shows the cap, the claim step, and a retry for parked events', () => {
    expect(source).toContain('待传 ${pendingCount} 条，已达上限')
    expect(source).toContain('待传 {{ anonymousPending }} 条，已达上限')
    expect(source).toContain('认领到当前账号')
    expect(source).toContain('重新上传')
    expect(source).toContain('data-testid="sync-claim"')
    expect(source).toContain('data-testid="sync-retry"')
    expect(source).toContain('不会记到下一个账号')
  })
})

describe('offline queue and history upload', () => {
  let store: Map<string, string>
  beforeEach(() => {
    store = mockStorage()
  })

  it('keeps a practice answer until the server accepts it', async () => {
    setActiveUser('boss')
    const event = captureAnswer({
      word: 'prompt',
      mode: 'spell',
      correct: false,
      answeredAt: Date.parse('2026-10-18T01:00:00.000Z'),
      durationMs: 1200,
      answerText: 'promt',
      pointId: 'en.prompt',
      level: 'L1',
      intervalDays: 1,
      dueAt: Date.parse('2026-10-18T16:00:00.000Z'),
      wordlistVer: 'v1.0',
    })
    expect(event?.word).toBe('prompt')
    expect(event?.mode).toBe('spell')
    expect(event?.next_review_on).toBe('2026-10-19')
    expect(event?.owner).toBe('boss')
    expect(listPending('boss')).toHaveLength(1)

    const { fetchImpl } = sessionFetch('boss', body => {
      expect(body.events).toHaveLength(1)
      expect(body.events[0].answer_text).toBe('promt')
      expect(body.events[0].interval_days).toBe(1)
      expect(body.events[0].owner).toBeUndefined()
      return { accepted: 1, duplicate: 0, rejected: [] }
    })

    const flushed = await flushSyncQueue(fetchImpl)
    expect(flushed.ok).toBe(true)
    expect(flushed.accepted).toBe(1)
    expect(listPending('boss')).toHaveLength(0)
  })

  it('imports existing practice history once and treats a second upload as already queued', () => {
    recordAnswer('token', 'teach', true, Date.parse('2026-10-01T02:00:00.000Z'))
    recordAnswer('token', 'spell', false, Date.parse('2026-10-02T02:00:00.000Z'))
    saveStat('token', { ...teachStat('token', Date.parse('2026-10-02T02:00:00.000Z')), box: 2, due: Date.parse('2026-10-09T04:00:00.000Z') })

    expect(importEnglishHistory()).toBe(2)
    expect(importEnglishHistory()).toBe(0)
    const pending = listPending(ANONYMOUS_OWNER)
    expect(pending.map(item => item.mode)).toEqual(['teach', 'spell'])
    expect(pending[0].interval_days).toBe(1)
    expect(pending[1].interval_days).toBe(7)
    expect(pending[1].next_review_on).toBe('2026-10-09')
    expect(pending[0].client_event_id).toHaveLength(36)
    expect(pending.every(item => item.owner === ANONYMOUS_OWNER)).toBe(true)
  })

  it('leaves the queue in place when the upload is offline or unauthenticated', async () => {
    setActiveUser('alice')
    captureAnswer({ word: 'queue', mode: 'choice', correct: true, answeredAt: 1_700_000_000_000, intervalDays: 3 })
    const offline = await flushSyncQueue(async () => {
      throw new Error('offline')
    })
    expect(offline.offline).toBe(true)
    expect(offline.pending).toBe(1)
    expect(getActiveUser()).toBe('alice')
    expect(listPending('alice')).toHaveLength(1)

    const denied = await flushSyncQueue(async () => jsonResponse({ message: 'Unauthorized' }, 401))
    expect(denied.needsLogin).toBe(true)
    expect(getActiveUser()).toBeNull()
    expect(listPending('alice')).toHaveLength(1)
    expect(listPending()).toHaveLength(0)
  })

  it('does not upload the previous account after logout', async () => {
    setActiveUser('alice')
    const ts = Date.parse('2026-10-18T01:00:00.000Z')
    recordAnswer('prompt', 'spell', false, ts)
    captureAnswer({
      word: 'prompt',
      mode: 'spell',
      correct: false,
      answeredAt: ts,
      eventId: historyEventId({ word: 'prompt', mode: 'spell', ts, correct: false }),
    })
    await logoutSync(async () => {
      throw new Error('offline')
    })
    expect(getActiveUser()).toBeNull()
    expect(listPending('alice')).toHaveLength(1)
    expect(listPending()).toHaveLength(0)

    const { fetchImpl, calls } = sessionFetch('bob', () => {
      throw new Error('bob must not receive alice')
    })
    const flushed = await flushSyncQueue(fetchImpl)
    expect(flushed.ok).toBe(true)
    expect(flushed.accepted).toBe(0)
    expect(flushed.unclaimed).toBe(0)
    expect(calls.some(url => url.endsWith('/attempts'))).toBe(false)
    expect(listPending('alice')).toHaveLength(1)
    expect(listPending('bob')).toHaveLength(0)
  })

  it('keeps anonymous history unsent until the signed-in user claims it', async () => {
    recordAnswer('token', 'teach', true, Date.parse('2026-10-01T02:00:00.000Z'))
    recordAnswer('token', 'spell', false, Date.parse('2026-10-02T02:00:00.000Z'))
    const posted: Array<Record<string, unknown>> = []
    const first = sessionFetch('bob', body => {
      posted.push(...body.events)
      return { accepted: body.events.length, duplicate: 0, rejected: [] }
    })
    const flushed = await flushSyncQueue(first.fetchImpl)
    expect(flushed.ok).toBe(true)
    expect(flushed.unclaimed).toBe(2)
    expect(posted).toEqual([])
    expect(first.calls.some(url => url.endsWith('/attempts'))).toBe(false)
    expect(listPending('bob')).toHaveLength(0)

    expect(claimAnonymous('bob')).toEqual({ moved: 2, remaining: 0 })
    const second = sessionFetch('bob', body => {
      posted.push(...body.events)
      return { accepted: body.events.length, duplicate: 0, rejected: [] }
    })
    const claimed = await flushSyncQueue(second.fetchImpl)
    expect(claimed.accepted).toBe(2)
    expect(posted).toHaveLength(2)
    expect(posted.every(event => event.owner === undefined)).toBe(true)
    expect(listPending('bob')).toHaveLength(0)
  })

  it('does not upload an event whose owner is a different account', async () => {
    const foreign = { ...attempt('foreign', 'foreign-id'), owner: 'alice' }
    localStorage.setItem(`${SYNC_QUEUE_KEY}:bob`, JSON.stringify([foreign]))
    const { fetchImpl, calls } = sessionFetch('bob', () => {
      throw new Error('foreign owner')
    })
    const flushed = await flushSyncQueue(fetchImpl)
    expect(flushed.ok).toBe(true)
    expect(calls.some(url => url.endsWith('/attempts'))).toBe(false)
    expect(listPending('alice').map(item => item.word)).toEqual(['foreign'])
    expect(listPending('bob')).toHaveLength(0)
  })

  it('stops accepting new records at the cap and keeps the oldest', () => {
    const events = Array.from({ length: MAX_PENDING }, (_, index) => attempt(`w${index}`, `id-${index}`))
    expect(enqueueAttempts(events, 'boss')).toMatchObject({ added: MAX_PENDING, full: true })
    const extra = enqueueAttempts([attempt('w-extra', 'id-extra')], 'boss')
    expect(extra).toMatchObject({ added: 0, skipped: 1, full: true })
    const pending = listPending('boss')
    expect(pending).toHaveLength(MAX_PENDING)
    expect(pending[0].word).toBe('w0')
    expect(pending.some(item => item.word === 'w-extra')).toBe(false)
  })

  it('imports history in segments and continues after a slot frees up', () => {
    const fillers = Array.from({ length: MAX_PENDING - 1 }, (_, index) => attempt(`p${index}`, `p-${index}`))
    enqueueAttempts(fillers, ANONYMOUS_OWNER)
    recordAnswer('alpha', 'teach', true, Date.parse('2026-10-01T02:00:00.000Z'))
    recordAnswer('beta', 'teach', true, Date.parse('2026-10-02T02:00:00.000Z'))
    recordAnswer('gamma', 'teach', true, Date.parse('2026-10-03T02:00:00.000Z'))

    expect(importEnglishHistory()).toBe(1)
    const full = listPending(ANONYMOUS_OWNER)
    expect(full).toHaveLength(MAX_PENDING)
    expect(full[0].word).toBe('p0')
    expect(full.filter(item => item.word === 'alpha')).toHaveLength(1)
    expect(importEnglishHistory()).toBe(0)

    ackAttempts([full[0].client_event_id], ANONYMOUS_OWNER)
    expect(listPending(ANONYMOUS_OWNER)).toHaveLength(MAX_PENDING - 1)
    expect(importEnglishHistory()).toBe(1)
    const continued = listPending(ANONYMOUS_OWNER)
    expect(continued.some(item => item.word === 'p0')).toBe(false)
    expect(continued.filter(item => ['alpha', 'beta', 'gamma'].includes(item.word))).toHaveLength(2)
  })

  it('does not ack a batch when the 200 body is not a matching tally', async () => {
    setActiveUser('boss')
    captureAnswer({ word: 'html', mode: 'spell', correct: true, answeredAt: 1_700_000_000_000 })
    const html = sessionFetch('boss', () => new Response('<html>', { status: 200 }))
    const broken = await flushSyncQueue(html.fetchImpl)
    expect(broken.ok).toBe(false)
    expect(listPending('boss')).toHaveLength(1)

    const short = sessionFetch('boss', () => ({ accepted: 0, duplicate: 0, rejected: [] }))
    const mismatch = await flushSyncQueue(short.fetchImpl)
    expect(mismatch.ok).toBe(false)
    expect(listPending('boss')).toHaveLength(1)

    const nameless = sessionFetch('boss', () => ({
      accepted: 0,
      duplicate: 0,
      rejected: [{ error: 'invalid' }],
    }))
    const unnamed = await flushSyncQueue(nameless.fetchImpl)
    expect(unnamed.ok).toBe(false)
    expect(listPending('boss')).toHaveLength(1)
  })

  it('parks rejected events until the settings page queues them again', async () => {
    setActiveUser('boss')
    const event = captureAnswer({ word: 'bad', mode: 'spell', correct: false, answeredAt: 1_700_000_000_000 })
    const reject = () => ({
      accepted: 0,
      duplicate: 0,
      rejected: [{ client_event_id: event?.client_event_id, error: 'invalid' }],
    })
    const firstFetch = sessionFetch('boss', reject)
    const first = await flushSyncQueue(firstFetch.fetchImpl)
    expect(first.rejected).toBe(1)
    expect(listPending('boss')).toHaveLength(0)
    expect(listParked('boss')).toHaveLength(1)

    const secondFetch = sessionFetch('boss', reject)
    await flushSyncQueue(secondFetch.fetchImpl)
    expect(secondFetch.calls.some(url => url.endsWith('/attempts'))).toBe(false)

    expect(requeueParked('boss').moved).toBe(1)
    expect(listPending('boss')).toHaveLength(1)
    const thirdFetch = sessionFetch('boss', reject)
    await flushSyncQueue(thirdFetch.fetchImpl)
    expect(thirdFetch.calls.some(url => url.endsWith('/attempts'))).toBe(true)
    expect(listParked('boss')).toHaveLength(1)
  })

  it('keeps more than 200 parked events', () => {
    const many = Array.from({ length: 201 }, (_, index) => attempt(`k${index}`, `k-${index}`))
    parkAttempts(many, 'boss')
    expect(listParked('boss')).toHaveLength(201)
  })

  it('logs in with the session cookie and does not keep the password', async () => {
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      expect(url).toBe(`${syncApiPrefix()}/auth/login`)
      expect(init?.credentials).toBe('include')
      expect(JSON.parse(String(init?.body))).toEqual({ username: 'boss', password: 'from-the-form' })
      return jsonResponse({ ok: true, user: { username: 'boss' } })
    })
    const loggedIn = await loginSync(' boss ', 'from-the-form', fetchImpl)
    expect(loggedIn).toEqual({ ok: true, username: 'boss' })
    expect(JSON.stringify(loggedIn)).not.toContain('from-the-form')

    const me = await currentSyncUser(async () => jsonResponse({ ok: true, user: { user_id: 'boss' } }))
    expect(me).toBe('boss')
    expect(localStorage.getItem(ACTIVE_USER_KEY)).toBe('boss')
    expect(localStorage.getItem(SYNC_QUEUE_KEY) || '').not.toContain('from-the-form')
    expect(localStorage.getItem(SYNC_ACKED_KEY)).toBeNull()
    expect([...store.values()].join('\n')).not.toContain('from-the-form')
  })
})
