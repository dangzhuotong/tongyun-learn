import { createError } from 'h3'
import crypto from 'node:crypto'

export interface TranslateResultItem {
  src: string
  dst: string
}

export interface TranslateResponse {
  from: string
  to: string
  trans_result: TranslateResultItem[]
}

export const BAIDU_TRANSLATE_API_URL = 'https://api.fanyi.baidu.com/api/trans/vip/translate'

export function getBaiduCredentials(): { appid: string; key: string } | null {
  const appid = process.env.BAIDU_TRANSLATE_APPID?.trim()
  const key = process.env.BAIDU_TRANSLATE_KEY?.trim()
  if (!appid || !key) {
    return null
  }
  return { appid, key }
}

export const LANG_MAP: Record<string, string> = {
  auto: 'auto',
  zh: 'zh',
  'zh-CN': 'zh',
  'zh-TW': 'cht',
  en: 'en',
  yue: 'yue',
  wyw: 'wyw',
  ja: 'jp',
  ko: 'kor',
  fr: 'fra',
  es: 'spa',
  th: 'th',
  ar: 'ara',
  ru: 'ru',
  pt: 'pt',
  de: 'de',
  it: 'it',
  el: 'el',
  nl: 'nl',
  pl: 'pl',
  bg: 'bul',
  est: 'est',
  dan: 'dan',
  fin: 'fin',
  cs: 'cs',
  rom: 'rom',
  slo: 'slo',
  swe: 'swe',
  hu: 'hu',
  vie: 'vie',
}

export function normalizeLang(lang?: string, fallback = 'auto'): string {
  if (!lang) return fallback
  return LANG_MAP[lang] || lang
}

export function computeBaiduSign(appid: string, q: string, salt: string | number, key: string): string {
  return crypto.createHash('md5').update(`${appid}${q}${salt}${key}`).digest('hex')
}

interface CacheEntry {
  response: TranslateResponse
  createdAt: number
}

const MAX_CACHE_ENTRIES = 2000
const CACHE_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours
const translateCache = new Map<string, CacheEntry>()

export function getCachedTranslation(q: string, from: string, to: string): TranslateResponse | null {
  const key = `${from}:${to}:${q}`
  const entry = translateCache.get(key)
  if (!entry) return null
  if (Date.now() - entry.createdAt > CACHE_TTL_MS) {
    translateCache.delete(key)
    return null
  }
  // Refresh LRU order
  translateCache.delete(key)
  translateCache.set(key, entry)
  return entry.response
}

export function setCachedTranslation(q: string, from: string, to: string, response: TranslateResponse): void {
  const key = `${from}:${to}:${q}`
  if (translateCache.size >= MAX_CACHE_ENTRIES) {
    const oldestKey = translateCache.keys().next().value
    if (oldestKey !== undefined) {
      translateCache.delete(oldestKey)
    }
  }
  translateCache.set(key, { response, createdAt: Date.now() })
}

export function clearTranslateCache(): void {
  translateCache.clear()
}

interface RateLimitEntry {
  count: number
  windowStart: number
}

const rateLimitMap = new Map<string, RateLimitEntry>()
const RATE_LIMIT_WINDOW_MS = 10000 // 10 seconds
const RATE_LIMIT_MAX_REQUESTS = 30 // 30 requests per 10s per IP

export function checkTranslateRateLimit(
  ip: string,
  maxRequests = RATE_LIMIT_MAX_REQUESTS,
  windowMs = RATE_LIMIT_WINDOW_MS
): { allowed: boolean; remaining: number } {
  const now = Date.now()
  const entry = rateLimitMap.get(ip)

  if (!entry || now - entry.windowStart >= windowMs) {
    rateLimitMap.set(ip, { count: 1, windowStart: now })
    return { allowed: true, remaining: maxRequests - 1 }
  }

  if (entry.count >= maxRequests) {
    return { allowed: false, remaining: 0 }
  }

  entry.count++
  return { allowed: true, remaining: maxRequests - entry.count }
}

export function resetTranslateRateLimits(): void {
  rateLimitMap.clear()
}

export async function executeBaiduTranslate(
  q: string,
  from = 'auto',
  to = 'zh',
  fetchFn: typeof fetch = globalThis.fetch
): Promise<TranslateResponse> {
  const credentials = getBaiduCredentials()
  if (!credentials) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable',
      message: 'Baidu translate service not configured',
    })
  }

  const normalizedFrom = normalizeLang(from, 'auto')
  const normalizedTo = normalizeLang(to, 'zh')

  if (!q || !q.trim()) {
    return {
      from: normalizedFrom,
      to: normalizedTo,
      trans_result: [],
    }
  }

  const cached = getCachedTranslation(q, normalizedFrom, normalizedTo)
  if (cached) {
    return cached
  }

  const salt = Date.now().toString()
  const sign = computeBaiduSign(credentials.appid, q, salt, credentials.key)

  const params = new URLSearchParams()
  params.set('q', q)
  params.set('from', normalizedFrom)
  params.set('to', normalizedTo)
  params.set('appid', credentials.appid)
  params.set('salt', salt)
  params.set('sign', sign)

  const res = await fetchFn(BAIDU_TRANSLATE_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  })

  if (!res.ok) {
    throw createError({
      statusCode: 502,
      statusMessage: 'Bad Gateway',
      message: `Baidu translate upstream HTTP error: ${res.status}`,
    })
  }

  const data = (await res.json()) as any
  if (data.error_code) {
    throw createError({
      statusCode: 502,
      statusMessage: 'Bad Gateway',
      message: `Baidu translate upstream error: ${data.error_code} - ${data.error_msg}`,
    })
  }

  const result: TranslateResponse = {
    from: data.from || normalizedFrom,
    to: data.to || normalizedTo,
    trans_result: data.trans_result || [],
  }

  setCachedTranslation(q, normalizedFrom, normalizedTo, result)
  return result
}
