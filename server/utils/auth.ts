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

function hmac(payloadPart: string, secret: string, encoding: 'hex' | 'base64' | 'base64url'): string {
  return crypto.createHmac('sha256', secret).update(payloadPart).digest(encoding)
}

/** One session codec. exp is always milliseconds. Signature is base64url; verification also accepts hex and standard base64. */
function encodeSession(claims: SessionPayload, secret: string): string {
  const payloadStr = Buffer.from(JSON.stringify(claims)).toString('base64url')
  return `${payloadStr}.${hmac(payloadStr, secret, 'base64url')}`
}

function expiryMs(exp: number): number {
  return exp > 1e11 ? exp : exp * 1000
}

function decodeSession(token: string, secret: string): SessionPayload | null {
  const dotIdx = token.lastIndexOf('.')
  if (dotIdx <= 0 || dotIdx === token.length - 1) return null

  const payloadPart = token.slice(0, dotIdx)
  const signaturePart = token.slice(dotIdx + 1)
  const valid =
    constantTimeCompare(signaturePart, hmac(payloadPart, secret, 'base64url')) ||
    constantTimeCompare(signaturePart, hmac(payloadPart, secret, 'hex')) ||
    constantTimeCompare(signaturePart, hmac(payloadPart, secret, 'base64'))
  if (!valid) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8'))
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null

  const record = parsed as Record<string, unknown>
  const userId = record.u || record.user_id || record.userId || record.sub || record.username
  if (typeof userId !== 'string' || !userId || typeof record.exp !== 'number') return null
  if (expiryMs(record.exp) < Date.now()) return null

  return {
    u: userId,
    iat: typeof record.iat === 'number' ? record.iat : Date.now(),
    exp: record.exp,
  }
}

function sessionUserId(payload: string | { user_id?: string; u?: string; userId?: string; [key: string]: any }): string {
  if (typeof payload === 'string') return payload
  const userId = payload.user_id || payload.u || payload.userId
  return typeof userId === 'string' ? userId : ''
}

export function signSessionToken(
  userId: string,
  secret = getSessionSecret(),
  maxAgeSec = DEFAULT_SESSION_MAX_AGE
): string {
  const now = Date.now()
  return encodeSession(
    {
      u: userId,
      iat: now,
      exp: now + maxAgeSec * 1000,
    },
    secret
  )
}

export function verifySessionToken(
  token: string | undefined | null,
  secret?: string
): { userId: string } | null {
  if (!token || typeof token !== 'string') return null
  const signingSecret = secret || process.env.WORDS_SESSION_SECRET
  if (!signingSecret) return null
  const claims = decodeSession(token, signingSecret)
  return claims ? { userId: claims.u } : null
}

/**
 * Sign a session payload with the same codec as signSessionToken.
 * A numeric exp at or below 1e11 is seconds and is stored as milliseconds.
 */
export function signSession(
  payload: string | { user_id: string; [key: string]: any },
  secret: string = process.env.WORDS_SESSION_SECRET || ''
): string {
  if (!secret) {
    throw new Error('WORDS_SESSION_SECRET is required to sign session')
  }
  const userId = sessionUserId(payload)
  if (!userId) {
    throw new Error('session user_id is required')
  }
  const providedExp = typeof payload === 'object' && payload && typeof payload.exp === 'number' ? payload.exp : undefined
  const now = Date.now()
  return encodeSession(
    {
      u: userId,
      iat: now,
      exp: providedExp === undefined ? now + DEFAULT_SESSION_MAX_AGE * 1000 : expiryMs(providedExp),
    },
    secret
  )
}

export function verifySessionCookie(
  cookieStr: string | null | undefined,
  secretOverride?: string
): { user_id: string; [key: string]: any } | null {
  if (!cookieStr || typeof cookieStr !== 'string') return null

  let token = cookieStr.trim()
  if (token.includes(';')) {
    const found = token
      .split(';')
      .map(part => part.trim())
      .find(part => part.startsWith('tw_sess='))
    if (found) token = found.slice('tw_sess='.length).trim()
  } else if (token.startsWith('tw_sess=')) {
    token = token.slice('tw_sess='.length).trim()
  }

  try {
    token = decodeURIComponent(token)
  } catch {
    // keep the raw token
  }
  if (token.startsWith('s:')) token = token.slice(2)

  const secret = secretOverride ?? process.env.WORDS_SESSION_SECRET
  if (!secret) return null
  const claims = decodeSession(token, secret)
  if (!claims) return null
  return {
    user_id: claims.u,
    u: claims.u,
    iat: claims.iat,
    exp: claims.exp,
  }
}

