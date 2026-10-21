import { beforeEach, describe, expect, it, vi } from 'vitest'
import { recordAnswer } from '../english/records'
import { saveStat, teachStat } from '../english/wordlist'
import { captureAnswer } from './capture'
import { currentSyncUser, flushSyncQueue, loginSync, syncApiPrefix } from './client'
import { historyEventId, importEnglishHistory } from './history'
import { shanghaiDay, stableEventId } from './event'
import { listPending, SYNC_ACKED_KEY, SYNC_QUEUE_KEY } from './queue'

function mockStorage() {
  const store = new Map<string, string>()
  ;(globalThis as any).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  }
  return store
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
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

describe('offline queue and history upload', () => {
  beforeEach(() => mockStorage())

  it('keeps a practice answer until the server accepts it', async () => {
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
    expect(listPending()).toHaveLength(1)

    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      expect(url).toBe(`${syncApiPrefix()}/attempts`)
      expect(init?.credentials).toBe('include')
      const body = JSON.parse(String(init?.body))
      expect(body.events).toHaveLength(1)
      expect(body.events[0].answer_text).toBe('promt')
      expect(body.events[0].interval_days).toBe(1)
      return jsonResponse({ accepted: 1, duplicate: 0, rejected: [] })
    })

    const flushed = await flushSyncQueue(fetchImpl)
    expect(flushed.ok).toBe(true)
    expect(flushed.accepted).toBe(1)
    expect(listPending()).toHaveLength(0)
  })

  it('imports existing practice history once and treats a second upload as already queued', () => {
    recordAnswer('token', 'teach', true, Date.parse('2026-10-01T02:00:00.000Z'))
    recordAnswer('token', 'spell', false, Date.parse('2026-10-02T02:00:00.000Z'))
    saveStat('token', { ...teachStat('token', Date.parse('2026-10-02T02:00:00.000Z')), box: 2, due: Date.parse('2026-10-09T04:00:00.000Z') })

    expect(importEnglishHistory()).toBe(2)
    expect(importEnglishHistory()).toBe(0)
    const pending = listPending()
    expect(pending.map(item => item.mode)).toEqual(['teach', 'spell'])
    expect(pending[0].interval_days).toBe(1)
    expect(pending[1].interval_days).toBe(7)
    expect(pending[1].next_review_on).toBe('2026-10-09')
    expect(pending[0].client_event_id).toHaveLength(36)
  })

  it('leaves the queue in place when the upload is offline or unauthenticated', async () => {
    captureAnswer({ word: 'queue', mode: 'choice', correct: true, answeredAt: 1_700_000_000_000, intervalDays: 3 })
    const offline = await flushSyncQueue(async () => {
      throw new Error('offline')
    })
    expect(offline.offline).toBe(true)
    expect(offline.pending).toBe(1)

    const denied = await flushSyncQueue(async () => jsonResponse({ message: 'Unauthorized' }, 401))
    expect(denied.needsLogin).toBe(true)
    expect(listPending()).toHaveLength(1)
  })

  it('parks rejected events and does not send them again', async () => {
    const event = captureAnswer({ word: 'bad', mode: 'spell', correct: false, answeredAt: 1_700_000_000_000 })
    const fetchImpl = vi.fn(async () =>
      jsonResponse({
        accepted: 0,
        duplicate: 0,
        rejected: [{ client_event_id: event?.client_event_id, error: 'invalid' }],
      })
    )
    const first = await flushSyncQueue(fetchImpl)
    expect(first.rejected).toBe(1)
    expect(listPending()).toHaveLength(0)
    await flushSyncQueue(fetchImpl)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
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
    expect(localStorage.getItem(SYNC_QUEUE_KEY) || '').not.toContain('from-the-form')
    expect(localStorage.getItem(SYNC_ACKED_KEY)).toBeNull()
  })
})
