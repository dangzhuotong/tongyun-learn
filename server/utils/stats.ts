import type { Pool } from 'mysql2/promise'
import { getLast7Dates, getShanghaiDate, ratio, shanghaiMidnightUtc, shiftShanghaiDate, sqlDayKey } from '../services/shanghai-date'

export { getShanghaiDate } from '../services/shanghai-date'

export interface DaySummary {
  date: string
  total: number
  correct: number
  accuracy?: number
}

export interface StatsSummaryResult {
  tz: string
  today: DaySummary
  last7d: {
    total: number
    correct: number
    accuracy: number
    daily: DaySummary[]
  }
  due_today: number
}

export interface MistakeItem {
  word: string
  point_id: string | null
  attempts: number
  wrong: number
  error_rate: number
  last_wrong_at: string
  current_interval: number | null
}

export interface StatsMistakesResult {
  days: number
  items: MistakeItem[]
}

export async function fetchStatsSummary(
  pool: Pool,
  userId = 'boss',
  now = new Date()
): Promise<StatsSummaryResult> {
  const todayDate = getShanghaiDate(now)
  const startDate = getLast7Dates(todayDate, now)[0]
  const todayStartUtc = shanghaiMidnightUtc(todayDate)
  const todayEndUtc = shanghaiMidnightUtc(shiftShanghaiDate(todayDate, 1))
  const windowStartUtc = shanghaiMidnightUtc(startDate)

  // Range on answered_at (UTC) so ix_user_time can be used. Shanghai midnight is UTC 16:00 the previous day.
  const [todayRows] = await pool.query<any[]>(
    `SELECT
       COUNT(*) AS total,
       COALESCE(SUM(correct), 0) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND answered_at >= ?
       AND answered_at < ?`,
    [userId, todayStartUtc, todayEndUtc]
  )
  const todayTotal = Number(todayRows[0]?.total || 0)
  const todayCorrect = Number(todayRows[0]?.correct || 0)
  const todayAccuracy = ratio(todayCorrect, todayTotal)

  // Inclusive Shanghai window [today-6, today], grouped by Shanghai day.
  const [last7dRows] = await pool.query<any[]>(
    `SELECT
       DATE_FORMAT(CONVERT_TZ(answered_at, '+00:00', '+08:00'), '%Y-%m-%d') AS day,
       COUNT(*) AS total,
       COALESCE(SUM(correct), 0) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND answered_at >= ?
       AND answered_at < ?
     GROUP BY day
     ORDER BY day ASC`,
    [userId, windowStartUtc, todayEndUtc]
  )

  let last7dTotal = 0
  let last7dCorrect = 0
  const daily: DaySummary[] = (last7dRows || []).map(r => {
    const t = Number(r.total || 0)
    const c = Number(r.correct || 0)
    last7dTotal += t
    last7dCorrect += c
    return {
      date: sqlDayKey(r.day),
      total: t,
      correct: c,
    }
  })

  const last7dAccuracy = ratio(last7dCorrect, last7dTotal)

  const [dueRows] = await pool.query<any[]>(
    `SELECT COUNT(*) AS count FROM words_card_state WHERE user_id = ? AND next_review_on <= ?`,
    [userId, todayDate]
  )
  const dueToday = Number(dueRows[0]?.count || 0)

  return {
    tz: 'Asia/Shanghai',
    today: {
      date: todayDate,
      total: todayTotal,
      correct: todayCorrect,
      accuracy: todayAccuracy,
    },
    last7d: {
      total: last7dTotal,
      correct: last7dCorrect,
      accuracy: last7dAccuracy,
      daily,
    },
    due_today: dueToday,
  }
}

export async function fetchStatsMistakes(
  pool: Pool,
  userId = 'boss',
  days = 30,
  limit = 20
): Promise<StatsMistakesResult> {
  const safeDays = Math.max(1, Math.min(365, days))
  const safeLimit = Math.max(1, Math.min(100, limit))

  const since = new Date(Date.now() - safeDays * 24 * 60 * 60 * 1000)
  const sinceUtc = since.toISOString().replace('T', ' ').replace('Z', '')
  const [rows] = await pool.query<any[]>(
    `SELECT
       a.word,
       a.point_id,
       COUNT(*) AS attempts,
       SUM(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong,
       ROUND(SUM(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) / COUNT(*), 3) AS error_rate,
       MAX(CASE WHEN a.correct = 0 THEN a.answered_at ELSE NULL END) AS last_wrong_at,
       c.interval_days AS current_interval
     FROM words_attempts a
     LEFT JOIN words_card_state c ON c.user_id = a.user_id AND c.word = a.word
     WHERE a.user_id = ?
       AND a.answered_at >= ?
     GROUP BY a.word, a.point_id, c.interval_days
     HAVING attempts >= 2 AND wrong > 0
     ORDER BY wrong DESC, error_rate DESC
     LIMIT ?`,
    [userId, sinceUtc, safeLimit]
  )

  const items: MistakeItem[] = (rows || []).map(r => ({
    word: r.word,
    point_id: r.point_id || null,
    attempts: Number(r.attempts),
    wrong: Number(r.wrong),
    error_rate: Number(r.error_rate),
    last_wrong_at: r.last_wrong_at instanceof Date ? r.last_wrong_at.toISOString() : String(r.last_wrong_at),
    current_interval: r.current_interval !== null ? Number(r.current_interval) : null,
  }))

  return {
    days: safeDays,
    items,
  }
}
