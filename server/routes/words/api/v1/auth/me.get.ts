import { defineEventHandler } from 'h3'
import { requireAuth } from '../../../../../utils/auth'

export default defineEventHandler(event => {
  const user = requireAuth(event)
  return {
    ok: true,
    user: {
      user_id: user.userId,
      username: user.userId,
    },
  }
})
