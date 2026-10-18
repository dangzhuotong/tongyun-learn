import { defineEventHandler, createError } from 'h3'
import { requireStatsAuth } from '../../../../../utils/auth'
import { getDbPool } from '../../../../../utils/db'
import { fetchStatsSummary } from '../../../../../utils/stats'

export default defineEventHandler(async event => {
  const auth = requireStatsAuth(event)

  const pool = getDbPool()
  if (!pool) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable',
      message: 'Database service is not configured',
    })
  }

  const result = await fetchStatsSummary(pool, auth.userId || 'boss')
  return result
})
