import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createEvent } from 'h3'
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import attemptsHandler from './routes/words/api/v1/attempts.post'
import stateHandler from './routes/words/api/v1/state.get'
import { resetDbPool, setDbPool } from './utils/db'
import bcrypt from 'bcryptjs'
import {
  signSessionToken,
  verifySessionToken,
  comparePassword,
  checkLoginRateLimit,
  resetLoginRateLimits,
} from './utils/auth'
import {
  validateAttemptEvent,
  BatchAttemptsPayloadSchema,
  processAttemptsBatch,
} from './utils/attempts'
import { fetchCardStates } from './utils/state'
import { getShanghaiDate, getStatsMistakes, getStatsSummary } from './services/stats'
import { getHealthStatus } from './utils/health'

describe('server/utils/auth', () => {
  beforeEach(() => {
    resetLoginRateLimits()
  })

  it('signs and verifies a valid session token', () => {
    const secret = 'test-secret-123456'
    const token = signSessionToken('boss', secret, 3600)
    expect(token).toBeDefined()
    expect(token.includes('.')).toBe(true)

    const verified = verifySessionToken(token, secret)
    expect(verified).not.toBeNull()
    expect(verified?.userId).toBe('boss')
  })

  it('rejects tampered session token', () => {
    const secret = 'test-secret-123456'
    const token = signSessionToken('boss', secret, 3600)
    const tampered = token.slice(0, -4) + 'abcd'

    const verified = verifySessionToken(tampered, secret)
    expect(verified).toBeNull()
  })

  it('rejects session token signed with different secret', () => {
    const token = signSessionToken('boss', 'secret-A', 3600)
    const verified = verifySessionToken(token, 'secret-B')
    expect(verified).toBeNull()
  })

  it('rejects expired session token', () => {
    const secret = 'test-secret-123456'
    // -10 seconds maxAge
    const token = signSessionToken('boss', secret, -10)
    const verified = verifySessionToken(token, secret)
    expect(verified).toBeNull()
  })

  it('rejects null or invalid string tokens', () => {
    expect(verifySessionToken(null)).toBeNull()
    expect(verifySessionToken('')).toBeNull()
    expect(verifySessionToken('not-a-valid-token')).toBeNull()
  })

  it('compares bcrypt passwords correctly', () => {
    const salt = bcrypt.genSaltSync(8)
    const hash = bcrypt.hashSync('my-secure-password', salt)

    expect(comparePassword('my-secure-password', hash)).toBe(true)
    expect(comparePassword('wrong-password', hash)).toBe(false)
    expect(comparePassword('', hash)).toBe(false)
  })

  it('rate limits login attempts to 5 per minute per IP', () => {
    const ip = '192.168.1.100'

    for (let i = 1; i <= 5; i++) {
      const res = checkLoginRateLimit(ip, 5, 60000)
      expect(res.allowed).toBe(true)
      expect(res.remaining).toBe(5 - i)
    }

    // 6th attempt should be blocked
    const blocked = checkLoginRateLimit(ip, 5, 60000)
    expect(blocked.allowed).toBe(false)
    expect(blocked.remaining).toBe(0)

    // Different IP should still be allowed
    const otherIpRes = checkLoginRateLimit('192.168.1.101', 5, 60000)
    expect(otherIpRes.allowed).toBe(true)
  })
})

describe('server/utils/attempts validation', () => {
  it('accepts valid attempt event', () => {
    const validRaw = {
      client_event_id: '123e4567-e89b-12d3-a456-426614174000',
      word: 'idempotent',
      point_id: 'en.ai-dev',
      level: 'L1',
      mode: 'recall',
      correct: false,
      duration_ms: 8420,
      answer_text: 'idempotant',
      answered_at: '2026-10-17T14:02:11.120Z',
      interval_days: 1,
      next_review_on: '2026-10-18',
      wordlist_ver: 'v0.2',
    }

    const res = validateAttemptEvent(validRaw)
    expect(res.success).toBe(true)
    expect(res.data?.word).toBe('idempotent')
    expect(res.data?.interval_days).toBe(1)
  })

  it('rejects attempt with invalid interval_days', () => {
    const invalidInterval = {
      client_event_id: '123e4567-e89b-12d3-a456-426614174000',
      word: 'idempotent',
      mode: 'recall',
      correct: true,
      duration_ms: 3000,
      answered_at: '2026-10-17T14:02:11.120Z',
      interval_days: 5, // Not in [1, 3, 7, 14, 30]
      next_review_on: '2026-10-18',
    }

    const res = validateAttemptEvent(invalidInterval)
    expect(res.success).toBe(false)
    expect(res.error).toContain('interval_days')
  })

  it('rejects attempt with invalid date format for next_review_on', () => {
    const invalidDate = {
      client_event_id: '123e4567-e89b-12d3-a456-426614174000',
      word: 'test',
      mode: 'recall',
      correct: true,
      duration_ms: 3000,
      answered_at: '2026-10-17T14:02:11.120Z',
      interval_days: 3,
      next_review_on: '2026/10/18', // should be YYYY-MM-DD
    }

    const res = validateAttemptEvent(invalidDate)
    expect(res.success).toBe(false)
    expect(res.error).toContain('next_review_on')
  })

  it('rejects batch payload exceeding 200 events', () => {
    const events = Array.from({ length: 201 }, (_, i) => ({
      client_event_id: `id-${i}`,
      word: 'word',
    }))

    const parsed = BatchAttemptsPayloadSchema.safeParse({ events })
    expect(parsed.success).toBe(false)
  })
})

