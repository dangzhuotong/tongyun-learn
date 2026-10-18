import { defineEventHandler, getQuery, createError } from 'h3'
import { requireStatsAuth } from '../../../../../utils/auth'
import { getDbPool } from '../../../../../utils/db'
import { fetchStatsMistakes } from '../../../../../utils/stats'

export default defineEventHandler(async event => {
  const auth = requireStatsAuth(event)
  const query = getQuery(event)

  const days = query.days ? parseInt(String(query.days), 10) : 30
  const limit = query.limit ? parseInt(String(query.limit), 10) : 20

  const pool = getDbPool()
  if (!pool) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable',
      message: 'Database service is not configured',
    })
  }

  const result = await fetchStatsMistakes(
    pool,
    auth.userId || 'boss',
    isNaN(days) ? 30 : days,
    isNaN(limit) ? 20 : limit
  )
  return result
})
