import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { createPool, type Pool, type RowDataPacket } from 'mysql2/promise'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { processAttemptsBatch, type AttemptEvent } from './utils/attempts'

/**
 * Real MySQL proof for the pre-check / unique-key race.
 * Skips unless WORDS_DATABASE_URL is set. Touches only words_attempts and words_card_state.
 */
const databaseUrl = process.env.WORDS_DATABASE_URL

function splitSql(file: string): string[] {
  return readFileSync(file, 'utf8')
    .split('\n')
    .filter(line => !line.trim().startsWith('--'))
    .join('\n')
    .split(';')
    .map(statement => statement.trim())
    .filter(Boolean)
}

async function applySql(pool: Pool, file: string) {
  for (const statement of splitSql(file)) {
    await pool.query(statement)
  }
}

function event(overrides: Partial<AttemptEvent> = {}): AttemptEvent {
  return {
    client_event_id: randomUUID(),
    word: `race-${randomUUID()}`,
    correct: false,
    duration_ms: 1200,
    answered_at: '2026-10-17T10:00:00.000Z',
    interval_days: 1,
    next_review_on: '2026-10-18',
    mode: 'recall',
    ...overrides,
  }
}

describe.skipIf(!databaseUrl)('words attempts against MySQL', () => {
  let pool: Pool | null = null

  beforeAll(async () => {
    pool = createPool({
      uri: databaseUrl,
      connectionLimit: 3,
      timezone: 'Z',
      dateStrings: true,
      charset: 'utf8mb4',
    })
    await applySql(pool, 'server/db/migrations/001_words_sync.sql')
    await pool.query('DELETE FROM words_card_state')
    await pool.query('DELETE FROM words_attempts')
  })

  afterAll(async () => {
    if (!pool) return
    await applySql(pool, 'server/db/migrations/001_words_sync.sql')
    await pool.end()
  })

  function db(): Pool {
    if (!pool) throw new Error('mysql pool is not open')
    return pool
  }

  it('a repeated batch does not increment reps or lapses', async () => {
    const sample = event({ word: `seq-${randomUUID()}` })
    const first = await processAttemptsBatch(db(), 'boss', [sample])
    const second = await processAttemptsBatch(db(), 'boss', [sample])

    expect(first).toEqual({ accepted: 1, duplicate: 0, rejected: [] })
    expect(second).toEqual({ accepted: 0, duplicate: 1, rejected: [] })

    const [attempts] = await db().query<RowDataPacket[]>(
      'SELECT COUNT(*) AS n FROM words_attempts WHERE client_event_id = ?',
      [sample.client_event_id]
    )
    const [state] = await db().query<RowDataPacket[]>(
      'SELECT reps, lapses FROM words_card_state WHERE user_id = ? AND word = ?',
      ['boss', sample.word]
    )
    expect(Number(attempts[0].n)).toBe(1)
    expect(state).toEqual([{ reps: 1, lapses: 1 }])
  })

  it('pre-check empty, insert hits unique key: duplicate, reps stay put', async () => {
    const sample = event({ word: `race-${randomUUID()}` })
    const answeredAt = '2026-10-17 10:00:00.000'

    const result = await processAttemptsBatch(db(), 'boss', [sample], undefined, {
      afterPrecheck: async () => {
        const other = await db().getConnection()
        try {
          await other.query(
            `INSERT INTO words_attempts
              (client_event_id, user_id, word, mode, correct, duration_ms, answered_at, interval_days, next_review_on)
             VALUES (?, 'boss', ?, 'recall', 0, ?, ?, ?, ?)`,
            [sample.client_event_id, sample.word, sample.duration_ms, answeredAt, sample.interval_days, sample.next_review_on]
          )
          await other.query(
            `INSERT INTO words_card_state
              (user_id, word, interval_days, next_review_on, reps, lapses, last_answered_at)
             VALUES ('boss', ?, ?, ?, 1, 1, ?)`,
            [sample.word, sample.interval_days, sample.next_review_on, answeredAt]
          )
        } finally {
          other.release()
        }
      },
    })

    expect(result).toEqual({ accepted: 0, duplicate: 1, rejected: [] })

    const [attempts] = await db().query<RowDataPacket[]>(
      'SELECT COUNT(*) AS n FROM words_attempts WHERE client_event_id = ?',
      [sample.client_event_id]
    )
    const [state] = await db().query<RowDataPacket[]>(
      'SELECT reps, lapses FROM words_card_state WHERE user_id = ? AND word = ?',
      ['boss', sample.word]
    )
    expect(Number(attempts[0].n)).toBe(1)
    expect(state).toEqual([{ reps: 1, lapses: 1 }])
  })

  it('down migration drops both words tables and up recreates them', async () => {
    await applySql(db(), 'server/db/migrations/001_words_sync.down.sql')
    const [gone] = await db().query<RowDataPacket[]>(
      `SELECT table_name AS name
       FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('words_attempts', 'words_card_state')`
    )
    expect(gone).toEqual([])

    await applySql(db(), 'server/db/migrations/001_words_sync.sql')
    const [back] = await db().query<RowDataPacket[]>(
      `SELECT table_name AS name
       FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('words_attempts', 'words_card_state')
       ORDER BY table_name`
    )
    expect(back.map(row => row.name)).toEqual(['words_attempts', 'words_card_state'])
  })
})
