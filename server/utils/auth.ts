import crypto from 'node:crypto'

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
  const maxAge = options.maxAge ?? 30 * 24 * 60 * 60 // 30 days
  return `tw_sess=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}`
}

export const signSessionCookie = createSessionCookie

/**
 * Verify a session cookie/token with HMAC signature.
 * Returns decoded session object { user_id: ... } or null if invalid/tampered/expired.
 */
export function verifySessionCookie(
  cookieStr: string | null | undefined,
  secretOverride?: string
): { user_id: string; [key: string]: any } | null {
  if (!cookieStr || typeof cookieStr !== 'string') {
    return null
  }

  // Parse out tw_sess if a Cookie header or key=value string was passed
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
  } catch {}

  // Strip Express-style 's:' prefix if present
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

  // Compute expected HMAC signatures (hex, base64, base64url)
  const expectedHex = crypto.createHmac('sha256', secret).update(payloadPart).digest('hex')
  const expectedB64 = crypto.createHmac('sha256', secret).update(payloadPart).digest('base64')
  const expectedB64Url = crypto.createHmac('sha256', secret).update(payloadPart).digest('base64url')

  const valid =
    constantTimeCompare(signaturePart, expectedHex) ||
    constantTimeCompare(signaturePart, expectedB64) ||
    constantTimeCompare(signaturePart, expectedB64Url)

  // MUST return null if signature is invalid or tampered!
  if (!valid) {
    return null
  }

  let parsed: any = null
  // 1. Try base64url
  try {
    const decoded = Buffer.from(payloadPart, 'base64url').toString('utf8')
    parsed = JSON.parse(decoded)
  } catch {}

  // 2. Try standard base64
  if (!parsed) {
    try {
      const decoded = Buffer.from(payloadPart, 'base64').toString('utf8')
      parsed = JSON.parse(decoded)
    } catch {}
  }

  // 3. Try raw JSON
  if (!parsed) {
    try {
      parsed = JSON.parse(payloadPart)
    } catch {}
  }

  // 4. Fallback to raw string
  if (!parsed && payloadPart) {
    parsed = { user_id: payloadPart }
  }

  if (typeof parsed === 'string') {
    parsed = { user_id: parsed }
  }

  if (parsed && typeof parsed === 'object') {
    const userId = parsed.user_id || parsed.userId || parsed.sub || parsed.username
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
export const verifySessionToken = verifySessionCookie

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
 * Authenticate stats request either by:
 * 1. Bearer token ($WORDS_STATS_TOKEN) in Authorization header (read-only for supervisors)
 * 2. Session cookie (tw_sess)
 */
export function authenticateStatsRequest(
  eventOrReq: any,
  options: { sessionSecret?: string; statsToken?: string } = {}
): AuthStatsResult {
  const secret = options.sessionSecret ?? process.env.WORDS_SESSION_SECRET ?? ''
  const statsToken = options.statsToken ?? process.env.WORDS_STATS_TOKEN ?? ''

  // 1. Check Bearer token in Authorization header
  let authHeader: string | undefined
  if (eventOrReq?.headers?.authorization) {
    authHeader = eventOrReq.headers.authorization
  } else if (eventOrReq?.headers?.['authorization']) {
    authHeader = eventOrReq.headers['authorization']
  } else if (typeof eventOrReq?.getHeader === 'function') {
    authHeader = eventOrReq.getHeader('authorization')
  } else if (eventOrReq?.node?.req?.headers?.authorization) {
    authHeader = eventOrReq.node.req.headers.authorization
  } else if (eventOrReq?.req?.headers?.authorization) {
    authHeader = eventOrReq.req.headers.authorization
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
      } else {
        return {
          authenticated: false,
          user_id: null,
          readOnly: false,
          error: 'Invalid or missing stats token',
        }
      }
    }
  }

  // 2. Check Session Cookie (tw_sess)
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
