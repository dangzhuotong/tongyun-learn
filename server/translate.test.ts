import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createEvent } from 'h3'
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import {
  computeBaiduSign,
  getBaiduCredentials,
  normalizeLang,
  getCachedTranslation,
  setCachedTranslation,
  clearTranslateCache,
  checkTranslateRateLimit,
  resetTranslateRateLimits,
  executeBaiduTranslate,
  BAIDU_TRANSLATE_API_URL,
} from './services/translate'
import translateHandler from './routes/learn/api/translate.post'

describe('server/services/translate', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    vi.restoreAllMocks()
    clearTranslateCache()
    resetTranslateRateLimits()
    delete process.env.BAIDU_TRANSLATE_APPID
    delete process.env.BAIDU_TRANSLATE_KEY
  })

  afterEach(() => {
    process.env = { ...originalEnv }
    clearTranslateCache()
    resetTranslateRateLimits()
  })

  describe('configuration & credentials', () => {
    it('returns null when credentials are not configured', () => {
      expect(getBaiduCredentials()).toBeNull()

      process.env.BAIDU_TRANSLATE_APPID = '   '
      process.env.BAIDU_TRANSLATE_KEY = ''
      expect(getBaiduCredentials()).toBeNull()
    })

    it('returns credentials when both appid and key are provided', () => {
      process.env.BAIDU_TRANSLATE_APPID = 'demo_appid_123'
      process.env.BAIDU_TRANSLATE_KEY = 'demo_key_456'
      expect(getBaiduCredentials()).toEqual({
        appid: 'demo_appid_123',
        key: 'demo_key_456',
      })
    })

    it('normalizes languages correctly', () => {
      expect(normalizeLang('zh-CN')).toBe('zh')
      expect(normalizeLang('zh-TW')).toBe('cht')
      expect(normalizeLang('en')).toBe('en')
      expect(normalizeLang('ja')).toBe('jp')
      expect(normalizeLang(undefined, 'auto')).toBe('auto')
    })
  })

  describe('MD5 signature algorithm', () => {
    it('calculates md5(appid + q + salt + key) accurately', () => {
      const appid = '2015063000000001'
      const q = 'apple'
      const salt = '1435660288'
      const key = '12345678'

      // Expected md5('2015063000000001apple143566028812345678')
      const sign = computeBaiduSign(appid, q, salt, key)
      expect(sign).toBe('f89f9594663708c1605f3d736d01d2d4')
    })
  })

  describe('caching mechanism', () => {
    it('stores and retrieves cached translations', () => {
      const dummyResponse = {
        from: 'en',
        to: 'zh',
        trans_result: [{ src: 'apple', dst: '苹果' }],
      }

      expect(getCachedTranslation('apple', 'en', 'zh')).toBeNull()

      setCachedTranslation('apple', 'en', 'zh', dummyResponse)
      expect(getCachedTranslation('apple', 'en', 'zh')).toEqual(dummyResponse)
    })

    it('clears cache properly', () => {
      setCachedTranslation('apple', 'en', 'zh', {
        from: 'en',
        to: 'zh',
        trans_result: [{ src: 'apple', dst: '苹果' }],
      })
      clearTranslateCache()
      expect(getCachedTranslation('apple', 'en', 'zh')).toBeNull()
    })
  })

  describe('rate limiting', () => {
    it('allows up to maxRequests and blocks subsequent calls within window', () => {
      const ip = '10.0.0.1'
      for (let i = 0; i < 5; i++) {
        const res = checkTranslateRateLimit(ip, 5, 10000)
        expect(res.allowed).toBe(true)
      }

      const blocked = checkTranslateRateLimit(ip, 5, 10000)
      expect(blocked.allowed).toBe(false)
      expect(blocked.remaining).toBe(0)

      // Other IP is unaffected
      const otherIp = checkTranslateRateLimit('10.0.0.2', 5, 10000)
      expect(otherIp.allowed).toBe(true)
    })
  })

  describe('executeBaiduTranslate', () => {
    it('throws 503 when credentials are not configured', async () => {
      await expect(executeBaiduTranslate('hello', 'en', 'zh')).rejects.toMatchObject({
        statusCode: 503,
        message: 'Baidu translate service not configured',
      })
    })

    it('returns empty result when query string is empty', async () => {
      process.env.BAIDU_TRANSLATE_APPID = 'demo_appid'
      process.env.BAIDU_TRANSLATE_KEY = 'demo_key'

      const result = await executeBaiduTranslate('', 'en', 'zh')
      expect(result).toEqual({
        from: 'en',
        to: 'zh',
        trans_result: [],
      })
    })

    it('forwards request to Baidu API with valid signature and parameters', async () => {
      process.env.BAIDU_TRANSLATE_APPID = 'demo_appid'
      process.env.BAIDU_TRANSLATE_KEY = 'demo_key'

      let capturedUrl = ''
      let capturedBody = ''

      const mockFetch = vi.fn().mockImplementation(async (url: string, options: any) => {
        capturedUrl = url
        capturedBody = options.body
        return {
          ok: true,
          status: 200,
          json: async () => ({
            from: 'en',
            to: 'zh',
            trans_result: [{ src: 'Good morning', dst: '早上好' }],
          }),
        }
      })

      const res = await executeBaiduTranslate('Good morning', 'en', 'zh-CN', mockFetch as any)

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(capturedUrl).toBe(BAIDU_TRANSLATE_API_URL)

      const bodyParams = new URLSearchParams(capturedBody)
      expect(bodyParams.get('q')).toBe('Good morning')
      expect(bodyParams.get('from')).toBe('en')
      expect(bodyParams.get('to')).toBe('zh')
      expect(bodyParams.get('appid')).toBe('demo_appid')

      const salt = bodyParams.get('salt')!
      const sign = bodyParams.get('sign')!
      expect(salt).toBeTruthy()
      expect(sign).toBe(computeBaiduSign('demo_appid', 'Good morning', salt, 'demo_key'))

      expect(res).toEqual({
        from: 'en',
        to: 'zh',
        trans_result: [{ src: 'Good morning', dst: '早上好' }],
      })

      // Second call should hit in-memory cache without calling mockFetch again
      const cachedRes = await executeBaiduTranslate('Good morning', 'en', 'zh-CN', mockFetch as any)
      expect(mockFetch).toHaveBeenCalledTimes(1) // Still 1
      expect(cachedRes).toEqual(res)
    })

    it('throws 502 when Baidu API returns error_code', async () => {
      process.env.BAIDU_TRANSLATE_APPID = 'demo_appid'
      process.env.BAIDU_TRANSLATE_KEY = 'demo_key'

      const mockFetch = vi.fn().mockImplementation(async () => {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            error_code: '54001',
            error_msg: 'Invalid Sign',
          }),
        }
      })

      await expect(executeBaiduTranslate('fail', 'en', 'zh', mockFetch as any)).rejects.toMatchObject({
        statusCode: 502,
      })
    })
  })
})

