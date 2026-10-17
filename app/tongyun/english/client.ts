// tongyun: 云芽英语调用 tongyun-learn。地址和令牌沿用学习服务设置。
// 线上 base 是 /learn/api/（反代去掉前缀），本机直连 http://127.0.0.1:8031/。
// GET  /v1/health
// GET  /v1/today          Authorization: Bearer
// POST /v1/type           { card_id, phase: "A"|"B", typed, duration_ms }
// GET  /v1/coach
// POST /v1/coach

import { getLearnConfig, joinUrl, type LearnConfig } from '../learn-client'
import { adaptCoach, adaptToday } from './adapt'
import type { AttemptState } from './attempt'
import type { CoachView, EnFailKind, EnResult, PracticeStep, TodayQueue, TypeEventBody } from './types'

const DEFAULT_URL = '/learn/api/'

function resolveCfg(cfg?: Partial<LearnConfig>): LearnConfig {
  const saved = getLearnConfig()
  const url = cfg?.url !== undefined ? cfg.url.trim() : saved.url
  const token = cfg?.token !== undefined ? cfg.token.trim() : saved.token
  return {
    url: url || DEFAULT_URL,
    token,
  }
}

function fail<T>(kind: EnFailKind, status: number, message: string): EnResult<T> {
  return { ok: false, kind, status, message }
}

async function readMessage(res: Response): Promise<string> {
  try {
    const data = await res.json()
    return data?.error?.message || data?.message || ''
  } catch {
    return ''
  }
}

async function enRequest(
  method: 'GET' | 'POST',
  path: string,
  cfg: Partial<LearnConfig> | undefined,
  body?: unknown
): Promise<EnResult<unknown>> {
  const active = resolveCfg(cfg)
  if (!active.token) {
    return fail('no_token', 0, '还没配置学习服务：到设置里填写地址和令牌')
  }
  const targetUrl = joinUrl(active.url, path)
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 15000)
  try {
    const res = await fetch(targetUrl, {
      method,
      headers: {
        Authorization: `Bearer ${active.token}`,
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    if (res.status === 401 || res.status === 403) {
      return fail('bad_token', res.status, '令牌无效或无权限，请检查设置里的令牌')
    }
    if (res.status === 404) {
      return fail('not_found', 404, '学习服务还没有这个接口')
    }
    if (!res.ok) {
      const message = await readMessage(res)
      return fail('unreachable', res.status, message || `服务暂时不可用（HTTP ${res.status}）`)
    }
    if (res.status === 204) return { ok: true, data: {}, status: res.status }
    try {
      const data = await res.json()
      return { ok: true, data, status: res.status }
    } catch {
      return { ok: true, data: {}, status: res.status }
    }
  } catch (err: any) {
    clearTimeout(timeoutId)
    if (err?.name === 'AbortError') return fail('unreachable', 0, '请求学习服务超时')
    return fail('unreachable', 0, '连不上学习服务')
  }
}

export function fetchToday(cfg?: Partial<LearnConfig>): Promise<EnResult<TodayQueue>> {
  return enRequest('GET', 'v1/today', cfg).then(res => {
    if (!res.ok) return res as EnResult<TodayQueue>
    return { ok: true, data: adaptToday(res.data), status: res.status }
  })
}

export function fetchCoach(cfg?: Partial<LearnConfig>): Promise<EnResult<CoachView>> {
  return enRequest('GET', 'v1/coach', cfg).then(res => {
    if (!res.ok) return res as EnResult<CoachView>
    return { ok: true, data: adaptCoach(res.data), status: res.status }
  })
}

/** 让服务端按最近的敲击重算教练。无模型时后端自己规则降级，这里不排课。 */
export function postCoach(cfg?: Partial<LearnConfig>): Promise<EnResult<CoachView>> {
  return enRequest('POST', 'v1/coach', cfg, {}).then(res => {
    if (!res.ok) return res as EnResult<CoachView>
    return { ok: true, data: adaptCoach(res.data), status: res.status }
  })
}

export function expectedOf(step: PracticeStep): string {
  return step.stage === 'A' ? step.word : step.sentence
}

export function buildTypeEvent(step: PracticeStep, state: AttemptState, durationMs: number): TypeEventBody | null {
  if (step.cardId === null || step.cardId === '') return null
  const typed = (state.eventTyped || state.typed).trim()
  if (!typed) return null
  return {
    card_id: step.cardId,
    phase: step.stage,
    typed,
    duration_ms: Math.max(0, Math.round(durationMs)),
  }
}

export function postTypeEvent(body: TypeEventBody, cfg?: Partial<LearnConfig>): Promise<EnResult<unknown>> {
  return enRequest('POST', 'v1/type', cfg, body)
}

export function failCopy(kind?: EnFailKind): string {
  if (kind === 'bad_token' || kind === 'no_token') return '令牌不对，去设置里重填。'
  if (kind === 'not_found') return '学习服务还没有这个接口。'
  return '连不上学习服务。'
}
