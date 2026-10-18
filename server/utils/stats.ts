import type { Pool } from 'mysql2/promise'

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

export function getShanghaiDate(date = new Date()): string {
  // Asia/Shanghai 是 UTC+8
  const utc = date.getTime() + date.getTimezoneOffset() * 60000
  const shanghaiTime = new Date(utc + 8 * 3600000)
  const y = shanghaiTime.getFullYear()
  const m = String(shanghaiTime.getMonth() + 1).padStart(2, '0')
  const d = String(shanghaiTime.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export async function fetchStatsSummary(
  pool: Pool,
  userId = 'boss'
): Promise<StatsSummaryResult> {
  const todayDate = getShanghaiDate()

  // 1. 今日统计（Asia/Shanghai）
  const [todayRows] = await pool.query<any[]>(
    `SELECT
       COUNT(*) AS total,
       COALESCE(SUM(correct), 0) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND DATE(CONVERT_TZ(answered_at, '+00:00', '+08:00')) = ?`,
    [userId, todayDate]
  )
  const todayTotal = Number(todayRows[0]?.total || 0)
  const todayCorrect = Number(todayRows[0]?.correct || 0)
  const todayAccuracy = todayTotal > 0 ? Number((todayCorrect / todayTotal).toFixed(3)) : 0

  // 2. 近 7 天统计（包含今天往回 6 天，共 7 天）
  const [last7dRows] = await pool.query<any[]>(
    `SELECT
       DATE_FORMAT(CONVERT_TZ(answered_at, '+00:00', '+08:00'), '%Y-%m-%d') AS day,
       COUNT(*) AS total,
       COALESCE(SUM(correct), 0) AS correct
     FROM words_attempts
     WHERE user_id = ?
       AND DATE(CONVERT_TZ(answered_at, '+00:00', '+08:00')) >= DATE_SUB(?, INTERVAL 6 DAY)
     GROUP BY day
     ORDER BY day ASC`,
    [userId, todayDate]
  )

  let last7dTotal = 0
  let last7dCorrect = 0
  const daily: DaySummary[] = (last7dRows || []).map(r => {
    const t = Number(r.total || 0)
    const c = Number(r.correct || 0)
    last7dTotal += t
    last7dCorrect += c
    return {
      date: r.day,
      total: t,
      correct: c,
    }
  })

  const last7dAccuracy = last7dTotal > 0 ? Number((last7dCorrect / last7dTotal).toFixed(3)) : 0

  // 3. 到期复习统计
  const [dueRows] = await pool.query<any[]>(
    `SELECT COUNT(*) AS count
     FROM words_card_state
     WHERE user_id = ?
       AND next_review_on <= ?`,
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
       AND a.answered_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
     GROUP BY a.word, a.point_id, c.interval_days
     HAVING attempts >= 2 AND wrong > 0
     ORDER BY wrong DESC, error_rate DESC
     LIMIT ?`,
    [userId, safeDays, safeLimit]
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