describe('server/utils/attempts processing (idempotency & DB logic)', () => {
  it('processes batch with new and duplicate events correctly', async () => {
    const queriesExecuted: string[] = []
    const mockConn = {
      beginTransaction: vi.fn().mockResolvedValue(undefined),
      commit: vi.fn().mockResolvedValue(undefined),
      rollback: vi.fn().mockResolvedValue(undefined),
      release: vi.fn(),
      query: vi.fn().mockImplementation((sql: string, params: any) => {
        queriesExecuted.push(sql)
        // 模拟查找已存在 ID：假设 event-dup 已经存在
        if (sql.includes('SELECT client_event_id FROM words_attempts')) {
          return [[{ client_event_id: 'event-dup' }]]
        }
        return [{ affectedRows: 1 }]
      }),
    }

    const mockPool: any = {
      getConnection: vi.fn().mockResolvedValue(mockConn),
    }

    const events = [
      {
        client_event_id: 'event-new-1',
        word: 'apple',
        correct: true,
        duration_ms: 1200,
        answered_at: '2026-10-17T10:00:00.000Z',
        interval_days: 3,
        next_review_on: '2026-10-20',
      },
      {
        client_event_id: 'event-dup',
        word: 'banana',
        correct: false,
        duration_ms: 4500,
        answered_at: '2026-10-17T10:05:00.000Z',
        interval_days: 1,
        next_review_on: '2026-10-18',
      },
      {
        // 格式非法事件，应进 rejected
        client_event_id: 'event-invalid',
        word: '',
        correct: true,
        duration_ms: -5,
        answered_at: 'invalid-date',
        interval_days: 99,
        next_review_on: 'bad',
      },
    ]

    const result = await processAttemptsBatch(mockPool, 'boss', events)

    expect(result.accepted).toBe(1)
    expect(result.duplicate).toBe(1)
    expect(result.rejected.length).toBe(1)
    expect(result.rejected[0].client_event_id).toBe('event-invalid')
    expect(mockConn.commit).toHaveBeenCalled()
  })

  it('handles in-batch duplicate event ids', async () => {
    const mockConn = {
      beginTransaction: vi.fn().mockResolvedValue(undefined),
      commit: vi.fn().mockResolvedValue(undefined),
      rollback: vi.fn().mockResolvedValue(undefined),
      release: vi.fn(),
      query: vi.fn().mockImplementation((sql: string) => {
        if (sql.includes('SELECT client_event_id FROM words_attempts')) {
          return [[]] // 库里没有
        }
        return [{ affectedRows: 1 }]
      }),
    }

    const mockPool: any = {
      getConnection: vi.fn().mockResolvedValue(mockConn),
    }

    const sameEvent = {
      client_event_id: 'same-uuid',
      word: 'cherry',
      correct: true,
      duration_ms: 2000,
      answered_at: '2026-10-17T11:00:00.000Z',
      interval_days: 7,
      next_review_on: '2026-10-24',
    }

    const result = await processAttemptsBatch(mockPool, 'boss', [sameEvent, sameEvent])

    expect(result.accepted).toBe(1)
    expect(result.duplicate).toBe(1)
    expect(result.rejected.length).toBe(0)
  })

  it('pre-check empty but insert raises ER_DUP_ENTRY: duplicate, no card-state write', async () => {
    const cardStateSql: string[] = []
    const mockConn = {
      beginTransaction: vi.fn().mockResolvedValue(undefined),
      commit: vi.fn().mockResolvedValue(undefined),
      rollback: vi.fn().mockResolvedValue(undefined),
      release: vi.fn(),
      query: vi.fn().mockImplementation((sql: string) => {
        if (sql.includes('SELECT client_event_id FROM words_attempts')) {
          return [[]]
        }
        if (sql.includes('INSERT INTO words_attempts')) {
          expect(sql).not.toMatch(/ON DUPLICATE KEY UPDATE|IGNORE/)
          const err = new Error("Duplicate entry 'race-uuid' for key 'words_attempts.uk_client_event'") as Error & {
            code: string
            errno: number
          }
          err.code = 'ER_DUP_ENTRY'
          err.errno = 1062
          throw err
        }
        if (sql.includes('words_card_state')) {
          cardStateSql.push(sql)
          return [{ affectedRows: 1 }]
        }
        return [{ affectedRows: 1 }]
      }),
    }
    const mockPool: any = {
      getConnection: vi.fn().mockResolvedValue(mockConn),
    }
    const event = {
      client_event_id: 'race-uuid',
      word: 'apple',
      correct: false,
      duration_ms: 1200,
      answered_at: '2026-10-17T10:00:00.000Z',
      interval_days: 1,
      next_review_on: '2026-10-18',
    }

    const result = await processAttemptsBatch(mockPool, 'boss', [event])

    expect(result.accepted).toBe(0)
    expect(result.duplicate).toBe(1)
    expect(result.rejected).toEqual([])
    expect(cardStateSql).toEqual([])
    expect(mockConn.commit).toHaveBeenCalled()
    expect(mockConn.rollback).not.toHaveBeenCalled()
  })

  it('throws non-duplicate insert errors and does not count them as duplicates', async () => {
    const cardStateSql: string[] = []
    const mockConn = {
      beginTransaction: vi.fn().mockResolvedValue(undefined),
      commit: vi.fn().mockResolvedValue(undefined),
      rollback: vi.fn().mockResolvedValue(undefined),
      release: vi.fn(),
      query: vi.fn().mockImplementation((sql: string) => {
        if (sql.includes('SELECT client_event_id FROM words_attempts')) {
          return [[]]
        }
        if (sql.includes('INSERT INTO words_attempts')) {
          const err = new Error('Data too long for column \'word\'') as Error & { code: string; errno: number }
          err.code = 'ER_DATA_TOO_LONG'
          err.errno = 1406
          throw err
        }
        if (sql.includes('words_card_state')) {
          cardStateSql.push(sql)
        }
        return [{ affectedRows: 1 }]
      }),
    }
    const mockPool: any = {
      getConnection: vi.fn().mockResolvedValue(mockConn),
    }
    const event = {
      client_event_id: 'trunc-uuid',
      word: 'apple',
      correct: true,
      duration_ms: 1200,
      answered_at: '2026-10-17T10:00:00.000Z',
      interval_days: 1,
      next_review_on: '2026-10-18',
    }

    await expect(processAttemptsBatch(mockPool, 'boss', [event])).rejects.toThrow(/Data too long/)
    expect(cardStateSql).toEqual([])
    expect(mockConn.commit).not.toHaveBeenCalled()
    expect(mockConn.rollback).toHaveBeenCalled()
    expect(mockConn.release).toHaveBeenCalled()
  })

  it('writes the batch in client_event_id order', async () => {
    const inserted: string[] = []
    const mockConn = {
      beginTransaction: vi.fn().mockResolvedValue(undefined),
      commit: vi.fn().mockResolvedValue(undefined),
      rollback: vi.fn().mockResolvedValue(undefined),
      release: vi.fn(),
      query: vi.fn().mockImplementation((sql: string, params: unknown[]) => {
        if (sql.includes('SELECT client_event_id FROM words_attempts')) {
          return [[]]
        }
        if (sql.includes('INSERT INTO words_attempts')) {
          expect(sql).not.toMatch(/ON DUPLICATE KEY UPDATE|IGNORE/)
          inserted.push(String(params[0]))
        }
        return [{ affectedRows: 1 }]
      }),
    }
    const mockPool: any = {
      getConnection: vi.fn().mockResolvedValue(mockConn),
    }
    const row = (client_event_id: string, answered_at: string) => ({
      client_event_id,
      word: `w-${client_event_id}`,
      correct: true,
      duration_ms: 1000,
      answered_at,
      interval_days: 1,
      next_review_on: '2026-10-18',
    })

    const result = await processAttemptsBatch(mockPool, 'boss', [
      row('c-id', '2026-10-17T08:00:00.000Z'),
      row('a-id', '2026-10-17T12:00:00.000Z'),
      row('b-id', '2026-10-17T10:00:00.000Z'),
    ])

    expect(inserted).toEqual(['a-id', 'b-id', 'c-id'])
    expect(result.accepted).toBe(3)
    expect(result.duplicate).toBe(0)
  })
})

