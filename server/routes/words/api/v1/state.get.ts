import { defineEventHandler, getQuery, createError } from 'h3'
import { requireAuth } from '../../../../utils/auth'
import { getDbPool } from '../../../../utils/db'
import { fetchCardStates } from '../../../../utils/state'

export default defineEventHandler(async event => {
  const user = requireAuth(event)
  const query = getQuery(event)
  const since = typeof query.since === 'string' ? query.since : undefined

  const pool = getDbPool()
  if (!pool) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable',
      message: 'Database service is not configured',
    })
  }

  const result = await fetchCardStates(pool, user.userId, since)
  return result
})
