import { defineEventHandler, getQuery, createError } from 'h3'
import { authenticateStatsRequest } from '../../../utils/auth'
import { getStatsMistakes, mistakesQuerySchema } from '../../../services/stats'

export default defineEventHandler(async (event) => {
  const auth = authenticateStatsRequest(event)
  if (!auth.authenticated) {
    throw createError({
      statusCode: 401,
      statusMessage: auth.error || 'Unauthorized',
    })
  }

  const rawQuery = getQuery(event)
  const parsed = mistakesQuerySchema.safeParse(rawQuery)
  const queryParams = parsed.success ? parsed.data : { days: 30, limit: 20 }

  return await getStatsMistakes(auth.user_id || 'boss', queryParams)
})
