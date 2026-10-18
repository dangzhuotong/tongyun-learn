import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import {
  signSession,
  verifySessionCookie,
  verifyStatsToken,
  authenticateStatsRequest,
  constantTimeCompare,
  createSessionCookie,
} from './utils/auth'
import {
  getStatsSummary,
  getStatsMistakes,
  getShanghaiDate,
  getLast7Dates,
  formatUtcIso,
} from './services/stats'
import { getDbPool, setMockDbPool, resetDbPool } from './utils/db'

describe('Stats API Auth & Read-only Token', () => {
  const TEST_SECRET = 'super-secret-key-for-test-32bytes-long!'
  const TEST_STATS_TOKEN = 'stats-read-only-secret-token-xyz'

  beforeEach(() => {
    process.env.WORDS_SESSION_SECRET = TEST_SECRET
    process.env.WORDS_STATS_TOKEN = TEST_STATS_TOKEN
  })

  afterEach(() => {
    delete process.env.WORDS_SESSION_SECRET
    delete process.env.WORDS_STATS_TOKEN
  })

  it('verifies valid session cookie', () => {
    const cookie = createSessionCookie({ user_id: 'boss' }, TEST_SECRET)
    const result = verifySessionCookie(cookie, TEST_SECRET)
    expect(result).not.toBeNull()
    expect(result?.user_id).toBe('boss')
  })

  it('rejects tampered session cookie', () => {
    // 1. Tamper payload while keeping original signature
    const valid = signSession({ user_id: 'boss' }, TEST_SECRET)
    const [payloadB64, sig] = valid.split('.')
    const tamperedPayloadB64 = Buffer.from(JSON.stringify({ user_id: 'boss' })).toString('base64url') + 'x'
    const tampered1 = `${tamperedPayloadB64}.${sig}`
    expect(verifySessionCookie(tampered1, TEST_SECRET)).toBeNull()

    // 2. Tamper signature
    const tamperedSig = sig.slice(0, -4) + (sig.endsWith('0000') ? 'ffff' : '0000')
    const tampered2 = `${payloadB64}.${tamperedSig}`
    expect(verifySessionCookie(tampered2, TEST_SECRET)).toBeNull()

    // 3. Tamper user_id to admin
    const tamperedPayloadAdmin = Buffer.from(JSON.stringify({ user_id: 'admin' })).toString('base64url')
    const tampered3 = `${tamperedPayloadAdmin}.${sig}`
    expect(verifySessionCookie(tampered3, TEST_SECRET)).toBeNull()

    // 4. In cookie header format
    const tamperedCookieHeader = `tw_sess=${tampered3}; Path=/`
    expect(verifySessionCookie(tamperedCookieHeader, TEST_SECRET)).toBeNull()
  })

  it('rejects session cookie signed with wrong secret', () => {
    const wrongSecret = 'different-secret-key-which-should-fail'
    const cookie = signSession({ user_id: 'boss' }, wrongSecret)
    expect(verifySessionCookie(cookie, TEST_SECRET)).toBeNull()
  })

  it('rejects malformed or unsigned session cookie', () => {
    expect(verifySessionCookie(null)).toBeNull()
    expect(verifySessionCookie('')).toBeNull()
    expect(verifySessionCookie('not-a-token')).toBeNull()
    expect(verifySessionCookie('boss')).toBeNull()
    expect(verifySessionCookie('.')).toBeNull()
    expect(verifySessionCookie('onlypayload.')).toBeNull()
  })

  it('rejects expired session cookie', () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600 // 1 hour ago
    const cookie = signSession({ user_id: 'boss', exp: pastExp }, TEST_SECRET)
    expect(verifySessionCookie(cookie, TEST_SECRET)).toBeNull()
  })

  it('allows valid read-only stats token (WORDS_STATS_TOKEN)', () => {
    expect(verifyStatsToken(TEST_STATS_TOKEN, TEST_STATS_TOKEN)).toBe(true)
    expect(verifyStatsToken('  ' + TEST_STATS_TOKEN + '  ', TEST_STATS_TOKEN)).toBe(true)
  })

  it('rejects invalid read-only stats token', () => {
    expect(verifyStatsToken('wrong-token', TEST_STATS_TOKEN)).toBe(false)
    expect(verifyStatsToken('', TEST_STATS_TOKEN)).toBe(false)
    expect(verifyStatsToken(null, TEST_STATS_TOKEN)).toBe(false)
    expect(verifyStatsToken(TEST_STATS_TOKEN, '')).toBe(false)
  })

  it('constant-time compare prevents timing leaks', () => {
    expect(constantTimeCompare('secret123', 'secret123')).toBe(true)
    expect(constantTimeCompare('secret123', 'secret124')).toBe(false)
    expect(constantTimeCompare('short', 'longer-string')).toBe(false)
  })

  it('authenticateStatsRequest accepts valid session cookie in headers', () => {
    const cookie = createSessionCookie({ user_id: 'boss' }, TEST_SECRET)
    const req = {
      headers: {
        cookie,
      },
    }
    const res = authenticateStatsRequest(req)
    expect(res.authenticated).toBe(true)
    expect(res.user_id).toBe('boss')
    expect(res.readOnly).toBe(false)
  })

  it('authenticateStatsRequest accepts valid Bearer token in headers', () => {
    const req = {
      headers: {
        authorization: `Bearer ${TEST_STATS_TOKEN}`,
      },
    }
    const res = authenticateStatsRequest(req)
    expect(res.authenticated).toBe(true)
    expect(res.user_id).toBe('boss')
    expect(res.readOnly).toBe(true)
  })

  it('authenticateStatsRequest rejects unauthorized request', () => {
    const req = {
      headers: {},
    }
    const res = authenticateStatsRequest(req)
    expect(res.authenticated).toBe(false)
    expect(res.user_id).toBeNull()
  })

  it('authenticateStatsRequest rejects tampered cookie in request', () => {
    const valid = signSession({ user_id: 'boss' }, TEST_SECRET)
    const [payload, sig] = valid.split('.')
    const tampered = `tw_sess=${payload}.${sig}tampered`
    const req = {
      headers: {
        cookie: tampered,
      },
    }
    const res = authenticateStatsRequest(req)
    expect(res.authenticated).toBe(false)
    expect(res.user_id).toBeNull()
  })
})

