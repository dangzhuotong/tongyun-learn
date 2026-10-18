import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchStatsSummary } from './utils/stats'
import { getLast7Dates, getShanghaiDate, getStatsSummary } from './services/stats'
import { resetDbPool, setMockDbPool } from './utils/db'

/**
 * Pins the stats miscount (46 vs 66, 0 vs 281) to either:
 * - the date window (today's aggregate reused for the last-7-day query), or
 * - the timezone (UTC calendar / runner TZ vs Asia/Shanghai).
 *
 * The boundary instant is 2026-10-17T16:30:00.000Z.
 * UTC calendar day: 2026-10-17. Asia/Shanghai calendar day: 2026-10-18.
 * Run this file under TZ=UTC and TZ=Asia/Shanghai. The two processes must agree.
 */

const BOUNDARY = new Date('2026-10-17T16:30:00.000Z')
const SHANGHAI_TODAY = '2026-10-18'
const UTC_TODAY = '2026-10-17'

function tzContext(): string {
  const runnerLocal = runnerLocalDay(BOUNDARY)
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return [
    `TZ=${process.env.TZ ?? '(unset)'}`,
    `resolved=${zone}`,
    `offsetMin=${BOUNDARY.getTimezoneOffset()}`,
    `runnerLocal=${runnerLocal}`,
    `utc=${UTC_TODAY}`,
    `shanghai=${SHANGHAI_TODAY}`,
  ].join(' ')
}

