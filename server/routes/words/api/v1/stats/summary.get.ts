import { defineEventHandler, createError } from 'h3'
import { authenticateStatsRequest } from '../../../../../utils/auth'
import { getStatsSummary } from '../../../../../services/stats'

export default defineEventHandler(async (event) => {
  const auth = authenticateStatsRequest(event)
  if (!auth.authenticated) {
    throw createError({
      statusCode: 401,
      statusMessage: auth.error || 'Unauthorized',
    })
  }
  return await getStatsSummary(auth.user_id || 'boss')
})