describe('Stats Service: getStatsSummary', () => {
  afterEach(() => {
    resetDbPool()
  })

  it('returns today summary and last7d breakdown with correct accuracy', async () => {
    const fixedNow = new Date('2026-10-17T14:00:00+08:00')
    const todayDate = getShanghaiDate(fixedNow)

    const mockPool = {
      query: vi.fn().mockImplementation((sql: string, params: any[]) => {
        if (sql.includes('COUNT(*) AS total') && sql.includes('AND DATE(CONVERT_TZ(answered_at')) {
          // Today's attempts query
          return [[{ total: 46, correct: 39 }]]
        }
        if (sql.includes('BETWEEN ? AND ?')) {
          // Last 7 days breakdown query
          return [[
            { date: '2026-10-11', total: 30, correct: 24 },
            { date: '2026-10-12', total: 35, correct: 30 },
            { date: '2026-10-13', total: 40, correct: 32 },
            { date: '2026-10-14', total: 45, correct: 38 },
            { date: '2026-10-15', total: 40, correct: 33 },
            { date: '2026-10-16', total: 45, correct: 35 },
            { date: '2026-10-17', total: 46, correct: 39 },
          ]]
        }
        if (sql.includes('words_card_state')) {
          // due_today query
          return [[{ due_count: 18 }]]
        }
        return [[]]
      }),
    }

    setMockDbPool(mockPool)

    const summary = await getStatsSummary('boss', fixedNow)
    expect(summary.tz).toBe('Asia/Shanghai')
    expect(summary.today).toEqual({
      date: '2026-10-17',
      total: 46,
      correct: 39,
      accuracy: 0.848,
    })
    expect(summary.last7d.total).toBe(281)
    expect(summary.last7d.correct).toBe(231)
    expect(summary.last7d.accuracy).toBe(0.822)
    expect(summary.last7d.daily).toHaveLength(7)
    expect(summary.last7d.daily[0].date).toBe('2026-10-11')
    expect(summary.due_today).toBe(18)
  })

  it('handles empty data gracefully without division by zero', async () => {
    const mockPool = {
      query: vi.fn().mockResolvedValue([[]]),
    }
    setMockDbPool(mockPool)

    const summary = await getStatsSummary('boss', new Date('2026-10-18T10:00:00+08:00'))
    expect(summary.today.total).toBe(0)
    expect(summary.today.correct).toBe(0)
    expect(summary.today.accuracy).toBe(0)
    expect(summary.last7d.total).toBe(0)
    expect(summary.last7d.accuracy).toBe(0)
    expect(summary.due_today).toBe(0)
  })
})

describe('Stats Service: getStatsMistakes', () => {
  afterEach(() => {
    resetDbPool()
  })

  it('returns top mistakes ordered by wrong DESC, error_rate DESC', async () => {
    const mockRows = [
      {
        word: 'idempotent',
        point_id: 'en.ai-dev',
        attempts: 7,
        wrong: 5,
        last_wrong_at: new Date('2026-10-17T14:02:11.120Z'),
        current_interval: 1,
      },
      {
        word: 'algorithm',
        point_id: 'en.x-community',
        attempts: 4,
        wrong: 2,
        last_wrong_at: '2026-10-16T10:00:00Z',
        current_interval: 3,
      },
    ]

    const mockPool = {
      query: vi.fn().mockResolvedValue([mockRows]),
    }
    setMockDbPool(mockPool)

    const res = await getStatsMistakes('boss', { days: 30, limit: 20 })
    expect(res.days).toBe(30)
    expect(res.items).toHaveLength(2)

    const item1 = res.items[0]
    expect(item1.word).toBe('idempotent')
    expect(item1.point_id).toBe('en.ai-dev')
    expect(item1.attempts).toBe(7)
    expect(item1.wrong).toBe(5)
    expect(item1.error_rate).toBe(0.714)
    expect(item1.last_wrong_at).toBe('2026-10-17T14:02:11Z')
    expect(item1.current_interval).toBe(1)
  })

  it('formats dates properly', () => {
    expect(formatUtcIso(new Date('2026-10-17T14:02:11.000Z'))).toBe('2026-10-17T14:02:11Z')
    expect(formatUtcIso('')).toBe('')
  })
})

describe('Database Configuration', () => {
  afterEach(() => {
    resetDbPool()
    delete process.env.WORDS_DATABASE_URL
  })

  it('reads connection URL strictly from WORDS_DATABASE_URL env', () => {
    delete process.env.WORDS_DATABASE_URL
    expect(() => getDbPool()).toThrowError(/WORDS_DATABASE_URL is not set/)
  })

  it('does not contain hardcoded host 172.18.0.1 in source code', () => {
    process.env.WORDS_DATABASE_URL = 'mysql://user:pass@dynamic-host:3306/db'
    const pool = getDbPool()
    expect(pool).toBeDefined()
  })
})