describe('server/routes/learn/api/translate.post handler', () => {
  const originalEnv = { ...process.env }

  beforeEach(() => {
    vi.restoreAllMocks()
    clearTranslateCache()
    resetTranslateRateLimits()
    delete process.env.BAIDU_TRANSLATE_APPID
    delete process.env.BAIDU_TRANSLATE_KEY
  })

  afterEach(() => {
    process.env = { ...originalEnv }
    clearTranslateCache()
    resetTranslateRateLimits()
  })

  function createTestEvent(body: any, ip = '127.0.0.1') {
    const socket = new Socket()
    Object.defineProperty(socket, 'remoteAddress', { value: ip })
    const req = new IncomingMessage(socket)
    req.method = 'POST'
    req.headers['content-type'] = 'application/json'
    req.headers['x-forwarded-for'] = ip

    const res = new ServerResponse(req)
    const event = createEvent(req, res)
    if (body !== undefined) {
      ;(req as any)[Symbol.for('h3ParsedBody')] = body
    }
    return event
  }

  it('returns 503 when env is not configured', async () => {
    const event = createTestEvent({ q: 'hello' })
    await expect(translateHandler(event)).rejects.toMatchObject({
      statusCode: 503,
      message: 'Baidu translate service not configured',
    })
  })

  it('returns 400 when body is invalid', async () => {
    process.env.BAIDU_TRANSLATE_APPID = 'demo_appid'
    process.env.BAIDU_TRANSLATE_KEY = 'demo_key'

    const event = createTestEvent('not-json')
    await expect(translateHandler(event)).rejects.toMatchObject({
      statusCode: 400,
    })
  })

  it('handles translation when configured and passes through result', async () => {
    process.env.BAIDU_TRANSLATE_APPID = 'demo_appid'
    process.env.BAIDU_TRANSLATE_KEY = 'demo_key'

    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        from: 'en',
        to: 'zh',
        trans_result: [{ src: 'hello', dst: '你好' }],
      }),
    })) as any

    try {
      const event = createTestEvent({ q: 'hello', from: 'en', to: 'zh' })
      const res = await translateHandler(event)
      expect(res).toEqual({
        from: 'en',
        to: 'zh',
        trans_result: [{ src: 'hello', dst: '你好' }],
      })
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