function runnerLocalDay(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function useBoundaryClock() {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(BOUNDARY)
}

describe('stats miscount: date window vs timezone', () => {
  afterEach(() => {
    vi.useRealTimers()
    resetDbPool()
  })

  it('Shanghai calendar day stays 2026-10-18 at 16:30Z under this runner TZ', () => {
    useBoundaryClock()
    const shanghai = getShanghaiDate(BOUNDARY)
    const runnerLocal = runnerLocalDay(BOUNDARY)
    const utc = BOUNDARY.toISOString().slice(0, 10)

    expect(utc, tzContext()).toBe(UTC_TODAY)
    expect(shanghai, tzContext()).toBe(SHANGHAI_TODAY)
    expect(getLast7Dates(SHANGHAI_TODAY), tzContext()).toEqual([
      '2026-10-12',
      '2026-10-13',
      '2026-10-14',
      '2026-10-15',
      '2026-10-16',
      '2026-10-17',
      '2026-10-18',
    ])

    // If this fails only when runnerLocal !== Shanghai, the counter follows the runner TZ.
    // If shanghai === utc, the counter follows UTC. Both are timezone bugs.
    expect(shanghai, `timezone follow: ${tzContext()}`).not.toBe(utc)
    if (runnerLocal !== SHANGHAI_TODAY) {
      expect(shanghai, `runner TZ leaked: ${tzContext()}`).not.toBe(runnerLocal)
    }
  })

  it('repro t101: last7d total is the 7-day window (66), not today alone (46)', async () => {
    useBoundaryClock()
    const sqls: string[] = []
    const mockPool: any = {
      query: vi.fn().mockImplementation((sql: string) => {
        sqls.push(sql.replace(/\s+/g, ' '))
        // Same dispatch as server/api.test.ts. The today predicate is checked first.
        if (sql.includes('DATE(CONVERT_TZ(answered_at')) {
          return [[{ total: 46, correct: 39 }]]
        }
        if (sql.includes('GROUP BY day')) {
          return [[
            { day: '2026-10-17', total: 20, correct: 18 },
            { day: '2026-10-18', total: 46, correct: 39 },
          ]]
        }
        if (sql.includes('COUNT(*) AS count FROM words_card_state')) {
          return [[{ count: 18 }]]
        }
        return [[]]
      }),
    }

    const summary = await fetchStatsSummary(mockPool, 'boss')
    const last7Sql = sqls.find(sql => sql.includes('GROUP BY') || sql.includes('INTERVAL 6') || sql.includes('BETWEEN'))
    const collapsed = last7Sql?.includes('DATE(CONVERT_TZ(answered_at') ?? false
    expect(summary.today.total, tzContext()).toBe(46)
    expect(
      summary.last7d.total,
      `DATE_WINDOW collapsed=${collapsed} last7=${summary.last7d.total} today=${summary.today.total} ${tzContext()} sql=${last7Sql}`
    ).toBe(66)
  })

  it('repro t102: last7d total is 281 when day keys match, not 0', async () => {
    useBoundaryClock()
    const sqls: string[] = []
    const mockPool = {
      query: vi.fn().mockImplementation((sql: string) => {
        sqls.push(sql.replace(/\s+/g, ' '))
        // Same dispatch as server/stats.test.ts. Today predicate wins over BETWEEN.
        if (sql.includes('COUNT(*) AS total') && sql.includes('AND DATE(CONVERT_TZ(answered_at')) {
          return [[{ total: 46, correct: 39 }]]
        }
        if (sql.includes('BETWEEN ? AND ?')) {
          return [[
            { date: '2026-10-12', total: 30, correct: 24 },
            { date: '2026-10-13', total: 35, correct: 30 },
            { date: '2026-10-14', total: 40, correct: 32 },
            { date: '2026-10-15', total: 45, correct: 38 },
            { date: '2026-10-16', total: 40, correct: 33 },
            { date: '2026-10-17', total: 45, correct: 35 },
            { date: '2026-10-18', total: 46, correct: 39 },
          ]]
        }
        if (sql.includes('words_card_state')) {
          return [[{ due_count: 18 }]]
        }
        return [[]]
      }),
    }
    setMockDbPool(mockPool)

    const fixedNow = new Date('2026-10-18T00:30:00+08:00')
    const summary = await getStatsSummary('boss', fixedNow)
    const dailySql = sqls[1] ?? ''
    const stoleTodayShape = dailySql.includes('COUNT(*) AS total') && dailySql.includes('AND DATE(CONVERT_TZ(answered_at')
    expect(summary.today.date, tzContext()).toBe(SHANGHAI_TODAY)
    expect(summary.today.total, tzContext()).toBe(46)
    expect(
      summary.last7d.total,
      `DATE_WINDOW today-shape-used-for-7d=${stoleTodayShape} keys=${summary.last7d.daily.map(d => d.date).join(',')} ${tzContext()} sql=${dailySql}`
    ).toBe(281)
    expect(summary.last7d.daily, tzContext()).toHaveLength(7)
  })

  it('semantic Shanghai window: midnight boundaries, not the runner calendar', async () => {
    useBoundaryClock()
    // 5 before the window, 1 on the first included Shanghai day, 20 yesterday, 46 today, 3 after.
    const attempts = [
      ...stamp('2026-10-11T15:59:59.999Z', 5, true),
      ...stamp('2026-10-11T16:00:00.000Z', 1, true),
      ...stamp('2026-10-17T15:00:00.000Z', 20, false),
      ...stamp('2026-10-17T16:30:00.000Z', 46, true),
      ...stamp('2026-10-18T16:00:00.000Z', 3, true),
    ]
    // UTC day of BOUNDARY is 2026-10-17, which contains both the 20 and the 46.
    const utcTodayCount = attempts.filter(row => row.answered_at.slice(0, 10) === UTC_TODAY).length
    expect(utcTodayCount, tzContext()).toBe(66)

    const pool = semanticPool(attempts)
    setMockDbPool(pool)

    const sparse = await fetchStatsSummary(pool, 'boss', BOUNDARY)
    const dense = await getStatsSummary('boss', BOUNDARY)

    expect(sparse.today.date, `expected Shanghai today, ${tzContext()}`).toBe(SHANGHAI_TODAY)
    expect(dense.today.date, `expected Shanghai today, ${tzContext()}`).toBe(SHANGHAI_TODAY)
    expect(sparse.today.total, `UTC today would be 66; Shanghai today is 46. ${tzContext()}`).toBe(46)
    expect(dense.today.total, `UTC today would be 66; Shanghai today is 46. ${tzContext()}`).toBe(46)
    // 1 + 20 + 46. The 5 before 2026-10-12 and the 3 on 2026-10-19 stay outside.
    expect(sparse.last7d.total, tzContext()).toBe(67)
    expect(dense.last7d.total, tzContext()).toBe(67)
    expect(dense.last7d.daily.map(day => day.date), tzContext()).toEqual([
      '2026-10-12',
      '2026-10-13',
      '2026-10-14',
      '2026-10-15',
      '2026-10-16',
      '2026-10-17',
      '2026-10-18',
    ])
    expect(dense.last7d.daily[0].total, tzContext()).toBe(1)
    expect(dense.last7d.daily[5].total, tzContext()).toBe(20)
    expect(dense.last7d.daily[6].total, tzContext()).toBe(46)
    expect(sparse.due_today, tzContext()).toBe(18)
    expect(dense.due_today, tzContext()).toBe(18)
  })
})

function stamp(iso: string, count: number, correct: boolean) {
  return Array.from({ length: count }, () => ({ answered_at: iso, correct }))
}

function shiftShanghaiDate(dateStr: string, days: number): string {
  const base = new Date(`${dateStr}T12:00:00+08:00`)
  return getShanghaiDate(new Date(base.getTime() + days * 86400000))
}

function semanticPool(attempts: Array<{ answered_at: string; correct: boolean }>) {
  return {
    query: vi.fn().mockImplementation((sql: string, params: any[] = []) => {
      if (sql.includes('words_card_state')) {
        return [[{ count: 18, due_count: 18 }]]
      }
      const dated = attempts.map(row => ({
        ...row,
        day: getShanghaiDate(new Date(row.answered_at)),
      }))
      const dateParams = params.filter((param: unknown) => typeof param === 'string' && /^\d{4}-\d{2}-\d{2}/.test(param)) as string[]

      if (/GROUP BY/i.test(sql) || sql.includes('BETWEEN') || sql.includes('INTERVAL 6 DAY')) {
        let start: string
        let end: string
        if (dateParams.length >= 2) {
          start = dateParams[0].slice(0, 10)
          end = dateParams[1].slice(0, 10)
        } else {
          end = (dateParams[0] || getShanghaiDate()).slice(0, 10)
          start = shiftShanghaiDate(end, -6)
        }
        const matched = dated.filter(row => row.day >= start && row.day <= end)
        const byDay = new Map<string, { day: string; date: string; total: number; correct: number }>()
        for (const row of matched) {
          const found = byDay.get(row.day) || { day: row.day, date: row.day, total: 0, correct: 0 }
          found.total += 1
          if (row.correct) found.correct += 1
          byDay.set(row.day, found)
        }
        return [[...byDay.values()].sort((a, b) => a.day.localeCompare(b.day))]
      }

      if (/=\s*\?/.test(sql)) {
        const day = (dateParams[0] || '').slice(0, 10)
        const matched = dated.filter(row => row.day === day)
        const correct = matched.filter(row => row.correct).length
        return [[{ total: matched.length, correct }]]
      }

      return [[]]
    }),
  }
}