describe('server/utils/state', () => {
  it('fetches card states with formatted date and optional since filter', async () => {
    const mockRows = [
      {
        user_id: 'boss',
        word: 'idempotent',
        point_id: 'en.ai-dev',
        interval_days: 3,
        next_review_on: '2026-10-20',
        reps: 4,
        lapses: 1,
        last_answered_at: new Date('2026-10-17T14:02:11.120Z'),
      },
    ]

    let executedSql = ''
    const mockPool: any = {
      query: vi.fn().mockImplementation((sql: string) => {
        executedSql = sql
        return [mockRows]
      }),
    }

    const res = await fetchCardStates(mockPool, 'boss', '2026-10-17T00:00:00Z')
    expect(res.items.length).toBe(1)
    expect(res.items[0].word).toBe('idempotent')
    expect(res.items[0].interval_days).toBe(3)
    expect(res.items[0].next_review_on).toBe('2026-10-20')
    expect(res.items[0].last_answered_at).toContain('2026-10-17T14:02:11.120Z')
    expect(executedSql).toContain('AND last_answered_at > ?')
  })
})

describe('server/services/stats', () => {
  afterEach(() => {
    resetDbPool()
  })

  it('formats shanghai date as YYYY-MM-DD', () => {
    const d = getShanghaiDate(new Date('2026-10-17T20:00:00Z'))
    expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('calculates summary metrics and daily breakdown', async () => {
    const mockPool: any = {
      query: vi.fn().mockImplementation((sql: string) => {
        if (/GROUP BY/i.test(sql)) {
          return [
            [
              { date: '2026-10-16', total: 20, correct: 18 },
              { date: '2026-10-17', total: 46, correct: 39 },
            ],
          ]
        }
        if (sql.includes('COUNT(*) AS total') && sql.includes('answered_at >=')) {
          return [[{ total: 46, correct: 39 }]]
        }
        if (sql.includes('words_card_state')) {
          return [[{ due_count: 18 }]]
        }
        return [[]]
      }),
    }
    setDbPool(mockPool)

    const summary = await getStatsSummary('boss', new Date('2026-10-17T12:00:00+08:00'))
    expect(summary.tz).toBe('Asia/Shanghai')
    expect(summary.today.total).toBe(46)
    expect(summary.today.correct).toBe(39)
    expect(summary.today.accuracy).toBe(0.848)
    expect(summary.last7d.total).toBe(66)
    expect(summary.due_today).toBe(18)
    expect(summary.last7d.daily).toHaveLength(7)
    expect(summary.last7d.daily.find(day => day.date === '2026-10-16')).toMatchObject({ total: 20, correct: 18 })
    expect(summary.last7d.daily.find(day => day.date === '2026-10-17')).toMatchObject({ total: 46, correct: 39 })
  })

  it('fetches top mistakes with attempts >= 2', async () => {
    const mockRows = [
      {
        word: 'idempotent',
        point_id: 'en.ai-dev',
        attempts: 7,
        wrong: 5,
        error_rate: 0.714,
        last_wrong_at: new Date('2026-10-17T14:02:11.000Z'),
        current_interval: 1,
      },
    ]

    setDbPool({
      query: vi.fn().mockResolvedValue([mockRows]),
    })

    const mistakes = await getStatsMistakes('boss', { days: 30, limit: 20 })
    expect(mistakes.days).toBe(30)
    expect(mistakes.items.length).toBe(1)
    expect(mistakes.items[0].word).toBe('idempotent')
    expect(mistakes.items[0].error_rate).toBe(0.714)
  })
})

describe('read-only stats token cannot call write routes', () => {
  const STATS_TOKEN = 'stats-read-only-secret-token-xyz'

  afterEach(() => {
    delete process.env.WORDS_STATS_TOKEN
    resetDbPool()
  })

  function bearerEvent(method: string, url: string) {
    const req = new IncomingMessage(new Socket())
    req.method = method
    req.url = url
    req.headers = {
      authorization: `Bearer ${STATS_TOKEN}`,
      'content-type': 'application/json',
    }
    return createEvent(req, new ServerResponse(req))
  }

  it('POST /attempts and GET /state return 401 and do not touch the database', async () => {
    process.env.WORDS_STATS_TOKEN = STATS_TOKEN
    const pool = {
      query: vi.fn(),
      getConnection: vi.fn(),
    }
    setDbPool(pool as any)

    await expect(attemptsHandler(bearerEvent('POST', '/words/api/v1/attempts'))).rejects.toMatchObject({
      statusCode: 401,
    })
    await expect(stateHandler(bearerEvent('GET', '/words/api/v1/state'))).rejects.toMatchObject({
      statusCode: 401,
    })
    expect(pool.query).not.toHaveBeenCalled()
    expect(pool.getConnection).not.toHaveBeenCalled()
  })
})

describe('server/utils/health', () => {
  it('returns ok status', async () => {
    setDbPool(null)
    const health = await getHealthStatus()
    expect(health.status).toBe('ok')
    expect(health.uptime).toBeGreaterThanOrEqual(0)
    expect(health.time).toBeDefined()
  })
})
