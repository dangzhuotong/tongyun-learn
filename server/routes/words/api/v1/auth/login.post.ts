import { defineEventHandler, readBody, getRequestIP, createError } from 'h3'
import {
  checkLoginRateLimit,
  comparePassword,
  setSessionCookie,
} from '../../../../../utils/auth'

export default defineEventHandler(async event => {
  const ip = getRequestIP(event, { xForwardedFor: true }) || '127.0.0.1'
  const rateLimit = checkLoginRateLimit(ip, 5, 60 * 1000)

  if (!rateLimit.allowed) {
    throw createError({
      statusCode: 429,
      statusMessage: 'Too Many Requests',
      message: `Too many login attempts. Please try again in ${Math.ceil(rateLimit.resetInMs / 1000)} seconds.`,
    })
  }

  const body = await readBody(event).catch(() => ({}))
  const { username, password } = body || {}

  if (!username || !password) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Bad Request',
      message: 'Username and password are required',
    })
  }

  const bossUser = process.env.WORDS_BOSS_USER || 'boss'
  const bossPassHash = process.env.WORDS_BOSS_PASS_HASH || ''

  if (username !== bossUser) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized',
      message: 'Invalid username or password',
    })
  }

  const passwordValid = bossPassHash
    ? comparePassword(password, bossPassHash)
    : false

  if (!passwordValid) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized',
      message: 'Invalid username or password',
    })
  }

  setSessionCookie(event, bossUser)

  return {
    ok: true,
    user: {
      username: bossUser,
    },
  }
})
