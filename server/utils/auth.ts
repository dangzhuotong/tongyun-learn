import crypto from 'crypto'
import bcrypt from 'bcryptjs'
import {
  type H3Event,
  getCookie,
  setCookie,
  deleteCookie,
  getHeader,
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
  const secret = process.env.WORDS_SESSION_SECRET
  if (!secret) {
    throw new Error('WORDS_SESSION_SECRET is not set')
  }
  return secret
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
  secret?: string
): { userId: string } | null {
  if (!token || typeof token !== 'string') return null
  const signingSecret = secret || process.env.WORDS_SESSION_SECRET
  if (!signingSecret) return null
  const parts = token.split('.')
  if (parts.length !== 2) return null

  const [payloadStr, signature] = parts
  const expectedSignature = crypto
    .createHmac('sha256', signingSecret)
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
    const statsToken = process.env.WORDS_STATS_TOKEN || ''
    if (verifyStatsToken(token, statsToken)) {
      return { role: 'stats_reader' }
    }
  }

  throw createError({
    statusCode: 401,
    statusMessage: 'Unauthorized',
    message: 'Valid session or stats token required',
  })
}

/**
 * Constant-time string comparison to prevent timing attacks.
 */
export function constantTimeCompare(a: string, b: string): boolean {
  if (typeof a !== 'string' || typeof b !== 'string') return false
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) return false
  return crypto.timingSafeEqual(bufA, bufB)
}

/**
 * Sign a session payload with HMAC-SHA256 using WORDS_SESSION_SECRET.
 * Produces `<base64url-payload>.<hmac-hex>`.
 */
export function signSession(
  payload: string | { user_id: string; [key: string]: any },
  secret: string = process.env.WORDS_SESSION_SECRET || ''
): string {
  if (!secret) {
    throw new Error('WORDS_SESSION_SECRET is required to sign session')
  }
  const data = typeof payload === 'string' ? { user_id: payload } : payload
  const jsonStr = JSON.stringify(data)
  const payloadB64 = Buffer.from(jsonStr, 'utf8').toString('base64url')
  const hmac = crypto.createHmac('sha256', secret).update(payloadB64).digest('hex')
  return `${payloadB64}.${hmac}`
}

/**
 * Create a Set-Cookie string for tw_sess.
 */
export function createSessionCookie(
  payload: string | { user_id: string; [key: string]: any },
  secret: string = process.env.WORDS_SESSION_SECRET || '',
  options: { maxAge?: number } = {}
): string {
  const token = signSession(payload, secret)
  const maxAge = options.maxAge ?? DEFAULT_SESSION_MAX_AGE
  return `tw_sess=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}`
}

export const signSessionCookie = createSessionCookie

/**
 * Verify a session cookie/token with HMAC signature.
 * Returns decoded session object { user_id } or null if invalid, tampered, or expired.
 * Accepts the hex signature used by signSession and the base64url signature used by signSessionToken.
 */
export function verifySessionCookie(
  cookieStr: string | null | undefined,
  secretOverride?: string
): { user_id: string; [key: string]: any } | null {
  if (!cookieStr || typeof cookieStr !== 'string') {
    return null
  }

  let token = cookieStr.trim()
  if (token.includes(';')) {
    const parts = token.split(';')
    const found = parts.map(p => p.trim()).find(p => p.startsWith('tw_sess='))
    if (found) {
      token = found.slice('tw_sess='.length).trim()
    }
  } else if (token.startsWith('tw_sess=')) {
    token = token.slice('tw_sess='.length).trim()
  }

  try {
    token = decodeURIComponent(token)
  } catch {
    // keep the raw token
  }

  if (token.startsWith('s:')) {
    token = token.slice(2)
  }

  const dotIdx = token.lastIndexOf('.')
  if (dotIdx === -1) {
    return null
  }

  const payloadPart = token.slice(0, dotIdx)
  const signaturePart = token.slice(dotIdx + 1)
  if (!payloadPart || !signaturePart) {
    return null
  }

  const secret = secretOverride ?? process.env.WORDS_SESSION_SECRET
  if (!secret) {
    return null
  }

  const expectedHex = crypto.createHmac('sha256', secret).update(payloadPart).digest('hex')
  const expectedB64 = crypto.createHmac('sha256', secret).update(payloadPart).digest('base64')
  const expectedB64Url = crypto.createHmac('sha256', secret).update(payloadPart).digest('base64url')

  const valid =
    constantTimeCompare(signaturePart, expectedHex) ||
    constantTimeCompare(signaturePart, expectedB64) ||
    constantTimeCompare(signaturePart, expectedB64Url)

  if (!valid) {
    return null
  }

  let parsed: any = null
  try {
    parsed = JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8'))
  } catch {
    parsed = null
  }

  if (!parsed) {
    try {
      parsed = JSON.parse(Buffer.from(payloadPart, 'base64').toString('utf8'))
    } catch {
      parsed = null
    }
  }

  if (!parsed) {
    try {
      parsed = JSON.parse(payloadPart)
    } catch {
      parsed = null
    }
  }

  if (!parsed && payloadPart) {
    parsed = { user_id: payloadPart }
  }

  if (typeof parsed === 'string') {
    parsed = { user_id: parsed }
  }

  if (parsed && typeof parsed === 'object') {
    const userId = parsed.user_id || parsed.userId || parsed.u || parsed.sub || parsed.username
    if (!userId) {
      return null
    }
    parsed.user_id = String(userId)

    if (parsed.exp && typeof parsed.exp === 'number') {
      const nowSec = Math.floor(Date.now() / 1000)
      const expSec = parsed.exp > 1e11 ? Math.floor(parsed.exp / 1000) : parsed.exp
      if (expSec < nowSec) {
        return null
      }
    }

    return parsed
  }

  return null
}

