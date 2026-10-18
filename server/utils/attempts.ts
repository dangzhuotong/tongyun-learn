import { z } from 'zod'
import type { Pool, PoolConnection } from 'mysql2/promise'

export const VALID_INTERVAL_DAYS = [1, 3, 7, 14, 30] as const

export const AttemptEventSchema = z.object({
  client_event_id: z.string().min(1).max(36),
  word: z.string().min(1).max(128),
  point_id: z.string().max(64).nullable().optional(),
  level: z.string().max(8).nullable().optional(),
  mode: z.string().max(16).default('recall'),
  correct: z.boolean(),
  duration_ms: z.number().int().nonnegative(),
  answer_text: z.string().max(512).nullable().optional(),
  answered_at: z.string().refine(val => !isNaN(Date.parse(val)), {
    message: 'answered_at must be a valid ISO 8601 date string',
  }),
  interval_days: z.number().refine(val => VALID_INTERVAL_DAYS.includes(val as any), {
    message: 'interval_days must be one of 1, 3, 7, 14, 30',
  }),
  next_review_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'next_review_on must be YYYY-MM-DD'),
  wordlist_ver: z.string().max(16).nullable().optional(),
  client_ua: z.string().max(64).nullable().optional(),
})

export type AttemptEvent = z.infer<typeof AttemptEventSchema>

export const BatchAttemptsPayloadSchema = z.object({
  events: z.array(z.any()).max(200, 'Batch size exceeds maximum limit of 200 events'),
})

export interface ProcessAttemptsResult {
  accepted: number
  duplicate: number
  rejected: Array<{ client_event_id?: string; error: string }>
}

export function validateAttemptEvent(raw: unknown): {
  success: boolean
  data?: AttemptEvent
  error?: string
} {
  const parsed = AttemptEventSchema.safeParse(raw)
  if (parsed.success) {
    return { success: true, data: parsed.data }
  }
  return {
    success: false,
    error: parsed.error.issues.map(i => `${i.path.join('.')}: ${i.message}`).join('; '),
  }
}

export function formatDateTime(isoStr: string): string {
  const d = new Date(isoStr)
  return d.toISOString().replace('T', ' ').replace('Z', '')
}

export interface ProcessAttemptsOptions {
  /**
   * Test seam. Runs after the pre-check and before INSERT IGNORE, so a
   * concurrent commit can land the same client_event_id. Card state is updated
   * only when that insert reports affectedRows === 1.
   */
  afterPrecheck?: () => Promise<void>
}

export async function processAttemptsBatch(
  pool: Pool,
  userId: string,
  rawEvents: unknown[],
  clientUaFallback?: string,
  options?: ProcessAttemptsOptions
): Promise<ProcessAttemptsResult> {
  const rejected: Array<{ client_event_id?: string; error: string }> = []
  const validEvents: AttemptEvent[] = []
  const seenInBatch = new Set<string>()
  let batchDuplicateCount = 0

  for (const raw of rawEvents) {
    const rawId = typeof raw === 'object' && raw !== null ? (raw as any).client_event_id : undefined
    const validation = validateAttemptEvent(raw)
    if (!validation.success || !validation.data) {
      rejected.push({
        client_event_id: rawId,
        error: validation.error || 'Invalid event data',
      })
      continue
    }

    const event = validation.data
    if (seenInBatch.has(event.client_event_id)) {
      batchDuplicateCount++
      continue
    }
    seenInBatch.add(event.client_event_id)
    validEvents.push(event)
  }

  if (validEvents.length === 0) {
    return {
      accepted: 0,
      duplicate: batchDuplicateCount,
      rejected,
    }
  }

  const conn: PoolConnection = await pool.getConnection()

  try {
    await conn.beginTransaction()

    // 1. 查找已存在的 client_event_id 进行幂等排重
    const eventIds = validEvents.map(e => e.client_event_id)
    const placeholders = eventIds.map(() => '?').join(',')
    const [existingRows] = await conn.query<any[]>(
      `SELECT client_event_id FROM words_attempts WHERE client_event_id IN (${placeholders})`,
      eventIds
    )

    const existingList = Array.isArray(existingRows) ? existingRows : []
    const existingIdSet = new Set(existingList.map(r => r.client_event_id))
    let duplicateCount = batchDuplicateCount + existingIdSet.size
    let accepted = 0

    // A concurrent request can commit the same client_event_id after this read.
    if (options?.afterPrecheck) {
      await options.afterPrecheck()
    }

    // answered_at order so a later event in this batch cannot be overwritten by an earlier one.
    const toTry = validEvents
      .filter(e => !existingIdSet.has(e.client_event_id))
      .sort((a, b) => new Date(a.answered_at).getTime() - new Date(b.answered_at).getTime())

    for (const e of toTry) {
      const answeredAtStr = formatDateTime(e.answered_at)
      // Per-row INSERT IGNORE: affectedRows === 1 only when this transaction inserted the row.
      // A duplicate unique key is a no-op (affectedRows === 0) and must not touch card state.
      const [header] = await conn.query<any>(
        `INSERT IGNORE INTO words_attempts
          (client_event_id, user_id, word, point_id, level, mode, correct, duration_ms, answer_text, answered_at, interval_days, next_review_on, wordlist_ver, client_ua)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          e.client_event_id,
          userId,
          e.word,
          e.point_id || null,
          e.level || null,
          e.mode || 'recall',
          e.correct ? 1 : 0,
          e.duration_ms,
          e.answer_text || null,
          answeredAtStr,
          e.interval_days,
          e.next_review_on,
          e.wordlist_ver || null,
          e.client_ua || clientUaFallback || null,
        ]
      )
      if (Number(header?.affectedRows ?? 0) !== 1) {
        duplicateCount += 1
        continue
      }
      accepted += 1

      const lapse = e.correct ? 0 : 1
      await conn.query(
        `INSERT INTO words_card_state
          (user_id, word, point_id, interval_days, next_review_on, reps, lapses, last_answered_at)
         VALUES (?, ?, ?, ?, ?, 1, ?, ?)
         ON DUPLICATE KEY UPDATE
           reps = reps + 1,
           lapses = lapses + ?,
           point_id = IF(? >= last_answered_at, VALUES(point_id), point_id),
           interval_days = IF(? >= last_answered_at, VALUES(interval_days), interval_days),
           next_review_on = IF(? >= last_answered_at, VALUES(next_review_on), next_review_on),
           last_answered_at = IF(? >= last_answered_at, VALUES(last_answered_at), last_answered_at)`,
        [
          userId,
          e.word,
          e.point_id || null,
          e.interval_days,
          e.next_review_on,
          lapse,
          answeredAtStr,
          lapse,
          answeredAtStr,
          answeredAtStr,
          answeredAtStr,
          answeredAtStr,
        ]
      )
    }

    await conn.commit()

    return {
      accepted,
      duplicate: duplicateCount,
      rejected,
    }
  } catch (err) {
    await conn.rollback()
    throw err
  } finally {
    conn.release()
  }
}
