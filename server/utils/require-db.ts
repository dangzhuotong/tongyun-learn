import { createError } from 'h3'
import { getDbPool } from './db'

/** Pool from WORDS_DATABASE_URL, or 503 when that env var is missing. */
export function requireDbPool() {
  try {
    return getDbPool()
  } catch (err) {
    const message = err instanceof Error ? err.message : ''
    if (message.includes('WORDS_DATABASE_URL is not set')) {
      throw createError({
        statusCode: 503,
        statusMessage: 'Service Unavailable',
        message: 'Database service is not configured',
      })
    }
    throw err
  }
}
