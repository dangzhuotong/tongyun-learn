import { defineEventHandler, readBody, getHeader, createError } from 'h3'
import { requireAuth } from '../../../../utils/auth'
import { requireDbPool } from '../../../../utils/require-db'
import {
  BatchAttemptsPayloadSchema,
  processAttemptsBatch,
} from '../../../../utils/attempts'

export default defineEventHandler(async event => {
  const user = requireAuth(event)

  const body = await readBody(event).catch(() => null)
  if (!body || typeof body !== 'object' || !Array.isArray(body.events)) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Bad Request',
      message: 'Body must be an object with an "events" array',
    })
  }

  const parsed = BatchAttemptsPayloadSchema.safeParse(body)
  if (!parsed.success) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Bad Request',
      message: parsed.error.issues[0]?.message || 'Invalid attempts batch format',
    })
  }

  const pool = requireDbPool()

  const userAgent = getHeader(event, 'user-agent') || undefined
  const result = await processAttemptsBatch(pool, user.userId, body.events, userAgent)

  return result
})
