import { z } from 'zod'
import { query } from '../utils/db'

export interface TodayStats {
  date: string
  total: number
  correct: number
  accuracy: number
}

export interface DailyStats {
  date: string
  total: number
  correct: number
}

export interface Last7dStats {
  total: number
  correct: number
  accuracy: number
  daily: DailyStats[]
}

export interface StatsSummaryResponse {
  tz: string
  today: TodayStats
  last7d: Last7dStats
  due_today: number
}

export interface MistakeItem {
  word: string
  point_id: string | null
  attempts: number
  wrong: number
  error_rate: number
  last_wrong_at: string
  current_interval: number
}

export interface StatsMistakesResponse {
  days: number
  items: MistakeItem[]
}

export const mistakesQuerySchema = z.object({
  days: z.coerce.number().int().min(1).max(365).default(30),
  limit: z.coerce.number().int().min(1).max(100).default(20),
})

/**
 * Get Shanghai date string YYYY-MM-DD.
 */
export function getShanghaiDate(d: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d)
}

/**
 * Get the list of last 7 dates in Asia/Shanghai up to and including referenceDate.
 */
export function getLast7Dates(referenceDateStr?: string): string[] {
  const dates: string[] = []
  const base = referenceDateStr ? new Date(`${referenceDateStr}T12:00:00+08:00`) : new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(base.getTime() - i * 24 * 60 * 60 * 1000)
    dates.push(getShanghaiDate(d))
  }
  return dates
}

/**
 * Format date to ISO-like UTC string without milliseconds: YYYY-MM-DDTHH:mm:ssZ
 */
export function formatUtcIso(d: Date | string | null | undefined): string {
  if (!d) return ''
  const dateObj = typeof d === 'string' ? new Date(d) : d
  if (isNaN(dateObj.getTime())) return String(d)
  return dateObj.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/**
 * Retrieve stats summary for a user.
 */
export async function getStatsSummary(
  userId: string = 'boss',
  now: Date = new Date()
): Promise<StatsSummaryResponse> {
  const todayDate = getShanghaiDate(now)
  const last7Dates = getLast7Dates(todayDate)
  const startDate = last7Dates[0]

  // 1. Query today's attempts
  const todayRows = await query<any>(
    `SELECT 
       COUNT(*) AS total,
       SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND DATE(CONVERT_TZ(answered_at, '+00:00', '+08:00')) = ?`,
    [userId, todayDate]
  )
  const todayTotal = Number(todayRows[0]?.total || 0)
  const todayCorrect = Number(todayRows[0]?.correct || 0)
  const todayAccuracy = todayTotal > 0 ? Math.round((todayCorrect / todayTotal) * 1000) / 1000 : 0

  // 2. Query last 7 days breakdown
  const dailyRows = await query<any>(
    `SELECT 
       DATE_FORMAT(CONVERT_TZ(answered_at, '+00:00', '+08:00'), '%Y-%m-%d') AS date,
       COUNT(*) AS total,
       SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND DATE(CONVERT_TZ(answered_at, '+00:00', '+08:00')) BETWEEN ? AND ?
     GROUP BY DATE_FORMAT(CONVERT_TZ(answered_at, '+00:00', '+08:00'), '%Y-%m-%d')
     ORDER BY date ASC`,
    [userId, startDate, todayDate]
  )

  const dailyMap = new Map<string, { total: number; correct: number }>()
  for (const row of dailyRows) {
    dailyMap.set(String(row.date), {
      total: Number(row.total || 0),
      correct: Number(row.correct || 0),
    })
  }

  const daily: DailyStats[] = last7Dates.map(date => {
    const found = dailyMap.get(date)
    return {
      date,
      total: found?.total ?? 0,
      correct: found?.correct ?? 0,
    }
  })

  const last7dTotal = daily.reduce((sum, d) => sum + d.total, 0)
  const last7dCorrect = daily.reduce((sum, d) => sum + d.correct, 0)
  const last7dAccuracy = last7dTotal > 0 ? Math.round((last7dCorrect / last7dTotal) * 1000) / 1000 : 0

  // 3. Query due today from words_card_state
  const dueRows = await query<any>(
    `SELECT COUNT(*) AS due_count
     FROM words_card_state
     WHERE user_id = ?
       AND next_review_on <= ?`,
    [userId, todayDate]
  )
  const dueToday = Number(dueRows[0]?.due_count || 0)

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

/**
 * Retrieve top mistake words for a user.
 */
export async function getStatsMistakes(
  userId: string = 'boss',
  options: { days?: number; limit?: number } = {}
): Promise<StatsMistakesResponse> {
  const days = options.days ?? 30
  const limit = options.limit ?? 20

  const rows = await query<any>(
    `SELECT 
       a.word,
       MAX(a.point_id) AS point_id,
       COUNT(*) AS attempts,
       SUM(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong,
       MAX(CASE WHEN a.correct = 0 THEN a.answered_at ELSE NULL END) AS last_wrong_at,
       COALESCE(c.interval_days, 1) AS current_interval
     FROM words_attempts a
     LEFT JOIN words_card_state c ON c.user_id = a.user_id AND c.word = a.word
     WHERE a.user_id = ?
       AND a.answered_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
     GROUP BY a.word, c.interval_days
     HAVING attempts >= 2 AND wrong > 0
     ORDER BY wrong DESC, (wrong / attempts) DESC, last_wrong_at DESC
     LIMIT ?`,
    [userId, days, limit]
  )

  const items: MistakeItem[] = rows.map((r: any) => {
    const attempts = Number(r.attempts || 0)
    const wrong = Number(r.wrong || 0)
    const errorRate = attempts > 0 ? Math.round((wrong / attempts) * 1000) / 1000 : 0
    return {
      word: String(r.word),
      point_id: r.point_id ? String(r.point_id) : null,
      attempts,
      wrong,
      error_rate: errorRate,
      last_wrong_at: formatUtcIso(r.last_wrong_at),
      current_interval: Number(r.current_interval || 1),
    }
  })

  return {
    days,
    items,
  }
}
