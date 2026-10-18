import type { Pool } from 'mysql2/promise'

export interface CardStateItem {
  user_id: string
  word: string
  point_id: string | null
  interval_days: number
  next_review_on: string
  reps: number
  lapses: number
  last_answered_at: string
}

export async function fetchCardStates(
  pool: Pool,
  userId: string,
  since?: string | null
): Promise<{ items: CardStateItem[]; server_time: string }> {
  let query = `
    SELECT
      user_id,
      word,
      point_id,
      interval_days,
      DATE_FORMAT(next_review_on, '%Y-%m-%d') AS next_review_on,
      reps,
      lapses,
      last_answered_at
    FROM words_card_state
    WHERE user_id = ?
  `
  const params: any[] = [userId]

  if (since) {
    const parsedSince = new Date(since)
    if (!isNaN(parsedSince.getTime())) {
      query += ` AND last_answered_at > ?`
      params.push(parsedSince)
    }
  }

  query += ` ORDER BY last_answered_at ASC`

  const [rows] = await pool.query<any[]>(query, params)

  const items: CardStateItem[] = (rows || []).map(r => ({
    user_id: r.user_id,
    word: r.word,
    point_id: r.point_id,
    interval_days: Number(r.interval_days),
    next_review_on: r.next_review_on,
    reps: Number(r.reps),
    lapses: Number(r.lapses),
    last_answered_at: r.last_answered_at instanceof Date ? r.last_answered_at.toISOString() : String(r.last_answered_at),
  }))

  return {
    items,
    server_time: new Date().toISOString(),
  }
}
