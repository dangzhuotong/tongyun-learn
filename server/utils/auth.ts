import crypto from 'crypto'
import bcrypt from 'bcryptjs'
import {
  type H3Event,
  getCookie,
  setCookie,
  deleteCookie,
  getHeader,
  getRequestIP,
  createError,
} from 'h3'

export const SESSION_COOKIE_NAME = 'tw_sess'
export const DEFAULT_SESSION_MAX_AGE = 30 * 24 * 60 * 60 // 30 天，秒

export interface SessionPayload {
  u: string // user_id
  iat: number // issued at (ms)
  exp: number // expires at (ms)
}

export function getSessionSecret(): string {
  return process.env.WORDS_SESSION_SECRET || 'tongyun-words-default-session-secret'
}

export function signSessionToken(
  userId: string,
  secret = getSessionSecret(),
  maxAgeSec = DEFAULT_SESSION_MAX_AGE
): string {
  const now = Date.now()
  const payload: SessionPayload = {
    u: userId,
    iat: now,
    exp: now + maxAgeSec * 1000,
  }
  const payloadStr = Buffer.from(JSON.stringify(payload)).toString('base64url')
  const signature = crypto
    .createHmac('sha256', secret)
    .update(payloadStr)
    .digest('base64url')
  return `${payloadStr}.${signature}`
}

export function verifySessionToken(
  token: string | undefined | null,
  secret = getSessionSecret()
): { userId: string } | null {
  if (!token || typeof token !== 'string') return null
  const parts = token.split('.')
  if (parts.length !== 2) return null

  const [payloadStr, signature] = parts
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(payloadStr)
    .digest('base64url')

  const sigBuffer = Buffer.from(signature)
  const expectedBuffer = Buffer.from(expectedSignature)
  if (sigBuffer.length !== expectedBuffer.length) return null
  if (!crypto.timingSafeEqual(sigBuffer, expectedBuffer)) return null

  try {
    const jsonStr = Buffer.from(payloadStr, 'base64url').toString('utf8')
    const payload = JSON.parse(jsonStr) as SessionPayload
    if (!payload.u || !payload.exp) return null
    if (payload.exp < Date.now()) return null
    return { userId: payload.u }
  } catch {
    return null
  }
}

export function comparePassword(password: string, hash: string): boolean {
  if (!password || !hash) return false
  try {
    return bcrypt.compareSync(password, hash)
  } catch {
    return false
  }
}

// 内存限流：限 5 次/分钟/IP
interface RateLimitBucket {
  count: number
  resetAt: number
}

const loginRateLimits = new Map<string, RateLimitBucket>()

export function checkLoginRateLimit(
  ip: string,
  maxAttempts = 5,
  windowMs = 60 * 1000
): { allowed: boolean; remaining: number; resetInMs: number } {
  const now = Date.now()
  const bucket = loginRateLimits.get(ip)

  if (!bucket || bucket.resetAt <= now) {
    loginRateLimits.set(ip, {
      count: 1,
      resetAt: now + windowMs,
    })
    return {
      allowed: true,
      remaining: maxAttempts - 1,
      resetInMs: windowMs,
    }
  }

  bucket.count += 1
  const remaining = Math.max(0, maxAttempts - bucket.count)
  const resetInMs = Math.max(0, bucket.resetAt - now)

  if (bucket.count > maxAttempts) {
    return { allowed: false, remaining: 0, resetInMs }
  }

  return { allowed: true, remaining, resetInMs }
}

export function resetLoginRateLimits(): void {
  loginRateLimits.clear()
}

export function setSessionCookie(
  event: H3Event,
  userId: string,
  maxAge = DEFAULT_SESSION_MAX_AGE
): void {
  const token = signSessionToken(userId, getSessionSecret(), maxAge)
  setCookie(event, SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge,
  })
}

export function clearSessionCookie(event: H3Event): void {
  deleteCookie(event, SESSION_COOKIE_NAME, {
    path: '/',
    httpOnly: true,
    sameSite: 'lax',
  })
}

export function getUserFromSession(event: H3Event): { userId: string } | null {
  const cookie = getCookie(event, SESSION_COOKIE_NAME)
  return verifySessionToken(cookie)
}

export function requireAuth(event: H3Event): { userId: string } {
  const user = getUserFromSession(event)
  if (!user) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized',
      message: 'Authentication required',
    })
  }
  return user
}

export function requireStatsAuth(event: H3Event): { role: 'boss' | 'stats_reader'; userId?: string } {
  const user = getUserFromSession(event)
  if (user) {
    return { role: 'boss', userId: user.userId }
  }

  const authHeader = getHeader(event, 'authorization')
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.slice(7).trim()
    const statsToken = process.env.WORDS_STATS_TOKEN
    if (statsToken && token && token === statsToken) {
      return { role: 'stats_reader' }
    }
  }

  throw createError({
    statusCode: 401,
    statusMessage: 'Unauthorized',
    message: 'Valid session or stats token required',
  })
}
