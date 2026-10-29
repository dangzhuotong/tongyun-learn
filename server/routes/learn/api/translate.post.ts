import { defineEventHandler, readBody, getRequestIP, getHeader, createError } from 'h3'
import {
  checkTranslateRateLimit,
  executeBaiduTranslate,
  getBaiduCredentials,
} from '../../../services/translate'

export default defineEventHandler(async event => {
  const credentials = getBaiduCredentials()
  if (!credentials) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable',
      message: 'Baidu translate service not configured',
    })
  }

  const clientIp =
    getRequestIP(event, { xForwardedFor: true }) ||
    getHeader(event, 'x-forwarded-for')?.split(',')[0]?.trim() ||
    event.node?.req?.socket?.remoteAddress ||
    '127.0.0.1'

  const rateCheck = checkTranslateRateLimit(clientIp)
  if (!rateCheck.allowed) {
    throw createError({
      statusCode: 429,
      statusMessage: 'Too Many Requests',
      message: 'Translate rate limit exceeded. Please try again later.',
    })
  }

  const body = await readBody(event).catch(() => null)
  if (!body || typeof body !== 'object') {
    throw createError({
      statusCode: 400,
      statusMessage: 'Bad Request',
      message: 'Request body must be a JSON object with "q" property',
    })
  }

  const q = typeof body.q === 'string' ? body.q : ''
  const from = typeof body.from === 'string' ? body.from : 'auto'
  const to = typeof body.to === 'string' ? body.to : 'zh'

  return await executeBaiduTranslate(q, from, to)
})