export const verifySession = verifySessionCookie

export function createSessionCookie(
  payload: string | { user_id: string; [key: string]: any },
  secret: string = process.env.WORDS_SESSION_SECRET || '',
  options: { maxAge?: number } = {}
): string {
  const maxAge = options.maxAge ?? DEFAULT_SESSION_MAX_AGE
  const base = typeof payload === 'string' ? { user_id: payload } : { ...payload }
  const exp = typeof base.exp === 'number' ? base.exp : Math.floor(Date.now() / 1000) + maxAge
  const token = signSession({ ...base, exp }, secret)
  return `tw_sess=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}`
}

export const signSessionCookie = createSessionCookie

export function comparePassword(password: string, hash: string): boolean {
  if (!password || !hash) return false
  try {
    return bcrypt.compareSync(password, hash)
  } catch {
    return false
  }
}

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

export function verifyStatsToken(
  token: string | null | undefined,
  expectedToken: string = process.env.WORDS_STATS_TOKEN || ''
): boolean {
  if (!token || typeof token !== 'string' || !expectedToken) return false
  return constantTimeCompare(token.trim(), expectedToken.trim())
}

export interface AuthStatsResult {
  authenticated: boolean
  user_id: string | null
  readOnly: boolean
  error?: string
}

function headerValue(eventOrReq: any, name: 'authorization' | 'cookie'): string | undefined {
  const lower = name
  if (typeof eventOrReq?.headers?.[lower] === 'string') return eventOrReq.headers[lower]
  if (typeof eventOrReq?.getHeader === 'function') {
    const value = eventOrReq.getHeader(lower)
    if (typeof value === 'string') return value
  }
  if (typeof eventOrReq?.node?.req?.headers?.[lower] === 'string') return eventOrReq.node.req.headers[lower]
  if (typeof eventOrReq?.req?.headers?.[lower] === 'string') return eventOrReq.req.headers[lower]
  try {
    return getHeader(eventOrReq, lower)
  } catch {
    return undefined
  }
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

  const authHeader = typeof eventOrReq === 'string' ? undefined : headerValue(eventOrReq, 'authorization')
  if (authHeader) {
    const match = authHeader.match(/^Bearer\s+(.+)$/i)
    if (match) {
      if (statsToken && verifyStatsToken(match[1].trim(), statsToken)) {
        return { authenticated: true, user_id: 'boss', readOnly: true }
      }
      return {
        authenticated: false,
        user_id: null,
        readOnly: false,
        error: 'Invalid or missing stats token',
      }
    }
  }

  let cookieHeader = typeof eventOrReq === 'string' ? eventOrReq : headerValue(eventOrReq, 'cookie')
  if (!cookieHeader && eventOrReq && typeof eventOrReq !== 'string') {
    try {
      const cookie = getCookie(eventOrReq, SESSION_COOKIE_NAME)
      if (cookie) cookieHeader = `${SESSION_COOKIE_NAME}=${cookie}`
    } catch {
      cookieHeader = undefined
    }
  }

  if (cookieHeader) {
    const session = verifySessionCookie(cookieHeader, secret)
    if (session?.user_id) {
      return { authenticated: true, user_id: session.user_id, readOnly: false }
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

export function requireStatsAuth(event: H3Event): { role: 'boss' | 'stats_reader'; userId?: string } {
  const auth = authenticateStatsRequest(event)
  if (!auth.authenticated) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized',
      message: 'Valid session or stats token required',
    })
  }
  if (auth.readOnly) return { role: 'stats_reader' }
  return { role: 'boss', userId: auth.user_id || undefined }
}
