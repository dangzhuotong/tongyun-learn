import { defineEventHandler, getQuery } from 'h3'
import { requireAuth } from '../../../../utils/auth'
import { requireDbPool } from '../../../../utils/require-db'
import { fetchCardStates } from '../../../../utils/state'

export default defineEventHandler(async event => {
  const user = requireAuth(event)
  const query = getQuery(event)
  const since = typeof query.since === 'string' ? query.since : undefined

  const pool = requireDbPool()

  const result = await fetchCardStates(pool, user.userId, since)
  return result
})