export const verifySession = verifySessionCookie

/**
 * Verify read-only stats token against WORDS_STATS_TOKEN using constant-time comparison.
 */
export function verifyStatsToken(
  token: string | null | undefined,
  expectedToken: string = process.env.WORDS_STATS_TOKEN || ''
): boolean {
  if (!token || typeof token !== 'string' || !expectedToken) {
    return false
  }
  return constantTimeCompare(token.trim(), expectedToken.trim())
}

export interface AuthStatsResult {
  authenticated: boolean
  user_id: string | null
  readOnly: boolean
  error?: string
}

/**
 * Authenticate a stats request by Bearer WORDS_STATS_TOKEN (read-only) or tw_sess cookie.
 */
export function authenticateStatsRequest(
  eventOrReq: any,
  options: { sessionSecret?: string; statsToken?: string } = {}
): AuthStatsResult {
  const secret = options.sessionSecret ?? process.env.WORDS_SESSION_SECRET ?? ''
  const statsToken = options.statsToken ?? process.env.WORDS_STATS_TOKEN ?? ''

  let authHeader: string | undefined
  if (eventOrReq?.headers?.authorization) {
    authHeader = eventOrReq.headers.authorization
  } else if (typeof eventOrReq?.getHeader === 'function') {
    authHeader = eventOrReq.getHeader('authorization')
  } else if (eventOrReq?.node?.req?.headers?.authorization) {
    authHeader = eventOrReq.node.req.headers.authorization
  } else if (eventOrReq?.req?.headers?.authorization) {
    authHeader = eventOrReq.req.headers.authorization
  } else {
    try {
      authHeader = getHeader(eventOrReq, 'authorization')
    } catch {
      authHeader = undefined
    }
  }

  if (authHeader && typeof authHeader === 'string') {
    const match = authHeader.match(/^Bearer\s+(.+)$/i)
    if (match) {
      const bearerToken = match[1].trim()
      if (statsToken && verifyStatsToken(bearerToken, statsToken)) {
        return {
          authenticated: true,
          user_id: 'boss',
          readOnly: true,
        }
      }
      return {
        authenticated: false,
        user_id: null,
        readOnly: false,
        error: 'Invalid or missing stats token',
      }
    }
  }

  let cookieHeader: string | undefined
  if (eventOrReq?.headers?.cookie) {
    cookieHeader = eventOrReq.headers.cookie
  } else if (typeof eventOrReq?.getHeader === 'function') {
    cookieHeader = eventOrReq.getHeader('cookie')
  } else if (eventOrReq?.node?.req?.headers?.cookie) {
    cookieHeader = eventOrReq.node.req.headers.cookie
  } else if (eventOrReq?.req?.headers?.cookie) {
    cookieHeader = eventOrReq.req.headers.cookie
  } else if (typeof eventOrReq === 'string') {
    cookieHeader = eventOrReq
  } else {
    try {
      const cookie = getCookie(eventOrReq, SESSION_COOKIE_NAME)
      if (cookie) cookieHeader = `${SESSION_COOKIE_NAME}=${cookie}`
    } catch {
      cookieHeader = undefined
    }
  }

  if (cookieHeader) {
    const session = verifySessionCookie(cookieHeader, secret)
    if (session && session.user_id) {
      return {
        authenticated: true,
        user_id: session.user_id,
        readOnly: false,
      }
    }
  }

  return {
    authenticated: false,
    user_id: null,
    readOnly: false,
    error: 'Unauthorized',
  }
}

export const authStats = authenticateStatsRequest
